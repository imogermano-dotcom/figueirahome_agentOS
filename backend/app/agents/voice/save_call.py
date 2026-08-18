import asyncio
import json
import logging

from anthropic import AsyncAnthropic

from app.agents.broker.guards import find_or_create_cliente
from app.agents.voice.session import CallSession
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_EXTRACT_TOOLS = [
    {
        "name": "guardar_dados_chamada",
        "description": "Extrai e guarda os dados recolhidos durante a chamada.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do cliente"},
                "telefone": {"type": "string", "description": "Telefone de contacto"},
                "tipo_interesse": {
                    "type": "string",
                    "enum": ["compra", "arrendamento", "venda", "outro"],
                },
                "orcamento": {"type": "number", "description": "Orçamento em euros"},
                "zona_preferida": {"type": "string"},
                "resumo": {"type": "string", "description": "Resumo da chamada em 2-3 frases"},
            },
            "required": ["resumo"],
        },
    }
]


async def _extract_data(transcricao: str) -> dict:
    resp = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system="Analisa a transcrição de uma chamada telefónica de uma agência imobiliária e extrai os dados do cliente.",
        messages=[
            {
                "role": "user",
                "content": f"Transcrição:\n{transcricao}\n\nExtrai os dados e gera um resumo.",
            }
        ],
        tools=_EXTRACT_TOOLS,
        tool_choice={"type": "any"},
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "guardar_dados_chamada":
            return block.input
    return {"resumo": "Chamada sem dados suficientes para extrair."}


def _supabase_insert_chamada(supabase, session: CallSession, cliente_id: str | None, dados: dict) -> None:
    duracao = int((session.iniciada_em.utcnow() - session.iniciada_em).total_seconds())
    supabase.table("agente_chamadas").insert(
        {
            "cliente_id": cliente_id,
            "numero_origem": session.numero_origem,
            "duracao": max(duracao, 0),
            "transcricao": session.transcricao_acumulada,
            "resumo_ia": dados.get("resumo"),
        }
    ).execute()


def _supabase_insert_lead(supabase, cliente_id: str, dados: dict) -> None:
    """Escreve em `leads` desde 2026-08-18 — `agente_leads` deixou de ser usada
    (ver `api/leads.py`). `origem='voz'` distingue estas das do WhatsApp e das da
    Meta na página de Leads."""
    if not cliente_id:
        return
    supabase.table("leads").insert(
        {
            "cliente_id": cliente_id,
            "estado": "nova",
            "origem": "voz",
            "notas": dados.get("resumo"),
        }
    ).execute()


async def save_call(session: CallSession) -> None:
    if not session.transcricao_acumulada.strip():
        logger.info("Chamada %s sem transcrição — skip save.", session.call_control_id)
        return

    try:
        dados = await _extract_data(session.transcricao_acumulada)
    except Exception:
        logger.exception("Erro ao extrair dados da chamada %s", session.call_control_id)
        dados = {"resumo": "Erro na extracção de dados."}

    # Dedup partilhado com os assistentes (spec §2.7): antes havia aqui uma
    # cópia artesanal do mesmo upsert por telefone, que não normalizava
    # formatos e por isso duplicava clientes já conhecidos do WhatsApp.
    cliente = await find_or_create_cliente(
        nome=dados.get("nome"),
        telefone=dados.get("telefone") or session.numero_origem,
        tipo_interesse=dados.get("tipo_interesse"),
        orcamento=dados.get("orcamento"),
        zona_preferida=dados.get("zona_preferida"),
        origem="chamada",
    )
    cliente_id = cliente["id"] if cliente else None

    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _save():
        _supabase_insert_chamada(supabase, session, cliente_id, dados)
        if cliente_id and dados.get("tipo_interesse"):
            _supabase_insert_lead(supabase, cliente_id, dados)

    await loop.run_in_executor(None, _save)
    logger.info("Chamada %s guardada no Supabase.", session.call_control_id)
