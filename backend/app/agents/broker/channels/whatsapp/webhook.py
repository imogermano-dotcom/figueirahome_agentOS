import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from app.agents.broker.channels.whatsapp.meta_api import mark_as_read, send_text_message
from app.agents.voice.whatsapp_intake import get_response
from app.config import settings

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
            messages = value.get("messages", [])
            for msg in messages:
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


async def _handle_message(from_number: str, message_id: str, text: str) -> None:
    try:
        await mark_as_read(message_id)
        response = await get_response(from_number=from_number, mensagem_user=text)
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
