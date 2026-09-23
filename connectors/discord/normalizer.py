from connectors.base import InboundMessage


def to_inbound_message(request) -> InboundMessage:
    """
    Normalizes a Discord-originated ChatRequest into an InboundMessage.

    The Discord bot (connectors/discord/bot.py) runs as its own process,
    already normalizes each discord.Message into this same ChatRequest shape
    (external_id prefixed with "discord_"), and posts it to this API.
    """
    return InboundMessage(
        channel="discord",
        external_id=request.telegram_chat_id,
        text=request.message,
        customer_name=request.customer_name,
    )
