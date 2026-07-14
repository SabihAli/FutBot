from services.ingestion.chunking.text_chunker import chunk_prose
from services.ingestion.chunking.tokens import count_tokens
from services.ingestion.chunking.types import ChunkResult
from services.ingestion.types import ExtractedBlock


def chunk_pdf_sections(blocks: list[ExtractedBlock], start_index: int = 0) -> list[ChunkResult]:
    results: list[ChunkResult] = []
    index = start_index

    for block in blocks:
        heading = block.section_heading or ""
        prefix = f"[SECTION: {heading}]\n" if heading else ""
        section_chunks = chunk_prose(
            block.text,
            source_file=block.source_file,
            chunk_type="pdf_section",
            section_heading=heading,
            page_number=block.page_number,
            start_index=index,
        )
        for chunk in section_chunks:
            chunk.text = prefix + chunk.text
            chunk.token_count = count_tokens(chunk.text)
            results.append(chunk)
        if section_chunks:
            index = section_chunks[-1].chunk_index + 1

    return results
