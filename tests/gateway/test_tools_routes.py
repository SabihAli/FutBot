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
async def test_tools_execute_stays_501_on_gateway(gateway_client):
    async with gateway_client as client:
        response = await client.post(
            "/tools/execute",
            json={"tool": "web_search", "arguments": {"query": "x"}},
        )
    assert response.status_code == 501
