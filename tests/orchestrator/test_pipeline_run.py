import pytest
from httpx import ASGITransport, AsyncClient

from services.rag_orchestrator.app import create_app


@pytest.fixture
def orchestrator_client(mocker):
    mocker.patch(
        "services.rag_orchestrator.routes._run_pipeline",
        return_value={
            "reply": "Arsenal won.",
            "snapshot": "{}",
            "snapshot_turn_count": 0,
            "citations": [{"chunk_id": "c1", "title": "Match", "snippet": "Arsenal 2-1"}],
            "run_id": 42,
            "classification": "KNOWLEDGE",
            "reached_max_retries": False,
        },
    )
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_pipeline_run(orchestrator_client):
    async with orchestrator_client as client:
        response = await client.post(
            "/pipeline/run",
            json={
                "session_id": "chat-1",
                "query": "Who won?",
                "context_messages": [{"role": "user", "content": "Who won?"}],
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reply"] == "Arsenal won."
    assert data["run_id"] == 42
    assert len(data["citations"]) == 1
