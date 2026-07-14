import pytest
from httpx import ASGITransport, AsyncClient

from services.gateway.app import create_app


@pytest.fixture
def gateway_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_ingest_route_stays_501_on_public_gateway(gateway_client):
    async with gateway_client as client:
        response = await client.post(
            "/ingest/jobs",
            json={
                "project_id": "proj-1",
                "file_id": "file-1",
                "filename": "notes.txt",
                "storage_key": "key",
            },
        )
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"
