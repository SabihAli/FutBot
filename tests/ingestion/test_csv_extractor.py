import os

from services.ingestion.extractors.spreadsheet import csv_relevance_sample, extract_csv

TEST_DATA = os.path.join(os.path.dirname(__file__), "test_data")


def test_extract_csv_rows():
    path = os.path.join(TEST_DATA, "squad_stats.csv")
    blocks = extract_csv(path, "squad_stats.csv")

    assert len(blocks) == 3
    assert all(b.chunk_type == "table_row" for b in blocks)
    assert "Erling Haaland" in blocks[0].text
    assert "Goals: 36" in blocks[0].text


def test_csv_relevance_sample_uses_columns_and_five_rows():
    path = os.path.join(TEST_DATA, "squad_stats.csv")
    sample = csv_relevance_sample(path)

    assert "columns:" in sample
    assert "Player" in sample
    assert "rows:" in sample
    assert "Erling Haaland" in sample
