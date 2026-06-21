import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from src.api import app, sessions_db
from src.context import ConversationContext, Message
from src.data_layer import Article

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions_db():
    """Clear the in-memory session store before each test."""
    sessions_db.clear()
    yield


# ---------------------------------------------------------------------------
# POST /api/ingest
# ---------------------------------------------------------------------------
def test_ingest_endpoint(mocker):
    # Mock scraper to return a real Article dataclass
    fake_article = Article(
        title="Messi Wins Ballon d'Or Again",
        body="Lionel Messi claimed his record ninth Ballon d'Or award.",
        url="https://www.bbc.com/sport/football/articles/12345",
        source="bbc",
        date_published=datetime(2025, 10, 20, tzinfo=timezone.utc),
    )
    mocker.patch("src.api.scrape_all", return_value=[fake_article])

    # Mock the retrievers so we don't need real ChromaDB/BM25 in tests
    mocker.patch("src.api.global_chroma.add_documents")
    mocker.patch("src.api.global_bm25.build_index")

    # Mock chunk_text to return predictable chunks
    mocker.patch("src.api.chunk_text", return_value=["chunk one", "chunk two"])

    response = client.post("/api/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["articles_ingested"] == 1
    assert data["total_chunks_indexed"] == 2


def test_ingest_no_articles(mocker):
    mocker.patch("src.api.scrape_all", return_value=[])

    response = client.post("/api/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["articles_ingested"] == 0


# ---------------------------------------------------------------------------
# GET /api/session/{session_id}
# ---------------------------------------------------------------------------
def test_get_session_new():
    response = client.get("/api/session/session-123")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-123"
    assert len(data["messages"]) == 0


def test_get_session_existing():
    msg = Message(role="user", content="Hello", timestamp=datetime.now(timezone.utc))
    ctx = ConversationContext(session_id="session-456", messages=[msg])
    sessions_db["session-456"] = ctx

    response = client.get("/api/session/session-456")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-456"
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "Hello"


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------
def test_post_chat(mocker):
    mock_pipeline = mocker.patch("src.api.run_pipeline", return_value="Here is your answer.")

    payload = {"session_id": "test-session", "message": "Who won the game?"}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["reply"] == "Here is your answer."

    # Pipeline called with correct keyword args
    mock_pipeline.assert_called_once()
    assert mock_pipeline.call_args[1]["query"] == "Who won the game?"
    assert isinstance(mock_pipeline.call_args[1]["context_messages"], list)
    # Empty list for a fresh session (no prior history)
    assert len(mock_pipeline.call_args[1]["context_messages"]) == 0

    # Both user and assistant messages stored in session
    session = sessions_db["test-session"]
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"
    assert session.messages[1].content == "Here is your answer."
