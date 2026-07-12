import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from futbot_common import CorrelationIdMiddleware
from futbot_common.context import CORRELATION_ID_HEADER


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_generates_correlation_id_when_missing(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert CORRELATION_ID_HEADER in response.headers
    uuid.UUID(response.headers[CORRELATION_ID_HEADER])


def test_preserves_incoming_correlation_id(client):
    cid = str(uuid.uuid4())
    response = client.get("/ping", headers={CORRELATION_ID_HEADER: cid})
    assert response.headers[CORRELATION_ID_HEADER] == cid
