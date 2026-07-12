import logging
import os
import time

from src.ingestion.errors import FootballRelevanceError
from src.ingestion.pipeline import ingest_from_path
from src.db_logger import update_ingestion_event
from src.retriever import BM25Retriever, ChromaRetriever

logger = logging.getLogger(__name__)


def run_background_ingest(
    event_id: int,
    tmp_path: str,
    filename: str,
    chroma: ChromaRetriever,
    bm25: BM25Retriever,
    images_total: int,
):
    started = time.monotonic()
    try:
        update_ingestion_event(event_id, images_total=images_total, images_processed=0)
        result = ingest_from_path(tmp_path, filename, chroma, bm25, ingestion_id=event_id)
        duration_ms = int((time.monotonic() - started) * 1000)
        update_ingestion_event(
            event_id,
            status="success",
            file_type=result["file_type"],
            chunk_count=result["chunks_indexed"],
            relevance_verdict=result["relevance_verdict"],
            duration_ms=duration_ms,
            images_processed=images_total,
        )
    except FootballRelevanceError as exc:
        update_ingestion_event(
            event_id,
            status="rejected",
            relevance_verdict="NO",
            error=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        logger.exception("Background ingestion failed for %s", filename)
        update_ingestion_event(
            event_id,
            status="failed",
            error=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
