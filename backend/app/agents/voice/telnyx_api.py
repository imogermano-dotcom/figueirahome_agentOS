import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.telnyx.com/v2"
_VOICE = "Polly.Ines-Neural"
_LANG = "pt-PT"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.telnyx_api_key}",
        "Content-Type": "application/json",
    }


async def answer(call_control_id: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE}/calls/{call_control_id}/actions/answer",
            headers=_headers(),
            json={},
        )
        if r.status_code >= 400:
            logger.error("Telnyx answer failed: %s %s", r.status_code, r.text)


async def speak(call_control_id: str, text: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE}/calls/{call_control_id}/actions/speak",
            headers=_headers(),
            json={"payload": text, "voice": _VOICE, "language": _LANG},
        )
        if r.status_code >= 400:
            logger.error("Telnyx speak failed: %s %s", r.status_code, r.text)


async def stream_start(call_control_id: str) -> None:
    ws_url = (
        settings.app_base_url.replace("https://", "wss://").replace("http://", "ws://")
        + f"/ws/audio/{call_control_id}"
    )
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE}/calls/{call_control_id}/actions/streaming_start",
            headers=_headers(),
            json={"stream_url": ws_url, "stream_track": "inbound_track"},
        )
        if r.status_code >= 400:
            logger.error("Telnyx stream_start failed: %s %s", r.status_code, r.text)


async def hangup(call_control_id: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE}/calls/{call_control_id}/actions/hangup",
            headers=_headers(),
            json={},
        )
        if r.status_code >= 400:
            logger.error("Telnyx hangup failed: %s %s", r.status_code, r.text)
