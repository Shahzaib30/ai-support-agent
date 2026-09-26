import os
import httpx
from loguru import logger


async def send_whatsapp_message(to: str, message: str) -> None:
    """Send a text message back to a customer via the WhatsApp Cloud API."""
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_number_id:
        logger.warning("WhatsApp API not configured")
        return

    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            logger.info(f"WhatsApp message sent to {to}: {message[:50]}...")
        except Exception as e:
            logger.error(f"WhatsApp message failed: {e}")
