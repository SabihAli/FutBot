import pytest
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient

from services.auth import redis_store
from services.auth.app import create_app
from services.auth.db import init_db


@pytest.fixture(autouse=True)
def fake_redis():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_store.reset_redis_for_tests(fake)
    yield


@pytest.fixture
async def auth_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "test-secret-thirty-two-bytes-min!!")
    await init_db("sqlite+aiosqlite:///:memory:")
    app = create_app(with_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
