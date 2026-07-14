import os
import tempfile

from src.ingestion.extractors.pdf import count_pdf_vlm_work
from src.ingestion.extractors.registry import get_extension


def should_process_in_background(path: str, filename: str) -> bool:
    from src.config import INGEST_ASYNC_IMAGE_THRESHOLD

    if get_extension(filename) != ".pdf":
        return False
    return count_pdf_vlm_work(path) >= INGEST_ASYNC_IMAGE_THRESHOLD


def ingest_from_path(*_args, **_kwargs) -> dict:
    raise NotImplementedError("Ingestion indexing moved to retrieval/ingestion services (Phase 5).")


def ingest_upload(*_args, **_kwargs) -> dict:
    raise NotImplementedError("Ingestion indexing moved to retrieval/ingestion services (Phase 5).")
