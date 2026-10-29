"""Confluence storage HTML → 섹션 목록.

- 헤딩(h1~h3) 기준으로 섹션을 나눈다. 섹션 = (heading, text)
- 표는 행 단위 문장("열1: 값 | 열2: 값")으로 펴서 검색에 걸리게 한다
- 매크로(ac:structured-macro)는 종류별 규칙: code → 코드 블록 그대로, status → "[상태: X]",
  info/note/warning/tip/panel/expand → 본문만, toc/jira 등 본문 없는 매크로 → 생략
- ac:link 는 링크 텍스트만 남긴다
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

_HEADINGS = ("h1", "h2", "h3")
_SKIP_MACROS = {"toc", "jira", "jiraissues", "recently-updated", "children", "pagetree", "contentbylabel", "livesearch", "anchor"}


@dataclass
class Section:
    heading: Optional[str]
    text: str


def _macro_text(tag: Tag) -> str:
    name = tag.get("ac:name", "")
    if name in _SKIP_MACROS:
        return ""
    if name == "code":
        body = tag.find("ac:plain-text-body")
        code = body.get_text() if body else ""
        lang = ""
        for p in tag.find_all("ac:parameter"):
            if p.get("ac:name") == "language":
                lang = p.get_text().strip()
        return f"```{lang}\n{code.strip()}\n```"
    if name == "status":
        for p in tag.find_all("ac:parameter"):
            if p.get("ac:name") == "title":
                return f"[상태: {p.get_text().strip()}]"
        return ""
    body = tag.find("ac:rich-text-body")
    if body:
        title = ""
        for p in tag.find_all("ac:parameter", recursive=False):
            if p.get("ac:name") == "title":
                title = p.get_text().strip()
        inner = _node_text(body)
        return f"{title}\n{inner}" if title else inner
    plain = tag.find("ac:plain-text-body")
    return plain.get_text().strip() if plain else ""


def _table_text(table: Tag) -> str:
    rows = table.find_all("tr")
    if not rows:
        return ""
    headers: List[str] = []
    first_cells = rows[0].find_all(["th", "td"])
    if first_cells and all(c.name == "th" for c in first_cells):
        headers = [_node_text(c).strip() for c in first_cells]
        rows = rows[1:]
    lines: List[str] = []
    for r in rows:
        cells = [_node_text(c).strip() for c in r.find_all(["th", "td"])]
        if not any(cells):
            continue
        if headers and len(headers) == len(cells):
            lines.append(" | ".join(f"{h}: {v}" for h, v in zip(headers, cells) if v))
        else:
            lines.append(" | ".join(v for v in cells if v))
    return "\n".join(lines)


def _node_text(node) -> str:
    """태그 트리를 읽기 좋은 평문으로 바꾼다 (블록 요소 사이 줄바꿈)."""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name == "ac:structured-macro":
        t = _macro_text(node)
        return t + "\n" if t else ""
    if name == "table":
        t = _table_text(node)
        return t + "\n" if t else ""
    if name in ("ac:link", "ri:page", "ri:attachment", "ri:user"):
        body = node.find("ac:link-body") or node.find("ac:plain-text-link-body")
        if body:
            return body.get_text()
        page = node.find("ri:page")
        return page.get("ri:content-title", "") if page else node.get_text()
    if name in ("script", "style"):
        return ""
    parts = [_node_text(c) for c in node.children]
    text = "".join(parts)
    if name in ("p", "div", "li", "br", "tr", "pre", "blockquote", "ul", "ol") or name in _HEADINGS:
        text = text.strip() + "\n"
        if name == "li":
            text = "- " + text
    return text


def _clean(text: str) -> str:
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_storage_html(html: str) -> List[Section]:
    """storage HTML 을 헤딩 단위 섹션으로 나눈다. 헤딩 전의 본문은 heading=None 섹션이 된다."""
    if not html or not html.strip():
        return []
    # html.parser 를 쓴다: lxml 은 Confluence 코드 매크로의 CDATA 본문을 버린다
    soup = BeautifulSoup(html, "html.parser")
    root = soup.body or soup
    sections: List[Section] = []
    current_heading: Optional[str] = None
    buf: List[str] = []

    def flush():
        text = _clean("".join(buf))
        if text:
            sections.append(Section(heading=current_heading, text=text))
        buf.clear()

    for child in root.children:
        if isinstance(child, Tag) and child.name and child.name.lower() in _HEADINGS:
            flush()
            current_heading = _clean(child.get_text()) or None
            continue
        buf.append(_node_text(child))
    flush()
    return sections


def html_to_text(html: str) -> str:
    return "\n\n".join((f"## {s.heading}\n{s.text}" if s.heading else s.text) for s in parse_storage_html(html))
