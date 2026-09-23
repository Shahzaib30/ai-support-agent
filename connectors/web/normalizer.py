from connectors.base import IncomingMessage


def to_incoming_message(request) -> IncomingMessage:
    """Normalizes a browser-originated ChatRequest into an IncomingMessage."""
    metadata = {"event_id": request.event_id} if request.event_id else {}
    return IncomingMessage(
        channel="web",
        customer_id=request.telegram_chat_id,
        message=request.message,
        customer_name=request.customer_name,
        metadata=metadata,
    )
