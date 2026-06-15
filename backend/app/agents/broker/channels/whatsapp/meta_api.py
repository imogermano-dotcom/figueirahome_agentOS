import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4000


async def send_text_message(to: str, text: str) -> None:
    url = f"https://graph.facebook.com/{settings.meta_api_version}/{settings.meta_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.meta_whatsapp_token}",
        "Content-Type": "application/json",
    }

    # Split long messages
    chunks = [text[i:i + _MAX_MESSAGE_LENGTH] for i in range(0, len(text), _MAX_MESSAGE_LENGTH)]

    async with httpx.AsyncClient(timeout=15.0) as client:
        for chunk in chunks:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": chunk},
            }
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code not in (200, 201):
                logger.error("Meta API erro %s: %s", resp.status_code, resp.text)
            else:
                logger.debug("Mensagem enviada para %s", to)


async def mark_as_read(message_id: str) -> None:
    url = f"https://graph.facebook.com/{settings.meta_api_version}/{settings.meta_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.meta_whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            logger.debug("mark_as_read falhou para %s: %s", message_id, resp.status_code)
