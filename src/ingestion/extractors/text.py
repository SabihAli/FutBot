import os

from src.ingestion.types import ExtractedBlock


def extract_text(path: str, source_file: str) -> list[ExtractedBlock]:
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    text = raw.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    return [
        ExtractedBlock(
            text=text,
            chunk_type="text",
            source_file=source_file,
        )
    ]
