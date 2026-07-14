from services.ingestion.extractors.registry import get_extension, get_file_type, get_relevance_sample
from services.ingestion.types import ExtractedBlock


def test_get_extension_and_file_type():
    assert get_extension("report.PDF") == ".pdf"
    assert get_file_type(".pdf") == "pdf"
    assert get_file_type(".xlsx") == "xlsx"
    assert get_file_type(".png") == "image"
    assert get_file_type(".md") == "md"


def test_get_relevance_sample_truncates_text_blocks():
    blocks = [
        ExtractedBlock(text="x" * 2000, chunk_type="text", source_file="notes.txt"),
    ]
    sample = get_relevance_sample("", "notes.txt", blocks)
    assert len(sample) == 1000
