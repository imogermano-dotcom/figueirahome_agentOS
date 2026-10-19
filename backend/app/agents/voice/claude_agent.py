import logging
import re

from anthropic import AsyncAnthropic

from app.agents.broker.assistants import load_config
from app.agents.broker.guards import normalizar_telefone
from app.agents.voice.session import CallSession
from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

# Dita pela Telnyx logo ao atender (`webhook.py`) e repetida ao modelo no prompt, para nunca divergirem.
# «Figueira Home» (duas palavras) como nos templates: o TTS pronuncia melhor. Diz que é uma IA (transparência),
# avisa da transcrição (guardamos a transcrição e o resumo em `agente_chamadas`) e não é gendrada («ajudar»).
SAUDACAO = (
    "Olá! Fala a assistente virtual da Figueira Home. "
    "Esta chamada é transcrita para o poder atender melhor. "
    "Em que posso ajudar?"
)

FIM_CHAMADA = "FIM_CHAMADA"  # marca da despedida: o webhook desliga quando a fala acaba

_SYSTEM_BASE = f"""És a assistente de voz da agência imobiliária Figueirahome, em Portugal.
Falas sempre em Português de Portugal, de forma natural e cordial.
O teu objectivo é recolher os seguintes dados do cliente:
  - Nome completo
  - Tipo de interesse: compra, arrendamento, venda ou outro
  - Orçamento (em euros)
  - Zona ou localização preferida

A chamada começa sempre com a saudação «{SAUDACAO}», que já foi dita antes da primeira resposta tua:
já te apresentaste como assistente virtual e avisaste que a chamada é transcrita. Nunca voltes a cumprimentar,
a apresentar-te nem a avisar da transcrição, e nunca digas «bem-vindo».

Instruções:
- Responde numa única frase curta (no máximo 25 palavras): é uma chamada, a pessoa não pode reler.
- Faz perguntas de forma natural, uma de cada vez.
- Não termines a chamada sem teres pelo menos o nome e o tipo de interesse.
- Quando tiveres os dados, lê-os em voz alta para confirmar. Só te despedes depois de a pessoa responder à pergunta
  sobre o contacto telefónico.
- A despedida final é a tua última frase da chamada: termina-a com a palavra {FIM_CHAMADA}, que nunca é falada.
  Usa-a uma só vez, e só nessa frase.
- O nome ouve-se mal ao telefone: repete-o de volta para confirmar. Se a pessoa corrigir, aceita a correção,
  repete a versão nova e usa sempre a última.
- Se uma resposta for incoerente ou impercetível, não a trates como dado: pede de novo, com calma.
- Nunca uses markdown, listas ou símbolos — só texto simples.
- Não tens ferramentas nem acesso a imóveis nesta chamada: nunca escrevas texto entre parênteses retos, nunca
  digas que vais «pesquisar» nem inventes resultados. Recolhe os dados e diz que um consultor entrará em contacto.
"""


_TELEFONE_CONHECIDO = (
    "\n\nO número de telefone de quem liga já é conhecido, é o da própria chamada: nunca o peças nem o leias. "
    "No fim, pergunta apenas «Um consultor pode ligar-lhe para este mesmo número?» (a pergunta é se o consultor "
    "pode ligar, nunca se a pessoa pode ligar). Só se a pessoa disser que não, "
    "pede o outro número completo, de uma só vez (nove dígitos), e aceita-o por inteiro. Se vier incompleto, "
    "pede-lhe que repita o número todo: nunca peças um dígito isolado nem em partes."
)
_TELEFONE_DESCONHECIDO = (
    "\n\nEsta chamada não mostra o número de quem liga. No fim, pede o número de telefone completo, de uma só "
    "vez (nove dígitos), e aceita-o por inteiro. Se vier incompleto, pede-lhe que repita o número todo: nunca "
    "peças um dígito isolado nem em partes."
)


def instrucao_telefone(numero_origem: str | None) -> str:
    """O número de quem liga vem na chamada (como o do WhatsApp): pedi-lo ao ouvido dá nove dígitos mal ouvidos.
    Em 17/10 a assistente pediu «o dígito que falta no final» a quem já tinha dito sete dos nove."""
    n = normalizar_telefone(numero_origem)
    return _TELEFONE_CONHECIDO if n and len(n) == 9 else _TELEFONE_DESCONHECIDO


_ENTRE_RETOS = re.compile(r"\[[^\]]*\]")
_SIMBOLOS = re.compile(r"[*_#`>~]")


def limpar_para_voz(texto: str) -> str:
    """O TTS lê tudo em voz alta. Em 17/10 o modelo escreveu «[A usar tool pesquisar_imoveis com: ...]»
    (imita ferramentas que a voz não tem): sai do texto antes de falar, e do histórico."""
    texto = _SIMBOLOS.sub("", _ENTRE_RETOS.sub(" ", texto))
    return re.sub(r"\s+", " ", texto).strip()


async def get_response(session: CallSession, user_text: str) -> str:
    if not session.system_prompt:
        # `load_config` é a versão partilhada: já não descarta `instrucoes`
        # quando a persona está vazia, e já não rebenta se a linha faltar.
        extra, _ativo = await load_config("voz")
        session.system_prompt = _SYSTEM_BASE + instrucao_telefone(session.numero_origem) + extra

    session.historico.append({"role": "user", "content": user_text})

    resp = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=session.system_prompt,
        messages=session.historico,
    )

    bruto = resp.content[0].text if resp.content else ""
    if FIM_CHAMADA in bruto:  # antes da limpeza: `_` é símbolo e sairia da marca
        session.terminar = True
        bruto = bruto.replace(FIM_CHAMADA, "")
    response_text = limpar_para_voz(bruto)
    response_text = response_text or "Desculpe, não percebi bem. Pode repetir, por favor?"
    session.historico.append({"role": "assistant", "content": response_text})
    return response_text
