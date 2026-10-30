"""Motor único dos assistentes.

Substitui três loops agênticos quase idênticos (`broker/claude_agent.py`,
`voice/whatsapp_intake.py` e, por herança, o de voz). Diferiam em constantes
e em duas capacidades que só uma das cópias tinha — prompt caching e tool
forcing — e que aqui passam a valer para todos.

Chamado por:
* `agents/broker/channels/whatsapp/webhook.py` — WhatsApp, com router
* `api/broker.py` — chat web do painel, com assistente escolhido à mão
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.agents.broker.assistants import (
    A1,
    A3,
    A4,
    APRESENTACAO_A1,
    ASSISTENTES,
    MAX_TOKENS,
    MENSAGEM_INATIVO,
    NOME_A1,
    NOME_A3,
    load_config,
)
from app.agents.broker.conversation import load_conversation, save_conversation
from app.agents.broker.custos import calcular_custo, somar_usage
from app.agents.broker.guards import (
    campos_mql_da_ficha,
    contacto_meta_aberto,
    e_despedida,
    e_fecho_da_pessoa,
    e_optout_explicito,
    lead_aberta,
    marcar_contacto_respondeu,
    marcar_nao_contactar,
    marcar_lead_respondeu,
    motivos_escalados,
    tools_ja_usadas,
    normalizar_telefone,
    promover_se_qualificada,
    variantes_telefone,
)
from app.agents.broker.router import route
from app.agents.broker.tools import execute_tool, tools_para
from app.agents.voice.claude_agent import FIM_CHAMADA, _CORPO_SAUDACAO, instrucao_telefone, periodo_do_dia
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.4  # spec §2.3: consistente sem ser robótico
# Na voz, estas ferramentas só registam: corre-se depois de a frase sair (a que pode recusar, `pedir_visita`, não).
_TOOLS_DIFERIVEIS_NA_VOZ = ("guardar_dados_cliente", "escalar_para_humano", "encerrar_lead")
_MAX_TOOL_ITERATIONS = 4  # A1 encadeia ficha -> guardar -> agendar
_ERRO = "Ocorreu um erro. Tenta novamente."
# Turno sem texto depois de o caso ir para um humano (achado 08/10: "Obrigado" a seguir a
# escalar -> o modelo refez as tools e calou-se; a candidata recebeu `_ERRO`). Neutra de propósito: serve a agradecimentos e a perguntas.
_RESPOSTA_ESCALADA = "Fica registado. O responsável entra em contacto consigo e esclarece as suas dúvidas."


# Nota de estado (`nota-de-estado-escalada-plano.md`): o `tool_use` não fica no histórico, por
# isso o modelo não sabe que já escalou e repetia as tools (74% dos turnos seguintes, 12 s cada).
_NOTA_ESCALADA = (
    "\n\nEstado desta conversa: o caso já foi entregue a um humano (motivo: {motivos}). Isso já "
    "está registado e o responsável vai contactar a pessoa. Só voltas a chamar escalar_para_humano se "
    "a pessoa der informação NOVA para o responsável (por exemplo disponibilidade ou outro contacto): "
    "nesse caso o resumo leva só o que é novo. Não chames guardar_dados_cliente sem dados novos. "
    "Responde sempre em texto ao que a pessoa escrever (mesmo um agradecimento: uma frase curta). "
    "Só chamas outras tools se surgir um assunto novo."
)


# Uma linha por tool de registo já usada (`estado-da-conversa-e-aviso-unico-plano.md`, 08/10):
# no chat do site "é tudo" fez repetir `guardar_dados_cliente` e a pessoa viu `_ERRO`.
_NOTAS_REGISTO = {
    "guardar_dados_cliente": (
        "Já guardaste os dados desta pessoa: só voltas a chamar guardar_dados_cliente se ela "
        "der dados novos ou corrigir algum."
    ),
    "pedir_visita": "O pedido de visita já está registado: não o repitas.",
    "encerrar_lead": "A lead já foi encerrada: não voltes a chamar encerrar_lead.",
}
_RESPOSTA_REGISTADA = "Fica registado. Se precisar de mais alguma coisa, é só escrever."


_INSTRUCAO_RESPOSTA_FINAL = (
    "Escreve agora a resposta à última mensagem da pessoa, em texto, sem usar tools."
)


def _com_instrucao_de_resposta(messages: list[dict]) -> list[dict]:
    """Cópia do histórico com a instrução no último turno do utilizador (a seguir aos `tool_result`,
    que têm de vir primeiro). Sem ela, a chamada final sem tools reenvia um histórico que acaba num
    `tool_result` e o modelo volta a calar-se (13/10: 'Eu não tenho carta de condução')."""
    if not messages or messages[-1].get("role") != "user":
        return list(messages)
    ultimo = messages[-1]["content"]
    blocos = list(ultimo) if isinstance(ultimo, list) else [{"type": "text", "text": ultimo}]
    blocos.append({"type": "text", "text": _INSTRUCAO_RESPOSTA_FINAL})
    return [*messages[:-1], {"role": "user", "content": blocos}]


def _nota_de_estado(escalados: list[str], ja_usadas: list[str]) -> str:
    nota = _NOTA_ESCALADA.format(motivos="; ".join(escalados)) if escalados else ""
    linhas = " ".join(_NOTAS_REGISTO[t] for t in ja_usadas if t in _NOTAS_REGISTO)
    if linhas and nota:
        nota += " " + linhas
    elif linhas:
        nota = (
            "\n\nEstado desta conversa: " + linhas + " Responde sempre em texto ao que a pessoa "
            "escrever (mesmo um agradecimento: uma frase curta)."
        )
    return nota


def _sem_erro_apos_registo(
    resposta: str, tools_usadas: list[str], ja_usadas: list[str] = (), escalados: list[str] = (),
) -> str:
    """Turno sem texto depois de uma tool de registo: frase neutra em vez de `_ERRO`.
    Sem nenhuma tool de registo mantém o erro — um turno vazio sem causa conhecida deve ver-se."""
    if resposta != _ERRO:
        return resposta
    usadas = set(tools_usadas) | set(ja_usadas)
    if escalados or "escalar_para_humano" in usadas:
        return _RESPOSTA_ESCALADA
    if usadas & set(_NOTAS_REGISTO):
        return _RESPOSTA_REGISTADA
    return resposta

# No WhatsApp o telefone vem sempre de graça — é o próprio `participante`. No
# site não há canal nenhum a identificar quem escreve, e `guards.find_or_create_cliente`
# (2026-09-02) recusa criar cliente ou lead sem telefone/email: nome sozinho não é
# contacto. Sem este lembrete o modelo regista "interesse" com um nome e mais nada,
# e `guardar_dados_cliente` fica a dizer "guardado" sem gravar coisa nenhuma —
# achado em produção quando uma lead do chat do site apareceu sem forma de contacto.
_INSTRUCAO_IDENTIDADE_SITE = (
    "\n\nEste contacto vem do chat do site — ao contrário do WhatsApp, não há "
    "telefone nenhum identificado à partida. Antes de guardar_dados_cliente ou de "
    "tratares isto como um interesse a registar, pergunta sempre o nome E o número "
    "de telefone. Sem os dois, os dados não ficam gravados e ninguém consegue "
    "voltar a contactar esta pessoa."
)


# O par do site, para o WhatsApp: o número de quem escreve é o do canal e as tools
# usam-no sozinhas (`contexto["telefone"]`), por isso pedi-lo é ruído. Visto a
# 07/10: a Maria pediu "nome completo e número de telefone" a uma candidata; medido
# em 411 interacções, o telefone também é pedido na Matilde (3/39) e na Inês (3/27,
# apesar de o prompt dela já o proibir) — por isso aqui, no motor, e não por prompt.
# Fala do número DE QUEM ESCREVE: o telefone da agência continua a poder ser dado.
_INSTRUCAO_TELEFONE_WHATSAPP = (
    "\n\nEste contacto vem do WhatsApp: o número de telefone de quem te escreve já "
    "é conhecido (é o do próprio WhatsApp) e é usado sozinho quando registas dados. "
    "Nunca o peças nem lhe peças para o confirmar; quando precisares de dados de "
    "contacto, pede só o nome."
)


# Canal `voz` (`voz-como-canal-plano.md`): a instrução vive aqui, no motor, e não no prompt de cada assistente.
# A pessoa ouve, não lê: sem ecrã não há links, listas, referências lidas dígito a dígito nem pesquisa de imóveis (fase 2).
_INSTRUCAO_VOZ = (
    "\n\nEstás numa chamada telefónica: a pessoa ouve-te, não te lê. A chamada começou com um «bom dia», «boa tarde» ou "
    "«boa noite» e «{saudacao}», já dito antes da primeira resposta tua: nunca voltes a cumprimentar, a apresentar-te como "
    "assistente virtual nem a avisar da transcrição. "
    "Fala como uma pessoa simpática ao telefone: responde em uma ou duas frases curtas (no máximo 25 palavras no total) e faz "
    "uma pergunta de cada vez. Por vezes (não em todas as respostas) começas por uma reação breve e natural ao que ouviste, como «Ótimo.», «Percebo.», "
    "«Claro.» ou «Boa escolha.», variando sempre; noutras entras direto na pergunta. Usa a linguagem do dia a dia e evita fórmulas de balcão como "
    "«fico a registar», «fico a aguardar» ou «apresentar as opções disponíveis». Não repitas o que a pessoa já confirmou: "
    "só o que for novo. Fala sempre com a pessoa, na 2.ª pessoa: nunca descrevas o que ela fez nem o que vais fazer («a pessoa despediu-se», «vou guardar»). "
    "Nunca uses markdown, listas, símbolos, emojis, links nem endereços de internet: se as instruções mandarem dar um link, "
    "diz que o responsável o envia por mensagem. Não tens ferramentas de pesquisa de imóveis nesta chamada: nunca digas "
    "que vais pesquisar nem inventes resultados; recolhe os dados e diz que um consultor entrará em contacto, sem prometer "
    "prazos nem horas («hoje», «amanhã de manhã»). "
    "O nome ouve-se mal ao telefone: repete-o para confirmar e, se a pessoa corrigir, usa sempre a versão nova. "
    "Se uma resposta for incoerente ou impercetível, não a trates como dado: pede de novo, com calma. "
    "O telefone corta palavras: se um valor (orçamento, renda) diferir do que já sabes da pessoa ou parecer pequeno demais, "
    "confirma-o em voz alta («Disse trezentos e cinquenta mil euros, certo?») antes de o aceitar. "
    "Nunca comentes preços, o mercado nem se o orçamento chega ou não para o que a pessoa procura: não tens esses dados; "
    "limita-te a recolher e diz que o consultor avalia as opções. "
    "Antes de te despedires, pergunta se um consultor pode ligar para este número e espera pela resposta; só depois "
    "confirmas e te despedes. Nunca digas «fico a registar»: o registo faz-se sem o anunciar. "
    "Quando tiveres de registar algo (guardar dados, escalar, encerrar), escreve primeiro a frase que vais dizer à pessoa "
    "e chama a ferramenta na mesma resposta: assim a pessoa ouve-te já. "
    "A frase tem de bastar-se a si própria: nunca digas «um momento», «já registo» nem «aguarde»; confirma o que ficou "
    "registado e faz a pergunta seguinte, ou despede-te. "
    "Se já conheces o nome da pessoa, usa-o de vez em quando (não em todas as frases), mas sem «olá», «bom dia» ou «boa tarde» "
    "no princípio: a saudação já foi feita. "
    "A despedida final é a tua última frase da chamada: calorosa e natural, com o agradecimento e um «boa {periodo}» "
    "(ou «boa noite») conforme a hora; termina-a com a palavra {fim}, que nunca é falada. "
    "Usa-a uma só vez, e só nessa frase."
)


def _periodo_despedida() -> str:
    return {"dia": "dia", "tarde": "tarde", "noite": "noite"}[periodo_do_dia()]


def _instrucao_voz(telefone: str | None) -> str:
    return _INSTRUCAO_VOZ.format(saudacao=_CORPO_SAUDACAO, fim=FIM_CHAMADA, periodo=_periodo_despedida()) + instrucao_telefone(telefone)


# Por chamada (`participante` = call_control_id): o perfil e a configuração não mudam durante a conversa, e cada
# leitura custa ~80–150 ms ao telefone (F0 do plano). Limpa-se no fim da chamada (`descartar_cache_voz`).
_cache_voz: dict[str, dict] = {}


def descartar_cache_voz(participante: str) -> None:
    _cache_voz.pop(participante, None)


def _perfil_cliente(telefone: str) -> str:
    """Contexto do cliente já conhecido, para o prompt. Só faz sentido com telefone.

    Procura pelas mesmas variantes que o dedup (`guards.variantes_telefone`):
    as linhas antigas guardam o número como a Meta o enviou (`351…`), as novas
    já ficam normalizadas. Procurar só por uma forma perdia metade delas.
    """
    try:
        resp = (
            get_supabase()
            .table("agente_clientes")
            .select("nome,tipo_interesse,orcamento,zona_preferida")
            .in_("telefone", variantes_telefone(telefone))
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("Erro ao procurar cliente %s", telefone)
        return ""

    if not resp.data:
        return ""

    return _texto_perfil(resp.data[0])


def _texto_perfil(c: dict) -> str:
    """A mesma frase, venha o perfil de `agente_clientes` ou de `leads.ficha`."""
    campos = [
        f"{rotulo}: {c[campo]}"
        for rotulo, campo in (
            ("Nome", "nome"), ("Interesse", "tipo_interesse"),
            ("Orçamento", "orcamento"), ("Zona", "zona_preferida"),
        )
        if c.get(campo)
    ]
    if not campos:
        return ""
    return (
        "\n\nEste cliente já está registado: " + " | ".join(campos) +
        "\nCumprimenta-o pelo nome e não voltes a pedir dados que já temos."
    )


_DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)


def _data_de_hoje() -> str:
    """Data real, para o modelo propor horários em dias úteis que existem.

    Sem isto o modelo inventa uma data plausível mas errada (ex.: A4
    `escalar_para_humano`) — observado ao vivo com a Bárbara a propor "22 de
    Julho" numa conversa de Setembro. UTC chega para "que dia é hoje"; não é
    caminho onde a hora exacta importe.
    """
    hoje = datetime.now(timezone.utc)
    return f"Hoje é {_DIAS_SEMANA[hoje.weekday()]}, {hoje.strftime('%d/%m/%Y')}."


def _montar_system_prompt(
    spec: dict, perfil: str, extra: str, canal: str,
    escalados: list[str] = (), ja_usadas: list[str] = (), telefone: str | None = None,
) -> str:
    system_prompt = spec["prompt"] + perfil + extra + f"\n\n{_data_de_hoje()}"
    if canal == "site":
        system_prompt += _INSTRUCAO_IDENTIDADE_SITE
    elif canal == "whatsapp":
        system_prompt += _INSTRUCAO_TELEFONE_WHATSAPP
    elif canal == "voz":
        system_prompt += _instrucao_voz(telefone)
    return system_prompt + _nota_de_estado(escalados, ja_usadas)


async def _contexto_recrutamento(
    telefone: str, perfil: str, thread_nova: bool
) -> tuple[str, dict | None, dict | None]:
    """Contexto da Inês. A candidatura da Meta vive em `contactos` (RPC
    `lead_meta_recrutamento`), nunca em `leads` — sem isto a Inês não sabia
    quem era: perguntou o nome a uma candidata a quem o template já chamava
    pelo nome e apresentou-se duas vezes (29/09).

    Mesmo desenho do A1: o template entra como mensagem do assistente só no
    1.º turno, e diz-se ao modelo, sem margem para inferência, se já se
    apresentou. `lead` continua a ser a de `leads` — é o que o fim de turno usa.
    """
    lead = await lead_aberta(telefone)
    contacto = await contacto_meta_aberto(telefone, "recrutamento")
    if not contacto:
        return perfil, None, lead

    if contacto.get("nome"):
        perfil += (
            f"\n\nEsta pessoa candidatou-se por um anúncio da Meta. Nome no formulário: "
            f"{contacto['nome']}. Já o sabes — não o perguntes."
        )

    template = contacto.get("template_enviado")
    if thread_nova and template:
        if NOME_A3.lower() in template.lower():
            perfil += f"\n\nJá te apresentaste como {NOME_A3} na mensagem inicial — não voltes a apresentar-te."
        now = datetime.now(timezone.utc).isoformat()
        return perfil, {"role": "assistant", "content": template, "timestamp": now}, lead
    return perfil, None, lead


async def _contexto_inicial(
    telefone: str, thread_nova: bool, agente: str | None = None
) -> tuple[str, dict | None, dict | None]:
    """Perfil para o prompt e, se for caso disso, o template já enviado.

    O fluxo real das leads da Meta não passa por endpoint nenhum nosso: o Make
    escreve a lead, o n8n manda o template, e o A1 só entra quando a pessoa
    responde. Nessa altura `agente_clientes` ainda não tem linha — quem tem as
    respostas do formulário é `leads.ficha`.

    Precedência: `agente_clientes` ganha sempre. É escrita durante a conversa e
    portanto mais recente do que o formulário; deixar a ficha sobrepor-se seria
    ressuscitar o orçamento inicial depois de o cliente o ter corrigido ao A1.

    O template entra como mensagem do assistente **só no primeiro turno**, para
    o A1 o ler como algo que já disse e não voltar a cumprimentar. Nos turnos
    seguintes já está no histórico gravado.
    """
    perfil = await asyncio.get_event_loop().run_in_executor(None, _perfil_cliente, telefone)

    if agente == A3:
        return await _contexto_recrutamento(telefone, perfil, thread_nova)

    lead = await lead_aberta(telefone)
    if not lead:
        return perfil, None, None

    if not perfil:
        campos = campos_mql_da_ficha(lead.get("ficha"))
        perfil = _texto_perfil({"nome": lead.get("nome"), **campos})

    # A lead da Meta vem do anúncio de UM imóvel, e `leads.imovel_ref` diz qual.
    # Sem isto o A1 ouve "quero saber mais sobre este imóvel" e pede a
    # referência — a quem acabou de clicar no anúncio desse imóvel. Visto ao
    # vivo a 2026-08-16 com a FH2581.
    if lead.get("imovel_ref"):
        perfil += (
            f"\n\nEsta pessoa veio do anúncio do imóvel {lead['imovel_ref']} — é a esse "
            'que se refere quando diz "este imóvel" ou "o imóvel do anúncio". '
            "Não lhe peças a referência: usa `ficha_imovel` e dá-lhe os detalhes."
        )

    # O template vive em `contactos` (o fluxo 01 do n8n passa a marcá-lo lá, como os de Recrutamento e
    # Angariação); `leads.template_enviado` fica como fallback para as leads anteriores
    # (`template-compra-contactos-plano.md`, 15/10).
    template = None
    if thread_nova:
        contacto = await contacto_meta_aberto(telefone, "comprador")
        template = (contacto or {}).get("template_enviado") or lead.get("template_enviado")
    if thread_nova and template:
        # Dizer ao modelo, sem margem para inferência, se a apresentação já foi
        # feita. Deixá-lo deduzir do histórico dava as duas falhas: repetir
        # "Sou a Matilde" logo a seguir ao template que já o dizia, ou nunca se
        # apresentar por assumir que o template tratou disso.
        #
        # O template da Meta é fixo e aprovado, portanto isto é uma pergunta com
        # uma resposta só — mas é o texto gravado que manda, não um palpite: o
        # template muda sem o código saber. A 2026-08-18 o que está em uso diz
        # apenas "Fala da Figueirahome", logo a A1 apresenta-se.
        if NOME_A1.lower() in template.lower():
            perfil += (
                f"\n\nJá te apresentaste como {NOME_A1} na mensagem inicial "
                "— não voltes a apresentar-te."
            )
        else:
            perfil += (
                "\n\nA mensagem inicial não te identificou. Começa a tua resposta "
                f'com "{APRESENTACAO_A1}".'
            )
        now = datetime.now(timezone.utc).isoformat()
        return perfil, {"role": "assistant", "content": template, "timestamp": now}, lead
    return perfil, None, lead


# Tools cujos argumentos são critérios de pesquisa e nada mais. Só destas se
# guardam os `input` em `agente_interacoes.tools_detalhe`.
#
# `guardar_dados_cliente`, `pedir_visita` e `escalar_para_humano` recebem
# nome, telefone e email — copiá-los para cá espalharia dados pessoais por uma
# segunda tabela sem necessidade. Dessas guarda-se o nome da tool e mais nada.
#
# Allowlist e não blocklist de propósito: uma tool nova entra por omissão no
# lado seguro. Acrescentar aqui exige olhar para o schema dela primeiro.
_TOOLS_INPUT_SEGURO = frozenset({"pesquisar_imoveis", "ficha_imovel"})


def _detalhe_tool(bloco: dict) -> dict:
    """Nome da tool, e os argumentos apenas quando não carregam PII."""
    nome = bloco.get("name", "")
    if nome in _TOOLS_INPUT_SEGURO:
        return {"nome": nome, "input": bloco.get("input") or {}}
    return {"nome": nome}


async def _registar_interacao(dados: dict) -> None:
    """Grava uma linha em `agente_interacoes`.

    Engolir a excepção é deliberado: isto corre depois de a resposta estar
    pronta, e observabilidade nunca pode derrubar uma conversa com um cliente.
    Se a tabela não existir (migration 0016 por aplicar), fica só o aviso.
    """

    def _inserir():
        get_supabase().table("agente_interacoes").insert(
            {k: v for k, v in dados.items() if v is not None}
        ).execute()

    try:
        await asyncio.get_event_loop().run_in_executor(None, _inserir)
    except Exception:
        logger.exception("Falha ao registar interacao (%s)", dados.get("agente"))


def _garantir_apresentacao(
    resposta: str, agente: str, thread_nova: bool, mensagens: list[dict], canal: str = "whatsapp",
) -> str:
    """A A1 identifica-se no primeiro turno, e isso não fica ao critério do modelo.

    Estava só no prompt, com a frase exacta e uma instrução injectada a dizer se
    já tinha sido feita. **Obedeceu em 4 de 7 conversas reais** (2026-08-22): a
    Ana Luísa, o Pedro Marques e o Jorge Pessoa falaram com uma IA sem lho ser
    dito. Numa instrução mole a competir com o resto do prompt, 43% de falha é o
    que se obtém — e aqui não é estilo, é transparência.

    Prefixar em código é determinístico e não estraga nada quando o modelo já
    acertou: verifica-se primeiro se o nome aparece na resposta **ou** numa
    mensagem anterior do assistente — que no primeiro turno é o template do n8n,
    o único sítio de onde a apresentação também pode ter vindo.

    Só a A1: a A2 não tem nome atribuído.
    """
    if agente != A1 or not thread_nova or resposta == _ERRO or canal == "voz":
        return resposta  # na voz a saudação da chamada já disse que é uma assistente virtual

    nome = NOME_A1.lower()
    if nome in resposta.lower():
        return resposta
    if any(nome in (m.get("content") or "").lower()
           for m in mensagens if m.get("role") == "assistant"):
        return resposta

    return f"{APRESENTACAO_A1}\n\n{resposta}"


# Duas mensagens quase simultâneas da mesma pessoa (WhatsApp entrega em bubbles
# separados, cada um o seu webhook/background task) corriam `load_conversation`
# em paralelo, nenhuma via a conversa que a outra ainda não tinha gravado, e
# cada uma inseria a sua própria linha — thread duplicada, duas respostas
# desencontradas. Achado ao vivo 25/09 (Margarida Lopes: 2 linhas em 3s, cada
# uma com a sua própria leitura da ficha do imóvel). Lock por (canal,
# participante) serializa load→responder→save para a mesma pessoa.
#
# ponytail: lock em memória do processo, nunca liberto — cresce um `Lock` por
# número visto, ao longo da vida do processo. Trivial ao volume actual
# (milhares de números = poucos MB); só serve enquanto for 1 máquina Fly — com
# 2+ réplicas precisa de lock a nível de BD (ex.: advisory lock do Postgres).
_log_voz = logging.getLogger("app.agents.voice.motor")  # a raiz está em WARNING; só o namespace da voz fala em INFO
_locks: dict[tuple[str, str], asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _lock_conversa(canal: str, participante: str) -> asyncio.Lock:
    chave = (canal, participante)
    async with _locks_guard:
        if chave not in _locks:
            _locks[chave] = asyncio.Lock()
        return _locks[chave]


async def responder(
    canal: str,
    participante: str,
    mensagem: str,
    agente: str | None = None,
    telefone: str | None = None,
) -> str:
    """Responde a uma mensagem e persiste a conversa.

    `agente=None` deixa o router decidir (e a decisão fica colada à thread).
    `telefone` só para a voz: o `participante` é o id da chamada e o número de quem liga vem à parte.
    Serializado por (canal, participante) — ver `_lock_conversa`.
    """
    lock = await _lock_conversa(canal, participante)
    if canal != "voz":
        async with lock:
            return await _responder_sem_lock(canal, participante, mensagem, agente, telefone)

    # Voz: a resposta sai logo e o resto do turno (ferramentas de registo, gravação, lead) corre a seguir, ainda com o
    # bloqueio da conversa — o turno seguinte espera por ele e lê a conversa já gravada. Ao telefone, cada segundo
    # antes da resposta é silêncio (chamada de 27/10: 6,9 s no turno que gravou os dados).
    t_espera = time.monotonic()
    await lock.acquire()
    espera = time.monotonic() - t_espera
    if espera >= 0.05:  # o turno anterior ainda tinha trabalho diferido (chamada de 28/10: 7 a 9 s em frases curtas)
        _log_voz.info("[%s] turno esperou %.1f s pelo fim do turno anterior", participante[-6:], espera)
    diferido: list = []
    try:
        resposta = await _responder_sem_lock(canal, participante, mensagem, agente, telefone, diferido)
    except BaseException:
        lock.release()
        raise
    if not diferido:
        lock.release()
        return resposta
    tarefa = asyncio.ensure_future(_correr_diferido(lock, diferido))
    _diferidos.add(tarefa)
    tarefa.add_done_callback(_diferidos.discard)
    return resposta


_diferidos: set = set()


async def _correr_diferido(lock: asyncio.Lock, passos: list) -> None:
    """O fim do turno de voz, depois de a resposta sair. Um passo que falha não impede os seguintes nem prende o bloqueio."""
    try:
        tempos = []
        for passo in passos:
            t0 = time.monotonic()
            try:
                await passo()
            except Exception:
                logger.exception("Erro no fim do turno de voz")
            tempos.append(f"{getattr(passo, '__name__', 'passo')} {time.monotonic() - t0:.1f}s")
        _log_voz.info("fim do turno diferido: %s", ", ".join(tempos))
    finally:
        lock.release()


async def esperar_diferidos() -> None:
    """Para os testes (e para um encerramento limpo): espera pelo que ficou por fazer depois das respostas."""
    if _diferidos:
        await asyncio.gather(*list(_diferidos), return_exceptions=True)


async def _responder_sem_lock(
    canal: str,
    participante: str,
    mensagem: str,
    agente: str | None = None,
    telefone_voz: str | None = None,
    diferir: list | None = None,
) -> str:
    conversa_id, mensagens, agente_atual = await load_conversation(canal, participante)

    # A conversa já acabou (a assistente despediu-se) e a pessoa só responde com emojis, «obrigado» ou «até logo»:
    # não se responde. Visto a 22/10: uma lead trocou ~40 mensagens de carinhas e «tchau» e o modelo respondeu a todas.
    # Só no WhatsApp: no site e no painel a mensagem vem sempre de quem a escreveu para ser lida.
    if (
        canal == "whatsapp" and mensagens and mensagens[-1].get("role") == "assistant"
        and e_despedida(mensagens[-1].get("content") if isinstance(mensagens[-1].get("content"), str) else "")
        and e_fecho_da_pessoa(mensagem)
    ):
        logger.info("Conversa já fechada e a mensagem só se despede: sem resposta (%s).", participante[-3:])
        return ""

    # Pedido explícito de não ser contactada («não me contactem», «stop»): fica gravado já, em código, sem esperar que o
    # modelo chame `encerrar_lead` (pedido #49). Bloqueia só os envios proativos; a resposta a esta mensagem segue normal.
    if canal == "whatsapp" and e_optout_explicito(mensagem):
        await asyncio.get_event_loop().run_in_executor(None, marcar_nao_contactar, participante)

    agente = agente or route(mensagem, agente_atual)
    if agente not in ASSISTENTES:
        logger.warning("Assistente '%s' desconhecido — fallback para o router.", agente)
        agente = route(mensagem, None)
    spec = ASSISTENTES[agente]

    if canal == "voz":
        cfg = _cache_voz.setdefault(participante, {}).setdefault("cfg", {})
        if agente not in cfg:
            cfg[agente] = await load_config(agente)
        extra, ativo = cfg[agente]
    else:
        extra, ativo = await load_config(agente)
    if not ativo:
        logger.info("Assistente %s inactivo — sem chamada à API.", agente)
        return MENSAGEM_INATIVO

    telefone = normalizar_telefone(telefone_voz if canal == "voz" else participante) if canal in ("whatsapp", "voz") else None
    perfil = ""
    lead = None
    thread_nova = not mensagens
    if telefone:
        if canal == "voz":
            guardado = _cache_voz.setdefault(participante, {}).setdefault("ctx", {})
            if agente not in guardado:
                # thread_nova=False: sem template (é de WhatsApp) nem nota de apresentação, a saudação da chamada já a fez
                guardado[agente] = await _contexto_inicial(telefone, thread_nova=False, agente=agente)
            perfil, template, lead = guardado[agente]
            template = None  # nunca na voz, mesmo que a leitura o devolva
        else:
            perfil, template, lead = await _contexto_inicial(
                telefone, thread_nova=thread_nova, agente=agente
            )
        if template:
            # Antes da mensagem do utilizador: o template foi o que veio primeiro.
            mensagens.append(template)

    escalados, ja_usadas = await asyncio.gather(
        motivos_escalados(conversa_id), tools_ja_usadas(conversa_id),
    )
    system_prompt = _montar_system_prompt(spec, perfil, extra, canal, escalados, ja_usadas, telefone)
    contexto = {
        "canal": canal,
        "telefone": telefone,
        "origem": canal,
        "agente": agente,
        "conversa_id": conversa_id,
    }

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "user", "content": mensagem, "timestamp": now})

    if conversa_id is None and canal != "voz":  # na voz não há nudge, e o telefone espera pela 1.ª resposta
        # Conversa nova: a linha tem de existir antes das ferramentas, senão a tarefa `escalar` do 1.º turno fica sem
        # `conversa_id` e o nudge não a vê (29–30/10: «podem ligar-me?» como 1.ª resposta e, no dia seguinte, «Ainda
        # está interessado?»). O fim do turno regrava a mesma linha com a resposta.
        try:
            conversa_id = await save_conversation(None, canal, participante, mensagens, agente)
        except Exception:
            logger.exception("Erro ao criar conversa %s/%s", canal, participante)
        contexto["conversa_id"] = conversa_id
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in mensagens]

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "prompt-caching-2024-07-31",
        "content-type": "application/json",
    }
    # System como lista com cache_control: cache hits custam 10% do preço.
    system_payload = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    forcar = None if canal == "voz" else spec.get("force")  # a tool forçada (pesquisa) não existe na voz
    # Sem este forcing o Claude ignorava as tools e prometia callbacks de
    # consultor — comportamento observado em produção (CLAUDE.md).
    forcar_agora = bool(forcar and forcar[1].search(mensagem))
    tool_a_forcar = forcar[0] if forcar_agora else None

    # Mas a tool certa depende de quem está do outro lado. `_SEARCH_RE` inclui
    # "imóvel", portanto "quero saber mais acerca deste imóvel" — a primeira
    # coisa que uma lead da Meta escreve — forçava `pesquisar_imoveis` **sem
    # critérios nenhuns**. Medido a 2026-08-16: chamada com `{}`, resposta
    # descartada, e só na 2.ª iteração é que o modelo fazia `ficha_imovel`.
    # Uma iteração inteira deitada fora na resposta que decide se a pessoa
    # continua a conversa.
    #
    # Só no primeiro turno: a seguir, "e tem T2 mais baratos?" volta a ser
    # pesquisa, e aí o forcing normal é o que está certo.
    if thread_nova and forcar_agora and lead and lead.get("imovel_ref"):
        tool_a_forcar = "ficha_imovel"

    resposta = _ERRO

    # Instrumentação do turno. O `usage` chega em cada resposta da API e antes
    # era descartado — sem ele o custo é incalculável.
    tokens: dict[str, int] = {}
    tools_usadas: list[str] = []
    tools_detalhe: list[dict] = []
    iteracoes = 0
    erro: str | None = None
    inicio = time.monotonic()

    async with httpx.AsyncClient(timeout=60.0) as client:
        for iteracao in range(_MAX_TOOL_ITERATIONS):
            iteracoes = iteracao + 1
            payload = {
                "model": _MODEL,
                "max_tokens": MAX_TOKENS.get(canal, 512),
                "temperature": _TEMPERATURE,
                "system": system_payload,
                "tools": tools_para(spec["tools"], canal),
                "messages": claude_messages,
            }
            if tool_a_forcar and iteracao == 0:
                payload["tool_choice"] = {"type": "tool", "name": tool_a_forcar}

            try:
                http_resp = await client.post(_URL, headers=headers, json=payload)
                http_resp.raise_for_status()
            except Exception as exc:
                logger.exception("Erro na API Anthropic (%s, %s)", agente, participante)
                erro = f"{type(exc).__name__}: {exc}"[:500]
                break

            data = http_resp.json()
            somar_usage(tokens, data.get("usage"))
            blocos = data.get("content", [])

            if data.get("stop_reason") == "tool_use":
                claude_messages.append({"role": "assistant", "content": blocos})
                chamadas = [b for b in blocos if b.get("type") == "tool_use"]
                falado = " ".join(b.get("text", "") for b in blocos if b.get("type") == "text").strip()
                if (
                    diferir is not None and falado and chamadas
                    and all(b["name"] in _TOOLS_DIFERIVEIS_NA_VOZ for b in chamadas)
                ):
                    # A frase já vem escrita e estas ferramentas só registam (o resultado não muda o que se diz):
                    # a pessoa ouve a resposta já e o registo corre a seguir. Uma 2.ª chamada ao modelo custava ~2 s.
                    for b in chamadas:
                        tools_usadas.append(b["name"])
                        tools_detalhe.append(_detalhe_tool(b))

                    async def _registar(chamadas=chamadas):
                        for b in chamadas:
                            await execute_tool(b["name"], b.get("input", {}), contexto)

                    diferir.append(_registar)
                    resposta = falado
                    break
                resultados = []
                for bloco in blocos:
                    if bloco.get("type") != "tool_use":
                        continue
                    tools_usadas.append(bloco["name"])
                    tools_detalhe.append(_detalhe_tool(bloco))
                    saida = await execute_tool(
                        bloco["name"], bloco.get("input", {}), contexto
                    )
                    resultados.append({
                        "type": "tool_result",
                        "tool_use_id": bloco["id"],
                        "content": saida,
                    })
                claude_messages.append({"role": "user", "content": resultados})
                continue

            motivo_paragem = data.get("stop_reason")
            if motivo_paragem not in ("end_turn", "stop_sequence"):
                # "max_tokens" corta um tool_use a meio em silêncio — sem isto
                # nunca se sabe que aconteceu (achado ao vivo 25/09, Carla
                # Pato: candidatura toda recolhida, tool nunca chamada).
                logger.warning(
                    "Turno terminou por '%s', não 'tool_use'/'end_turn' — pode ter cortado "
                    "uma tool a meio (%s, %s)",
                    motivo_paragem, agente, participante,
                )

            for bloco in blocos:
                if bloco.get("type") == "text":
                    resposta = bloco["text"]
                    break
            break

        # Sem texto e sem excepção: ou o modelo fechou com `end_turn` vazio depois
        # das tools (achado 29/09, Inês a responder "Obrigada!" após escalar), ou
        # esgotou as iterações só a chamar tools. Nos dois casos o histórico acaba
        # num tool_result — uma chamada final sem tools obriga-o a escrever, em vez
        # de a candidata receber "Ocorreu um erro".
        if resposta == _ERRO and erro is None:
            erro = "sem_texto"
            try:
                http_resp = await client.post(
                    _URL, headers=headers,
                    json={
                        **payload, "tool_choice": {"type": "none"},
                        "messages": _com_instrucao_de_resposta(claude_messages),
                    },
                )
                http_resp.raise_for_status()
                data = http_resp.json()
                somar_usage(tokens, data.get("usage"))
                iteracoes += 1
                for bloco in data.get("content", []):
                    if bloco.get("type") == "text" and bloco["text"].strip():
                        resposta = bloco["text"]
                        break
            except Exception as exc:
                logger.exception("Erro na chamada final sem tools (%s, %s)", agente, participante)
                erro = f"sem_texto; {type(exc).__name__}: {exc}"[:500]

    latencia_ms = int((time.monotonic() - inicio) * 1000)
    resposta = _sem_erro_apos_registo(resposta, tools_usadas, ja_usadas, escalados)

    # Antes de gravar: o que fica no histórico tem de ser o que a pessoa recebeu.
    resposta = _garantir_apresentacao(resposta, agente, thread_nova, mensagens, canal)

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "assistant", "content": resposta, "timestamp": now})

    async def _fechar_turno() -> None:
        nonlocal conversa_id
        try:
            conversa_id = await save_conversation(
                conversa_id, canal, participante, mensagens, agente
            )
        except Exception:
            logger.exception("Erro ao guardar conversa %s/%s", canal, participante)

        await _registar_interacao({
            "conversa_id": conversa_id,
            "agente": agente,
            "canal": canal,
            "modelo": _MODEL,
            **tokens,
            "custo_usd": calcular_custo(tokens, _MODEL),
            "latencia_ms": latencia_ms,
            "iteracoes": iteracoes,
            "tools_usadas": tools_usadas or None,
            "tools_detalhe": tools_detalhe or None,
            # A coluna é boolean (migration 0016). Qual foi a tool forçada lê-se em
            # `tools_detalhe[0]`, que é sempre a da iteração 0.
            "tool_forcada": bool(tool_a_forcar),
            "erro": erro,
        })

        # Este turno é a prova de que a lead respondeu — e é a única. Sem o registar,
        # uma lead que fala mas não qualifica fica indistinguível de uma que nunca
        # respondeu, e o follow-up às 48h escreveria a quem já está em conversa.
        # A lead vem de `_contexto_inicial`, que já a leu: não há consulta extra.
        if lead:
            await marcar_lead_respondeu(lead["id"], conversa_id)
            if agente == A1 and telefone:
                # Os follow-ups da Matilde passaram a viver em `contactos`
                # (23/09, mesmo padrão da Inês/Bárbara) — `respondeu_em` tem de
                # ficar marcado lá também, ou o follow-up nunca saberia que a
                # pessoa já respondeu (só olha a `contactos`, não a `leads`).
                contacto = await contacto_meta_aberto(telefone, "comprador")
                if contacto:
                    await marcar_contacto_respondeu(contacto["id"])
        elif agente == A3 and telefone:
            # Recrutamento não passa por `_contexto_inicial`/`leads` — mesmo sinal,
            # tabela diferente (`contactos`, sem semeadura). Ver `guards.py`.
            contacto = await contacto_meta_aberto(telefone, "recrutamento")
            if contacto:
                await marcar_contacto_respondeu(contacto["id"])
        elif agente == A4 and telefone:
            # Angariação via Meta (`lead_meta_angariacao`) tem o mesmo problema:
            # só escreve em `contactos`, nunca em `leads`.
            contacto = await contacto_meta_aberto(telefone, "vendedor")
            if contacto:
                await marcar_contacto_respondeu(contacto["id"])

        # A lead da Meta chega com o MQL já preenchido pelo formulário: o A1 não tem
        # dados para escrever, `find_or_create_cliente` nunca corre e a promoção
        # nunca dispara. Ao fim do turno sabem-se as duas metades da condição —
        # respondeu (é este turno) e o perfil está completo.
        if telefone:
            await promover_se_qualificada(telefone, agente=agente)


    if diferir is not None:
        diferir.append(_fechar_turno)
    else:
        await _fechar_turno()

    return resposta
