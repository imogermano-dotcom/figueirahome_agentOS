import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_CONVERSATION_TTL_HOURS = 48


async def load_conversation(canal: str, participante: str) -> tuple[str | None, list[dict]]:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _fetch():
        return (
            supabase.table("agente_conversas")
            .select("id,mensagens,atualizado_em")
            .eq("canal", canal)
            .eq("participante", participante)
            .order("criado_em", desc=True)
            .limit(1)
            .execute()
        )

    resp = await loop.run_in_executor(None, _fetch)
    if resp.data:
        row = resp.data[0]
        atualizado_em = row.get("atualizado_em")
        if atualizado_em:
            ultima = datetime.fromisoformat(atualizado_em.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - ultima > timedelta(hours=_CONVERSATION_TTL_HOURS):
                logger.info("Conversa %s expirada (>%dh) — nova thread", row["id"], _CONVERSATION_TTL_HOURS)
                return None, []
        mensagens = row.get("mensagens") or []
        return row["id"], mensagens
    return None, []


async def save_conversation(
    conversa_id: str | None,
    canal: str,
    participante: str,
    mensagens: list[dict],
) -> str:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()
    now = datetime.now(timezone.utc).isoformat()

    def _upsert():
        if conversa_id:
            result = (
                supabase.table("agente_conversas")
                .update({"mensagens": mensagens, "atualizado_em": now})
                .eq("id", conversa_id)
                .execute()
            )
            return conversa_id
        else:
            result = (
                supabase.table("agente_conversas")
                .insert(
                    {
                        "canal": canal,
                        "participante": participante,
                        "mensagens": mensagens,
                        "criado_em": now,
                        "atualizado_em": now,
                    }
                )
                .execute()
            )
            return result.data[0]["id"] if result.data else None

    return await loop.run_in_executor(None, _upsert)
