import pandas as pd

from services.ingestion.extractors.spreadsheet import extract_xlsx, xlsx_relevance_sample


def test_extract_xlsx_all_sheets(tmp_path):
    path = tmp_path / "stats.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(
            {"Player": ["Haaland"], "Goals": [36]},
        ).to_excel(writer, sheet_name="Premier League", index=False)
        pd.DataFrame(
            {"Player": ["Kane"], "Goals": [44]},
        ).to_excel(writer, sheet_name="Bundesliga", index=False)

    blocks = extract_xlsx(str(path), "stats.xlsx")
    assert len(blocks) == 2
    sheets = {block.sheet_name for block in blocks}
    assert sheets == {"Premier League", "Bundesliga"}
    assert all(block.chunk_type == "table_row" for block in blocks)


def test_xlsx_relevance_sample_per_sheet(tmp_path):
    path = tmp_path / "stats.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Player": ["Haaland"], "Goals": [36]}).to_excel(
            writer, sheet_name="Squad", index=False
        )

    sample = xlsx_relevance_sample(str(path))
    assert "sheet: Squad" in sample
    assert "columns:" in sample
    assert "rows:" in sample
    assert "Haaland" in sample
