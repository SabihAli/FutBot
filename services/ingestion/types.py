from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractedBlock:
    text: str
    chunk_type: str  # text | pdf_section | table_row | image_derived
    source_file: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    sheet_name: Optional[str] = None
