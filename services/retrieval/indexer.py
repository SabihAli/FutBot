import hashlib
from datetime import datetime, timezone
from typing import Any

from services.ingestion.chunking.types import ChunkResult


def _filename_stem(source_file: str) -> str:
    if "." in source_file:
        return source_file.rsplit(".", 1)[0]
    return source_file


def _chunk_id_prefix(source_file: str) -> str:
    digest = hashlib.sha256(source_file.encode("utf-8")).hexdigest()[:12]
    return f"user_{digest}"


def _bm25_prefix(stem: str, section_heading: str = "") -> str:
    parts = [stem, stem, stem]
    if section_heading:
        parts.extend([section_heading, section_heading])
    return "\n".join(parts)


def chunked_to_index_payload(
    chunks: list[ChunkResult],
    *,
    source_file: str,
    extra_metadata: dict[str, Any] | None = None,
    id_prefix: str | None = None,
    id_offset: int = 0,
) -> tuple[list[str], list[str], list[dict[str, Any]], list[str]]:
    chunk_texts: list[str] = []
    bm25_texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    chunk_ids: list[str] = []
    ingested_at = datetime.now(timezone.utc).isoformat()
    stem = _filename_stem(source_file)
    prefix = id_prefix or _chunk_id_prefix(source_file)
    extra = extra_metadata or {}

    for chunk in chunks:
        chunk_texts.append(chunk.text)
        bm25_texts.append(f"{_bm25_prefix(stem, chunk.section_heading)}\n{chunk.text}")
        metadata = {
            "source_file": source_file,
            "chunk_type": chunk.chunk_type,
            "section_heading": chunk.section_heading or "",
            "page_number": chunk.page_number if chunk.page_number is not None else -1,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
            "url": extra.get("url", ""),
            "title": extra.get("title", stem),
            "source": extra.get("source", "user_upload"),
            "date": extra.get("date", ""),
            "ingested_at": ingested_at,
        }
        if chunk.sheet_name:
            metadata["sheet_name"] = chunk.sheet_name
        metadatas.append(metadata)
        chunk_ids.append(f"{prefix}_{id_offset + chunk.chunk_index}")

    return chunk_texts, bm25_texts, metadatas, chunk_ids
