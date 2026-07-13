import pytest
from httpx import ASGITransport, AsyncClient

from services.project.app import create_app
from services.project.db import init_db
from services.project.storage import reset_storage_for_tests


@pytest.fixture
async def project_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    reset_storage_for_tests()
    await init_db("sqlite+aiosqlite:///:memory:")
    app = create_app(with_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def auth_headers(user_id: str = "user-1") -> dict[str, str]:
    return {"X-User-ID": user_id}
