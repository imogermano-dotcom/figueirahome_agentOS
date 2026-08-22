"""Regras de negócio que não podem depender do modelo.

Duas guardas, ambas da spec `assistentes-ia-especificacao.md`:

* **Deduplicação de clientes** (§2.7) — regra transversal a todos os
  assistentes: pesquisar sempre antes de criar, por telefone -> email -> nome.
  Todos os caminhos de escrita passam por `find_or_create_cliente`; é essa
  partilha que a torna eficaz. Antes desta função havia quatro upserts
  artesanais quase iguais (WhatsApp, voz, e cada tool que gravava cliente).

* **Regra dos 80%** (§3.2 SV) — não marcar visita se o orçamento declarado
  for inferior a 80% do preço de venda. Aplicada dentro de `agendar_visita`,
  antes de qualquer escrita: o modelo fica impedido de marcar, em vez de ser
  apenas instruído a não o fazer.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from app.db.supabase_client import get_supabase
from app.notificacoes import notificar

logger = logging.getLogger(__name__)

_LIMIAR_VISITA = 0.80

_SO_DIGITOS = re.compile(r"\D+")


def normalizar_telefone(raw: str | None) -> str | None:
    """Reduz um número português à sua forma nacional de 9 dígitos.

    A Meta entrega `351912345678`, o cliente escreve `+351 912 345-678` e o
    painel guarda `912345678` — todos a mesma pessoa.
    Números não-portugueses ficam só sem pontuação.
    """
    if not raw:
        return None
    digitos = _SO_DIGITOS.sub("", raw)
    digitos = digitos.lstrip("0")  # prefixo internacional 00; nº PT nunca começa por 0
    if len(digitos) > 9 and digitos.startswith("351"):
        digitos = digitos[3:]
    return digitos or None


def normalizar_email(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().lower() or None


def variantes_telefone(numero: str) -> list[str]:
    """Formatos sob os quais o mesmo número pode já estar gravado.

    As linhas existentes em produção guardam o que a Meta enviou. Normalizar
    só para a frente faria os lookups novos falharem e duplicarem o cliente.
    """
    return [numero, f"351{numero}", f"+351{numero}", f"00351{numero}"]


# MQL segundo o CLAUDE.md: orçamento + zona + tipo de interesse. O `prazo_compra`
# (migration 0020) fica de fora de propósito — só o gate das landing pages o
# recolhe, e exigi-lo aqui deixava toda a lead de WhatsApp por qualificar.
_CAMPOS_MQL = ("tipo_interesse", "orcamento", "zona_preferida")

_TAREFA_QUALIFICADA = "Lead qualificada — passar ao eGO"


def lead_qualificada(cliente: dict | None) -> bool:
    """Os três campos do MQL preenchidos. Função pura, sem DB."""
    if not cliente:
        return False
    return all(cliente.get(campo) not in (None, "") for campo in _CAMPOS_MQL)


def _promover_lead(
    supabase, cliente: dict, estados: tuple[str, ...] = ("contactada",)
) -> None:
    """Marca a lead como qualificada e cria a tarefa para o corretor.

    A passagem ao eGO é manual: `contactos` é espelho do eGO (upsert por
    `ego_link`, que só o eGO atribui) e um insert nosso ficaria órfão — ver
    `docs/decisoes.md`. Não existe API de escrita do eGO configurada, por isso
    esta fase pára aqui, na tarefa.

    Chamada de dentro de `find_or_create_cliente` porque é o ponto único por
    onde todos os caminhos de escrita passam — WhatsApp, painel e landing pages
    ganham a regra sem a repetir.
    """
    telefone = normalizar_telefone(cliente.get("telefone"))
    email = normalizar_email(cliente.get("email"))
    if not telefone and not email:
        return

    # `estados` é quem decide o que conta como "já respondeu". Por omissão só
    # `contactada`, porque este caminho (escrita de cliente) inclui a semeadura,
    # que chama `find_or_create_cliente` com os campos do formulário: sem o
    # filtro criava a tarefa antes de a pessoa dizer fosse o que fosse — e o
    # `contactada` que o endpoint escreve a seguir apagava a promoção na mesma.
    # `promover_se_qualificada` alarga a `nova` porque aí houve mesmo um turno.
    q = supabase.table("leads").select("id,estado,cliente_id,imovel_ref").in_("estado", list(estados))
    q = q.in_("telefone", variantes_telefone(telefone)) if telefone else q.eq("email", email)
    leads = q.limit(1).execute().data
    if not leads:
        return
    lead = leads[0]

    agora = datetime.now(timezone.utc).isoformat()
    supabase.table("leads").update({
        "estado": "qualificada",
        "qualificada_em": agora,
        "cliente_id": cliente.get("id"),
        "atualizado_em": agora,
    }).eq("id", lead["id"]).execute()

    quem = cliente.get("nome") or telefone or email
    supabase.table("agente_tarefas").insert({
        "titulo": f"{_TAREFA_QUALIFICADA} — {quem}",
        "descricao": (
            "Lead da Meta qualificada pelo assistente "
            f"(interesse: {cliente.get('tipo_interesse')}, "
            f"orçamento: {cliente.get('orcamento')}, "
            f"zona: {cliente.get('zona_preferida')}). "
            "Criar o contacto no eGO e associar a oportunidade."
        ),
    }).execute()
    logger.info("Lead %s qualificada (cliente %s)", lead["id"], cliente.get("id"))

    # A tarefa é o registo; isto é o toque no ombro. Uma lead imobiliária é
    # perecível e ninguém tem o painel aberto às 23h. `notificar` engole os
    # próprios erros de propósito — ver `app/notificacoes.py`.
    notificar(
        f"Lead qualificada — {quem}",
        "\n".join((
            "Uma lead da Meta acabou de qualificar na conversa com o A1.",
            "",
            f"Nome:      {cliente.get('nome') or '—'}",
            f"Telefone:  {telefone or '—'}",
            f"Email:     {email or '—'}",
            f"Interesse: {cliente.get('tipo_interesse') or '—'}",
            f"Orçamento: {cliente.get('orcamento') or '—'}",
            f"Zona:      {cliente.get('zona_preferida') or '—'}",
            "",
            f"Imóvel do anúncio: {lead.get('imovel_ref') or '—'}",
            "",
            "Passo seguinte: criar o contacto no eGO e associar a oportunidade.",
            "A tarefa também está no painel.",
        )),
        imovel_ref=lead.get("imovel_ref"),
    )


# Uma lead da Meta responde ao template quando lhe apetece. A thread semeada
# expira às 48h (`conversation._CONVERSATION_TTL_HOURS`) e a partir daí a
# resposta ("Sim", "Olá") deixa de ter routing colado e cai no A2. Esta janela
# cobre esse intervalo sem forçar o A1 para sempre a quem já foi trabalhado.
_JANELA_LEAD_DIAS = 30
#
# `sem_resposta` conta como aberta: é o estado que o follow-up das 48h escreve, e
# quer dizer "desistimos de insistir", não "não falar com esta pessoa". Quem
# responde uma semana depois tem de manter a A1 e o `imovel_ref` do anúncio.
# Como esta mesma tupla é o filtro de `promover_se_qualificada`, uma resposta
# tardia que traga o MQL completo continua a ser promovida.
_ESTADOS_LEAD_ABERTA = ("nova", "contactada", "sem_resposta")


# `ficha` (respostas do formulário da Meta) → colunas do MQL. Vive aqui, ao lado
# de `_CAMPOS_MQL`, porque tem dois leitores: o endpoint de semeadura
# (`api/leads_meta.py`, hoje inerte) e o contexto que o `engine` monta quando a
# lead responde sem ter havido semeadura.
#
# Os alias vieram do que `leads_angariacao` já usava. **São palpites**: o
# formulário de venda do Meta Lead Ads ainda não existe. Se os nomes reais não
# baterem, o A1 fica sem contexto e a lead nunca é qualificada — confirmar os
# campos antes de assumir que este mapa cobre alguma coisa.
_ALIAS_FICHA = {
    "tipo_interesse": ("tipo_interesse", "tipo_imovel", "interesse"),
    "orcamento": ("orcamento", "expectativa_preco", "valor_expectativa"),
    "zona_preferida": ("zona_preferida", "zona", "freguesia", "local"),
}


def campos_mql_da_ficha(ficha: dict | None) -> dict:
    """Os três campos do MQL, tirados da ficha seja qual for o alias usado."""
    if not isinstance(ficha, dict):
        return {}
    campos = {}
    for coluna, chaves in _ALIAS_FICHA.items():
        for chave in chaves:
            valor = ficha.get(chave)
            if valor not in (None, ""):
                campos[coluna] = valor
                break
    return campos


async def lead_aberta(telefone: str | None) -> dict | None:
    """A lead ainda em aberto deste número, ou `None`.

    Ponto único da consulta: serve o router (`agente_de_lead`) e o contexto que
    o `engine` monta ao primeiro turno. Devolve `None` em qualquer falha —
    incluindo a tabela ainda não existir — para tudo continuar a decidir como
    decidia antes.
    """
    numero = normalizar_telefone(telefone)
    if not numero:
        return None

    limite = (datetime.now(timezone.utc) - timedelta(days=_JANELA_LEAD_DIAS)).isoformat()

    def _fetch():
        return (
            get_supabase()
            .table("leads")
            .select("id,tipo,nome,ficha,template_enviado,imovel_ref")
            .in_("telefone", variantes_telefone(numero))
            .in_("estado", list(_ESTADOS_LEAD_ABERTA))
            .gte("criado_em", limite)
            .limit(1)
            .execute()
        )

    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception:
        logger.exception("Falha a procurar lead para %s", numero)
        return None

    return resp.data[0] if resp.data else None


async def agente_de_lead(telefone: str | None) -> str | None:
    """`a1_vendedor` se o número for de uma lead de compra ainda em aberto.

    Devolve `None` em qualquer outro caso, para o router decidir como decidia.
    """
    lead = await lead_aberta(telefone)
    if lead and lead.get("tipo") in ("compra", "arrendamento"):
        return "a1_vendedor"
    return None


async def marcar_lead_respondeu(lead_id: str, conversa_id: str | None) -> None:
    """Regista a **primeira** resposta da lead (migration 0027).

    Sem isto, uma lead que responde mas não qualifica fica `contactada` —
    indistinguível de uma que nunca respondeu — e o follow-up às 48h mandava
    segunda mensagem a quem já está a falar com o A1.

    O filtro `respondeu_em is null` faz duas coisas de uma vez: guarda o
    primeiro turno em vez do último, e evita ter de ler antes de escrever.
    """
    agora = datetime.now(timezone.utc).isoformat()
    dados = {"respondeu_em": agora, "atualizado_em": agora}
    if conversa_id:
        dados["conversa_id"] = conversa_id

    def _marcar():
        return (
            get_supabase()
            .table("leads")
            .update(dados)
            .eq("id", lead_id)
            .is_("respondeu_em", "null")
            .execute()
        )

    try:
        await asyncio.get_event_loop().run_in_executor(None, _marcar)
    except Exception:
        # Corre depois de a resposta já ter ido para o cliente. Falhar aqui
        # custa um follow-up a mais, não uma conversa.
        logger.exception("Falha a marcar resposta da lead %s", lead_id)


async def promover_se_qualificada(telefone: str | None) -> None:
    """Promove ao fim do turno a lead cujo perfil já veio completo do formulário.

    `_promover_lead` só corre de dentro de `find_or_create_cliente`, que exige
    que o assistente **escreva** dados do cliente. Quando o formulário da Meta
    já trouxe os três campos do MQL — o caso normal, não a excepção — o A1 não
    tem nada para escrever, nunca chama, e a lead ficava por qualificar para
    sempre. A condição real é "respondeu" **e** "perfil completo"; o fim de um
    turno de `engine.responder` é o único sítio que sabe as duas coisas.

    Aceita `nova` além de `contactada`: aqui o turno é prova directa de que a
    pessoa respondeu, ao contrário da semeadura, que corre antes disso. Apanha
    assim a lead que escreve sem nunca ter recebido template.
    """
    numero = normalizar_telefone(telefone)
    if not numero:
        return

    def _run():
        supabase = get_supabase()
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email,tipo_interesse,orcamento,zona_preferida")
            .in_("telefone", variantes_telefone(numero))
            .limit(1)
            .execute()
        )
        cliente = resp.data[0] if resp.data else None
        if lead_qualificada(cliente):
            _promover_lead(supabase, cliente, _ESTADOS_LEAD_ABERTA)

    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception:
        # Corre depois de a resposta estar entregue ao cliente: falhar aqui não
        # pode derrubar a conversa. Repete-se no turno seguinte na mesma.
        logger.exception("Falha ao promover lead de %s", numero)


_MOTIVOS_ENCERRAMENTO = ("engano", "sem_interesse")


async def encerrar_lead_do_telefone(
    telefone: str | None, motivo: str, nota: str | None = None
) -> bool:
    """Fecha a lead deste número. Desfecho "Engano" da spec §2.2.

    A spec diz "Regista o contacto na base de dados com o estado 'engano'. Sem
    mais ações" — e é à letra: nem cliente, nem tarefa, nem email. O único efeito
    é o estado, e o estado é o que faz a pessoa deixar de ser perseguida:
    `engano` está em `ESTADOS_FECHADOS`, logo `lead_aberta` passa a devolver
    `None` (o router larga a A1), `_criar_lead_se_preciso` não reabre, e o
    follow-up das 48h filtra por `estado in (nova, contactada)`.

    Quem decide que houve engano é o modelo, via tool; quem escreve é isto. Só
    mexe em leads abertas: uma segunda chamada sobre algo já fechado não reescreve
    o motivo original.
    """
    numero = normalizar_telefone(telefone)
    if not numero or motivo not in _MOTIVOS_ENCERRAMENTO:
        return False

    agora = datetime.now(timezone.utc).isoformat()
    dados = {"estado": motivo, "atualizado_em": agora}
    if nota:
        dados["notas"] = nota

    def _fechar():
        return (
            get_supabase()
            .table("leads")
            .update(dados)
            .in_("telefone", variantes_telefone(numero))
            .in_("estado", list(_ESTADOS_LEAD_ABERTA))
            .execute()
        )

    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, _fechar)
    except Exception:
        logger.exception("Falha a encerrar lead de %s (%s)", numero, motivo)
        return False

    fechadas = len(resp.data or [])
    logger.info("Lead de %s encerrada como '%s' (%d linha(s))", numero, motivo, fechadas)
    return fechadas > 0


def visita_permitida(orcamento: float | None, preco: float | None) -> bool:
    """Regra dos 80% (spec §3.2 SV).

    Limiar inclusivo: a spec dá o exemplo de €240k sobre €300k a avançar
    (com ressalva verbal do assistente). Sem orçamento declarado recusa —
    a spec manda insistir e, se o cliente persistir, escalar.
    Sem preço recusa também, em vez de dividir por zero.
    """
    if not orcamento or not preco or preco <= 0:
        return False
    return orcamento / preco >= _LIMIAR_VISITA


def _procurar_cliente(supabase, telefone: str | None, email: str | None, nome: str | None):
    """Telefone -> email -> nome, a ordem de prioridade da spec §2.7."""
    if telefone:
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email")
            .in_("telefone", variantes_telefone(telefone))
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

    if email:
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

    # Nome é só confirmação (spec §2.7) — mas é preciso tentá-lo mesmo quando
    # há telefone ou email que não deram correspondência.
    #
    # Bug real (2026-08-03): `guardar_dados_cliente` gravava o nome sem
    # telefone (o modelo nem sempre o passa) e, no turno seguinte,
    # `agendar_visita` trazia o telefone. A procura por telefone falhava e a
    # procura por nome era saltada — duas linhas para a mesma pessoa. É o
    # padrão normal de uma conversa: dados parciais primeiro, completos depois.
    #
    # Só se aceita a correspondência por nome quando o registo encontrado
    # **não contradiz** os identificadores que trazemos: telefone/email vazios
    # ou iguais. Dois "João Silva" com telefones diferentes continuam a ser
    # duas pessoas — a spec proíbe fundir por nome sozinho.
    if nome:
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email")
            .ilike("nome", nome.strip())
            .limit(5)
            .execute()
        )
        for candidato in resp.data or []:
            if _compativel(candidato, telefone, email):
                return candidato

    return None


def _compativel(candidato: dict, telefone: str | None, email: str | None) -> bool:
    """O candidato pode ser a mesma pessoa? Só se nada contradisser."""
    tel_c = normalizar_telefone(candidato.get("telefone"))
    if telefone and tel_c and tel_c != telefone:
        return False
    email_c = normalizar_email(candidato.get("email"))
    if email and email_c and email_c != email:
        return False
    return True


async def find_or_create_cliente(
    nome: str | None = None,
    telefone: str | None = None,
    email: str | None = None,
    **campos,
) -> dict | None:
    """Devolve o cliente existente (actualizado) ou cria um novo.

    Devolve `None` quando não há identificador nenhum — é assim que o banco
    de ensaio do painel (participante `painel_a1_vendedor`, sem telefone)
    não polui `agente_clientes`.
    """
    telefone = normalizar_telefone(telefone)
    email = normalizar_email(email)
    if not telefone and not email and not nome:
        return None

    dados = {"nome": nome, "telefone": telefone, "email": email, **campos}
    dados = {k: v for k, v in dados.items() if v is not None}

    def _run():
        supabase = get_supabase()
        existente = _procurar_cliente(supabase, telefone, email, nome)

        if existente:
            resp = (
                supabase.table("agente_clientes")
                .update(dados)  # grava já na forma normalizada
                .eq("id", existente["id"])
                .execute()
            )
            cliente = resp.data[0] if resp.data else existente
        else:
            resp = supabase.table("agente_clientes").insert(dados).execute()
            cliente = resp.data[0] if resp.data else None

        # A promoção nunca pode derrubar a gravação do cliente nem a conversa em
        # curso: se a `leads` não existir (migration 0021 por aplicar) ou falhar,
        # fica o aviso e o cliente é devolvido na mesma.
        if lead_qualificada(cliente):
            try:
                _promover_lead(supabase, cliente)
            except Exception:
                logger.exception("Falha ao promover lead (cliente=%s)", cliente.get("id"))

        return cliente

    try:
        cliente = await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception:
        logger.exception("Falha ao guardar cliente (telefone=%s)", telefone)
        return None

    if cliente:
        logger.info("Cliente %s (telefone=%s)", cliente.get("id"), telefone)
    return cliente


def demo() -> None:
    """Auto-verificação das funções puras. `python -m app.agents.broker.guards`"""
    assert normalizar_telefone("+351 912 345-678") == "912345678"
    assert normalizar_telefone("00351912345678") == "912345678"
    assert normalizar_telefone("351912345678") == "912345678"
    assert normalizar_telefone("912345678") == "912345678"
    assert normalizar_telefone("") is None
    assert normalizar_telefone(None) is None

    assert normalizar_email("  A@B.COM ") == "a@b.com"
    assert normalizar_email(None) is None

    assert visita_permitida(240000, 300000) is True  # limiar exacto: avança
    assert visita_permitida(239999, 300000) is False
    assert visita_permitida(None, 300000) is False
    assert visita_permitida(100000, None) is False
    assert visita_permitida(100000, 0) is False

    print("guards OK")


if __name__ == "__main__":
    demo()
