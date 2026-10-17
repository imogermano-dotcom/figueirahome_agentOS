import base64
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.voice import session as session_mgr
from app.agents.voice import telnyx_api
from app.agents.voice.claude_agent import get_response
from app.agents.voice.stt import transcribe
from app.agents.voice.vad import DetetorDeFrase

logger = logging.getLogger(__name__)
router = APIRouter()

_STT_RETRY_MSG = "Desculpe, não percebi. Pode repetir, por favor?"


@router.websocket("/ws/audio/{call_control_id}")
async def audio_websocket(websocket: WebSocket, call_control_id: str):
    await websocket.accept()
    session = session_mgr.get_session(call_control_id)
    detetor = DetetorDeFrase()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                if session is None or session.is_speaking:
                    detetor.reset()  # o que a assistente diz (ou o eco) nunca é uma frase da pessoa
                    continue

                frase = detetor.feed(base64.b64decode(msg["media"]["payload"]))
                if frase:
                    await _process_turn(session, call_control_id, frase)

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Erro no WebSocket da chamada %s", call_control_id)


async def _process_turn(session, call_control_id: str, audio_bytes: bytes) -> None:
    """Uma frase completa (o detetor já esperou pelo silêncio). Texto vazio = fala que o STT não percebeu."""
    t0 = time.monotonic()
    text = await transcribe(audio_bytes)
    logger.info("[%s] frase de %.1fs → STT (%.1fs): %r", call_control_id[-6:], len(audio_bytes) / 8000,
                time.monotonic() - t0, text)

    if not text or len(text.strip()) < 3:
        session.stt_fail_count += 1
        if session.stt_fail_count >= 2:
            session.stt_fail_count = 0
            session.is_speaking = True
            await telnyx_api.speak(call_control_id, _STT_RETRY_MSG)
        return

    session.stt_fail_count = 0
    session.transcricao_acumulada += f"\nCliente: {text}"

    t1 = time.monotonic()
    response_text = await get_response(session, text)
    session.transcricao_acumulada += f"\nAgente: {response_text}"
    logger.info("[%s] Claude (%.1fs): %r", call_control_id[-6:], time.monotonic() - t1, response_text)

    session.is_speaking = True
    await telnyx_api.speak(call_control_id, response_text)
