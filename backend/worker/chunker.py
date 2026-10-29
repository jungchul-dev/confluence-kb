"""청킹 — 섹션(헤딩 단위)을 목표 길이로 나누고 경로 접두를 붙인다.

- 섹션이 CHUNK_MAX_TOKENS 보다 길면 문단 경계에서, 그래도 길면 문장 경계에서 나눈다
- 짧은 섹션 여러 개는 CHUNK_TARGET_TOKENS 까지 합친다 (같은 헤딩 안에서만)
- 겹침: 다음 청크 앞에 직전 청크 끝부분을 CHUNK_OVERLAP_RATIO 만큼 둔다
- 접두: "공간 > 상위 > 제목 > 섹션" (첨부는 "제목 > 파일명 > 섹션")
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from app.config import settings
from app.services.context import approx_tokens
from worker.parsers.html_page import Section


@dataclass
class ChunkDraft:
    ordinal: int
    heading: Optional[str]
    content: str  # 접두 포함
    token_count: int


_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s+|\n")


def _split_long(text: str, max_tokens: int) -> List[str]:
    """문단 → 문장 순으로 잘라 max_tokens 이하 조각으로 만든다."""
    if approx_tokens(text) <= max_tokens:
        return [text]
    pieces: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if approx_tokens(para) <= max_tokens:
            pieces.append(para)
            continue
        buf = ""
        for sent in _SENT_SPLIT.split(para):
            sent = sent.strip()
            if not sent:
                continue
            if buf and approx_tokens(buf + " " + sent) > max_tokens:
                pieces.append(buf)
                buf = sent
            else:
                buf = (buf + " " + sent).strip()
            # 한 문장이 상한을 넘으면 글자 수로 강제 분할
            while approx_tokens(buf) > max_tokens:
                cut = max(50, int(len(buf) * max_tokens / approx_tokens(buf)))
                pieces.append(buf[:cut])
                buf = buf[cut:]
        if buf:
            pieces.append(buf)
    return pieces


def _pack(pieces: List[str], target: int) -> List[str]:
    """조각을 target 토큰까지 합친다."""
    out: List[str] = []
    buf = ""
    for p in pieces:
        if buf and approx_tokens(buf + "\n\n" + p) > target:
            out.append(buf)
            buf = p
        else:
            buf = (buf + "\n\n" + p).strip() if buf else p
    if buf:
        out.append(buf)
    return out


def _tail(text: str, ratio: float) -> str:
    n = int(len(text) * ratio)
    if n <= 0:
        return ""
    tail = text[-n:]
    # 단어 중간에서 시작하지 않게 첫 공백 뒤부터
    sp = tail.find(" ")
    return tail[sp + 1:] if 0 <= sp < len(tail) - 1 else tail


def chunk_sections(sections: List[Section], path_prefix: str) -> List[ChunkDraft]:
    target = settings.chunk_target_tokens
    max_tokens = settings.chunk_max_tokens
    overlap = settings.chunk_overlap_ratio
    drafts: List[ChunkDraft] = []
    prev_body = ""
    ordinal = 0
    for sec in sections:
        pieces = _split_long(sec.text, max_tokens)
        bodies = _pack(pieces, target)
        for body in bodies:
            head = f"{path_prefix} > {sec.heading}" if sec.heading else path_prefix
            if prev_body and overlap > 0:
                body_with_overlap = (_tail(prev_body, overlap) + "\n" + body).strip()
            else:
                body_with_overlap = body
            content = f"[{head}]\n{body_with_overlap}"
            drafts.append(ChunkDraft(ordinal=ordinal, heading=sec.heading, content=content, token_count=approx_tokens(content)))
            ordinal += 1
            prev_body = body
    return drafts
