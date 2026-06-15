import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.voice import session as session_mgr
from app.agents.voice import telnyx_api
from app.agents.voice.claude_agent import get_response
from app.agents.voice.stt import transcribe

logger = logging.getLogger(__name__)
router = APIRouter()

# Telnyx sends ~50 chunks/second (20ms each).
# Accumulate 2 seconds before processing.
_CHUNKS_PER_BATCH = 100
_MIN_CHUNKS = 20  # ~400ms minimum to attempt STT
_STT_RETRY_MSG = "Desculpe, não percebi. Pode repetir, por favor?"


@router.websocket("/ws/audio/{call_control_id}")
async def audio_websocket(websocket: WebSocket, call_control_id: str):
    await websocket.accept()
    session = session_mgr.get_session(call_control_id)
    chunk_count = 0

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                if session is None or session.is_speaking:
                    continue

                payload = msg["media"]["payload"]
                session.audio_buffer.extend(base64.b64decode(payload))
                chunk_count += 1

                if chunk_count >= _CHUNKS_PER_BATCH:
                    await _process_turn(session, call_control_id)
                    chunk_count = 0

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Erro no WebSocket da chamada %s", call_control_id)


async def _process_turn(session, call_control_id: str) -> None:
    if len(session.audio_buffer) < _MIN_CHUNKS * 160:
        session.audio_buffer.clear()
        return

    audio_bytes = bytes(session.audio_buffer)
    session.audio_buffer.clear()

    text = await transcribe(audio_bytes)

    if not text or len(text.strip()) < 3:
        session.stt_fail_count += 1
        if session.stt_fail_count >= 2:
            session.stt_fail_count = 0
            session.is_speaking = True
            await telnyx_api.speak(call_control_id, _STT_RETRY_MSG)
        return

    session.stt_fail_count = 0
    session.transcricao_acumulada += f"\nCliente: {text}"
    logger.info("[%s] STT: %s", call_control_id, text)

    response_text = await get_response(session, text)
    session.transcricao_acumulada += f"\nAgente: {response_text}"
    logger.info("[%s] Claude: %s", call_control_id, response_text)

    session.is_speaking = True
    await telnyx_api.speak(call_control_id, response_text)
