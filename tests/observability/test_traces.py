import pytest
from httpx import ASGITransport, AsyncClient

from services.observability.app import create_app
from services.observability import trace_store


@pytest.fixture
def obs_client(tmp_path, monkeypatch):
    db_path = tmp_path / "traces.db"
    monkeypatch.setattr(trace_store, "DB_PATH", str(db_path))
    trace_store.init_db()
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_get_trace_returns_run(obs_client):
    with trace_store.PipelineRunLogger(original_query="hello", session_id="chat-1") as run:
        run.log_tool_call("web_search", skipped=True)
        run.finish(classification="SIMPLE", final_answer="hi", total_iterations=0)

    async with obs_client as client:
        response = await client.get(f"/traces/{run.run_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["original_query"] == "hello"
    assert data["final_answer"] == "hi"
    assert len(data["tool_calls"]) == 1
    assert data["tool_calls"][0]["tool_name"] == "web_search"
    assert data["tool_calls"][0]["skipped"] is True


@pytest.mark.asyncio
async def test_get_trace_not_found(obs_client):
    async with obs_client as client:
        response = await client.get("/traces/99999")
    assert response.status_code == 404
