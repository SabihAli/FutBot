import pytest
from httpx import ASGITransport, AsyncClient

from services.llm_gateway.app import create_app


@pytest.fixture
def llm_client(mocker):
    mocker.patch(
        "services.llm_gateway.components.invoke_llm",
        return_value='{"topics":["compressed"]}',
    )
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_compress_endpoint_returns_snapshot(llm_client, mocker):
    mocker.patch(
        "services.llm_gateway.routes.SnapshotCompressor.compress_incremental",
        return_value='{"topics":["compressed"]}',
    )
    async with llm_client as client:
        response = await client.post(
            "/llm/compress",
            json={
                "existing_snapshot": "{}",
                "aged_messages": [{"role": "user", "content": "old message"}],
            },
        )
    assert response.status_code == 200
    assert "compressed" in response.json()["data"]["snapshot"]


@pytest.mark.asyncio
async def test_complete_endpoint(llm_client, mocker):
    mocker.patch(
        "services.llm_gateway.routes.invoke_llm",
        return_value="Hello",
    )
    async with llm_client as client:
        response = await client.post(
            "/llm/complete",
            json={"step": "rewriter", "system_prompt": "", "user_content": "Hi"},
        )
    assert response.status_code == 200
    assert response.json()["data"]["content"] == "Hello"
