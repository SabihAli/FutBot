import os
import tempfile
import time

from src.config import INGEST_ASYNC_IMAGE_THRESHOLD
from src.ingestion.errors import EmptyFileError, IngestionProviderError
from src.ingestion.extractors.pdf import count_pdf_vlm_work
from src.ingestion.extractors.registry import extract_file, get_extension, get_file_type, get_relevance_sample
from src.ingestion.indexer import index_blocks
from src.ingestion.relevance import enforce_football_relevance
from src.llm_components import LLM_PROVIDER
from src.retriever import BM25Retriever, ChromaRetriever


def should_process_in_background(path: str, filename: str) -> bool:
    if get_extension(filename) != ".pdf":
        return False
    return count_pdf_vlm_work(path) >= INGEST_ASYNC_IMAGE_THRESHOLD


def ingest_from_path(
    path: str,
    filename: str,
    chroma: ChromaRetriever,
    bm25: BM25Retriever,
    ingestion_id: int | None = None,
) -> dict:
    if LLM_PROVIDER != "groq":
        raise IngestionProviderError()

    started = time.monotonic()
    blocks, file_type = extract_file(path, filename)
    if not blocks:
        raise EmptyFileError(filename)

    sample = get_relevance_sample(path, filename, blocks)
    verdict = enforce_football_relevance(sample, filename)
    chunk_count = index_blocks(blocks, chroma, bm25, ingestion_id=ingestion_id)

    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "status": "success",
        "filename": filename,
        "file_type": file_type,
        "chunks_indexed": chunk_count,
        "relevance_verdict": verdict,
        "duration_ms": duration_ms,
        "ingestion_id": ingestion_id,
    }


def ingest_upload(
    file_bytes: bytes,
    filename: str,
    chroma: ChromaRetriever,
    bm25: BM25Retriever,
    ingestion_id: int | None = None,
) -> dict:
    if not file_bytes:
        raise EmptyFileError(filename)

    suffix = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return ingest_from_path(tmp_path, filename, chroma, bm25, ingestion_id=ingestion_id)
    finally:
        os.unlink(tmp_path)
