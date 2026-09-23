from connectors.base import IncomingMessage
from connectors.whatsapp.normalizer import to_incoming_message


def test_text_message_normalizes_to_incoming_message(whatsapp_text_payload):
    result = to_incoming_message(whatsapp_text_payload)

    assert isinstance(result, IncomingMessage)
    assert result.channel == "whatsapp"
    assert result.customer_id == "15558675309"
    assert result.message == "Do you offer refunds after 30 days?"
    assert result.customer_name == "Jordan Rivera"
    assert result.conversation_id is None
    assert result.metadata["event_id"].startswith("wamid.")


def test_status_event_is_ignored(whatsapp_status_payload):
    result = to_incoming_message(whatsapp_status_payload)
    assert result is None


def test_missing_message_id_omits_event_id(whatsapp_text_payload):
    del whatsapp_text_payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    result = to_incoming_message(whatsapp_text_payload)
    assert "event_id" not in result.metadata
