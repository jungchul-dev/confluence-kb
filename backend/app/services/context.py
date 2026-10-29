"""맥락 구성 — 같은 문서의 청크를 순서대로 묶고 문서별 헤더(제목·경로·URL·수정일)를 단다.

총 길이는 LLM_MAX_CONTEXT_TOKENS 안으로 자른다 (토큰 근사: 한글 1자 ≈ 1토큰, 영문 4자 ≈ 1토큰).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from app.config import settings
from app.services.retrieval import Candidate


@dataclass
class SourceDoc:
    index: int  # 답변에 붙는 [n]
    document_id: str
    title: str
    path: str
    url: str
    kind: str
    file_name: str
    updated_at: str
    score: float
    chunks: List[Candidate] = field(default_factory=list)


def approx_tokens(text: str) -> int:
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return (len(text) - ascii_chars) + ascii_chars // 4 + 1


def build_context(candidates: List[Candidate]) -> Tuple[List[SourceDoc], str]:
    """후보를 문서별로 묶어 (출처 목록, 프롬프트에 넣을 맥락 문자열) 을 돌려준다. 문서 순서는 최고 점수순."""
    by_doc: Dict[str, SourceDoc] = {}
    for c in candidates:
        key = str(c.document_id)
        if key not in by_doc:
            by_doc[key] = SourceDoc(
                index=0, document_id=key, title=c.title, path=c.path, url=c.url, kind=c.kind,
                file_name=c.file_name or "", updated_at=c.updated_at.isoformat(), score=c.rerank_score or 0.0,
            )
        doc = by_doc[key]
        doc.chunks.append(c)
        doc.score = max(doc.score, c.rerank_score or 0.0)

    docs = sorted(by_doc.values(), key=lambda d: d.score, reverse=True)
    parts: List[str] = []
    budget = settings.llm_max_context_tokens
    used = 0
    kept: List[SourceDoc] = []
    for i, doc in enumerate(docs, start=1):
        doc.index = i
        doc.chunks.sort(key=lambda c: c.ordinal)
        header = f"[{i}] {doc.title}\n경로: {doc.path}\nURL: {doc.url}\n수정일: {doc.updated_at[:10]}"
        if doc.kind == "attachment" and doc.file_name:
            header += f"\n첨부파일: {doc.file_name}"
        body_parts: List[str] = []
        for c in doc.chunks:
            t = approx_tokens(c.content)
            if used + t > budget:
                break
            body_parts.append(c.content)
            used += t
        if not body_parts:
            break
        parts.append(header + "\n---\n" + "\n\n".join(body_parts))
        kept.append(doc)
    return kept, "\n\n=====\n\n".join(parts)
