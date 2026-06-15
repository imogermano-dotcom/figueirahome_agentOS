import json
import logging

import telnyx
from fastapi import APIRouter, HTTPException, Request

from app.agents.voice import session as session_mgr
from app.agents.voice import telnyx_api
from app.agents.voice.save_call import save_call
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_SAUDACAO = (
    "Olá! Obrigada por contactar a Figueirahome. "
    "Em que posso ajudá-lo?"
)


@router.post("/webhook/telnyx")
async def telnyx_webhook(request: Request):
    body = await request.body()

    if settings.environment == "production" and settings.telnyx_public_key:
        sig = request.headers.get("telnyx-signature-ed25519", "")
        timestamp = request.headers.get("telnyx-timestamp", "")
        try:
            telnyx.public_key = settings.telnyx_public_key
            telnyx.Webhook.construct_event(body, sig, timestamp)
        except Exception:
            raise HTTPException(status_code=403, detail="Assinatura inválida")

    payload = json.loads(body)
    data = payload.get("data", {})
    event_type = data.get("event_type", "")
    call_data = data.get("payload", {})
    call_control_id = call_data.get("call_control_id", "")

    logger.info("Telnyx event: %s | call_control_id: %s", event_type, call_control_id)

    if event_type == "call.initiated":
        if call_data.get("direction") == "incoming":
            numero_origem = call_data.get("from", "desconhecido")
            session_mgr.create_session(call_control_id, numero_origem)
            await telnyx_api.answer(call_control_id)

    elif event_type == "call.answered":
        await telnyx_api.stream_start(call_control_id)
        await telnyx_api.speak(call_control_id, _SAUDACAO)

    elif event_type == "call.speak.ended":
        session = session_mgr.get_session(call_control_id)
        if session:
            session.is_speaking = False

    elif event_type == "call.hangup":
        session = session_mgr.remove_session(call_control_id)
        if session:
            await save_call(session)

    return {"result": "ok"}
