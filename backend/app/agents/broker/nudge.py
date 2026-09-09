"""Lembrete dentro da janela de 24h — quando a Matilde fica sem resposta a
meio de uma conversa activa e ninguém mais toca no assunto.

Frente A de `docs/fases/matilde-followup-plano.md`. Distinto do follow-up por
template (n8n `01`/`02`/`03`): aqui a lead já respondeu pelo menos uma vez, a
conversa está viva, e o que falta é um empurrão de texto livre — por isso a
restrição real não é a nossa TTL de 48h (`conversation.py`), é a janela de
mensagem livre da Cloud API, 24h desde a última mensagem da pessoa. Disparar
perto desse limite arrisca a Meta rejeitar; a janela de disparo fica bem
dentro dela.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.agents.broker import guards
from app.agents.broker.channels.whatsapp import meta_api
from app.agents.broker.conversation import save_conversation
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_JANELA_MIN_HORAS = 6
_JANELA_MAX_HORAS = 20  # margem de segurança antes das 24h da Cloud API

TEXTO_NUDGE = (
    "Ainda está interessado? Fico a postos para continuar, ou diga-me só que "
    "não para eu não voltar a incomodar."
)

# Marcadores da despedida da própria Matilde — voz nossa, controlada, por
# isso mais fiável do que adivinhar o tom de quem escreve. Substring, não
# prefixo: aparecem a meio da frase ("Cuide-se, Maria. Até quando precisar!").
_MARCAS_FECHO = ("👋", "cuide-se", "boa continuação", "muita força", "boa sorte")


def _e_despedida(texto: str) -> bool:
    texto = (texto or "").lower()
    return any(marca in texto for marca in _MARCAS_FECHO)


async def _candidatos() -> list[dict]:
    agora = datetime.now(timezone.utc)
    desde = (agora - timedelta(hours=_JANELA_MAX_HORAS)).isoformat()
    ate = (agora - timedelta(hours=_JANELA_MIN_HORAS)).isoformat()

    def _fetch():
        return (
            get_supabase()
            .table("agente_conversas")
            .select("id,participante,mensagens")
            .eq("agente", "a1_vendedor")
            .eq("canal", "whatsapp")
            .is_("nudge_em", "null")
            .gte("atualizado_em", desde)
            .lte("atualizado_em", ate)
            .execute()
        )

    resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)

    candidatos = []
    for row in resp.data:
        mensagens = row.get("mensagens") or []
        if not mensagens:
            continue
        ultima = mensagens[-1]
        if ultima.get("role") != "assistant":
            continue
        if _e_despedida(ultima.get("content", "")):
            continue
        lead = await guards.lead_aberta(row["participante"])
        if not lead or lead.get("contacto_humano_em"):
            continue
        candidatos.append(row)
    return candidatos


async def enviar_nudges() -> dict:
    candidatos = await _candidatos()
    enviados = 0
    erros = 0
    detalhes: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in candidatos:
        try:
            await meta_api.send_text_message(row["participante"], TEXTO_NUDGE)
            mensagens = [*row["mensagens"], {"role": "assistant", "timestamp": now, "content": TEXTO_NUDGE}]
            await save_conversation(row["id"], "whatsapp", row["participante"], mensagens, "a1_vendedor")

            def _marcar(conversa_id=row["id"]):
                get_supabase().table("agente_conversas").update({"nudge_em": now}).eq("id", conversa_id).execute()

            await asyncio.get_event_loop().run_in_executor(None, _marcar)
            enviados += 1
            detalhes.append({"conversa_id": row["id"], "participante": row["participante"], "tipo": "enviado"})
        except Exception:
            logger.exception("Falha a enviar nudge para a conversa %s", row["id"])
            erros += 1
            detalhes.append({"conversa_id": row["id"], "tipo": "erro"})

    resumo = {"candidatos": len(candidatos), "enviados": enviados, "erros": erros}

    def _log():
        return get_supabase().table("agente_sync_log").insert({
            "tipo": "nudge_matilde", "resumo": resumo, "detalhes": detalhes, "origem": "cron",
        }).execute()

    try:
        await asyncio.get_event_loop().run_in_executor(None, _log)
    except Exception:
        logger.exception("Falha a gravar o log do nudge — o envio em si correu.")

    return resumo


def demo() -> None:
    assert _e_despedida("Cuide-se, Maria. Até quando precisar! 👋")
    assert _e_despedida("Boa continuação, João! 😊")
    assert not _e_despedida("Antes de lhe dar o preço, só duas perguntas rápidas:")
    print("nudge.demo: ok")


if __name__ == "__main__":
    demo()
