"""docx / pptx / xlsx / md / txt → 섹션 목록. 바이트를 받아 메모리에서 처리한다.

- docx: 제목 스타일(Heading N)을 섹션 경계로, 표는 행 단위 문장으로
- pptx: 슬라이드 1장 = 섹션 1개 ("슬라이드 n: 제목")
- xlsx: 시트 1개 = 섹션 1개, 첫 행을 헤더로 보고 "헤더: 값 | ..." 행 문장
"""
import io
import re
from typing import List

from worker.parsers.html_page import Section

_MAX_SHEET_ROWS = 2000


def parse_docx(data: bytes) -> List[Section]:
    from docx import Document  # type: ignore

    doc = Document(io.BytesIO(data))
    sections: List[Section] = []
    heading = None
    buf: List[str] = []

    def flush():
        text = "\n".join(t for t in buf if t.strip()).strip()
        if text:
            sections.append(Section(heading=heading, text=text))
        buf.clear()

    for p in doc.paragraphs:
        style = (p.style.name or "") if p.style is not None else ""
        if re.match(r"Heading [1-3]$", style) or style in ("Title", "제목 1", "제목 2", "제목 3"):
            flush()
            heading = p.text.strip() or None
            continue
        buf.append(p.text)
    for table in doc.tables:
        rows = []
        headers: List[str] = []
        for i, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            if i == 0:
                headers = cells
                continue
            if headers and len(headers) == len(cells):
                rows.append(" | ".join(f"{h}: {v}" for h, v in zip(headers, cells) if v))
            else:
                rows.append(" | ".join(v for v in cells if v))
        if rows:
            buf.append("\n".join(rows))
    flush()
    return sections


def parse_pptx(data: bytes) -> List[Section]:
    from pptx import Presentation  # type: ignore

    prs = Presentation(io.BytesIO(data))
    sections: List[Section] = []
    for n, slide in enumerate(prs.slides, start=1):
        title = ""
        lines: List[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                if getattr(shape, "has_table", False) and shape.has_table:
                    for row in shape.table.rows:
                        cells = [c.text.strip() for c in row.cells]
                        if any(cells):
                            lines.append(" | ".join(v for v in cells if v))
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            if not title and shape == getattr(slide.shapes, "title", None):
                title = text
            else:
                lines.append(text)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"(발표자 노트) {notes}")
        body = "\n".join(lines).strip()
        if title or body:
            sections.append(Section(heading=f"슬라이드 {n}" + (f": {title}" if title else ""), text=body or title))
    return sections


def parse_xlsx(data: bytes) -> List[Section]:
    from openpyxl import load_workbook  # type: ignore

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sections: List[Section] = []
    for ws in wb.worksheets:
        headers: List[str] = []
        lines: List[str] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= _MAX_SHEET_ROWS:
                lines.append(f"... (이후 {ws.max_row - _MAX_SHEET_ROWS}행 생략)")
                break
            cells = ["" if v is None else str(v).strip() for v in row]
            if not any(cells):
                continue
            if i == 0:
                headers = cells
                continue
            if headers and len(headers) == len(cells):
                lines.append(" | ".join(f"{h}: {v}" for h, v in zip(headers, cells) if v and h))
            else:
                lines.append(" | ".join(v for v in cells if v))
        if lines:
            sections.append(Section(heading=f"시트: {ws.title}", text="\n".join(lines)))
    return sections


def parse_text(data: bytes) -> List[Section]:
    text = data.decode("utf-8", errors="replace")
    sections: List[Section] = []
    heading = None
    buf: List[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append(Section(heading=heading, text=body))
        buf.clear()

    for line in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            flush()
            heading = m.group(2).strip() or None
            continue
        buf.append(line)
    flush()
    return sections
