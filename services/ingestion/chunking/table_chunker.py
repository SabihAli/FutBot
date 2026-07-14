from services.ingestion.config import TABLE_CHUNK_ROWS
from services.ingestion.chunking.tokens import count_tokens
from services.ingestion.chunking.types import ChunkResult
from services.ingestion.types import ExtractedBlock


def _header_from_row(row_text: str) -> str:
    columns = []
    for part in row_text.split(" | "):
        if ": " in part:
            columns.append(part.split(": ", 1)[0])
    return " | ".join(columns)


def chunk_table_rows(
    rows: list[ExtractedBlock],
    *,
    start_index: int = 0,
) -> list[ChunkResult]:
    if not rows:
        return []

    source_file = rows[0].source_file
    sheet_name = rows[0].sheet_name
    header = _header_from_row(rows[0].text)
    header_line = f"[TABLE HEADER: {header}]"
    if sheet_name:
        header_line = f"[SHEET: {sheet_name}]\n{header_line}"

    chunks: list[ChunkResult] = []
    chunk_index = start_index

    for i in range(0, len(rows), TABLE_CHUNK_ROWS):
        group = rows[i : i + TABLE_CHUNK_ROWS]
        body = header_line + "\n" + "\n".join(row.text for row in group)
        chunks.append(
            ChunkResult(
                text=body,
                chunk_type="table_row",
                source_file=source_file,
                sheet_name=sheet_name,
                chunk_index=chunk_index,
                token_count=count_tokens(body),
            )
        )
        chunk_index += 1

    return chunks


def chunk_tables(blocks: list[ExtractedBlock], start_index: int = 0) -> list[ChunkResult]:
    grouped: dict[tuple[str, str | None], list[ExtractedBlock]] = {}
    for block in blocks:
        key = (block.source_file, block.sheet_name)
        grouped.setdefault(key, []).append(block)

    results: list[ChunkResult] = []
    index = start_index
    for group_rows in grouped.values():
        group_chunks = chunk_table_rows(group_rows, start_index=index)
        results.extend(group_chunks)
        if group_chunks:
            index = group_chunks[-1].chunk_index + 1
    return results
