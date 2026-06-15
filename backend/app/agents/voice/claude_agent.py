import asyncio
import logging

from anthropic import AsyncAnthropic

from app.agents.voice.session import CallSession
from app.config import settings
from app.db.supabase_client import get_supabase

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

Instruções:
- Faz perguntas de forma natural, uma de cada vez.
- Não termines a chamada sem teres pelo menos o nome, o telefone e o tipo de interesse.
- Quando tiveres todos os dados, lê-os em voz alta para confirmar e despede-te de forma cordial.
- As tuas respostas devem ser curtas (máximo 2 frases), adequadas para voz.
- Nunca uses markdown, listas ou símbolos — só texto simples.
"""


async def _load_config() -> str:
    loop = asyncio.get_event_loop()
    supabase = get_supabase()

    def _fetch():
        return (
            supabase.table("agente_config")
            .select("persona,instrucoes")
            .eq("agente", "voz")
            .single()
            .execute()
        )

    resp = await loop.run_in_executor(None, _fetch)
    data = resp.data or {}
    persona = data.get("persona", "")
    instrucoes = data.get("instrucoes", "")
    extra = f"\nPersona: {persona}\n{instrucoes}" if persona else ""
    return _SYSTEM_BASE + extra


async def get_response(session: CallSession, user_text: str) -> str:
    if not session.system_prompt:
        session.system_prompt = await _load_config()

    session.historico.append({"role": "user", "content": user_text})

    resp = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=session.system_prompt,
        messages=session.historico,
    )

    response_text = resp.content[0].text if resp.content else "Desculpe, ocorreu um erro."
    session.historico.append({"role": "assistant", "content": response_text})
    return response_text
