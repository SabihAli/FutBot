import os

import pytest
from fastapi.testclient import TestClient

from src.api import app

client = TestClient(app)

TEST_DATA = os.path.join(os.path.dirname(__file__), "test_data")


@pytest.fixture(autouse=True)
def groq_provider(mocker):
    mocker.patch("src.ingestion.pipeline.LLM_PROVIDER", "groq")


def test_ingest_upload_txt_success(mocker):
    mocker.patch(
        "src.ingestion.pipeline.enforce_football_relevance",
        return_value="YES",
    )
    mocker.patch("src.api.global_chroma.add_documents")
    mocker.patch("src.api.global_bm25.build_index")
    mocker.patch("src.api.global_bm25.save")
    mocker.patch("src.api.find_duplicate_ingestion", return_value=None)
    mocker.patch("src.api.create_ingestion_event", return_value=99)
    mocker.patch("src.api.update_ingestion_event")
    mocker.patch("src.ingestion.indexer.log_ingestion_chunks")

    path = os.path.join(TEST_DATA, "arsenal_notes.txt")
    with open(path, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("arsenal_notes.txt", f, "text/plain")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == "arsenal_notes.txt"
    assert data["relevance_verdict"] == "YES"
    assert data["chunks_indexed"] >= 1
    assert data["event_id"] == 99


def test_ingest_upload_rejected(mocker):
    from src.ingestion.errors import FootballRelevanceError

    mocker.patch(
        "src.ingestion.pipeline.enforce_football_relevance",
        side_effect=FootballRelevanceError("earnings.csv"),
    )
    mocker.patch("src.api.find_duplicate_ingestion", return_value=None)
    mocker.patch("src.api.create_ingestion_event", return_value=5)
    mocker.patch("src.api.update_ingestion_event")

    path = os.path.join(TEST_DATA, "earnings.csv")
    with open(path, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("earnings.csv", f, "text/csv")},
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "FootballRelevanceError"
    assert detail["filename"] == "earnings.csv"


def test_ingest_upload_unsupported_format():
    response = client.post(
        "/api/ingest",
        files={"file": ("report.docx", b"data", "application/octet-stream")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["error"] == "UnsupportedFormatError"


def test_ingest_upload_requires_groq(mocker):
    mocker.patch("src.ingestion.pipeline.LLM_PROVIDER", "local")

    path = os.path.join(TEST_DATA, "arsenal_notes.txt")
    with open(path, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("arsenal_notes.txt", f, "text/plain")},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "IngestionProviderError"


def test_ingest_upload_duplicate(mocker):
    mocker.patch(
        "src.api.find_duplicate_ingestion",
        return_value={"id": 12, "filename": "arsenal_notes.txt", "status": "success"},
    )

    path = os.path.join(TEST_DATA, "arsenal_notes.txt")
    with open(path, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("copy.txt", f, "text/plain")},
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "DuplicateUploadError"
    assert detail["existing_ingestion_id"] == 12


def test_ingest_pdf_background_response(mocker, tmp_path):
    import fitz

    pdf_path = tmp_path / "heavy.pdf"
    doc = fitz.open()
    for _ in range(4):
        doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    mocker.patch("src.ingestion.pipeline.LLM_PROVIDER", "groq")
    mocker.patch("src.api.should_process_in_background", return_value=True)
    mocker.patch("src.api.count_pdf_vlm_work", return_value=4)
    mocker.patch("src.api.find_duplicate_ingestion", return_value=None)
    mocker.patch("src.api.create_ingestion_event", return_value=42)
    mocker.patch("src.api.run_background_ingest")

    with open(pdf_path, "rb") as f:
        response = client.post(
            "/api/ingest",
            files={"file": ("heavy.pdf", f, "application/pdf")},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "processing"
    assert data["event_id"] == 42
    assert data["status_url"] == "/api/ingest/status/42"
    assert "continue chatting" in data["message"]


def test_ingest_status_endpoint(mocker):
    mocker.patch(
        "src.api.get_ingestion_event",
        return_value={
            "id": 1,
            "filename": "heavy.pdf",
            "file_type": "pdf",
            "status": "processing",
            "chunk_count": None,
            "relevance_verdict": None,
            "error": None,
            "duration_ms": None,
            "images_total": 4,
            "images_processed": 1,
            "ingested_at": "2026-07-09T00:00:00+00:00",
        },
    )

    response = client.get("/api/ingest/status/1")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert "continue chatting" in data["message"]
