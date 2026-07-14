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
async def test_pipeline_route_stays_501_on_public_gateway(gateway_client):
    async with gateway_client as client:
        response = await client.post(
            "/pipeline/run",
            json={"session_id": "c1", "query": "hi"},
        )
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_traces_route_proxies_when_observability_up(gateway_client, mocker):
    class FakeResponse:
        status_code = 404
        content = b'{"error":{"code":"NOT_FOUND","message":"x"}}'
        headers = {"content-type": "application/json"}

        async def aclose(self):
            return None

    mocker.patch(
        "services.gateway.app._get_client",
        return_value=mocker.Mock(
            request=mocker.AsyncMock(return_value=FakeResponse())
        ),
    )

    async with gateway_client as client:
        response = await client.get("/traces/1")

    assert response.status_code == 404
