from connectors.base import IncomingMessage
from connectors.web.normalizer import to_incoming_message
from connectors.web.router import ChatRequest


def test_web_chat_request_normalizes_to_incoming_message():
    request = ChatRequest(
        telegram_chat_id="a1b2c3",
        message="What's your refund policy?",
        customer_name="Web User",
        channel="web",
    )

    result = to_incoming_message(request)

    assert isinstance(result, IncomingMessage)
    assert result.channel == "web"
    assert result.customer_id == "a1b2c3"
    assert result.message == "What's your refund policy?"
    assert result.customer_name == "Web User"
