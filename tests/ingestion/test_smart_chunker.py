from services.ingestion.chunking.smart_chunker import SmartChunker
from services.ingestion.chunking.table_chunker import chunk_table_rows
from services.ingestion.chunking.text_chunker import chunk_prose
from services.ingestion.types import ExtractedBlock


def test_chunk_prose_respects_sentence_boundaries():
    text = "Arsenal won the match. Chelsea scored late. Liverpool drew at home."
    chunks = chunk_prose(text, source_file="notes.txt")
    assert len(chunks) >= 1
    assert all("chunk_index" in chunk.__dict__ for chunk in chunks)
    assert chunks[0].token_count > 0


def test_chunk_table_rows_groups_rows():
    rows = [
        ExtractedBlock(
            text=f"Player: P{i} | Goals: {i}",
            chunk_type="table_row",
            source_file="stats.csv",
        )
        for i in range(12)
    ]
    chunks = chunk_table_rows(rows)
    assert len(chunks) == 2
    assert "[TABLE HEADER:" in chunks[0].text
    assert "Player: P0" in chunks[0].text


def test_smart_chunker_mixed_blocks():
    blocks = [
        ExtractedBlock(text="Arsenal beat Chelsea.", chunk_type="text", source_file="notes.txt"),
        ExtractedBlock(
            text="Player: Haaland | Goals: 36",
            chunk_type="table_row",
            source_file="stats.csv",
        ),
    ]
    chunks = SmartChunker().chunk_blocks(blocks)
    assert len(chunks) == 2
    types = {chunk.chunk_type for chunk in chunks}
    assert types == {"text", "table_row"}


def test_smart_chunker_article_bootstrap_path():
    body = "First sentence about football. Second sentence with more detail."
    chunks = SmartChunker().chunk_article(body, "Example Title")
    assert len(chunks) >= 1
    assert chunks[0].chunk_type == "text"
