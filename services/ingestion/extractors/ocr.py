import io
import logging
import shutil

from PIL import Image

from services.ingestion.config import ingest_settings

logger = logging.getLogger(__name__)

try:
    import pytesseract
except ImportError:
    pytesseract = None


def _tesseract_available() -> bool:
    if pytesseract is None:
        return False
    return shutil.which(pytesseract.pytesseract.tesseract_cmd or "tesseract") is not None


def ocr_image(image_bytes: bytes) -> str | None:
    """Run Tesseract OCR and return cleaned text, or None if unavailable/empty."""
    if not ingest_settings.ingest_ocr_enabled:
        return None
    if not _tesseract_available():
        logger.warning("Tesseract OCR is not available; skipping OCR pass.")
        return None

    image = Image.open(io.BytesIO(image_bytes))
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--oem 3 --psm 6",
    )

    lines: list[str] = []
    current_words: list[str] = []
    current_line_num = None

    for i, word in enumerate(data["text"]):
        if not word or not word.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < ingest_settings.ingest_ocr_min_confidence:
            continue

        line_num = data["line_num"][i]
        if current_line_num is None:
            current_line_num = line_num
        if line_num != current_line_num:
            line = " ".join(current_words).strip()
            if len(line) >= 3:
                lines.append(line)
            current_words = [word.strip()]
            current_line_num = line_num
        else:
            current_words.append(word.strip())

    if current_words:
        line = " ".join(current_words).strip()
        if len(line) >= 3:
            lines.append(line)

    if not lines:
        return None
    return "\n".join(lines)
