"""PDF → 섹션 목록. 페이지 1장 = 섹션 1개 ("페이지 n").

텍스트 레이어가 없는(스캔) 페이지는 PDF_OCR=true 이고 pytesseract·pdf2image 가 있을 때만 OCR 한다.
"""
import io
import logging
from typing import List

from app.config import settings
from worker.parsers.html_page import Section

logger = logging.getLogger(__name__)


def _ocr_pages(data: bytes, page_numbers: List[int]) -> dict:
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        logger.warning("PDF_OCR=true 지만 pytesseract/pdf2image 가 없어 OCR 을 건너뜁니다")
        return {}
    out = {}
    for n in page_numbers:
        try:
            images = convert_from_bytes(data, first_page=n, last_page=n, dpi=200)
            if images:
                out[n] = pytesseract.image_to_string(images[0], lang="kor+eng")
        except Exception as e:  # noqa: BLE001
            logger.warning("OCR failed on page %d: %s", n, e)
    return out


def parse_pdf(data: bytes) -> List[Section]:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(io.BytesIO(data))
    sections: List[Section] = []
    empty_pages: List[int] = []
    texts = {}
    for n, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("pdf text extract failed on page %d: %s", n, e)
            text = ""
        if text:
            texts[n] = text
        else:
            empty_pages.append(n)
    if empty_pages and settings.pdf_ocr:
        texts.update(_ocr_pages(data, empty_pages))
    for n in sorted(texts):
        body = texts[n].strip()
        if body:
            sections.append(Section(heading=f"페이지 {n}", text=body))
    return sections
