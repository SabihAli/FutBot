import pytest

from services.ingestion.jobs import JobStore


def test_job_store_create_and_get():
    store = JobStore()
    job = store.create(
        project_id="proj-1",
        file_id="file-1",
        filename="notes.txt",
        storage_key="projects/proj-1/abc/notes.txt",
    )
    assert job.id
    assert job.status == "pending"

    loaded = store.get(job.id)
    assert loaded is not None
    assert loaded.file_id == "file-1"


def test_job_store_update_status():
    store = JobStore()
    job = store.create(
        project_id="proj-1",
        file_id="file-1",
        filename="notes.txt",
        storage_key="key",
    )
    store.update(job.id, status="ingested", chunks_indexed=3)
    loaded = store.get(job.id)
    assert loaded.status == "ingested"
    assert loaded.chunks_indexed == 3
