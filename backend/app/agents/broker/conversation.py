import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.agents.broker.guards import normalizar_telefone, variantes_telefone
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_CONVERSATION_TTL_HOURS = 48


def _participantes(canal: str, participante: str) -> list[str]:
    """Formatos sob os quais a mesma thread pode estar gravada.

    No WhatsApp o mesmo número aparece de várias formas: a Meta entrega
    `351912345678` no webhook, mas uma conversa semeada por nós (lead da Meta,
    `api/leads_meta.py`) guarda o número já normalizado. Um `.eq()` exacto não
    encontrava a thread semeada e a lead caía no A2 — que é precisamente o que a
    semeadura existe para evitar. `engine._perfil_cliente` já procura por
    variantes em `agente_clientes` pela mesma razão.
    """
    if canal != "whatsapp":
        return [participante]
    numero = normalizar_telefone(participante)
    if not numero:
        return [participante]
    return list(dict.fromkeys([participante, *variantes_telefone(numero)]))


async def load_conversation(
    canal: str, participante: str
) -> tuple[str | None, list[dict], str | None]:
    """Devolve `(conversa_id, mensagens, agente)` da thread activa.

    O `agente` sustenta o routing sticky: uma vez decidido quem responde, a
    thread fica com esse assistente em vez de ser re-classificada a cada
    mensagem. `None` significa thread nova ou linha anterior à migration 0014
    — nos dois casos o router decide.
    """
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _fetch():
        return (
            supabase.table("agente_conversas")
            .select("id,mensagens,atualizado_em,agente")
            .eq("canal", canal)
            .in_("participante", _participantes(canal, participante))
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
                return None, [], None
        mensagens = row.get("mensagens") or []
        return row["id"], mensagens, row.get("agente")
    return None, [], None


async def save_conversation(
    conversa_id: str | None,
    canal: str,
    participante: str,
    mensagens: list[dict],
    agente: str | None = None,
) -> str:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()
    now = datetime.now(timezone.utc).isoformat()

    def _upsert():
        if conversa_id:
            dados = {"mensagens": mensagens, "atualizado_em": now}
            if agente:
                dados["agente"] = agente
            result = (
                supabase.table("agente_conversas")
                .update(dados)
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
                        "agente": agente,
                        "mensagens": mensagens,
                        "criado_em": now,
                        "atualizado_em": now,
                    }
                )
                .execute()
            )
            return result.data[0]["id"] if result.data else None

    return await loop.run_in_executor(None, _upsert)
