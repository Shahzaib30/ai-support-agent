import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def whatsapp_text_payload() -> dict:
    return load_fixture("whatsapp_text_message.json")


@pytest.fixture
def whatsapp_status_payload() -> dict:
    return load_fixture("whatsapp_status_event.json")


@pytest.fixture
def telegram_chat_payload() -> dict:
    return load_fixture("telegram_chat_request.json")


@pytest.fixture
def no_db_lifespan(monkeypatch):
    """
    Stubs out the FastAPI app's startup/shutdown DB & Redis connections so
    integration tests can exercise real routes through a real ASGI app
    without a live Postgres/Redis — every route under test here has
    core.agent.process_message mocked separately, so no DB call is actually
    reachable; this only satisfies the lifespan handshake itself.
    """
    async def fake_connect():
        return None

    async def fake_disconnect():
        return None

    async def fake_restore_count():
        return 0

    monkeypatch.setattr("api.main.connect", fake_connect)
    monkeypatch.setattr("api.main.disconnect", fake_disconnect)
    monkeypatch.setattr("api.main.restore_active_conversation_count", fake_restore_count)
