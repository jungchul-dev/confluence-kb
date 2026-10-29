"""사용자 식별 — SSO(리버스 프록시)가 넣어 주는 헤더에서 사용자 id 와 그룹을 읽는다.

개발 중에는 헤더가 없으므로 DEV_USER_GROUPS 를 쓴다 ("*" 면 모든 문서 열람).
문서의 allowed_groups 에 "*" 가 있으면 제한 없는 문서다. 검색 쿼리는
  allowed_groups && :groups  OR  '*' = ANY(allowed_groups)
조건으로 필터한다 (services/retrieval.py).
"""
from dataclasses import dataclass
from typing import List

from fastapi import Request

from app.config import settings


@dataclass
class CurrentUser:
    id: str
    groups: List[str]

    @property
    def sees_everything(self) -> bool:
        return "*" in self.groups


def get_current_user(request: Request) -> CurrentUser:
    user_id = (request.headers.get(settings.user_id_header) or "").strip()
    groups_raw = (request.headers.get(settings.user_groups_header) or "").strip()
    if groups_raw:
        groups = [g.strip() for g in groups_raw.split(",") if g.strip()]
    else:
        groups = [g.strip() for g in settings.dev_user_groups.split(",") if g.strip()]
    return CurrentUser(id=user_id or "dev", groups=groups or ["*"])
