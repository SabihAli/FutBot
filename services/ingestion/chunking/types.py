from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChunkResult:
    text: str
    chunk_type: str
    source_file: str = ""
    section_heading: str = ""
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    chunk_index: int = 0
    token_count: int = 0
