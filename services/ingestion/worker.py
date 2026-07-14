import logging

from services.ingestion.jobs import JobStore, get_job_store
from services.ingestion.processor import process_file_bytes
from services.ingestion.project_client import update_file_status
from services.ingestion.storage import fetch_object_bytes
from services.ingestion.errors import FootballRelevanceError

logger = logging.getLogger(__name__)


def run_project_file_job(job_id: str) -> None:
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        return

    store.mark_processing(job_id)
    update_file_status(
        project_id=job.project_id,
        file_id=job.file_id,
        status="processing",
    )

    try:
        file_bytes = fetch_object_bytes(job.storage_key)
        result = process_file_bytes(
            project_id=job.project_id,
            file_id=job.file_id,
            filename=job.filename,
            file_bytes=file_bytes,
        )
        store.mark_completed(job_id, chunks_indexed=result["chunks_indexed"])
        update_file_status(
            project_id=job.project_id,
            file_id=job.file_id,
            status="ingested",
        )
    except FootballRelevanceError as exc:
        store.mark_failed(job_id, str(exc))
        update_file_status(
            project_id=job.project_id,
            file_id=job.file_id,
            status="failed",
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("Ingest job %s failed", job_id)
        store.mark_failed(job_id, str(exc))
        update_file_status(
            project_id=job.project_id,
            file_id=job.file_id,
            status="failed",
            error_message=str(exc),
        )
