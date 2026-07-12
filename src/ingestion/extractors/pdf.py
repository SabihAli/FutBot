import logging

import fitz

from src.ingestion.extractors.image import process_image
from src.ingestion.types import ExtractedBlock

logger = logging.getLogger(__name__)

_MIN_PAGE_TEXT_CHARS = 20
_HEADING_MAX_CHARS = 120


def count_pdf_vlm_work(path: str) -> int:
    """Estimate how many VLM calls a PDF will require."""
    doc = fitz.open(path)
    work = 0
    try:
        for page in doc:
            text = page.get_text().strip()
            images = page.get_images(full=True)
            work += len(images)
            if len(text) < _MIN_PAGE_TEXT_CHARS and not images:
                work += 1
    finally:
        doc.close()
    return work


def _extract_page_sections(page, page_num: int, source_file: str) -> list[ExtractedBlock]:
    data = page.get_text("dict")
    lines: list[tuple[str, float, bool]] = []

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            size = max(span.get("size", 0) for span in spans)
            bold = any(span.get("flags", 0) & 2**4 for span in spans)
            lines.append((text, size, bold))

    if not lines:
        return []

    sizes = [line[1] for line in lines]
    modal = max(set(sizes), key=sizes.count)

    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_body: list[str] = []

    for text, size, bold in lines:
        is_heading = (bold or size > modal * 1.15) and len(text) <= _HEADING_MAX_CHARS
        if is_heading and current_body:
            sections.append((current_heading, current_body))
            current_heading = text
            current_body = []
        elif is_heading:
            current_heading = text
        else:
            current_body.append(text)

    if current_body:
        sections.append((current_heading, current_body))

    blocks: list[ExtractedBlock] = []
    for heading, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        blocks.append(
            ExtractedBlock(
                text=body,
                chunk_type="pdf_section",
                source_file=source_file,
                page_number=page_num,
                section_heading=heading or None,
            )
        )
    return blocks


def extract_pdf(path: str, source_file: str) -> list[ExtractedBlock]:
    doc = fitz.open(path)
    blocks: list[ExtractedBlock] = []

    try:
        for page_num, page in enumerate(doc, start=1):
            section_blocks = _extract_page_sections(page, page_num, source_file)
            blocks.extend(section_blocks)

            page_text = page.get_text().strip()
            images = page.get_images(full=True)

            for img in images:
                try:
                    img_bytes = doc.extract_image(img[0])["image"]
                    combined = process_image(img_bytes)
                    blocks.append(
                        ExtractedBlock(
                            text=combined,
                            chunk_type="image_derived",
                            source_file=source_file,
                            page_number=page_num,
                        )
                    )
                except Exception as exc:
                    logger.warning("Failed to describe embedded image on page %s: %s", page_num, exc)

            if len(page_text) < _MIN_PAGE_TEXT_CHARS and not images and not section_blocks:
                try:
                    pix = page.get_pixmap()
                    combined = process_image(pix.tobytes("png"))
                    blocks.append(
                        ExtractedBlock(
                            text=combined,
                            chunk_type="image_derived",
                            source_file=source_file,
                            page_number=page_num,
                        )
                    )
                except Exception as exc:
                    logger.warning("Failed to render/describe page %s: %s", page_num, exc)
    finally:
        doc.close()

    return blocks
