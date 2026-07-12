from src.ingestion.extractors import ocr as ocr_module
from src.ingestion.extractors.ocr import ocr_image


def test_ocr_image_disabled(mocker):
    mocker.patch.object(ocr_module, "INGEST_OCR_ENABLED", False)
    assert ocr_image(b"image") is None


def test_ocr_image_unavailable(mocker):
    mocker.patch.object(ocr_module, "INGEST_OCR_ENABLED", True)
    mocker.patch.object(ocr_module, "_tesseract_available", return_value=False)
    assert ocr_image(b"image") is None


def test_ocr_image_filters_low_confidence_and_short_lines(mocker):
    mocker.patch.object(ocr_module, "INGEST_OCR_ENABLED", True)
    mocker.patch.object(ocr_module, "_tesseract_available", return_value=True)
    mocker.patch.object(ocr_module, "INGEST_OCR_MIN_CONFIDENCE", 60)
    mocker.patch.object(ocr_module.Image, "open", return_value=mocker.Mock())
    mocker.patch.object(
        ocr_module.pytesseract,
        "image_to_data",
        return_value={
            "text": ["Arsenal", "2", "-", "1", "Chelsea", "x"],
            "conf": ["95", "90", "90", "90", "92", "40"],
            "line_num": [1, 1, 1, 1, 1, 2],
        },
    )
    mocker.patch.object(ocr_module.pytesseract, "Output", mocker.Mock(DICT="dict"))

    result = ocr_image(b"image")
    assert result == "Arsenal 2 - 1 Chelsea"
