from src.ingestion.extractors.image import process_image


def test_process_image_combines_vlm_and_ocr(mocker):
    mocker.patch(
        "src.ingestion.extractors.image._describe_image",
        return_value="Arsenal players in red jerseys pressing high.",
    )
    mocker.patch(
        "src.ingestion.extractors.image.ocr_image",
        return_value="Arsenal 2 - 1 Chelsea\n74'",
    )
    mocker.patch("src.ingestion.extractors.image.INGEST_IMAGE_DELAY_MS", 0)
    mocker.patch("src.ingestion.extractors.image.LLM_PROVIDER", "groq")

    result = process_image(b"fake-image")
    assert "[VISUAL DESCRIPTION]" in result
    assert "Arsenal players" in result
    assert "[TEXT IN IMAGE]" in result
    assert "Arsenal 2 - 1 Chelsea" in result


def test_process_image_omits_empty_ocr_block(mocker):
    mocker.patch(
        "src.ingestion.extractors.image._describe_image",
        return_value="A football pitch with players training.",
    )
    mocker.patch("src.ingestion.extractors.image.ocr_image", return_value=None)
    mocker.patch("src.ingestion.extractors.image.INGEST_IMAGE_DELAY_MS", 0)
    mocker.patch("src.ingestion.extractors.image.LLM_PROVIDER", "groq")

    result = process_image(b"fake-image")
    assert "[VISUAL DESCRIPTION]" in result
    assert "[TEXT IN IMAGE]" not in result


def test_extract_image_file(tmp_path, mocker):
    from src.ingestion.extractors.image import extract_image

    mocker.patch(
        "src.ingestion.extractors.image.process_image",
        return_value="[VISUAL DESCRIPTION]\nMatch photo.",
    )

    path = tmp_path / "shot.png"
    path.write_bytes(b"png-bytes")

    blocks = extract_image(str(path), "shot.png")
    assert len(blocks) == 1
    assert blocks[0].chunk_type == "image_derived"
    assert "Match photo" in blocks[0].text
