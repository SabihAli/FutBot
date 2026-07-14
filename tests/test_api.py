import pytest
from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)


def test_ingest_endpoint_returns_501():
    response = client.post("/api/ingest")
    assert response.status_code == 501


def test_post_chat_returns_501():
    payload = {"session_id": "test-session", "message": "Who won the game?"}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 501
