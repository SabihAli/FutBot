import pytest
from httpx import ASGITransport, AsyncClient

from services.ingestion.app import create_app
from services.ingestion.jobs import JobStore, get_job_store


@pytest.fixture
def ingestion_client(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
    store = JobStore()
    mocker.patch(
        "services.ingestion.routes.run_job",
        side_effect=lambda job_id, bg=None: store.mark_processing(job_id),
    )
    mocker.patch(
        "services.ingestion.worker.run_project_file_job",
        side_effect=lambda job_id: store.mark_completed(job_id, chunks_indexed=3),
    )
    app = create_app()
    app.dependency_overrides[get_job_store] = lambda: store
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), store


@pytest.mark.asyncio
async def test_create_job_returns_processing(ingestion_client):
    client, store = ingestion_client

    async with client:
        response = await client.post(
            "/ingest/jobs",
            json={
                "project_id": "proj-1",
                "file_id": "file-9",
                "filename": "notes.txt",
                "storage_key": "projects/proj-1/abc/notes.txt",
                "content_hash": "abc123",
            },
        )

    assert response.status_code == 202
    data = response.json()["data"]
    assert data["status"] in ("processing", "completed")
    assert data["project_id"] == "proj-1"
    assert data["file_id"] == "file-9"


@pytest.mark.asyncio
async def test_get_job_status(ingestion_client):
    client, store = ingestion_client

    async with client:
        created = await client.post(
            "/ingest/jobs",
            json={
                "project_id": "proj-1",
                "file_id": "file-9",
                "filename": "notes.txt",
                "storage_key": "projects/proj-1/abc/notes.txt",
                "content_hash": "abc123",
            },
        )
        job_id = created.json()["data"]["id"]
        status = await client.get(f"/ingest/jobs/{job_id}")

    assert status.status_code == 200
    assert status.json()["data"]["id"] == job_id
