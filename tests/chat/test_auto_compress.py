from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from services.chat.app import create_app
from services.chat.db import init_db


@pytest.fixture
async def chat_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    await init_db("sqlite+aiosqlite:///:memory:")
    app = create_app(with_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _usage(should_compress: bool, percent: float = 50.0) -> dict:
    return {
        "used_tokens": 80 if should_compress else 10,
        "limit_tokens": 100,
        "percent_used": percent,
        "breakdown": {
            "snapshot": 0,
            "hot_messages": 80 if should_compress else 10,
            "current_query": 0,
            "memory": 0,
            "retrieved_chunks": 0,
        },
        "should_compress": should_compress,
    }


@pytest.mark.asyncio
async def test_post_message_auto_compress_clears_pending(chat_client, monkeypatch):
    calls = []

    async def fake_run_auto_compress(db, chat):
        calls.append(1)
        chat.compression_pending = False
        return True

    create = await chat_client.post("/chats", json={"title": "Compress"})
    chat_id = create.json()["data"]["id"]

    monkeypatch.setattr("services.chat.routes.run_auto_compress", fake_run_auto_compress)
    monkeypatch.setattr(
        "services.chat.routes.build_context_usage",
        AsyncMock(side_effect=[_usage(True, 90), _usage(False, 5)]),
    )

    response = await chat_client.post(
        f"/chats/{chat_id}/messages",
        json={"role": "user", "content": "trigger compress"},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert calls == [1]
    assert body["compression_pending"] is False
    assert body["should_compress"] is False
