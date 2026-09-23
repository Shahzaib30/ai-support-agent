from connectors.base import InboundMessage


def to_inbound_message(request) -> InboundMessage:
    """
    Normalizes a Telegram-originated ChatRequest into an InboundMessage.

    Telegram messages reach this API via the n8n Telegram workflow, which
    relays each update as a ChatRequest (telegram_chat_id/message/customer_name)
    rather than the API terminating a Telegram webhook directly.
    """
    return InboundMessage(
        channel="telegram",
        external_id=request.telegram_chat_id,
        text=request.message,
        customer_name=request.customer_name,
    )
