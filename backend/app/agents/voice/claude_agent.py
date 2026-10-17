import logging
import re

from anthropic import AsyncAnthropic

from app.agents.broker.assistants import load_config
from app.agents.voice.session import CallSession
from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_SYSTEM_BASE = """És a assistente de voz da agência imobiliária Figueirahome, em Portugal.
Falas sempre em Português de Portugal, de forma natural e cordial.
O teu objectivo é recolher os seguintes dados do cliente:
  - Nome completo
  - Número de telefone de contacto
  - Tipo de interesse: compra, arrendamento, venda ou outro
  - Orçamento (em euros)
  - Zona ou localização preferida

A chamada começa sempre com a saudação «Olá! Obrigada por contactar a Figueirahome. Em que posso ajudá-lo?»,
que já foi dita antes da primeira resposta tua: nunca voltes a cumprimentar nem a dizer «bem-vindo».

Instruções:
- Responde numa única frase curta (no máximo 25 palavras): é uma chamada, a pessoa não pode reler.
- Faz perguntas de forma natural, uma de cada vez.
- Não termines a chamada sem teres pelo menos o nome, o telefone e o tipo de interesse.
- Quando tiveres todos os dados, lê-os em voz alta para confirmar e despede-te de forma cordial.
- Nunca uses markdown, listas ou símbolos — só texto simples.
- Não tens ferramentas nem acesso a imóveis nesta chamada: nunca escrevas texto entre parênteses retos, nunca
  digas que vais «pesquisar» nem inventes resultados. Recolhe os dados e diz que um consultor entrará em contacto.
"""


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
        session.system_prompt = _SYSTEM_BASE + extra

    session.historico.append({"role": "user", "content": user_text})

    resp = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=session.system_prompt,
        messages=session.historico,
    )

    response_text = limpar_para_voz(resp.content[0].text) if resp.content else ""
    response_text = response_text or "Desculpe, não percebi bem. Pode repetir, por favor?"
    session.historico.append({"role": "assistant", "content": response_text})
    return response_text
