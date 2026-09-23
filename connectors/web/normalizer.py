from connectors.base import InboundMessage


def to_inbound_message(request) -> InboundMessage:
    """Normalizes a browser-originated ChatRequest into an InboundMessage."""
    return InboundMessage(
        channel="web",
        external_id=request.telegram_chat_id,
        text=request.message,
        customer_name=request.customer_name,
    )
