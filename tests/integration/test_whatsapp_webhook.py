from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app
from connectors.base import AgentReply


def _fake_reply(**overrides) -> AgentReply:
    defaults = dict(
        answer="We offer refunds within 30 days of purchase.",
        escalated=False,
        cache_hit=False,
        sentiment_label="neutral",
        sentiment_score=0.0,
        conversation_id="conv-123",
    )
    defaults.update(overrides)
    return AgentReply(**defaults)


def test_whatsapp_message_normalizes_and_reaches_core_agent(no_db_lifespan, whatsapp_text_payload):
    """Proves payload -> WhatsApp adapter -> IncomingMessage -> core agent,
    without any live WhatsApp credentials, DB, Redis, or LLM."""
    with patch("connectors.whatsapp.router.process_message", new=AsyncMock(return_value=_fake_reply())) as mock_process, \
         patch("connectors.whatsapp.router.send_whatsapp_message", new=AsyncMock()) as mock_send:
        with TestClient(app) as client:
            response = client.post("/whatsapp", json=whatsapp_text_payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    mock_process.assert_awaited_once()
    incoming = mock_process.await_args.args[0]
    assert incoming.channel == "whatsapp"
    assert incoming.customer_id == "15558675309"
    assert incoming.message == "Do you offer refunds after 30 days?"
    assert incoming.customer_name == "Jordan Rivera"
    assert incoming.metadata["event_id"].startswith("wamid.")

    mock_send.assert_awaited_once_with("15558675309", "We offer refunds within 30 days of purchase.")


def test_whatsapp_status_event_never_reaches_core_agent(no_db_lifespan, whatsapp_status_payload):
    with patch("connectors.whatsapp.router.process_message", new=AsyncMock()) as mock_process:
        with TestClient(app) as client:
            response = client.post("/whatsapp", json=whatsapp_status_payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    mock_process.assert_not_awaited()


def test_whatsapp_duplicate_delivery_sends_nothing(no_db_lifespan, whatsapp_text_payload):
    """A retried webhook delivery that core.agent recognizes as a duplicate
    returns an empty answer — the connector must not re-send to the customer."""
    with patch("connectors.whatsapp.router.process_message", new=AsyncMock(return_value=_fake_reply(answer="", conversation_id=""))), \
         patch("connectors.whatsapp.router.send_whatsapp_message", new=AsyncMock()) as mock_send:
        with TestClient(app) as client:
            response = client.post("/whatsapp", json=whatsapp_text_payload)

    assert response.status_code == 200
    mock_send.assert_not_awaited()


def test_whatsapp_verify_rejects_wrong_token(no_db_lifespan, monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "correct-token")
    with TestClient(app) as client:
        response = client.get(
            "/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1234"},
        )
    assert response.status_code == 403


def test_whatsapp_verify_accepts_correct_token(no_db_lifespan, monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "correct-token")
    with TestClient(app) as client:
        response = client.get(
            "/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "correct-token", "hub.challenge": "1234"},
        )
    assert response.status_code == 200
    assert response.json() == 1234
