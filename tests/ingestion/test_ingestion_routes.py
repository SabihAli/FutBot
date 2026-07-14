import pytest
from httpx import ASGITransport, AsyncClient

from services.ingestion.app import create_app
from services.ingestion.jobs import reset_job_store


@pytest.fixture
def ingestion_client(mocker):
    reset_job_store()
    mocker.patch("services.ingestion.routes.run_job")
    app = create_app()
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    reset_job_store()


@pytest.mark.asyncio
async def test_create_ingest_job_returns_202(ingestion_client):
    async with ingestion_client as client:
        response = await client.post(
            "/ingest/jobs",
            json={
                "project_id": "proj-1",
                "file_id": "file-1",
                "filename": "notes.txt",
                "storage_key": "projects/proj-1/abc/notes.txt",
            },
        )

    assert response.status_code == 202
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["project_id"] == "proj-1"
    assert data["file_id"] == "file-1"


@pytest.mark.asyncio
async def test_get_ingest_job(ingestion_client):
    async with ingestion_client as client:
        created = await client.post(
            "/ingest/jobs",
            json={
                "project_id": "proj-2",
                "file_id": "file-2",
                "filename": "doc.pdf",
                "storage_key": "key",
            },
        )
        job_id = created.json()["data"]["id"]

        response = await client.get(f"/ingest/jobs/{job_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["file_id"] == "file-2"


@pytest.mark.asyncio
async def test_get_ingest_job_not_found(ingestion_client):
    async with ingestion_client as client:
        response = await client.get("/ingest/jobs/missing-id")

    assert response.status_code == 404
