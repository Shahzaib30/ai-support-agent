from connectors.base import IncomingMessage


def to_incoming_message(request) -> IncomingMessage:
    """
    Normalizes a Telegram-originated ChatRequest into an IncomingMessage.

    Telegram messages reach this API via the n8n Telegram workflow (Workflow
    A), which relays each update as a ChatRequest (telegram_chat_id/message/
    customer_name, plus Telegram's own update_id as event_id for idempotency)
    rather than the API terminating a Telegram webhook directly.
    """
    metadata = {"event_id": request.event_id} if request.event_id else {}
    return IncomingMessage(
        channel="telegram",
        customer_id=request.telegram_chat_id,
        message=request.message,
        customer_name=request.customer_name,
        metadata=metadata,
    )
