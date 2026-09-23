from connectors.base import IncomingMessage


def to_incoming_message(request) -> IncomingMessage:
    """
    Normalizes a Discord-originated ChatRequest into an IncomingMessage.

    The Discord bot (connectors/discord/bot.py) runs as its own process,
    already normalizes each discord.Message into this same ChatRequest shape
    (customer_id prefixed with "discord_"), and posts it to this API. Discord
    delivers over a persistent gateway connection (not at-least-once webhook
    retries), so no event_id/idempotency handling is needed here.
    """
    return IncomingMessage(
        channel="discord",
        customer_id=request.telegram_chat_id,
        message=request.message,
        customer_name=request.customer_name,
    )
