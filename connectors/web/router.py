from fastapi import APIRouter
from pydantic import BaseModel

from connectors.discord import normalizer as discord_normalizer
from connectors.telegram import normalizer as telegram_normalizer
from connectors.web import normalizer as web_normalizer
from core.agent import process_message

router = APIRouter()


class ChatRequest(BaseModel):
    telegram_chat_id: str
    message: str
    customer_name: str | None = None
    # "telegram" is the historical default: this endpoint was originally built
    # for the n8n Telegram workflow, which still doesn't always send this field.
    channel: str = "telegram"
    # Upstream event id (e.g. Telegram's update_id) for webhook-retry
    # idempotency. Optional — channels that don't have at-least-once
    # redelivery semantics (web, discord) can omit it.
    event_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    escalated: bool
    cache_hit: bool
    sentiment_label: str
    sentiment_score: float
    conversation_id: str = ""


NORMALIZERS = {
    "web": web_normalizer.to_incoming_message,
    "telegram": telegram_normalizer.to_incoming_message,
    "discord": discord_normalizer.to_incoming_message,
}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Channel-agnostic chat ingress. Used directly by the web frontend, and as
    the relay target for the n8n Telegram workflow (Workflow A) and the
    Discord bot — each of which normalizes its own platform payload into this
    same shape before calling here, and is normalized again into an
    IncomingMessage below.
    """
    normalize = NORMALIZERS.get(request.channel, telegram_normalizer.to_incoming_message)
    inbound = normalize(request)
    reply = await process_message(inbound)

    return ChatResponse(
        answer=reply.answer,
        escalated=reply.escalated,
        cache_hit=reply.cache_hit,
        sentiment_label=reply.sentiment_label,
        sentiment_score=reply.sentiment_score,
        conversation_id=reply.conversation_id,
    )
