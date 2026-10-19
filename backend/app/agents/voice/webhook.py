import base64
import json
import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, HTTPException, Request

from app.agents.voice import session as session_mgr
from app.agents.voice import telnyx_api
from app.agents.voice.claude_agent import SAUDACAO
from app.agents.voice.save_call import save_call
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()



_TOLERANCIA_S = 300  # a Telnyx reenvia em segundos; 5 min chega e corta o replay


def assinatura_valida(body: bytes, assinatura: str, timestamp: str, chave_publica: str, agora: float | None = None) -> bool:
    """Ed25519 da Telnyx: a assinatura cobre `timestamp|corpo`; chave pública e assinatura vão em base64.

    Verificada aqui e não com a lib `telnyx`: na 4.x `telnyx.Webhook` deixou de existir e a `webhooks.unwrap`
    espera os cabeçalhos do Standard Webhooks, não `telnyx-signature-ed25519`. O `except Exception` antigo
    transformou esse AttributeError em 403 em todos os pedidos (17/10) e a chamada ficava a tocar.
    Chave vazia ou mal formada = inválida: um segredo em falta nunca deixa passar.
    """
    try:
        if abs((agora if agora is not None else time.time()) - int(timestamp)) > _TOLERANCIA_S:
            return False
        Ed25519PublicKey.from_public_bytes(base64.b64decode(chave_publica.strip())).verify(
            base64.b64decode(assinatura), timestamp.encode() + b"|" + body
        )
        return True
    except (InvalidSignature, ValueError, TypeError):  # binascii.Error é ValueError
        return False


@router.post("/webhook/telnyx")
async def telnyx_webhook(request: Request):
    body = await request.body()

    if settings.environment == "production" and not assinatura_valida(
        body,
        request.headers.get("telnyx-signature-ed25519", ""),
        request.headers.get("telnyx-timestamp", ""),
        settings.telnyx_public_key,
    ):
        logger.warning("Telnyx webhook recusado: assinatura inválida (chave configurada: %s)", bool(settings.telnyx_public_key))
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
        session = session_mgr.get_session(call_control_id)
        if session:
            session.is_speaking = True  # até ao `call.speak.ended`
        await telnyx_api.speak(call_control_id, SAUDACAO)

    elif event_type == "call.speak.ended":
        session = session_mgr.get_session(call_control_id)
        if session:
            session.is_speaking = False
            if session.terminar:
                await telnyx_api.hangup(call_control_id)

    elif event_type == "call.hangup":
        session = session_mgr.remove_session(call_control_id)
        if session:
            await save_call(session)

    return {"result": "ok"}
