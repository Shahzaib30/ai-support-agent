from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app
from connectors.base import AgentReply


def _fake_reply() -> AgentReply:
    return AgentReply(
        answer="Standard shipping takes 5-7 business days.",
        escalated=False,
        cache_hit=False,
        sentiment_label="neutral",
        sentiment_score=0.1,
        conversation_id="conv-456",
    )


def _post_chat(client, payload):
    with patch("connectors.web.router.process_message", new=AsyncMock(return_value=_fake_reply())) as mock_process:
        response = client.post("/chat", json=payload)
    return response, mock_process


def test_telegram_channel_normalizes_correctly(no_db_lifespan, telegram_chat_payload):
    with TestClient(app) as client:
        response, mock_process = _post_chat(client, telegram_chat_payload)

    assert response.status_code == 200
    incoming = mock_process.await_args.args[0]
    assert incoming.channel == "telegram"
    assert incoming.customer_id == "987654321"
    assert incoming.metadata["event_id"] == "telegram_update_5551234"


def test_web_channel_normalizes_correctly(no_db_lifespan):
    payload = {
        "telegram_chat_id": "session-abc",
        "message": "What's your refund policy?",
        "customer_name": "Web User",
        "channel": "web",
    }
    with TestClient(app) as client:
        response, mock_process = _post_chat(client, payload)

    assert response.status_code == 200
    incoming = mock_process.await_args.args[0]
    assert incoming.channel == "web"
    assert incoming.customer_id == "session-abc"


def test_discord_channel_normalizes_correctly(no_db_lifespan):
    payload = {
        "telegram_chat_id": "discord_999",
        "message": "Do you have an API?",
        "customer_name": "devuser",
        "channel": "discord",
    }
    with TestClient(app) as client:
        response, mock_process = _post_chat(client, payload)

    assert response.status_code == 200
    incoming = mock_process.await_args.args[0]
    assert incoming.channel == "discord"
    assert incoming.customer_id == "discord_999"


def test_missing_channel_defaults_to_telegram(no_db_lifespan):
    """Historical default — old n8n exports and any caller that predates the
    channel field should still work exactly as they did before."""
    payload = {"telegram_chat_id": "legacy-caller", "message": "hi"}
    with TestClient(app) as client:
        response, mock_process = _post_chat(client, payload)

    assert response.status_code == 200
    incoming = mock_process.await_args.args[0]
    assert incoming.channel == "telegram"


def test_chat_response_shape(no_db_lifespan):
    payload = {"telegram_chat_id": "x", "message": "hi", "channel": "web"}
    with TestClient(app) as client:
        response, _ = _post_chat(client, payload)

    body = response.json()
    assert body == {
        "answer": "Standard shipping takes 5-7 business days.",
        "escalated": False,
        "cache_hit": False,
        "sentiment_label": "neutral",
        "sentiment_score": 0.1,
        "conversation_id": "conv-456",
    }
