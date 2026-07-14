import pytest
from fastapi.testclient import TestClient

from src.api import app

client = TestClient(app)


def test_monolith_ingest_returns_501():
    response = client.post(
        "/api/ingest",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 501


def test_monolith_ingest_status_returns_501():
    response = client.get("/api/ingest/status/1")
    assert response.status_code == 501
