import pytest
from fastapi.testclient import TestClient
from src.api import app, sessions_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_sessions_db():
    """Clear the in-memory session store before each test."""
    sessions_db.clear()
    yield

# ---------------------------------------------------------------------------
# POST /api/ingest
# ---------------------------------------------------------------------------
def test_ingest_endpoint_returns_501():
    response = client.post("/api/ingest")
    assert response.status_code == 501


def test_ingest_no_articles_returns_501():
    response = client.post("/api/ingest")
    assert response.status_code == 501


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------
def test_post_chat(mocker):
    mock_pipeline = mocker.patch(
        "src.api._run_pipeline",
        return_value=("Here is your answer.", "{}", 0),
    )

    payload = {"session_id": "test-session", "message": "Who won the game?"}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["reply"] == "Here is your answer."

    mock_pipeline.assert_called_once()
    call_kwargs = mock_pipeline.call_args[1]
    assert call_kwargs["query"] == "Who won the game?"
    assert isinstance(call_kwargs["context_messages"], list)
    assert len(call_kwargs["context_messages"]) == 1
    assert call_kwargs["context_messages"][0]["content"] == "Who won the game?"
    assert call_kwargs["snapshot"] == ""
    assert call_kwargs["snapshot_turn_count"] == 0

    # Both user and assistant messages stored in session
    session = sessions_db["test-session"]
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"
    assert session.messages[1].content == "Here is your answer."
