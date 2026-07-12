import logging
import time
from concurrent.futures import ThreadPoolExecutor

from src.config import INGEST_IMAGE_DELAY_MS
from src.ingestion.errors import IngestionProviderError
from src.ingestion.extractors.ocr import ocr_image
from src.ingestion.types import ExtractedBlock
from src.llm_components import LLM_PROVIDER, MODEL_GENERATOR, invoke_llm
from src.prompt_loader import get_prompt_parts

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _describe_image(image_bytes: bytes) -> str:
    if LLM_PROVIDER != "groq":
        raise IngestionProviderError()

    system_prompt, user_prompt = get_prompt_parts("VISION")
    description = invoke_llm(
        prompt=user_prompt,
        model_name=MODEL_GENERATOR,
        step="vision",
        system_prompt=system_prompt,
        image=image_bytes,
    )
    return description.strip()


def process_image(image_bytes: bytes) -> str:
    """Two-pass extraction: VLM description and OCR, run concurrently."""
    if LLM_PROVIDER != "groq":
        raise IngestionProviderError()

    with ThreadPoolExecutor(max_workers=2) as executor:
        vlm_future = executor.submit(_describe_image, image_bytes)
        ocr_future = executor.submit(ocr_image, image_bytes)
        description = vlm_future.result()
        ocr_text = ocr_future.result()

    if INGEST_IMAGE_DELAY_MS > 0:
        time.sleep(INGEST_IMAGE_DELAY_MS / 1000.0)

    parts = [f"[VISUAL DESCRIPTION]\n{description}"]
    if ocr_text:
        parts.append(f"[TEXT IN IMAGE]\n{ocr_text}")
    return "\n\n".join(parts)


def describe_image(image_bytes: bytes) -> str:
    """Backward-compatible VLM-only helper used where OCR is not needed."""
    text = _describe_image(image_bytes)
    if INGEST_IMAGE_DELAY_MS > 0:
        time.sleep(INGEST_IMAGE_DELAY_MS / 1000.0)
    return text


def extract_image(path: str, source_file: str) -> list[ExtractedBlock]:
    with open(path, "rb") as handle:
        image_bytes = handle.read()

    if not image_bytes:
        return []

    combined = process_image(image_bytes)
    return [
        ExtractedBlock(
            text=combined,
            chunk_type="image_derived",
            source_file=source_file,
        )
    ]


def is_image_extension(ext: str) -> bool:
    return ext in _IMAGE_EXTENSIONS
