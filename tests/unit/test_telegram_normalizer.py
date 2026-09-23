from connectors.base import IncomingMessage
from connectors.telegram.normalizer import to_incoming_message
from connectors.web.router import ChatRequest


def test_telegram_chat_request_normalizes_to_incoming_message(telegram_chat_payload):
    request = ChatRequest(**telegram_chat_payload)

    result = to_incoming_message(request)

    assert isinstance(result, IncomingMessage)
    assert result.channel == "telegram"
    assert result.customer_id == "987654321"
    assert result.message == "How long does shipping take internationally?"
    assert result.customer_name == "Alex Chen"
    assert result.metadata["event_id"] == "telegram_update_5551234"


def test_missing_event_id_leaves_metadata_empty():
    request = ChatRequest(telegram_chat_id="1", message="hi", channel="telegram")
    result = to_incoming_message(request)
    assert result.metadata == {}
