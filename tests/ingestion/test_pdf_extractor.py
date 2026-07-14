import os

import fitz

from services.ingestion.extractors.pdf import count_pdf_vlm_work, extract_pdf

TEST_DATA = os.path.join(os.path.dirname(__file__), "test_data")


def _write_text_pdf(path: str, text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_count_pdf_vlm_work_text_only(tmp_path):
    path = tmp_path / "report.pdf"
    _write_text_pdf(str(path), "Arsenal defeated Chelsea 2-1 at the Emirates Stadium.")

    assert count_pdf_vlm_work(str(path)) == 0


def test_extract_pdf_text_only(tmp_path):
    path = tmp_path / "report.pdf"
    _write_text_pdf(str(path), "Liverpool won the Premier League title.")

    blocks = extract_pdf(str(path), "report.pdf")
    assert len(blocks) >= 1
    assert blocks[0].chunk_type == "pdf_section"
    assert "Liverpool" in blocks[0].text


def test_extract_pdf_describes_scanned_page(tmp_path, mocker):
    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()

    mocker.patch(
        "services.ingestion.extractors.pdf.process_image",
        return_value="[VISUAL DESCRIPTION]\nScoreboard shows Arsenal 2-1 Chelsea.",
    )

    blocks = extract_pdf(str(path), "scan.pdf")
    assert len(blocks) == 1
    assert blocks[0].chunk_type == "image_derived"
    assert "Arsenal" in blocks[0].text
