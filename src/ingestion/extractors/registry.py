import os

from src.ingestion.errors import UnsupportedFormatError
from src.ingestion.extractors.image import extract_image, is_image_extension
from src.ingestion.extractors.spreadsheet import (
    csv_relevance_sample,
    extract_csv,
    extract_xlsx,
    xlsx_relevance_sample,
)
from src.ingestion.extractors.text import extract_text
from src.ingestion.types import ExtractedBlock

ACCEPTED_EXTENSIONS = {".txt", ".md", ".csv", ".xlsx", ".pdf", ".jpg", ".jpeg", ".png", ".webp"}


def get_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def get_file_type(ext: str) -> str:
    if ext in {".txt", ".md"}:
        return "txt" if ext == ".txt" else "md"
    if ext == ".csv":
        return "csv"
    if ext == ".xlsx":
        return "xlsx"
    if ext == ".pdf":
        return "pdf"
    if is_image_extension(ext):
        return "image"
    return ext.lstrip(".")


def extract_file(path: str, filename: str) -> tuple[list[ExtractedBlock], str]:
    ext = get_extension(filename)
    if ext not in ACCEPTED_EXTENSIONS:
        raise UnsupportedFormatError(
            filename=filename,
            extension=ext or "(none)",
            accepted=sorted(ACCEPTED_EXTENSIONS),
        )

    source_file = os.path.basename(filename)
    if ext in {".txt", ".md"}:
        return extract_text(path, source_file), get_file_type(ext)
    if ext == ".csv":
        return extract_csv(path, source_file), "csv"
    if ext == ".xlsx":
        return extract_xlsx(path, source_file), "xlsx"
    if is_image_extension(ext):
        return extract_image(path, source_file), "image"

    from src.ingestion.extractors.pdf import extract_pdf

    return extract_pdf(path, source_file), "pdf"


def get_relevance_sample(path: str, filename: str, blocks: list[ExtractedBlock]) -> str:
    ext = get_extension(filename)
    if ext == ".csv":
        return csv_relevance_sample(path)
    if ext == ".xlsx":
        return xlsx_relevance_sample(path)
    return "\n\n".join(b.text for b in blocks)[:1000]
