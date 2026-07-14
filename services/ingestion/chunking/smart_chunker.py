from services.ingestion.chunking.image_chunker import chunk_image_derived
from services.ingestion.chunking.pdf_chunker import chunk_pdf_sections
from services.ingestion.chunking.table_chunker import chunk_tables
from services.ingestion.chunking.text_chunker import chunk_prose
from services.ingestion.chunking.types import ChunkResult
from services.ingestion.types import ExtractedBlock


class SmartChunker:
    def chunk_blocks(self, blocks: list[ExtractedBlock]) -> list[ChunkResult]:
        if not blocks:
            return []

        prose_blocks = [b for b in blocks if b.chunk_type == "text"]
        pdf_blocks = [b for b in blocks if b.chunk_type == "pdf_section"]
        table_blocks = [b for b in blocks if b.chunk_type == "table_row"]
        image_blocks = [b for b in blocks if b.chunk_type == "image_derived"]

        results: list[ChunkResult] = []
        index = 0

        for block in prose_blocks:
            chunks = chunk_prose(
                block.text,
                source_file=block.source_file,
                chunk_type="text",
                page_number=block.page_number,
                sheet_name=block.sheet_name,
                start_index=index,
            )
            results.extend(chunks)
            if chunks:
                index = chunks[-1].chunk_index + 1

        if pdf_blocks:
            pdf_chunks = chunk_pdf_sections(pdf_blocks, start_index=index)
            results.extend(pdf_chunks)
            if pdf_chunks:
                index = pdf_chunks[-1].chunk_index + 1

        if table_blocks:
            table_chunks = chunk_tables(table_blocks, start_index=index)
            results.extend(table_chunks)
            if table_chunks:
                index = table_chunks[-1].chunk_index + 1

        if image_blocks:
            image_chunks = chunk_image_derived(image_blocks, start_index=index)
            results.extend(image_chunks)

        return results

    def chunk_article(self, body: str, source_file: str) -> list[ChunkResult]:
        block = ExtractedBlock(text=body, chunk_type="text", source_file=source_file)
        return self.chunk_blocks([block])
