import pytest
from httpx import ASGITransport, AsyncClient

from services.tools.app import create_app
from services.tools.registry import reset_registry_for_tests
from services.tools.builtins.web_search import register_web_search


@pytest.fixture
def tools_client():
    reset_registry_for_tests()
    register_web_search()
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_list_tools(tools_client):
    async with tools_client as client:
        response = await client.get("/tools")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()["data"]]
    assert "web_search" in names
    assert "markdown_to_pdf" not in names


@pytest.mark.asyncio
async def test_execute_web_search_mocked(tools_client, mocker):
    mocker.patch(
        "services.tools.builtins.web_search.search_web",
        return_value={"snippets": ["a"], "sources": [], "provider": "tavily"},
    )
    async with tools_client as client:
        response = await client.post(
            "/tools/execute",
            json={"tool": "web_search", "arguments": {"query": "test"}, "web_search_enabled": True},
        )
    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
