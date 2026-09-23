from connectors.base import IncomingMessage
from connectors.discord.normalizer import to_incoming_message
from connectors.web.router import ChatRequest


def test_discord_chat_request_normalizes_to_incoming_message():
    request = ChatRequest(
        telegram_chat_id="discord_123456789",
        message="Is there a student discount?",
        customer_name="pixelwolf",
        channel="discord",
    )

    result = to_incoming_message(request)

    assert isinstance(result, IncomingMessage)
    assert result.channel == "discord"
    assert result.customer_id == "discord_123456789"
    assert result.message == "Is there a student discount?"
    assert result.customer_name == "pixelwolf"
    # Discord delivers over a persistent gateway connection, not at-least-once
    # webhook retries, so no idempotency metadata is expected.
    assert result.metadata == {}
