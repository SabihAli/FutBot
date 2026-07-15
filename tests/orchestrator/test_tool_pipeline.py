import pytest
from httpx import ASGITransport, AsyncClient

from services.rag_orchestrator.app import create_app


@pytest.fixture
def orchestrator_client(mocker):
    mocker.patch(
        "services.rag_orchestrator.routes._run_pipeline",
        return_value={
            "reply": "Arsenal won 2-1.",
            "snapshot": "{}",
            "snapshot_turn_count": 0,
            "citations": [],
            "run_id": 42,
            "classification": "TOOL",
            "reached_max_retries": False,
            "tool_results": [{"tool": "mcp:livescore:get_live_scores", "result": {"matches": []}}],
            "tool_errors": [],
            "tool_notice": "Web search was needed for this answer but is disabled. Enable web search for broader coverage.",
            "tool_notice_code": "WEB_SEARCH_SKIPPED",
            "web_search_skipped": True,
        },
    )
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_pipeline_run_with_tools(orchestrator_client):
    async with orchestrator_client as client:
        response = await client.post(
            "/pipeline/run",
            json={
                "session_id": "chat-1",
                "query": "Score?",
                "context_messages": [{"role": "user", "content": "Score?"}],
                "web_search_enabled": False,
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classification"] == "TOOL"
    assert data["web_search_skipped"] is True
    assert data["tool_notice_code"] == "WEB_SEARCH_SKIPPED"
