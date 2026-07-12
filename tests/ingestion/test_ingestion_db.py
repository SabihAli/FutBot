import os
import sqlite3
import tempfile

import pytest

from src import db_logger
from src.db_logger import (
    compute_content_hash,
    create_ingestion_event,
    find_duplicate_ingestion,
    get_ingestion_chunks,
    log_ingestion_chunks,
    update_ingestion_event,
)
from src.ingestion.errors import DuplicateUploadError
from src.ingestion.indexer import index_blocks
from src.ingestion.types import ExtractedBlock
from src.retriever import BM25Retriever, ChromaRetriever


@pytest.fixture
def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "trace_logs.db")
        monkeypatch.setattr(db_logger, "DB_PATH", db_path)
        db_logger.init_db()
        yield db_path


def test_compute_content_hash_stable():
    data = b"same bytes"
    assert compute_content_hash(data) == compute_content_hash(data)
    assert compute_content_hash(b"other") != compute_content_hash(data)


def test_find_duplicate_ingestion_blocks_success_and_processing(temp_db):
    content_hash = compute_content_hash(b"football notes")
    assert find_duplicate_ingestion(content_hash) is None

    event_id = create_ingestion_event(
        filename="notes.txt",
        file_type="text",
        status="success",
        content_hash=content_hash,
    )
    duplicate = find_duplicate_ingestion(content_hash)
    assert duplicate is not None
    assert duplicate["id"] == event_id
    assert duplicate["filename"] == "notes.txt"

    update_ingestion_event(event_id, status="failed")
    assert find_duplicate_ingestion(content_hash) is None


def test_log_ingestion_chunks_persists_rows(temp_db):
    ingestion_id = create_ingestion_event(
        filename="squad.csv",
        file_type="csv",
        status="success",
        content_hash=compute_content_hash(b"csv"),
    )
    log_ingestion_chunks(
        ingestion_id,
        chunk_texts=["row chunk"],
        metadatas=[{
            "chunk_index": 0,
            "chunk_type": "table",
            "section_heading": "",
            "page_number": -1,
            "token_count": 12,
        }],
        chunk_ids=["user_abc_0"],
    )

    rows = get_ingestion_chunks(ingestion_id)
    assert len(rows) == 1
    assert rows[0]["ingestion_id"] == ingestion_id
    assert rows[0]["chunk_id"] == "user_abc_0"
    assert rows[0]["chunk_text"] == "row chunk"
    assert rows[0]["chunk_type"] == "table"
    assert rows[0]["token_count"] == 12


def test_index_blocks_logs_chunks_when_ingestion_id_provided(temp_db, mocker):
    ingestion_id = create_ingestion_event(
        filename="notes.txt",
        file_type="text",
        status="processing",
        content_hash=compute_content_hash(b"notes"),
    )
    chroma = mocker.Mock()
    bm25 = mocker.Mock()
    bm25.corpus = []
    bm25.chunk_ids = []

    blocks = [
        ExtractedBlock(
            text="Arsenal beat Chelsea 2-1 in the Premier League.",
            chunk_type="text",
            source_file="notes.txt",
        )
    ]

    count = index_blocks(blocks, chroma, bm25, ingestion_id=ingestion_id)
    assert count >= 1
    rows = get_ingestion_chunks(ingestion_id)
    assert len(rows) == count
    chroma.add_documents.assert_called_once()


def test_duplicate_upload_error_message():
    err = DuplicateUploadError("copy.txt", 7, "original.txt")
    assert err.existing_ingestion_id == 7
    assert "original.txt" in str(err)
