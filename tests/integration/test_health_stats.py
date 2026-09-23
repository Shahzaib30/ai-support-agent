from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint(no_db_lifespan):
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stats_endpoint_shape(no_db_lifespan):
    fake_stats = {
        "total_messages": 10,
        "total_conversations": 4,
        "total_escalations": 1,
        "avg_sentiment": 0.2,
        "avg_response_ms": 850,
        "cache_hit_rate": 30.0,
    }
    with patch("api.routes.stats.get_today_stats", new=AsyncMock(return_value=fake_stats)):
        with TestClient(app) as client:
            response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {"today": fake_stats}


def test_openapi_lists_every_channel_route(no_db_lifespan):
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    paths = set(response.json()["paths"].keys())
    assert {
        "/chat", "/whatsapp", "/health", "/stats",
        "/human_reply", "/resolve/{conversation_id}",
        "/messages/{conversation_id}", "/conversation/{telegram_chat_id}",
        "/ingest",
    }.issubset(paths)
