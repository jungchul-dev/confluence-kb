"""확장자 → 파서 매핑과 허용 목록·크기 상한 검사."""
from typing import Callable, Dict, List, Optional

from app.config import settings
from worker.parsers.html_page import Section
from worker.parsers.office import parse_docx, parse_pptx, parse_text, parse_xlsx
from worker.parsers.pdf import parse_pdf

_PARSERS: Dict[str, Callable[[bytes], List[Section]]] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "pptx": parse_pptx,
    "xlsx": parse_xlsx,
    "md": parse_text,
    "txt": parse_text,
    "csv": parse_text,
}


def extension_of(file_name: str) -> str:
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def parser_for(file_name: str) -> Optional[Callable[[bytes], List[Section]]]:
    ext = extension_of(file_name)
    if ext not in settings.attachment_ext_list:
        return None
    return _PARSERS.get(ext)


def is_allowed(file_name: str, size: int) -> bool:
    if parser_for(file_name) is None:
        return False
    return size <= settings.attachment_max_mb * 1024 * 1024


def parse_attachment(file_name: str, data: bytes) -> List[Section]:
    fn = parser_for(file_name)
    if fn is None:
        return []
    return fn(data)
