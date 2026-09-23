import os

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from connectors.whatsapp.client import send_whatsapp_message
from connectors.whatsapp.normalizer import to_inbound_message
from core.agent import process_message

router = APIRouter()


@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta calls this once to verify your webhook.
    Must return the challenge string or Meta won't connect."""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if mode == "subscribe" and token == verify_token:
        logger.info("WhatsApp webhook verified")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """Meta sends all incoming WhatsApp messages here. Runs them through the
    same core agent pipeline as every other channel and replies via the
    WhatsApp Cloud API."""
    body = await request.json()
    try:
        inbound = to_inbound_message(body)
        if inbound is None:
            return {"status": "ignored"}

        logger.info(f"Received WhatsApp from {inbound.external_id}: {inbound.text[:50]}...")

        reply = await process_message(inbound)
        await send_whatsapp_message(inbound.external_id, reply.answer)
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
