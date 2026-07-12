import pandas as pd

from src.ingestion.types import ExtractedBlock


def _serialize_row(columns: list[str], row) -> str:
    parts = [f"{col}: {row[col]}" for col in columns]
    return " | ".join(parts)


def extract_csv(path: str, source_file: str) -> list[ExtractedBlock]:
    df = pd.read_csv(path)
    if df.empty:
        return []

    columns = [str(c) for c in df.columns]
    blocks: list[ExtractedBlock] = []

    for _, row in df.iterrows():
        blocks.append(
            ExtractedBlock(
                text=_serialize_row(columns, row),
                chunk_type="table_row",
                source_file=source_file,
                sheet_name=None,
            )
        )

    return blocks


def extract_xlsx(path: str, source_file: str) -> list[ExtractedBlock]:
    workbook = pd.ExcelFile(path)
    blocks: list[ExtractedBlock] = []

    for sheet_name in workbook.sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet_name)
        if df.empty:
            continue

        columns = [str(c) for c in df.columns]
        for _, row in df.iterrows():
            blocks.append(
                ExtractedBlock(
                    text=_serialize_row(columns, row),
                    chunk_type="table_row",
                    source_file=source_file,
                    sheet_name=sheet_name,
                )
            )

    return blocks


def csv_relevance_sample(path: str) -> str:
    df = pd.read_csv(path, nrows=5)
    columns = ", ".join(str(c) for c in df.columns)
    rows = df.to_csv(index=False).strip()
    return f"columns: {columns}\nrows:\n{rows}"


def xlsx_relevance_sample(path: str) -> str:
    workbook = pd.ExcelFile(path)
    parts: list[str] = []
    for sheet_name in workbook.sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet_name, nrows=5)
        if df.empty:
            continue
        columns = ", ".join(str(c) for c in df.columns)
        rows = df.to_csv(index=False).strip()
        parts.append(f"sheet: {sheet_name}\ncolumns: {columns}\nrows:\n{rows}")
    return "\n\n".join(parts)
