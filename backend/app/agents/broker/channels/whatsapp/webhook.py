import asyncio
import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from app.agents.broker.channels.whatsapp.meta_api import mark_as_read, send_text_message
from app.agents.broker.engine import responder
from app.agents.broker.guards import agente_de_lead
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("WhatsApp webhook verificado.")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Token de verificação inválido.")


def _registar_estado(estado: dict) -> None:
    """Recibo de entrega da Meta: `sent` → `delivered` → `read`, ou `failed`.

    Só log, de propósito: sem tabela nova, sem migration. O que faltava era
    conseguir ver, não conseguir consultar histórico. Se um dia isto tiver de
    responder a "quantas falharam esta semana", aí sim vale uma tabela.
    """
    qual = estado.get("status")
    destino = estado.get("recipient_id")
    if qual == "failed":
        erro = (estado.get("errors") or [{}])[0]
        logger.error(
            "WhatsApp NAO ENTREGUE a %s — codigo %s: %s | %s",
            destino,
            erro.get("code"),
            erro.get("title") or erro.get("message"),
            (erro.get("error_data") or {}).get("details"),
        )
    else:
        logger.info("WhatsApp %s -> %s", qual, destino)


@router.post("/webhook/whatsapp")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body_bytes = await request.body()

    # Verificar assinatura X-Hub-Signature-256 (Meta usa o App Secret, não o token)
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if settings.environment == "production":
        expected = "sha256=" + hmac.new(
            settings.meta_app_secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature_header, expected):
            raise HTTPException(status_code=403, detail="Assinatura inválida.")

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    # Extrair mensagem
    entry = payload.get("entry", [])
    if not entry:
        return {"status": "ok"}

    for e in entry:
        for change in e.get("changes", []):
            value = change.get("value", {})

            # A Meta manda os recibos de entrega aqui, NÃO em `messages`. Foram
            # ignorados até 2026-08-29, e isso deixou-nos cegos: a 29/08 uma
            # mensagem de teste teve `200 accepted` da Graph API e nunca chegou
            # ao telefone. `accepted` quer dizer "aceite para envio", não
            # "entregue" — a diferença entre as duas só aparece aqui.
            for estado in value.get("statuses", []):
                _registar_estado(estado)

            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    # Ignorar imagens, áudio, etc.
                    continue
                from_number = msg.get("from")
                message_id = msg.get("id")
                text_body = msg.get("text", {}).get("body", "")

                if from_number and text_body:
                    background_tasks.add_task(
                        _handle_message, from_number, message_id, text_body
                    )

    return {"status": "ok"}


def _ja_processada(message_id: str) -> bool:
    """`INSERT ... ON CONFLICT DO NOTHING`, não "ler depois escrever": entre as
    duas há uma janela onde duas reentregas quase simultâneas passam ambas. A
    UNIQUE em `message_id` torna a verificação atómica.

    A Meta garante "at least once" e reenvia o mesmo webhook em falhas
    transitórias — sem isto, a reentrega reprocessa a mensagem do zero e
    duplica o que as tools escrevem (achado em produção: visitas e leads
    qualificadas duplicadas, sempre 30-65s de diferença entre cópias).
    """
    if not message_id:
        return False
    try:
        resp = (
            get_supabase().table("agente_mensagens_processadas")
            .upsert({"message_id": message_id}, on_conflict="message_id", ignore_duplicates=True)
            .execute()
        )
        return not resp.data
    except Exception:
        logger.exception("Falha a verificar dedupe de %s — a processar na mesma.", message_id)
        return False


async def _handle_message(from_number: str, message_id: str, text: str) -> None:
    if await asyncio.get_event_loop().run_in_executor(None, _ja_processada, message_id):
        logger.info("Mensagem %s já processada — reentrega da Meta, a ignorar.", message_id)
        return
    try:
        await mark_as_read(message_id)
        # Normalmente sem `agente=`: o router decide e a escolha fica colada à
        # thread. A excepção são as leads da Meta — a resposta a um template é
        # "Sim" ou "Olá", que `router._A1_RE` não reconhece, e a thread semeada
        # já pode ter expirado (48h). Aí força-se o A1, que é quem as segue.
        agente = await agente_de_lead(from_number)
        response = await responder(
            canal="whatsapp", participante=from_number, mensagem=text, agente=agente
        )
        await send_text_message(from_number, response)
    except Exception:
        logger.exception("Erro ao processar mensagem WhatsApp de %s", from_number)
        try:
            await send_text_message(
                from_number,
                "Ocorreu um erro interno. Por favor tenta novamente mais tarde.",
            )
        except Exception:
            pass
