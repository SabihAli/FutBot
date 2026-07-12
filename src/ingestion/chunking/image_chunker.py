from src.config import CHUNK_TARGET_TOKENS
from src.ingestion.chunking.tokens import count_tokens, truncate_to_tokens
from src.ingestion.chunking.types import ChunkResult
from src.ingestion.types import ExtractedBlock


def chunk_image_derived(
    blocks: list[ExtractedBlock],
    start_index: int = 0,
) -> list[ChunkResult]:
    results: list[ChunkResult] = []
    for offset, block in enumerate(blocks):
        text = block.text
        if count_tokens(text) > CHUNK_TARGET_TOKENS:
            text = truncate_to_tokens(text, CHUNK_TARGET_TOKENS)
        results.append(
            ChunkResult(
                text=text,
                chunk_type="image_derived",
                source_file=block.source_file,
                page_number=block.page_number,
                chunk_index=start_index + offset,
                token_count=count_tokens(text),
            )
        )
    return results
