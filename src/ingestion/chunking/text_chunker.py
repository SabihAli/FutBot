import nltk

from src.config import CHUNK_OVERLAP_SENTENCES, CHUNK_TARGET_TOKENS
from src.ingestion.chunking.tokens import count_tokens
from src.ingestion.chunking.types import ChunkResult


def _ensure_nltk_punkt():
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except (LookupError, OSError):
            nltk.download(resource, quiet=True)


def chunk_prose(
    text: str,
    *,
    source_file: str,
    chunk_type: str = "text",
    section_heading: str = "",
    page_number: int | None = None,
    sheet_name: str | None = None,
    start_index: int = 0,
) -> list[ChunkResult]:
    _ensure_nltk_punkt()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    sentences: list[str] = []
    for paragraph in paragraphs:
        sentences.extend(nltk.sent_tokenize(paragraph))

    if not sentences:
        if not text.strip():
            return []
        sentences = [text.strip()]

    chunks: list[ChunkResult] = []
    current: list[str] = []
    chunk_index = start_index

    def flush():
        nonlocal chunk_index, current
        if not current:
            return
        body = " ".join(current).strip()
        chunks.append(
            ChunkResult(
                text=body,
                chunk_type=chunk_type,
                source_file=source_file,
                section_heading=section_heading,
                page_number=page_number,
                sheet_name=sheet_name,
                chunk_index=chunk_index,
                token_count=count_tokens(body),
            )
        )
        chunk_index += 1
        current = []

    for sentence in sentences:
        candidate = " ".join(current + [sentence]).strip()
        if current and count_tokens(candidate) > CHUNK_TARGET_TOKENS:
            flush()
        current.append(sentence)

    flush()

    if CHUNK_OVERLAP_SENTENCES > 0 and len(chunks) > 1:
        overlapped: list[ChunkResult] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_sents = nltk.sent_tokenize(chunks[i - 1].text)
            overlap = prev_sents[-CHUNK_OVERLAP_SENTENCES:]
            merged = " ".join(overlap + nltk.sent_tokenize(chunks[i].text)).strip()
            overlapped.append(
                ChunkResult(
                    text=merged,
                    chunk_type=chunk_type,
                    source_file=source_file,
                    section_heading=section_heading,
                    page_number=page_number,
                    sheet_name=sheet_name,
                    chunk_index=chunks[i].chunk_index,
                    token_count=count_tokens(merged),
                )
            )
        chunks = overlapped

    return chunks
