import os

from src.ingestion.extractors.text import extract_text

TEST_DATA = os.path.join(os.path.dirname(__file__), "test_data")


def test_extract_text_file():
    path = os.path.join(TEST_DATA, "arsenal_notes.txt")
    blocks = extract_text(path, "arsenal_notes.txt")

    assert len(blocks) == 1
    assert blocks[0].chunk_type == "text"
    assert "Arsenal" in blocks[0].text
    assert "Chelsea" in blocks[0].text


def test_extract_empty_text_returns_empty_list(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n  ", encoding="utf-8")

    blocks = extract_text(str(path), "empty.txt")
    assert blocks == []
