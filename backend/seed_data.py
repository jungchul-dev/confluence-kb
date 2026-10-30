"""테스트용 시드 데이터 생성기 — Confluence 없이 페이지·첨부를 만들어 실제 수집 파이프라인으로 적재한다.

  ./venv/bin/python seed_data.py --reset            # 테이블 드롭·재생성 후 200 페이지 + 100 첨부 적재
  ./venv/bin/python seed_data.py --pages 50 --attachments 20
  ./venv/bin/python seed_data.py --dump ./seed_out   # DB 적재 대신 HTML·첨부 파일을 디렉터리에 저장 (확인용)

생성 → storage HTML 파싱(worker/parsers) → 청킹(worker/chunker) → 임베딩(.env 의 EMBEDDING_*) → DB 적재(worker/indexer)
까지 실제 워커와 같은 코드를 탄다. 첨부는 docx·pptx·xlsx·pdf·md·txt 를 실제 바이너리로 만들어 파서를 거친다.

공간: PROJ(제안·실행) · DEVOPS · CLOUD(프라이빗 클라우드) · NET(네트워크)
동기화 탭에 보이게 하려면 .env 의 CONFLUENCE_SPACES=PROJ,DEVOPS,CLOUD,NET 로 둔다.
"""
import argparse
import asyncio
import io
import logging
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings  # noqa: E402
from app.db.models import SyncRun  # noqa: E402
from app.db.session import AsyncSessionLocal, Base, engine  # noqa: E402
from worker import indexer  # noqa: E402
from worker.chunker import chunk_sections  # noqa: E402
from worker.parsers.html_page import parse_storage_html  # noqa: E402
from worker.parsers.registry import parse_attachment  # noqa: E402

logger = logging.getLogger("seed")
rng = random.Random(20261030)

BASE_URL = "https://wiki.example.com/wiki"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# 데이터 풀
# ──────────────────────────────────────────────────────────────────────────────

PEOPLE = ["김민수", "이서연", "박지훈", "최유진", "정우성", "한지민", "오세훈", "윤아름", "장도윤", "서하늘",
          "임재현", "강수빈", "조현우", "배소정", "신동혁", "문예린", "홍성민", "노지원", "권태양", "류은비"]
ROLES = ["PM", "PL", "아키텍트", "백엔드 개발", "프론트 개발", "DevOps 엔지니어", "DBA", "네트워크 엔지니어", "QA", "보안 담당"]

CUSTOMERS = [
    ("한빛금융그룹", "HBF"), ("대성물류", "DSL"), ("서울메디컬센터", "SMC"), ("코리아에너지", "KEN"),
    ("동양제조", "DYM"), ("미래교육재단", "MEF"), ("청해해운", "CHS"), ("국민통신", "KMT"),
    ("태평양보험", "TPI"), ("한국철도정보", "KRI"), ("남산유통", "NSD"), ("백두건설", "BDC"),
]
SYSTEMS = [
    "차세대 코어뱅킹", "통합 물류관리(WMS/TMS)", "전자의무기록(EMR) 고도화", "발전소 설비 예지보전 플랫폼",
    "스마트팩토리 MES", "통합 학사정보시스템", "선박 운항관리 시스템", "고객센터 상담 플랫폼",
    "보험금 청구 자동심사", "열차 운행정보 통합관제", "옴니채널 커머스", "건설 현장 안전관리 플랫폼",
]
MQ = [("Kafka 3.6", "파티션 기반 순서 보장과 리플레이가 필요"), ("RabbitMQ 3.13", "라우팅 토폴로지가 복잡하고 메시지 단위 ACK 가 필요"),
      ("Redis Streams", "경량 큐로 충분하고 운영 컴포넌트를 줄이고 싶음"), ("NATS JetStream", "경량 바이너리와 멀티테넌시가 필요")]
DBS = [("PostgreSQL 16", "pgvector·JSONB 등 확장성"), ("Oracle 19c", "기존 라이선스 보유, 레거시 PL/SQL 자산"),
       ("MySQL 8.0", "운영 인력 숙련도"), ("MariaDB 10.11", "비용과 호환성")]
CACHES = ["Redis 7 (Sentinel)", "Redis 7 (Cluster)", "Hazelcast 5", "Valkey 8"]
LANGS = [("Java 17 / Spring Boot 3.2", "Gradle"), ("Kotlin 1.9 / Spring Boot 3.2", "Gradle"), ("Python 3.11 / FastAPI", "poetry"),
         ("Go 1.22 / Gin", "go mod"), ("Node.js 20 / NestJS", "pnpm")]
FRONTS = ["React 18 + Vite", "Vue 3 + Vite", "Next.js 14", "Angular 17"]
PLATFORMS = [("Kubernetes 1.29 (RKE2)", "온프레미스"), ("OpenShift 4.14", "온프레미스"), ("Kubernetes 1.29 (kubeadm)", "프라이빗 클라우드"),
             ("Docker Swarm", "소규모")]
CI = ["GitLab CI", "Jenkins", "GitHub Actions (self-hosted runner)", "Tekton"]
MONITOR = ["Prometheus + Grafana", "Zabbix 6", "Datadog", "Elastic APM"]
LOGGING = ["Loki + Promtail", "ELK (Elasticsearch 8)", "OpenSearch 2", "Fluent Bit + Loki"]
SECRETS = ["HashiCorp Vault", "Sealed Secrets", "External Secrets Operator + Vault", "SOPS + age"]
IAC = ["Terraform 1.7 + Ansible 2.16", "Ansible 2.16", "Pulumi (Go)", "Terraform 1.7"]
STORAGE = ["Ceph Quincy (RBD/CephFS)", "NetApp AFF A400 (NFS)", "Dell PowerStore 1200T (iSCSI)", "Pure Storage FlashArray//X (FC)"]
HYPERVISOR = ["OpenStack 2024.1 (Caracal) / KVM", "VMware vSphere 8.0 U2", "Proxmox VE 8.2", "Nutanix AHV"]
SWITCHES = ["Cisco Nexus 93180YC-FX", "Arista 7050SX3", "Juniper QFX5120", "HPE Aruba CX 8325"]
FIREWALLS = ["Palo Alto PA-3260", "Fortinet FortiGate 600F", "Check Point 6600", "Cisco Firepower 2130"]
LBS = ["F5 BIG-IP i5800", "Citrix ADC MPX 8900", "HAProxy 2.8 (keepalived)", "NGINX Plus"]
VENDORS = ["Cisco", "Juniper", "Arista", "HPE", "Dell", "Fortinet", "Palo Alto", "F5"]
RISKS = [
    ("레거시 인터페이스 명세 부재", "현행 시스템 분석 기간을 2주 추가 확보하고 인터페이스 담당자를 고객 측에서 지정"),
    ("데이터 이관 품질", "3회 리허설 이관과 검증 스크립트 자동화"),
    ("성능 목표 미달", "부하 테스트를 개발 중반부터 반복 수행하고 병목 구간을 조기 식별"),
    ("고객 요구사항 변경 빈도", "변경관리위원회(CCB) 격주 운영, 변경 영향도 분석서 의무화"),
    ("핵심 인력 이탈", "모듈별 백업 담당자 지정과 문서화 의무"),
    ("외부 연계 기관 일정 지연", "연계 테스트 일정을 고객과 사전 합의하고 스텁 서버로 선행 개발"),
    ("보안 심사 지연", "설계 단계부터 보안팀 참여, 취약점 점검을 2회로 분리"),
    ("하드웨어 납기 지연", "발주를 착수 직후 진행, 납기 지연 시 임시 클라우드 환경 사용"),
]
REQ_AREAS = ["계정·권한", "거래 처리", "배치 처리", "대외 연계", "보고서·통계", "알림", "감사 로그", "관리자 기능", "모바일 지원", "데이터 이관"]
NFR = [("동시 사용자", lambda: f"{rng.choice([500, 1000, 2000, 3000, 5000])}명"), ("평균 응답 시간", lambda: f"{rng.choice([1, 2, 3])}초 이내"),
       ("가용성", lambda: rng.choice(["99.9%", "99.95%", "99.99%"])), ("RPO / RTO", lambda: rng.choice(["15분 / 1시간", "1시간 / 4시간", "0 / 30분"])),
       ("데이터 보존", lambda: f"{rng.choice([3, 5, 10])}년"), ("배치 처리량", lambda: f"일 {rng.choice([200, 500, 1000, 3000])}만 건")]
GROUPS_RESTRICTED = ["pm-group", "infra-admins", "security-team", "finance-dept"]


# ──────────────────────────────────────────────────────────────────────────────
# HTML 빌더 (Confluence storage format)
# ──────────────────────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def p(*texts: str) -> str:
    return "".join(f"<p>{esc(t)}</p>" for t in texts if t)


def h(level: int, text: str) -> str:
    return f"<h{level}>{esc(text)}</h{level}>"


def ul(items: List[str]) -> str:
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def ol(items: List[str]) -> str:
    return "<ol>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ol>"


def table(headers: List[str], rows: List[List[str]]) -> str:
    th = "".join(f"<th>{esc(x)}</th>" for x in headers)
    trs = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tbody><tr>{th}</tr>{trs}</tbody></table>"


def code(lang: str, body: str) -> str:
    return (f'<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">{lang}</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{body}]]></ac:plain-text-body></ac:structured-macro>")


def status(text: str) -> str:
    return f'<ac:structured-macro ac:name="status"><ac:parameter ac:name="title">{esc(text)}</ac:parameter></ac:structured-macro>'


def panel(kind: str, title: str, body_html: str) -> str:
    return (f'<ac:structured-macro ac:name="{kind}"><ac:parameter ac:name="title">{esc(title)}</ac:parameter>'
            f"<ac:rich-text-body>{body_html}</ac:rich-text-body></ac:structured-macro>")


def toc() -> str:
    return '<ac:structured-macro ac:name="toc"/>'


def meta_table(rows: List[Tuple[str, str]]) -> str:
    return table(["항목", "내용"], [[a, b] for a, b in rows])


def dstr(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def pick(seq, n):
    return rng.sample(list(seq), min(n, len(seq)))


def money(v: int) -> str:
    return f"{v:,}백만 원"


@dataclass
class SeedPage:
    space_key: str
    title: str
    ancestors: List[str]
    html: str
    updated_at: datetime
    version: int = 1
    allowed_groups: List[str] = field(default_factory=lambda: ["*"])
    facts: Dict = field(default_factory=dict)
    page_id: str = ""
    attachments: List["SeedAttachment"] = field(default_factory=list)


@dataclass
class SeedAttachment:
    file_name: str
    data: bytes
    version: int = 1
    att_id: str = ""


@dataclass
class Project:
    code: str
    customer: str
    system: str
    pm: str
    pl: str
    arch: str
    start: datetime
    months: int
    budget: int
    headcount: int
    mq: Tuple[str, str]
    db: Tuple[str, str]
    cache: str
    lang: Tuple[str, str]
    front: str
    platform: Tuple[str, str]
    ci: str
    monitor: str
    logging: str
    secrets: str
    iac: str
    risks: List[Tuple[str, str]]
    nfr: List[Tuple[str, str]]
    members: List[Tuple[str, str]]

    @property
    def name(self) -> str:
        return f"{self.customer} {self.system}"

    @property
    def end(self) -> datetime:
        return self.start + timedelta(days=30 * self.months)


def make_projects(n: int) -> List[Project]:
    out = []
    for i in range(n):
        cust, code = CUSTOMERS[i % len(CUSTOMERS)]
        people = pick(PEOPLE, 8)
        members = [(people[0], "PM"), (people[1], "PL"), (people[2], "아키텍트")] + [(x, rng.choice(ROLES[3:])) for x in people[3:]]
        start = datetime(2025, 1 + (i * 2) % 12, 1 + (i * 7) % 27, tzinfo=timezone.utc)
        out.append(Project(
            code=f"{code}-{2025 + i // 6}", customer=cust, system=SYSTEMS[i % len(SYSTEMS)],
            pm=people[0], pl=people[1], arch=people[2], start=start, months=rng.choice([6, 8, 10, 12, 14]),
            budget=rng.choice([850, 1200, 1800, 2400, 3200, 4500]), headcount=rng.randint(8, 28),
            mq=rng.choice(MQ), db=rng.choice(DBS), cache=rng.choice(CACHES), lang=rng.choice(LANGS), front=rng.choice(FRONTS),
            platform=rng.choice(PLATFORMS), ci=rng.choice(CI), monitor=rng.choice(MONITOR), logging=rng.choice(LOGGING),
            secrets=rng.choice(SECRETS), iac=rng.choice(IAC), risks=pick(RISKS, 4), nfr=[(k, f()) for k, f in NFR],
            members=members,
        ))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 제안 (PROJ > 제안 > 프로젝트명 > 페이지)
# ──────────────────────────────────────────────────────────────────────────────

def proposal_pages(pj: Project) -> List[SeedPage]:
    anc = ["프로젝트 제안", pj.name]
    base_dt = pj.start - timedelta(days=rng.randint(45, 90))
    pages: List[SeedPage] = []

    def add(title, html, days=0, groups=None, facts=None):
        pages.append(SeedPage("PROJ", f"[{pj.code}] {title}", anc, html, base_dt + timedelta(days=days),
                              allowed_groups=groups or ["*"], facts=facts or {}))

    # 1. 제안 개요
    html = toc() + h(1, "사업 개요") + meta_table([
        ("사업명", f"{pj.name} 구축"), ("발주처", pj.customer), ("사업 기간", f"{dstr(pj.start)} ~ {dstr(pj.end)} ({pj.months}개월)"),
        ("사업 예산", money(pj.budget)), ("제안 PM", pj.pm), ("제안 아키텍트", pj.arch), ("투입 인력", f"{pj.headcount}명 (피크 기준)"),
    ]) + p(
        f"{pj.customer}는 현행 {pj.system.split('(')[0].strip()} 시스템의 노후화와 업무 변화에 대응하기 위해 본 사업을 발주하였다. "
        f"현행 시스템은 도입 후 {rng.randint(8, 15)}년이 경과하여 유지보수 비용이 연 {rng.randint(15, 30)}% 증가하고 있으며, "
        f"신규 요구사항 반영에 평균 {rng.randint(3, 6)}개월이 소요되는 문제가 있다.",
        f"본 제안은 {pj.platform[0]} 기반의 컨테이너 플랫폼 위에 {pj.lang[0]} 로 핵심 업무를 재구축하고, "
        f"{pj.mq[0]} 를 통한 이벤트 기반 연계로 시스템 간 결합도를 낮추는 것을 골자로 한다. "
        f"데이터베이스는 {pj.db[0]} 를 채택하며 선정 근거는 '{pj.db[1]}' 이다.",
    ) + h(1, "추진 배경 및 목표") + ul([
        f"업무 처리 시간 {rng.randint(30, 50)}% 단축 (현행 평균 {rng.randint(8, 15)}분 → 목표 {rng.randint(3, 6)}분)",
        f"장애 복구 시간(RTO) {pj.nfr[3][1].split('/')[1].strip()} 이내 달성",
        "모바일·웹 채널 통합으로 사용자 경험 일원화",
        f"연간 운영비 {rng.randint(15, 35)}% 절감 (라이선스 비용 및 인프라 통합)",
        "데이터 표준화와 마스터 데이터 관리(MDM) 체계 정립",
    ]) + h(1, "추진 전략") + p(
        f"1단계에서는 현행 분석과 데이터 모델 표준화를 {rng.randint(6, 10)}주 동안 수행한다. 2단계는 핵심 업무(거래 처리·배치)를 우선 구축하고, "
        f"3단계에서 대외 연계와 보고서를 구축한다. 각 단계 종료 시 고객 검수를 받으며, 검수 기준은 '수행 일정' 페이지의 마일스톤 표를 따른다.",
        f"개발 방법론은 2주 스프린트의 스크럼을 기본으로 하되, 데이터 이관과 인프라 구축은 워터폴로 관리한다. "
        f"스프린트 리뷰에는 {pj.customer} 현업 담당자가 참석하며, 백로그 우선순위는 PM({pj.pm})과 고객 PMO 가 격주로 조정한다.",
    ) + panel("info", "제안 핵심 차별점", ul([
        f"{pj.mq[0]} 기반 이벤트 아키텍처로 대외 연계 장애가 핵심 거래에 전파되지 않음",
        f"{pj.iac} 로 인프라를 코드화하여 DR 환경을 {rng.randint(2, 6)}시간 내 재구성 가능",
        f"{pj.monitor} 기반 통합 관제로 SLA 지표를 실시간 가시화",
    ])) + h(1, "기대 효과") + table(["구분", "현행", "목표", "측정 방법"], [
        ["평균 응답 시간", f"{rng.randint(4, 8)}초", pj.nfr[1][1], "APM 월간 리포트"],
        ["동시 사용자", f"{rng.randint(200, 500)}명", pj.nfr[0][1], "부하 테스트 결과서"],
        ["배포 주기", f"분기 1회", "2주 1회", "배포 이력"],
        ["장애 건수(월)", f"{rng.randint(5, 12)}건", f"{rng.randint(1, 3)}건 이하", "장애 관리 대장"],
    ])
    add("제안 개요", html, 0, facts={"kind": "proposal"})

    # 2. 요구사항 분석
    areas = pick(REQ_AREAS, 7)
    rows = []
    for i, a in enumerate(areas, 1):
        for j in range(rng.randint(2, 4)):
            rows.append([f"FR-{i:02d}-{j+1:02d}", a, rng.choice([
                f"{a} 기능은 역할 기반 접근 제어(RBAC)를 적용해야 한다",
                f"{a} 처리 결과는 감사 로그에 기록되어야 한다",
                f"{a} 화면은 모바일 해상도(360px)에서 정상 동작해야 한다",
                f"{a} 데이터는 일 1회 데이터 웨어하우스로 적재되어야 한다",
                f"{a} 오류 발생 시 담당자에게 5분 이내 알림이 발송되어야 한다",
                f"{a} 는 현행 시스템과 병행 운영 기간 동안 양방향 동기화되어야 한다",
            ]), rng.choice(["상", "상", "중", "하"]), rng.choice(["확정", "확정", "검토중"])])
    html = toc() + h(1, "요구사항 수집 방법") + p(
        f"요구사항은 {dstr(base_dt - timedelta(days=30))} 부터 3주간 {pj.customer} 현업 부서 {rng.randint(4, 9)}개를 대상으로 인터뷰와 워크숍을 통해 수집하였다. "
        f"총 {len(rows) + rng.randint(20, 60)}건의 요구사항이 식별되었으며 이 중 기능 요구사항 {len(rows)}건을 본 페이지에 정리한다. 비기능 요구사항은 별도 절에 기술한다.",
        "요구사항 ID 체계는 FR(기능)-영역번호-일련번호, NFR(비기능)-일련번호를 따른다. 우선순위 '상'은 1단계 오픈 필수, '중'은 2단계, '하'는 안정화 기간 반영 대상이다.",
    ) + h(1, "기능 요구사항") + table(["ID", "영역", "요구사항", "우선순위", "상태"], rows) + h(1, "비기능 요구사항") + table(
        ["ID", "항목", "목표", "검증 방법"],
        [[f"NFR-{i+1:02d}", k, v, rng.choice(["부하 테스트", "DR 모의훈련", "운영 모니터링", "설계 검토"])] for i, (k, v) in enumerate(pj.nfr)]
    ) + h(1, "제약 사항") + ul([
        f"데이터베이스는 고객 보유 라이선스 정책에 따라 {pj.db[0]} 를 사용한다",
        f"모든 서버는 {pj.platform[1]} 환경에 배치하며 퍼블릭 클라우드 사용은 금지된다",
        "개인정보는 암호화 저장(AES-256)하고 키는 HSM 또는 Vault 로 관리한다",
        f"대외 연계는 기관별 전용선 또는 VPN 을 통해서만 허용된다",
        "브라우저는 Chrome·Edge 최신 2개 버전을 지원한다",
    ]) + h(1, "미결 사항") + table(["No", "내용", "담당", "기한"], [
        [str(i + 1), x, rng.choice(PEOPLE), dstr(base_dt + timedelta(days=rng.randint(7, 30)))] for i, x in enumerate([
            "현행 배치 작업 목록과 의존 관계 확인", "대외 연계 기관별 인터페이스 규격서 입수", "모바일 앱 배포 방식(스토어/MDM) 결정", "보고서 양식 표준 확정"])
    ])
    add("요구사항 분석서", html, 5)

    # 3. 목표 아키텍처
    html = toc() + h(1, "아키텍처 개요") + p(
        f"목표 시스템은 {pj.platform[0]} 위에서 동작하는 마이크로서비스 구조로, 업무 도메인별로 {rng.randint(6, 14)}개의 서비스로 분리한다. "
        f"서비스 간 동기 호출은 REST(OpenAPI 3.0)로, 비동기 연계는 {pj.mq[0]} 로 처리한다. {pj.mq[0]} 를 선택한 이유는 '{pj.mq[1]}' 하기 때문이다.",
        f"백엔드는 {pj.lang[0]} (빌드: {pj.lang[1]}), 프론트엔드는 {pj.front} 로 구현한다. 캐시는 {pj.cache} 를 사용하며 세션·조회 캐시·분산 락에 활용한다.",
    ) + h(1, "기술 스택") + table(["계층", "선정 기술", "선정 사유", "대안"], [
        ["컨테이너 플랫폼", pj.platform[0], f"{pj.platform[1]} 운영 경험, 고객 표준", "OpenShift"],
        ["백엔드", pj.lang[0], "팀 숙련도와 생태계", "Kotlin / Spring"],
        ["프론트엔드", pj.front, "컴포넌트 재사용, 빌드 속도", "Vue 3"],
        ["데이터베이스", pj.db[0], pj.db[1], "PostgreSQL"],
        ["메시지 큐", pj.mq[0], pj.mq[1], "RabbitMQ"],
        ["캐시", pj.cache, "HA 구성 용이", "Memcached"],
        ["CI/CD", pj.ci, "고객 보유 도구와 통합", "Jenkins"],
        ["모니터링", pj.monitor, "메트릭·알림 통합", "Zabbix"],
        ["로그", pj.logging, "비용 대비 검색 성능", "ELK"],
        ["시크릿", pj.secrets, "감사·키 교체 자동화", "Sealed Secrets"],
    ]) + h(1, "논리 구성") + h(2, "서비스 분해") + ul([
        f"{a} 서비스 — {rng.choice(['거래 원장', '마스터 데이터', '이벤트 발행', '조회 API', '배치 실행'])} 담당, DB 스키마 분리" for a in pick(REQ_AREAS, 6)
    ]) + h(2, "데이터 흐름") + ol([
        "사용자 요청은 API Gateway(Kong) 에서 인증 토큰(JWT)을 검증한 뒤 각 서비스로 라우팅된다",
        f"거래 서비스는 원장을 {pj.db[0]} 에 저장하고 '거래 완료' 이벤트를 {pj.mq[0]} 토픽에 발행한다",
        "연계 서비스가 이벤트를 소비하여 대외 기관에 전송하고 결과를 별도 토픽으로 회신한다",
        f"조회 서비스는 {pj.cache} 에 읽기 모델을 유지하며 TTL 은 {rng.choice([60, 300, 600])}초로 둔다",
        "배치 서비스는 야간에 정산·집계를 수행하고 결과를 데이터 웨어하우스로 적재한다",
    ]) + h(1, "배포 구성") + code("yaml", f"""# {pj.code} 네임스페이스 구성 (요약)
namespaces:
  - {pj.code.lower()}-prod      # 운영
  - {pj.code.lower()}-stg       # 스테이징
  - {pj.code.lower()}-dev       # 개발
replicas:
  api-gateway: 3
  transaction-svc: {rng.choice([3, 4, 6])}
  query-svc: {rng.choice([2, 3, 4])}
  batch-svc: 1
resources:
  transaction-svc: {{ cpu: "2", memory: "4Gi" }}
  query-svc: {{ cpu: "1", memory: "2Gi" }}
ingress:
  class: nginx
  tls: wildcard-{pj.code.lower()}""") + h(1, "보안 설계") + ul([
        "인증: 고객 SSO(SAML 2.0) 연동, 내부 서비스 간 mTLS",
        "인가: RBAC + 데이터 레벨 권한(부서·지점 단위)",
        "암호화: 전송 TLS 1.3, 저장 AES-256-GCM, 키는 " + pj.secrets,
        "취약점 점검: 개발 중 SAST(SonarQube) 주 1회, 오픈 전 모의해킹 1회",
    ]) + h(1, "가용성 설계") + p(
        f"운영 환경은 2개 가용 존에 분산 배치하며 데이터베이스는 동기 복제(Primary-Standby) 로 구성한다. "
        f"목표 가용성은 {pj.nfr[2][1]}, RPO/RTO 는 {pj.nfr[3][1]} 이다. DR 사이트는 {rng.choice(['비동기 복제', '일 1회 스냅샷'])} 방식으로 유지한다.",
    )
    add("목표 아키텍처", html, 9)

    # 4. 수행 일정
    ms = []
    cur = pj.start
    for name, w in [("착수 및 현행 분석", 6), ("설계", 6), ("1차 개발", 10), ("2차 개발", 8), ("통합 테스트", 5), ("데이터 이관·오픈", 4), ("안정화", 6)]:
        w = max(2, int(w * pj.months / 12))
        ms.append([name, dstr(cur), dstr(cur + timedelta(weeks=w)), f"{w}주", rng.choice(["산출물 검수", "단계 완료 보고", "고객 승인"])])
        cur += timedelta(weeks=w)
    html = toc() + h(1, "단계별 일정") + table(["단계", "시작", "종료", "기간", "완료 기준"], ms) + h(1, "주요 마일스톤") + ul([
        f"M1 착수 보고: {dstr(pj.start + timedelta(days=7))}",
        f"M2 설계 완료(아키텍처·데이터 모델 승인): {ms[1][2]}",
        f"M3 1차 기능 시연: {ms[2][2]}",
        f"M4 통합 테스트 완료: {ms[4][2]}",
        f"M5 오픈: {ms[5][2]}",
        f"M6 안정화 종료 및 최종 검수: {ms[6][2]}",
    ]) + h(1, "산출물") + table(["단계", "산출물", "형식"], [
        ["분석", "현행 분석서, 요구사항 정의서, 요구사항 추적표", "docx, xlsx"],
        ["설계", "아키텍처 정의서, 데이터 모델(ERD), 인터페이스 설계서, 화면 설계서", "docx, pptx, xlsx"],
        ["개발", "소스 코드, 단위 테스트 결과, API 명세(OpenAPI)", "git, html"],
        ["테스트", "통합 테스트 시나리오·결과서, 부하 테스트 결과서", "xlsx, docx"],
        ["이관", "데이터 이관 계획서, 이관 검증 결과", "docx, xlsx"],
        ["운영", "운영 매뉴얼, 장애 대응 절차서, 인수인계서", "docx"],
    ]) + h(1, "일정 관리 방안") + p(
        "일정은 MS Project 로 관리하고 매주 월요일 주간 보고에서 진척률(계획 대비 실적)을 보고한다. 진척률이 계획 대비 5%p 이상 지연되면 PM 이 만회 계획을 수립하여 고객 PMO 에 보고한다.",
        f"크리티컬 패스는 '데이터 모델 확정 → 거래 서비스 개발 → 통합 테스트 → 이관' 이며, 이 경로의 작업은 {pj.pl} PL 이 직접 관리한다.",
    )
    add("수행 일정 및 마일스톤", html, 12)

    # 5. 투입 인력 및 비용 (제한 페이지)
    cost_rows = [["인건비", money(int(pj.budget * 0.62)), "등급별 M/M 단가 적용"], ["HW/SW", money(int(pj.budget * 0.22)), "서버·스토리지·라이선스"],
                 ["교육·기타", money(int(pj.budget * 0.05)), "사용자 교육, 출장"], ["예비비", money(int(pj.budget * 0.11)), "변경 요청 대응"]]
    html = toc() + h(1, "투입 인력") + table(["이름", "역할", "등급", "투입 기간", "M/M"], [
        [n, r, rng.choice(["특급", "고급", "고급", "중급", "초급"]), f"{dstr(pj.start)} ~ {dstr(pj.end)}", str(rng.choice([pj.months, pj.months - 2, pj.months - 4]))] for n, r in pj.members
    ]) + p(f"총 투입 M/M 는 {sum(rng.randint(4, pj.months) for _ in range(pj.headcount))} M/M 이며 피크 인원은 {pj.headcount}명이다. PM {pj.pm} 과 PL {pj.pl} 은 전 기간 상주한다.") + h(1, "비용 산정") + table(
        ["항목", "금액", "비고"], cost_rows + [["합계", money(pj.budget), ""]]
    ) + h(1, "지급 조건") + ul(["착수금 30% (계약 후 14일 이내)", "중도금 40% (설계 완료 및 1차 개발 검수 후)", "잔금 30% (최종 검수 후)"]) + panel(
        "warning", "대외비", p("본 페이지의 단가와 인력 정보는 제안 참여자와 PM 그룹만 열람할 수 있다."))
    add("투입 인력 및 비용", html, 14, groups=["pm-group", "finance-dept"])

    # 6. 리스크 관리
    html = toc() + h(1, "리스크 식별") + table(["ID", "리스크", "영향", "발생 가능성", "대응 방안", "담당"], [
        [f"R-{i+1:02d}", r, rng.choice(["상", "중"]), rng.choice(["상", "중", "하"]), m, rng.choice([pj.pm, pj.pl, pj.arch])] for i, (r, m) in enumerate(pj.risks)
    ]) + h(1, "리스크 관리 절차") + ol([
        "주간 보고에서 리스크 등록부를 검토하고 신규 리스크를 등록한다",
        "영향·가능성이 모두 '상'인 리스크는 이슈로 승격하여 고객 PMO 에 보고한다",
        "대응 방안 실행 여부를 2주마다 점검하고 잔여 리스크를 재평가한다",
    ]) + h(1, "가정 사항") + ul([
        f"{pj.customer} 는 현행 시스템 담당자를 분석 기간 동안 50% 이상 배정한다",
        "인프라(서버·네트워크)는 착수 후 8주 이내 제공된다",
        "대외 연계 기관 테스트 환경은 통합 테스트 시작 4주 전까지 확보된다",
    ]) + h(1, "품질 관리") + p(
        f"코드 품질은 SonarQube 로 측정하며 신규 코드 커버리지 {rng.choice([60, 70, 80])}% 이상, 블로커·크리티컬 이슈 0건을 머지 조건으로 한다. "
        "통합 테스트는 시나리오 기반으로 수행하고 결함은 심각도(S1~S4)로 분류하여 S1·S2 는 오픈 전 100% 조치한다.",
    )
    add("리스크 및 품질 관리 계획", html, 16)
    return pages


# ──────────────────────────────────────────────────────────────────────────────
# 실행 (PROJ > 프로젝트 실행 > 프로젝트명 > 페이지)
# ──────────────────────────────────────────────────────────────────────────────

ISSUE_POOL = [
    ("로그인 세션 만료 후 재로그인 시 이전 화면 복귀 안 됨", "프론트", "S3"), ("대량 조회 시 API 응답 8초 초과", "백엔드", "S2"),
    ("배치 중복 실행으로 정산 데이터 2건 생성", "배치", "S1"), ("첨부파일 업로드 20MB 초과 시 502 오류", "인프라", "S2"),
    ("대외 연계 응답 타임아웃(30초) 미설정", "연계", "S2"), ("한글 파일명 다운로드 시 깨짐", "프론트", "S3"),
    ("권한 없는 사용자가 관리자 메뉴 URL 직접 접근 가능", "보안", "S1"), ("DB 커넥션 풀 고갈로 야간 배치 실패", "DB", "S1"),
    ("캐시 TTL 만료 시점에 조회 응답 지연", "백엔드", "S3"), ("모바일 화면 표 가로 스크롤 안 됨", "프론트", "S4"),
    ("메시지 재처리 시 순서 역전", "연계", "S2"), ("감사 로그에 요청 IP 미기록", "보안", "S3"),
]


def execution_pages(pj: Project, weeks: int) -> List[SeedPage]:
    anc = ["프로젝트 실행", pj.name]
    pages: List[SeedPage] = []

    def add(title, html, days, groups=None):
        pages.append(SeedPage("PROJ", f"[{pj.code}] {title}", anc, html, pj.start + timedelta(days=days), allowed_groups=groups or ["*"]))

    # 킥오프 회의록
    html = meta_table([("일시", f"{dstr(pj.start + timedelta(days=3))} 14:00~16:00"), ("장소", f"{pj.customer} 본사 대회의실"),
                       ("참석자", ", ".join(n for n, _ in pj.members[:5]) + f" / 고객 측 {rng.randint(3, 6)}명"), ("작성자", pj.pl)]) + h(1, "안건") + ol([
        "사업 범위와 일정 재확인", "의사소통 체계 및 보고 주기", "개발 환경·계정 발급 일정", "현행 시스템 분석 협조 요청"]) + h(1, "논의 내용") + p(
        f"고객 PMO 는 오픈 일정({dstr(pj.end - timedelta(weeks=6))})이 고정이며 범위 조정은 가능하다고 밝혔다. PM {pj.pm} 은 2단계 범위를 우선순위 '중' 요구사항 기준으로 재조정하겠다고 답했다.",
        f"개발 서버는 {pj.platform[1]} 환경에 {dstr(pj.start + timedelta(weeks=3))} 까지 제공되며, 그 전까지는 사내 개발 클러스터를 사용하기로 했다. 네트워크 방화벽 오픈 요청은 인프라 담당이 취합한다.",
        f"현행 시스템 분석을 위해 고객 측 담당자 2명이 분석 기간 동안 50% 배정된다. 인터페이스 명세가 없는 연계 {rng.randint(3, 7)}건은 패킷 캡처로 역분석하기로 했다.",
    ) + h(1, "결정 사항") + table(["No", "결정", "근거"], [
        ["1", f"메시지 큐는 {pj.mq[0]} 로 확정", pj.mq[1]], ["2", f"캐시는 {pj.cache} 로 확정", "HA 구성과 운영 경험"],
        ["3", "주간 보고는 매주 월요일 10시", "고객 PMO 정례 회의와 연계"], ["4", f"소스 저장소는 고객 {pj.ci.split()[0]} 사용", "보안 정책"],
    ]) + h(1, "액션 아이템") + table(["내용", "담당", "기한", "상태"], [
        ["개발 계정 발급 요청서 제출", pj.pl, dstr(pj.start + timedelta(days=7)), "완료"],
        ["현행 배치 목록 입수", rng.choice(PEOPLE), dstr(pj.start + timedelta(days=14)), "진행중"],
        ["방화벽 오픈 요청(개발→DB, 개발→MQ)", rng.choice(PEOPLE), dstr(pj.start + timedelta(days=10)), "완료"],
        ["데이터 모델 초안 공유", pj.arch, dstr(pj.start + timedelta(days=21)), "예정"],
    ])
    add("킥오프 회의록", html, 3)

    # 주간 보고 N건
    done = 0
    for w in range(1, weeks + 1):
        d = pj.start + timedelta(weeks=w)
        plan = min(100, int(100 * w / (pj.months * 4.3)))
        actual = max(0, plan - rng.randint(-2, 7))
        issues = pick(ISSUE_POOL, rng.randint(2, 4))
        done += rng.randint(3, 9)
        html = meta_table([("보고 주차", f"{w}주차 ({dstr(d - timedelta(days=6))} ~ {dstr(d)})"), ("작성자", pj.pm), ("전체 진척률", f"계획 {plan}% / 실적 {actual}%"),
                           ("상태", "지연" if plan - actual >= 5 else "정상")]) + h(1, "금주 실적") + ul([
            f"{rng.choice(REQ_AREAS)} 서비스 API {rng.randint(3, 12)}건 개발 완료 (누적 {done}건)",
            f"{rng.choice(['데이터 모델', '화면 설계', '인터페이스 설계', '테스트 시나리오'])} 리뷰 {rng.randint(1, 3)}회 수행",
            f"{pj.ci} 파이프라인에 {rng.choice(['SAST 단계', '컨테이너 스캔', '통합 테스트 단계', '배포 승인 단계'])} 추가",
            rng.choice([f"{pj.db[0]} 파티셔닝 전략 확정 (월 단위 범위 파티션)", f"{pj.mq[0]} 토픽 설계 확정 (토픽 {rng.randint(8, 20)}개, 파티션 {rng.choice([6, 12, 24])})",
                        f"{pj.cache} 장애 조치 테스트 완료", "부하 테스트 1차 수행 (TPS " + str(rng.randint(300, 1500)) + ")"]),
        ]) + h(1, "차주 계획") + ul([
            f"{rng.choice(REQ_AREAS)} 서비스 개발 착수", f"{rng.choice(['단위 테스트', '통합 테스트', '사용자 테스트'])} 시나리오 작성",
            f"고객 리뷰 회의 ({dstr(d + timedelta(days=3))})",
        ]) + h(1, "이슈 및 리스크") + table(["ID", "이슈", "영역", "심각도", "조치", "담당"], [
            [f"I-{w:02d}-{i+1}", t, a, s, rng.choice(["원인 분석 중", "수정 완료, 검증 대기", "고객 협의 필요", "다음 스프린트 반영"]), rng.choice(PEOPLE)] for i, (t, a, s) in enumerate(issues)
        ]) + h(1, "고객 요청 사항") + p(rng.choice([
            f"고객이 {rng.choice(REQ_AREAS)} 화면의 레이아웃 변경을 요청했다. 영향도 분석 결과 {rng.randint(2, 6)} M/D 로 예비비 내에서 수용 가능하다.",
            "고객 PMO 가 오픈 2주 전 리허설 2회 수행을 요청했다. 일정에 반영하기로 했다.",
            f"보안팀이 {pj.secrets} 키 교체 주기를 90일로 단축할 것을 요청했다. 운영 절차에 반영했다.",
            "특이 사항 없음.",
        ])) + h(1, "지표") + table(["지표", "값"], [
            ["완료 API 수", str(done)], ["열린 결함", str(rng.randint(5, 30))], ["단위 테스트 커버리지", f"{rng.randint(55, 85)}%"],
            ["SonarQube 블로커", str(rng.choice([0, 0, 1, 2]))], ["투입 인원", str(min(pj.headcount, 6 + w))],
        ])
        add(f"주간 보고 {w}주차", html, 7 * w)

    # 이슈 목록
    issues = pick(ISSUE_POOL, 8)
    html = h(1, "이슈 관리 대장") + p("프로젝트 전 기간의 주요 이슈를 관리한다. 심각도 S1 은 운영 중단, S2 는 주요 기능 장애, S3 는 부분 오류, S4 는 경미한 UI 문제이다.") + table(
        ["ID", "제목", "영역", "심각도", "등록일", "원인", "조치", "상태"], [
            [f"ISS-{i+1:03d}", t, a, s, dstr(pj.start + timedelta(days=rng.randint(20, 120))),
             rng.choice(["설정 누락", "레이스 컨디션", "쿼리 인덱스 부재", "입력 검증 누락", "타임아웃 미설정", "트랜잭션 범위 오류"]),
             rng.choice(["코드 수정 및 테스트 추가", "인덱스 추가 (복합 인덱스)", "설정값 조정", "재처리 로직 멱등성 보장", "권한 필터 추가"]),
             rng.choice(["해결", "해결", "검증중", "진행중"])] for i, (t, a, s) in enumerate(issues)
        ]) + h(1, "주요 이슈 상세") + "".join(
        h(2, f"ISS-{i+1:03d} {t}") + p(
            f"현상: {t}. {rng.choice(['운영 리허설', '통합 테스트', '사용자 테스트'])} 중 발견되었다.",
            f"원인: " + rng.choice([f"{pj.db[0]} 의 커넥션 풀 최대값이 20 으로 설정되어 야간 배치와 온라인 요청이 경합했다.",
                                 f"{pj.mq[0]} 컨슈머가 재시작되면서 커밋되지 않은 오프셋이 재처리되었다.",
                                 "API Gateway 의 업로드 크기 제한(client_max_body_size)이 기본값 1MB 였다.",
                                 "인가 체크가 메뉴 렌더링 단계에만 있고 API 단계에 없었다."]),
            f"조치: " + rng.choice(["커넥션 풀을 50 으로 상향하고 배치 전용 풀을 분리했다.", "컨슈머에 멱등 키(거래번호)를 두어 중복 처리를 차단했다.",
                                 "Ingress 어노테이션으로 50MB 로 상향했다.", "API 인터셉터에 역할 검사를 추가하고 테스트를 보강했다."]),
        ) for i, (t, a, s) in enumerate(issues[:4]))
    add("이슈 관리 대장", html, 100)

    # 릴리스 노트 2~3건
    for r in range(1, rng.randint(3, 4)):
        d = int(pj.months * 30 * r / 4)
        ver = f"1.{r}.0"
        html = meta_table([("버전", ver), ("배포일", dstr(pj.start + timedelta(days=d))), ("배포 환경", rng.choice(["스테이징", "운영"])), ("배포 방식", rng.choice(["Blue-Green", "Canary 10%→50%→100%", "Rolling"]))]) + h(1, "신규 기능") + ul([
            f"{a}: {rng.choice(['신규 화면 추가', '엑셀 내보내기', '대량 처리 API', '알림 발송', '권한 세분화'])}" for a in pick(REQ_AREAS, rng.randint(3, 6))
        ]) + h(1, "개선") + ul([
            f"조회 API 응답 시간 {rng.randint(30, 60)}% 개선 (인덱스 추가, N+1 제거)", f"{pj.cache} 캐시 적중률 {rng.randint(70, 95)}% 달성",
            "로그 포맷 JSON 표준화", f"컨테이너 이미지 크기 {rng.randint(20, 50)}% 축소 (distroless 베이스)",
        ]) + h(1, "수정된 결함") + table(["ID", "내용"], [[f"ISS-{rng.randint(1, 40):03d}", t] for t, _, _ in pick(ISSUE_POOL, 4)]) + h(1, "배포 절차") + code("bash", f"""# {pj.code} {ver} 배포
kubectl -n {pj.code.lower()}-prod set image deploy/transaction-svc app=registry.example.com/{pj.code.lower()}/transaction-svc:{ver}
kubectl -n {pj.code.lower()}-prod rollout status deploy/transaction-svc --timeout=300s
# 롤백
kubectl -n {pj.code.lower()}-prod rollout undo deploy/transaction-svc""") + h(1, "알려진 문제") + ul([
            rng.choice(["대용량 엑셀(10만 행 이상) 내보내기 시 메모리 사용량 증가 — 다음 버전에서 스트리밍 방식으로 변경 예정",
                        "모바일 Safari 에서 날짜 선택기 표시 오류 — 우회: 직접 입력",
                        "대외 연계 기관 B 의 테스트 환경 불안정으로 일부 시나리오 미검증"]),
        ])
        add(f"릴리스 노트 v{ver}", html, d)

    # 교훈
    html = h(1, "잘된 점") + ul([
        f"{pj.mq[0]} 도입으로 연계 장애가 핵심 거래에 전파되지 않았다. 오픈 후 연계 기관 장애 {rng.randint(2, 5)}회 발생했으나 거래 영향 없음.",
        f"{pj.iac} 로 운영·DR 환경을 코드화하여 DR 모의훈련에서 {rng.randint(1, 3)}시간 내 재구성에 성공했다.",
        "스프린트 리뷰에 현업이 참석하면서 요구사항 오해로 인한 재작업이 크게 줄었다.",
    ]) + h(1, "아쉬운 점") + ul([
        "데이터 이관 리허설을 2회만 수행하여 오픈 당일 코드값 불일치가 발견되었다. 다음 사업에서는 최소 3회를 권장한다.",
        f"{pj.db[0]} 파티셔닝을 개발 후반에 적용하면서 쿼리 수정 범위가 컸다. 데이터 모델 단계에서 결정해야 한다.",
        "부하 테스트 환경이 운영의 50% 규모라 결과 해석에 가정이 많았다.",
    ]) + h(1, "다음 사업에 권고") + ol([
        "착수 시 인터페이스 명세 입수 여부를 계약 조건에 포함", "운영 모니터링 대시보드를 설계 단계부터 정의", "보안 점검을 2회로 분리(설계 검토, 오픈 전)",
    ]) + h(1, "최종 지표") + table(["지표", "목표", "실적"], [
        ["평균 응답 시간", pj.nfr[1][1], f"{rng.choice([0.8, 1.2, 1.5, 2.1])}초"], ["가용성(안정화 기간)", pj.nfr[2][1], rng.choice(["99.95%", "99.97%", "100%"])],
        ["오픈 후 S1 장애", "0건", str(rng.choice([0, 0, 1]))], ["일정 준수", "계획 대비 100%", f"{rng.choice([100, 98, 104])}%"],
    ])
    add("프로젝트 완료 보고 및 교훈", html, pj.months * 30)
    return pages


# ──────────────────────────────────────────────────────────────────────────────
# DevOps (DEVOPS 공간)
# ──────────────────────────────────────────────────────────────────────────────

def _dt(days_ago: int) -> datetime:
    return NOW - timedelta(days=days_ago, hours=rng.randint(0, 20))


def devops_pages(n: int) -> List[SeedPage]:
    pages: List[SeedPage] = []

    def add(title, anc, html, days_ago, groups=None):
        pages.append(SeedPage("DEVOPS", title, anc, html, _dt(days_ago), version=rng.randint(1, 9), allowed_groups=groups or ["*"]))

    ci = rng.choice(CI)
    # 표준 문서
    add("CI/CD 파이프라인 표준", ["플랫폼 표준"], toc() + h(1, "목적") + p(
        f"사내 모든 서비스는 {ci} 로 빌드·테스트·배포한다. 본 문서는 파이프라인 단계, 필수 게이트, 아티팩트 규칙을 정의한다. 예외는 플랫폼팀 승인이 필요하다.") + h(1, "파이프라인 단계") + table(
        ["단계", "내용", "실패 시", "소요 목표"], [
            ["lint", "코드 스타일·정적 분석 (SonarQube, ESLint, golangci-lint)", "머지 차단", "2분"],
            ["unit", "단위 테스트, 커버리지 리포트", "머지 차단", "5분"],
            ["build", "컨테이너 이미지 빌드 (Kaniko, 캐시 사용)", "머지 차단", "5분"],
            ["scan", "이미지 취약점 스캔 (Trivy), CRITICAL 0건", "머지 차단", "3분"],
            ["integration", "testcontainers 기반 통합 테스트", "머지 차단", "10분"],
            ["deploy-stg", "스테이징 자동 배포 (Argo CD 동기화)", "알림", "3분"],
            ["e2e", "스테이징 E2E (Playwright)", "운영 배포 차단", "15분"],
            ["deploy-prod", "운영 배포 (수동 승인 2인)", "롤백", "5분"],
        ]) + h(1, "브랜치 전략") + p("trunk-based 개발을 기본으로 한다. feature 브랜치는 3일 이내 머지하며, 릴리스는 태그(vX.Y.Z)로 만든다. hotfix 는 태그에서 분기하여 main 으로 체리픽한다.") + ul([
        "main: 보호 브랜치, 리뷰어 1인 이상 승인 + 파이프라인 통과 필수", "release/*: 사용하지 않음 (태그로 대체)", "hotfix/*: 운영 긴급 수정, 24시간 내 main 반영"]) + h(1, "이미지 태그 규칙") + code("text", """registry.example.com/<team>/<service>:<git-sha-8>      # 모든 빌드
registry.example.com/<team>/<service>:v1.4.2            # 릴리스 태그
registry.example.com/<team>/<service>:latest            # 금지 (운영 참조 불가)""") + h(1, "파이프라인 예시") + code("yaml", """stages: [lint, unit, build, scan, integration, deploy-stg, e2e, deploy-prod]
variables:
  IMAGE: registry.example.com/$CI_PROJECT_NAMESPACE/$CI_PROJECT_NAME
build:
  stage: build
  image: gcr.io/kaniko-project/executor:v1.21.0-debug
  script:
    - /kaniko/executor --context $CI_PROJECT_DIR --destination $IMAGE:$CI_COMMIT_SHORT_SHA --cache=true
scan:
  stage: scan
  script: trivy image --severity CRITICAL --exit-code 1 $IMAGE:$CI_COMMIT_SHORT_SHA
deploy-prod:
  stage: deploy-prod
  when: manual
  environment: production
  script: argocd app sync $CI_PROJECT_NAME-prod --revision $CI_COMMIT_TAG""") + h(1, "필수 게이트 요약") + ul([
        "단위 테스트 커버리지 신규 코드 70% 이상", "Trivy CRITICAL 0건, HIGH 는 30일 내 조치", "SonarQube Quality Gate 통과", "운영 배포는 승인자 2인(팀 리드 + 운영 담당)"]), 120)

    add("배포 전략 — Blue-Green 과 Canary", ["플랫폼 표준"], toc() + h(1, "개요") + p(
        "서비스 특성에 따라 Blue-Green 또는 Canary 를 선택한다. 상태를 가진 서비스(세션·장기 커넥션)는 Blue-Green, 무상태 API 는 Canary 를 기본으로 한다. Argo Rollouts 를 사용한다.") + h(1, "Blue-Green") + ol([
        "Green(신규) ReplicaSet 을 기동하고 preview 서비스로 스모크 테스트", "승인 후 active 서비스의 selector 를 Green 으로 전환 (수 초)", "Blue 는 30분 유지 후 스케일 다운 (즉시 롤백 대비)"]) + code("yaml", """apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  strategy:
    blueGreen:
      activeService: order-svc
      previewService: order-svc-preview
      autoPromotionEnabled: false
      scaleDownDelaySeconds: 1800""") + h(1, "Canary") + table(["단계", "트래픽", "유지", "자동 분석"], [
        ["1", "10%", "10분", "5xx 비율 < 1%, p95 < 800ms"], ["2", "30%", "10분", "동일"], ["3", "60%", "10분", "동일"], ["4", "100%", "-", "-"]]) + p(
        "자동 분석(AnalysisTemplate)은 Prometheus 에서 5xx 비율과 p95 지연을 조회하며, 조건 위반 시 자동 롤백한다. 분석 실패 알림은 #deploy-alerts 채널로 발송된다.") + h(1, "롤백 기준") + ul([
        "5xx 비율 1% 초과 5분 지속", "p95 응답 시간 기준치 2배 초과", "헬스체크 실패 Pod 20% 초과", "비즈니스 지표(주문 성공률) 전일 대비 5%p 하락"]) + h(1, "DB 스키마 변경과 배포") + p(
        "스키마 변경은 expand-contract 패턴을 따른다. 1차 배포에서 컬럼 추가(expand), 2차 배포에서 코드 전환, 3차에서 구 컬럼 제거(contract). 마이그레이션은 Flyway 로 관리하며 운영 적용 전 스테이징에서 실제 데이터 사본으로 검증한다."), 90)

    add("Kubernetes 클러스터 운영 가이드", ["플랫폼 운영"], toc() + h(1, "클러스터 구성") + table(["클러스터", "용도", "버전", "노드", "CNI", "스토리지"], [
        ["k8s-prod-a", "운영 (존 A)", "1.29.6", "마스터 3 / 워커 12", "Cilium 1.15", "Ceph RBD"], ["k8s-prod-b", "운영 (존 B)", "1.29.6", "마스터 3 / 워커 12", "Cilium 1.15", "Ceph RBD"],
        ["k8s-stg", "스테이징", "1.29.6", "마스터 3 / 워커 6", "Cilium 1.15", "Ceph RBD"], ["k8s-dev", "개발", "1.30.2", "마스터 1 / 워커 4", "Cilium 1.15", "NFS"]]) + h(1, "노드 사양") + table(
        ["역할", "CPU", "메모리", "디스크", "네트워크"], [["마스터", "8 vCPU", "32GB", "200GB SSD", "2×10GbE"], ["워커(일반)", "32 vCPU", "128GB", "500GB NVMe", "2×25GbE"], ["워커(DB)", "48 vCPU", "256GB", "2TB NVMe", "2×25GbE"]]) + h(1, "네임스페이스 정책") + ul([
        "네임스페이스는 <프로젝트코드>-<환경> 형식 (예: hbf-2025-prod)", "ResourceQuota 와 LimitRange 필수 (기본 요청: cpu 100m, memory 128Mi)", "NetworkPolicy 기본 deny-all, 필요한 통신만 허용", "PodSecurity: restricted 프로필 (privileged 금지)"]) + h(1, "업그레이드 절차") + ol([
        "릴리스 노트 검토, deprecated API 사용 여부 점검 (kubent)", "k8s-dev → k8s-stg 순으로 업그레이드 후 2주 관찰", "운영은 존 B 먼저, 노드 drain 은 한 번에 2대까지", "업그레이드 중 PDB 위반 시 중단하고 원인 확인"]) + code("bash", """# 노드 drain 예시
kubectl drain worker-07 --ignore-daemonsets --delete-emptydir-data --timeout=600s
# 업그레이드 (RKE2)
curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION=v1.29.6+rke2r1 sh -
systemctl restart rke2-server
kubectl uncordon worker-07""") + h(1, "용량 관리") + p(
        f"워커 노드 CPU 요청 합계가 할당 가능량의 75% 를 넘으면 노드 증설을 검토한다. 현재 운영 클러스터 사용률은 CPU {rng.randint(50, 70)}%, 메모리 {rng.randint(55, 75)}% 이다. 증설 리드타임은 하드웨어 {rng.randint(4, 8)}주이므로 분기별 용량 계획 회의에서 선행 발주한다.") + h(1, "주요 애드온") + table(["구성 요소", "버전", "역할"], [
        ["Argo CD", "2.11", "GitOps 배포"], ["Argo Rollouts", "1.7", "점진적 배포"], ["cert-manager", "1.14", "TLS 인증서 자동 발급"], ["ingress-nginx", "1.10", "L7 인그레스"],
        ["external-dns", "0.14", "DNS 자동 등록"], ["Velero", "1.13", "클러스터 백업"], ["kube-prometheus-stack", "58", "모니터링"]]), 45)

    add("모니터링 및 알림 표준 (Prometheus · Grafana · Alertmanager)", ["플랫폼 운영"], toc() + h(1, "구성") + p(
        "kube-prometheus-stack 을 클러스터별로 운영하고, Thanos 로 장기 보관(1년)과 전역 조회를 제공한다. Grafana 는 중앙 1대이며 SSO(OIDC) 로 로그인한다.") + h(1, "필수 메트릭") + table(["대상", "메트릭", "수집 방법"], [
        ["애플리케이션", "http_server_requests (count, duration), jvm_*, process_*", "/actuator/prometheus 또는 /metrics"], ["Kubernetes", "kube_pod_*, container_cpu_*, container_memory_*", "kube-state-metrics, cAdvisor"],
        ["노드", "node_cpu_*, node_memory_*, node_filesystem_*", "node-exporter"], ["DB", "pg_stat_*, mysql_global_status_*", "postgres-exporter, mysqld-exporter"], ["MQ", "kafka_consumergroup_lag, rabbitmq_queue_messages", "kafka-exporter, rabbitmq prometheus plugin"]]) + h(1, "알림 등급") + table(
        ["등급", "조건 예", "채널", "대응 시간"], [["P1", "서비스 전체 5xx > 5% 5분, DB Primary 다운", "전화 + Slack #oncall", "15분"], ["P2", "p95 > 2초 10분, 디스크 85%", "Slack #oncall", "1시간"], ["P3", "인증서 만료 14일 전, 파드 재시작 5회/시간", "Slack #alerts", "익일"]]) + h(1, "알림 규칙 예시") + code("yaml", """groups:
- name: service.rules
  rules:
  - alert: HighErrorRate
    expr: sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m])) by (service)
          / sum(rate(http_server_requests_seconds_count[5m])) by (service) > 0.05
    for: 5m
    labels: {severity: P1}
    annotations: {summary: "{{ $labels.service }} 5xx 비율 {{ $value | humanizePercentage }}"}
  - alert: KafkaConsumerLag
    expr: kafka_consumergroup_lag > 10000
    for: 10m
    labels: {severity: P2}""") + h(1, "대시보드 표준") + ul([
        "서비스별 RED 대시보드 (Rate, Errors, Duration) 필수", "SLO 대시보드: 월간 에러 버짓 소진율 표시", "변수: cluster, namespace, service 를 모든 대시보드에 공통 적용"]) + h(1, "보존 정책") + p("Prometheus 로컬 15일, Thanos 객체 스토리지(Ceph RGW) 1년. 다운샘플링은 5분(30일 후)·1시간(90일 후)."), 60)

    add("로그 수집 표준 (Loki · Fluent Bit)", ["플랫폼 운영"], toc() + h(1, "구성") + p(
        "모든 파드 로그는 Fluent Bit DaemonSet 이 수집하여 Loki 로 전송한다. 보존은 운영 90일, 비운영 14일이며 감사 로그는 별도 테넌트로 1년 보관한다.") + h(1, "로그 포맷") + p("애플리케이션 로그는 JSON 한 줄 형식을 따른다. 필수 필드는 아래와 같다.") + code("json", """{"ts":"2026-03-02T11:22:33.123Z","level":"INFO","service":"order-svc","trace_id":"4bf92f3577b34da6","span_id":"00f067aa0ba902b7",
 "user_id":"u-1023","msg":"order created","order_id":"O-20260302-0001","latency_ms":42}""") + table(["필드", "필수", "설명"], [
        ["ts", "예", "ISO-8601 UTC"], ["level", "예", "TRACE/DEBUG/INFO/WARN/ERROR"], ["service", "예", "서비스 이름"], ["trace_id", "예", "OpenTelemetry trace id"], ["msg", "예", "사람이 읽는 메시지"], ["user_id", "아니오", "개인정보 아닌 내부 id 만"]]) + h(1, "금지 사항") + ul([
        "주민번호·카드번호·비밀번호·토큰을 로그에 남기지 않는다 (마스킹 필터 적용)", "스택트레이스는 ERROR 레벨에만, 최대 50줄", "운영에서 DEBUG 레벨 상시 활성화 금지"]) + h(1, "LogQL 예시") + code("logql", """{namespace="hbf-2025-prod", service="order-svc"} |= "ERROR" | json | latency_ms > 1000
sum by (service) (rate({namespace=~".*-prod"} | json | level="ERROR" [5m]))""") + h(1, "Fluent Bit 설정 요약") + code("ini", """[INPUT]
    Name tail
    Path /var/log/containers/*.log
    Parser cri
    Mem_Buf_Limit 50MB
[FILTER]
    Name kubernetes
    Merge_Log On
[OUTPUT]
    Name loki
    Host loki-gateway.monitoring.svc
    Labels namespace=$kubernetes['namespace_name'], service=$kubernetes['labels']['app']"""), 75)

    add("시크릿 관리 — Vault 와 External Secrets", ["플랫폼 표준"], toc() + h(1, "원칙") + ul([
        "시크릿은 Git 에 평문으로 저장하지 않는다", "모든 시크릿은 HashiCorp Vault 에 저장하고 External Secrets Operator 가 Kubernetes Secret 으로 동기화한다", "DB 자격 증명은 Vault Database Engine 으로 동적 발급 (TTL 24시간)", "키 교체 주기: API 키 90일, TLS 1년, DB 루트 180일"]) + h(1, "Vault 구성") + table(["항목", "값"], [
        ["버전", "1.16 (HA, Raft 스토리지, 3노드)"], ["인증", "Kubernetes auth, OIDC(사용자)"], ["경로 규칙", "secret/<team>/<service>/<env>"], ["감사", "파일 + syslog 감사 장치 활성화"], ["백업", "Raft 스냅샷 매시간, 객체 스토리지 보관 30일"]]) + h(1, "ExternalSecret 예시") + code("yaml", """apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata: {name: order-svc-db, namespace: hbf-2025-prod}
spec:
  refreshInterval: 1h
  secretStoreRef: {name: vault-kv, kind: ClusterSecretStore}
  target: {name: order-svc-db}
  data:
    - secretKey: DB_PASSWORD
      remoteRef: {key: secret/hbf/order-svc/prod, property: db_password}""") + h(1, "정책 예시") + code("hcl", """path "secret/data/hbf/order-svc/prod" { capabilities = ["read"] }
path "database/creds/hbf-order-ro"   { capabilities = ["read"] }""") + h(1, "운영 절차") + ol(["신규 서비스는 플랫폼팀에 Vault 경로·정책 생성을 요청한다", "키 교체는 Vault 에서 값 변경 → ESO 가 1시간 내 동기화 → 파드 재시작(Reloader)", "유출 의심 시 즉시 revoke 하고 보안팀에 보고"]), 110, groups=["infra-admins", "security-team"])

    add("IaC 표준 — Terraform 과 Ansible", ["플랫폼 표준"], toc() + h(1, "역할 분담") + table(["도구", "담당 범위", "저장소"], [
        ["Terraform 1.7", "OpenStack 프로젝트·네트워크·VM, DNS, 로드밸런서 VIP", "infra/terraform"], ["Ansible 2.16", "OS 설정, 패키지, RKE2 설치, 에이전트 배포", "infra/ansible"], ["Helm + Argo CD", "Kubernetes 워크로드", "apps/<team>"]]) + h(1, "Terraform 규칙") + ul([
        "상태 파일은 원격 백엔드(S3 호환 Ceph RGW) + 잠금(DynamoDB 대체: PostgreSQL 백엔드)", "환경별 workspace 대신 디렉터리 분리 (envs/prod, envs/stg)", "모듈 버전은 태그로 고정, 모듈 변경 시 CHANGELOG 필수", "plan 결과는 MR 에 자동 코멘트, apply 는 main 머지 후 파이프라인에서만"]) + code("hcl", """module "k8s_workers" {
  source  = "git::https://git.example.com/infra/tf-modules.git//openstack-vm?ref=v2.3.0"
  count   = 12
  name    = "k8s-prod-a-worker-${count.index + 1}"
  flavor  = "m2.8xlarge"
  image   = "ubuntu-22.04-20260115"
  network = module.net_prod.k8s_subnet_id
  tags    = { role = "worker", cluster = "k8s-prod-a" }
}""") + h(1, "Ansible 규칙") + ul(["인벤토리는 동적 인벤토리(OpenStack 플러그인) 사용", "롤은 Molecule 로 테스트", "민감 값은 ansible-vault 대신 Vault lookup 플러그인 사용", "멱등성 검증: --check 모드 통과 필수"]) + code("yaml", """- hosts: k8s_workers
  become: true
  roles:
    - { role: common.baseline, tags: [baseline] }
    - { role: rke2.agent, rke2_version: "v1.29.6+rke2r1", tags: [rke2] }
    - { role: observability.node_exporter, tags: [monitoring] }""") + h(1, "변경 절차") + ol(["MR 생성 → plan/--check 결과 리뷰", "리뷰어 승인(플랫폼팀 1인)", "머지 후 파이프라인 apply, 결과 Slack 통지", "운영 변경은 변경 관리 티켓 번호를 커밋 메시지에 포함"]), 130)

    add("온콜 및 장애 대응 절차", ["플랫폼 운영"], toc() + h(1, "온콜 체계") + p("플랫폼팀은 주 단위 1차·2차 온콜을 운영한다. 1차는 알림을 15분 내 확인하고, 30분 내 해결이 어려우면 2차와 서비스 담당을 호출한다. 온콜 일정은 PagerDuty 에서 관리한다.") + h(1, "장애 등급") + table(
        ["등급", "정의", "보고", "사후 분석"], [["Sev1", "핵심 서비스 전면 중단 또는 데이터 손실", "즉시 경영진·고객 통보", "48시간 내 포스트모템 필수"], ["Sev2", "주요 기능 장애, 우회 가능", "1시간 내 관리자 보고", "1주 내 포스트모템"], ["Sev3", "부분 성능 저하", "일일 보고", "선택"]]) + h(1, "대응 절차") + ol([
        "알림 확인 및 영향 범위 파악 (대시보드, 최근 배포 이력)", "#incident-<날짜> 채널 개설, 커맨더 지정", "완화 조치 우선 (롤백, 스케일 아웃, 트래픽 차단)", "30분마다 상황 공유", "복구 확인 후 채널에 타임라인 정리", "포스트모템 작성 (비난 없는 원칙)"]) + h(1, "자주 쓰는 명령") + code("bash", """# 최근 배포 확인
argocd app history order-svc-prod | tail -5
# 즉시 롤백
kubectl argo rollouts undo order-svc -n hbf-2025-prod
# 파드 상태·이벤트
kubectl -n hbf-2025-prod get pods -o wide | grep -v Running
kubectl -n hbf-2025-prod get events --sort-by=.lastTimestamp | tail -20
# 트래픽 차단 (ingress 어노테이션)
kubectl -n hbf-2025-prod annotate ingress order-svc nginx.ingress.kubernetes.io/whitelist-source-range=10.0.0.0/8 --overwrite""") + h(1, "에스컬레이션 연락망") + table(["역할", "담당", "대체"], [["플랫폼 1차", rng.choice(PEOPLE), rng.choice(PEOPLE)], ["플랫폼 2차", rng.choice(PEOPLE), rng.choice(PEOPLE)], ["DBA", rng.choice(PEOPLE), rng.choice(PEOPLE)], ["네트워크", rng.choice(PEOPLE), rng.choice(PEOPLE)]]), 30, groups=["infra-admins"])

    add("백업 및 복구 정책 (Velero · DB · 객체 스토리지)", ["플랫폼 운영"], toc() + h(1, "백업 대상과 주기") + table(["대상", "도구", "주기", "보존", "저장 위치"], [
        ["Kubernetes 리소스·PV", "Velero 1.13 + CSI 스냅샷", "일 1회 02:00", "30일", "Ceph RGW (버킷 velero-prod)"], ["PostgreSQL", "pgBackRest (full 주 1회, incr 일 1회, WAL 연속)", "연속", "full 4주", "Ceph RGW"],
        ["MySQL", "XtraBackup + binlog", "일 1회", "14일", "Ceph RGW"], ["Vault", "Raft snapshot", "매시간", "30일", "Ceph RGW (암호화)"], ["GitLab", "gitlab-backup", "일 1회", "14일", "NetApp NFS"]]) + h(1, "복구 목표") + table(["시스템", "RPO", "RTO", "최근 모의훈련"], [["핵심 거래 DB", "0 (동기 복제)", "30분", dstr(_dt(40))], ["일반 서비스", "24시간", "4시간", dstr(_dt(70))], ["GitLab", "24시간", "8시간", dstr(_dt(120))]]) + h(1, "복구 절차 (PostgreSQL PITR)") + code("bash", """# 특정 시점 복구
pgbackrest --stanza=hbf-prod --type=time --target="2026-03-02 09:30:00+09" --target-action=promote restore
systemctl start postgresql
psql -c "select pg_is_in_recovery();" """) + h(1, "모의훈련") + p("분기 1회 운영 DB 를 격리 환경에 복구하여 데이터 정합성(행 수, 체크섬)을 검증한다. 결과는 본 페이지 하위에 기록한다. 최근 훈련에서 PostgreSQL 복구 소요 시간은 " + f"{rng.randint(18, 40)}분이었다."), 85)

    # 포스트모템 여러 건
    pm_cases = [
        ("Kafka 브로커 디스크 풀로 인한 주문 이벤트 지연", "Kafka 브로커 3대 중 2대의 로그 디렉터리가 95% 를 넘어 프로듀서 쓰기가 거부됐다", "retention.bytes 미설정 토픽이 생성되어 보존 정책이 적용되지 않았다", "토픽 생성 시 기본 retention 강제, 디스크 80% 알림 추가"),
        ("인증서 만료로 인한 API Gateway 503", "와일드카드 인증서가 만료되어 모든 외부 API 가 503 을 반환했다", "cert-manager 갱신이 DNS01 챌린지 권한 변경으로 실패했으나 알림이 없었다", "인증서 만료 14일 전 P2 알림, cert-manager 실패 이벤트 알림 추가"),
        ("배포 중 ConfigMap 누락으로 결제 서비스 CrashLoop", "Canary 10% 단계에서 신규 파드가 기동 실패하여 자동 롤백됐다", "Helm 차트에서 ConfigMap 키 이름이 변경됐으나 values 가 갱신되지 않았다", "차트 스키마 검증(values.schema.json) 추가, 스테이징 E2E 에 설정 검증 포함"),
        ("Ceph OSD 장애로 PV I/O 지연", "OSD 4개가 동시에 다운되어 PG 복구 트래픽이 급증, RBD 지연이 20배 증가했다", "동일 랙의 전원 분배 장치(PDU) 장애", "OSD 를 랙 단위 CRUSH 규칙으로 분산, 복구 트래픽 제한(osd_max_backfills=1)"),
        ("Argo CD 동기화 폭주로 API 서버 과부하", "Argo CD 가 모든 애플리케이션을 동시에 재동기화하여 kube-apiserver 지연이 발생했다", "Argo CD 업그레이드 후 리소스 캐시가 초기화됐다", "동기화 동시성 제한(controller.sharding), 업그레이드 절차에 캐시 워밍 추가"),
        ("Redis Sentinel 페일오버 실패로 세션 손실", "마스터 장애 시 Sentinel 쿼럼이 충족되지 않아 페일오버가 15분 지연됐다", "Sentinel 3대 중 1대가 유지보수로 내려가 있었다", "Sentinel 5대로 증설, 유지보수 전 쿼럼 확인 체크리스트"),
        ("GitLab 러너 디스크 풀로 전체 파이프라인 실패", "공용 러너 4대의 Docker 캐시가 디스크를 가득 채워 모든 빌드가 실패했다", "docker system prune 크론이 러너 재설치 후 누락됐다", "러너 롤에 정리 크론 포함, 디스크 알림 추가"),
    ]
    for i, (title, impact, cause, action) in enumerate(pick(pm_cases, min(len(pm_cases), max(3, n - 9)))):
        days = rng.randint(10, 300)
        dt = _dt(days)
        dur = rng.randint(25, 180)
        html = meta_table([("장애 일시", f"{dstr(dt)} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"), ("지속 시간", f"{dur}분"), ("등급", rng.choice(["Sev1", "Sev2"])), ("커맨더", rng.choice(PEOPLE)), ("작성자", rng.choice(PEOPLE)), ("상태", "조치 완료")]) + h(1, "요약") + p(impact + f" 영향 범위는 {rng.choice(['주문·결제 API 전체', '외부 API 전체', '결제 서비스', '스토리지를 쓰는 모든 서비스', '모든 배포', '로그인 세션'])} 이며 사용자 영향은 약 {rng.randint(500, 20000):,}건의 요청 실패로 추정된다.") + h(1, "타임라인") + table(["시각", "내용"], [
            ["T+0", "알림 발생 (" + rng.choice(["HighErrorRate", "KafkaConsumerLag", "CertificateExpiry", "PodCrashLooping", "CephHealthWarn"]) + ")"], ["T+5분", "1차 온콜 확인, #incident 채널 개설"], ["T+15분", "원인 후보 식별: " + cause[:40] + "…"],
            [f"T+{dur // 2}분", "완화 조치 적용: " + rng.choice(["롤백", "디스크 정리", "수동 인증서 갱신", "트래픽 차단", "노드 격리"])], [f"T+{dur}분", "정상 복구 확인, 모니터링 지속"]]) + h(1, "근본 원인") + p(cause + ". " + rng.choice(["사전에 감지할 수 있는 알림이 없었다.", "변경 관리 절차에서 영향 분석이 누락됐다.", "런북에 해당 상황의 대응 절차가 없었다."])) + h(1, "잘된 점 / 아쉬운 점") + ul([
            "알림에서 채널 개설까지 5분 이내로 신속했다", "완화 조치 결정에 " + str(rng.randint(10, 40)) + "분이 걸렸다 — 런북 보강 필요", "고객 공지가 " + rng.choice(["적시에 이루어졌다", "30분 지연됐다"])]) + h(1, "조치 항목") + table(["항목", "담당", "기한", "상태"], [
            [action.split(",")[0], rng.choice(PEOPLE), dstr(dt + timedelta(days=7)), "완료"], [action.split(",")[-1].strip() if "," in action else "런북 보강", rng.choice(PEOPLE), dstr(dt + timedelta(days=14)), rng.choice(["완료", "진행중"])],
            ["모의 장애 훈련에 시나리오 추가", rng.choice(PEOPLE), dstr(dt + timedelta(days=30)), rng.choice(["완료", "예정"])]]) + h(1, "재발 방지 검증") + p(rng.choice([
            "조치 후 동일 조건을 스테이징에서 재현하여 알림이 발생하고 자동 조치가 동작함을 확인했다.", "조치 항목 완료 후 2주간 동일 알림이 발생하지 않았다.", "분기 모의 장애 훈련에서 복구 시간이 15분으로 단축됐다."]))
        pages.append(SeedPage("DEVOPS", f"포스트모템 {dstr(dt)} — {title}", ["장애 보고서"], html, dt + timedelta(days=2), version=rng.randint(1, 4)))

    # 런북 몇 개
    runbooks = [
        ("Kafka 컨슈머 랙 급증", ["kafka-consumer-groups.sh --describe 로 랙 확인", "컨슈머 파드 로그에서 리밸런싱·예외 확인", "파티션 수 대비 컨슈머 수 확인, 필요 시 스케일 아웃", "DLQ 적재 여부 확인"], "kafka-consumer-groups.sh --bootstrap-server kafka-0:9092 --describe --group order-consumer"),
        ("PostgreSQL 커넥션 고갈", ["pg_stat_activity 에서 상태별 커넥션 수 확인", "idle in transaction 장기 세션 종료", "애플리케이션 풀 설정(max 50) 확인", "pgbouncer 통계 확인"], "select state, count(*) from pg_stat_activity group by 1;\nselect pg_terminate_backend(pid) from pg_stat_activity where state='idle in transaction' and now()-state_change > interval '10 min';"),
        ("노드 NotReady", ["kubectl describe node 로 조건 확인 (MemoryPressure, DiskPressure)", "kubelet·containerd 상태 확인", "디스크 정리 또는 재시작", "복구 불가 시 drain 후 교체"], "kubectl describe node worker-07 | grep -A5 Conditions\nssh worker-07 'systemctl status rke2-agent; df -h /var/lib/rancher'"),
        ("인그레스 502/504", ["ingress-nginx 로그에서 upstream 오류 확인", "백엔드 파드 readiness 확인", "proxy-read-timeout 값과 요청 처리 시간 비교", "대용량 업로드면 client_max_body_size 확인"], "kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --since=10m | grep -E 'upstream (timed out|prematurely)'"),
    ]
    for title, steps, cmd in runbooks:
        html = h(1, "증상") + p(f"{title} 상황에서의 1차 대응 절차이다. 알림 이름과 대시보드 링크는 모니터링 표준 페이지를 참고한다.") + h(1, "진단 절차") + ol(steps) + h(1, "명령") + code("bash", cmd) + h(1, "완화 조치") + ul([
            rng.choice(["관련 파드 스케일 아웃 (최대 2배)", "문제 세션 강제 종료", "노드 cordon 후 워크로드 이동", "타임아웃 상향 (임시)"]), "조치 후 10분간 지표 관찰", "해결되지 않으면 2차 온콜 호출"]) + h(1, "에스컬레이션") + p("30분 내 해결되지 않으면 2차 온콜과 서비스 담당 개발자를 호출하고, Sev1 이면 커맨더를 지정한다.") + h(1, "관련 문서") + ul(["온콜 및 장애 대응 절차", "모니터링 및 알림 표준", "Kubernetes 클러스터 운영 가이드"])
        pages.append(SeedPage("DEVOPS", f"런북 — {title}", ["런북"], html, _dt(rng.randint(20, 200)), version=rng.randint(1, 6)))

    return pages[:n]


# ──────────────────────────────────────────────────────────────────────────────
# 프라이빗 클라우드 (CLOUD 공간)
# ──────────────────────────────────────────────────────────────────────────────

def cloud_pages(n: int) -> List[SeedPage]:
    pages: List[SeedPage] = []

    def add(title, anc, html, days_ago, groups=None):
        pages.append(SeedPage("CLOUD", title, anc, html, _dt(days_ago), version=rng.randint(1, 12), allowed_groups=groups or ["*"]))

    add("프라이빗 클라우드 전체 구성 개요", ["아키텍처"], toc() + h(1, "개요") + p(
        "사내 프라이빗 클라우드는 OpenStack 2024.1 (Caracal) 과 VMware vSphere 8.0 U2 두 플랫폼으로 운영한다. 신규 워크로드는 OpenStack 을 기본으로 하고, 레거시 Windows 워크로드와 라이선스 제약이 있는 상용 솔루션은 vSphere 에 둔다.",
        "데이터센터는 판교(주)와 부산(DR) 2곳이며, 판교는 3개 존(A·B·C)으로 전원·네트워크를 분리한다. 전체 물리 서버는 " + str(rng.randint(180, 260)) + "대, 가용 vCPU 약 " + f"{rng.randint(9, 14)},000 개, 메모리 약 {rng.randint(60, 90)}TB 이다.") + h(1, "플랫폼 비교") + table(
        ["항목", "OpenStack", "vSphere"], [["용도", "컨테이너 플랫폼 노드, 신규 서비스 VM, 개발·테스트", "레거시 Windows, Oracle RAC, 상용 어플라이언스"], ["하이퍼바이저", "KVM (QEMU 8.2)", "ESXi 8.0 U2"], ["스토리지", "Ceph Quincy (RBD)", "Pure FlashArray//X (FC) + NetApp (NFS)"],
            ["네트워크", "OVN (Geneve), 프로바이더 VLAN", "NSX-T 4.1 / 분산 스위치"], ["규모", "컴퓨트 120대", "ESXi 48대 (클러스터 6개)"], ["관리", "Kolla-Ansible, Horizon, Terraform", "vCenter 8, Aria Operations"]]) + h(1, "존 구성") + table(
        ["존", "위치", "컴퓨트", "스토리지", "용도"], [["pangyo-a", "판교 2층 A열", "40", "Ceph 12 OSD 노드", "운영"], ["pangyo-b", "판교 2층 B열", "40", "Ceph 12 OSD 노드", "운영"], ["pangyo-c", "판교 3층", "24", "Ceph 8 OSD 노드", "개발·스테이징"], ["busan-dr", "부산 IDC", "16", "Ceph 6 OSD 노드", "DR"]]) + h(1, "서비스 카탈로그") + ul([
        "컴퓨트: VM(플레이버 m1~m3, c1, r1), GPU VM(g1, A30 ×1·×2)", "스토리지: 블록(RBD, 3복제), 파일(CephFS, NFS), 객체(RGW S3 호환)", "네트워크: 테넌트 네트워크, 공인/사설 Floating IP, Octavia 로드밸런서, VPNaaS", "데이터베이스: PostgreSQL·MySQL 관리형 (Trove 대신 자체 Ansible 롤)"]) + h(1, "운영 조직") + table(["팀", "담당", "인원"], [["클라우드 플랫폼팀", "OpenStack·Ceph 운영, 용량 계획", "6"], ["가상화팀", "vSphere·NSX 운영", "4"], ["네트워크팀", "물리·언더레이 네트워크", "5"], ["보안팀", "방화벽 정책, 취약점 관리", "3"]]), 20)

    add("OpenStack 컨트롤 플레인 구성", ["OpenStack"], toc() + h(1, "컨트롤러 노드") + p("컨트롤러는 3대로 HA 를 구성한다. 모든 API 는 HAProxy + keepalived VIP(10.10.0.10) 뒤에 두고, 데이터베이스는 MariaDB Galera 3노드, 메시지 큐는 RabbitMQ 3노드 쿼럼 큐를 사용한다. 배포 도구는 Kolla-Ansible 2024.1 이다.") + table(
        ["노드", "IP (mgmt)", "역할", "사양"], [[f"ctl-0{i}", f"10.10.0.1{i}", "API, Scheduler, Conductor, Galera, RabbitMQ, Memcached", "32C / 256GB / 2×960GB SSD"] for i in (1, 2, 3)]) + h(1, "활성 서비스") + table(["서비스", "버전", "비고"], [
        ["Keystone", "2024.1", "LDAP(AD) 연동, 도메인별 분리"], ["Nova", "2024.1", "KVM, CPU 오버커밋 4:1, 메모리 1.2:1"], ["Neutron", "2024.1", "OVN, DVR, 프로바이더 VLAN 100~199"], ["Cinder", "2024.1", "Ceph RBD 백엔드, 볼륨 타입 ssd/hdd"], ["Glance", "2024.1", "Ceph RBD 저장, 이미지 서명 검증"],
        ["Octavia", "2024.1", "Amphora, 이미지 월 1회 갱신"], ["Horizon", "2024.1", "SSO(SAML)"], ["Heat", "2024.1", "제한적 사용, Terraform 권장"], ["Barbican", "2024.1", "볼륨 암호화 키"], ["Ceilometer/Gnocchi", "2024.1", "과금 지표"]]) + h(1, "globals.yml 주요 설정") + code("yaml", """kolla_base_distro: "ubuntu"
openstack_release: "2024.1"
kolla_internal_vip_address: "10.10.0.10"
kolla_external_vip_address: "10.20.0.10"
network_interface: "bond0.10"
neutron_external_interface: "bond1"
neutron_plugin_agent: "ovn"
enable_octavia: "yes"
enable_barbican: "yes"
enable_ceph_rgw: "yes"
nova_compute_virt_type: "kvm"
enable_haproxy: "yes"
enable_mariabackup: "yes" """) + h(1, "업그레이드 이력") + table(["일자", "버전", "비고"], [[dstr(_dt(400)), "2023.1 Antelope → 2023.2 Bobcat", "컨트롤러 순차, 무중단"], [dstr(_dt(200)), "2023.2 → 2024.1 Caracal", "OVN 업그레이드 포함, 4시간"], [dstr(_dt(30)), "보안 패치 (Nova CVE)", "컨테이너 교체"]]) + h(1, "점검 명령") + code("bash", """openstack compute service list --service nova-compute | grep -c enabled
openstack network agent list | grep -v ':-)'
docker exec -it mariadb mysql -e "SHOW STATUS LIKE 'wsrep_cluster_size';"
rabbitmqctl cluster_status | grep -A3 'Running Nodes'"""), 40)

    add("컴퓨트 노드 및 플레이버 정책", ["OpenStack"], toc() + h(1, "컴퓨트 노드 사양") + table(["세대", "모델", "CPU", "메모리", "로컬 디스크", "NIC", "대수"], [
        ["G1 (2022)", "Dell R750", "2×Xeon Gold 6338 (64C)", "512GB", "2×480GB SSD (OS)", "2×25GbE + 2×25GbE", "64"], ["G2 (2024)", "Dell R760", "2×Xeon Platinum 8462Y+ (64C)", "1TB", "2×480GB SSD (OS)", "2×100GbE", "40"], ["GPU", "Dell R750xa", "2×Xeon Gold 6338", "512GB", "2×1.92TB NVMe", "2×100GbE", "8 (A30 ×4)"], ["DR", "HPE DL380 Gen10", "2×Xeon Gold 6248 (40C)", "384GB", "2×480GB SSD", "2×25GbE", "16"]]) + h(1, "플레이버") + table(
        ["이름", "vCPU", "메모리", "루트 디스크", "용도", "호스트 애그리게이트"], [["m1.small", "2", "4GB", "40GB", "개발·소규모", "general"], ["m1.medium", "4", "8GB", "40GB", "일반 서비스", "general"], ["m2.large", "8", "32GB", "80GB", "API 서버", "general"], ["m2.8xlarge", "32", "128GB", "100GB", "k8s 워커", "k8s"],
            ["c1.xlarge", "16", "32GB", "80GB", "CPU 집약", "general"], ["r1.2xlarge", "8", "128GB", "80GB", "메모리 집약·DB", "db"], ["g1.a30", "16", "128GB", "200GB", "GPU 1장", "gpu"], ["g1.a30x2", "32", "256GB", "400GB", "GPU 2장", "gpu"]]) + h(1, "오버커밋 및 스케줄링") + ul([
        "CPU 오버커밋 4:1 (general), 1:1 (db, gpu), 2:1 (k8s)", "메모리 오버커밋 1.2:1 (general), 1:1 (db, gpu, k8s)", "DB 애그리게이트는 NUMA 고정(hw:numa_nodes=1)과 hugepage 사용", "안티어피니티 서버 그룹으로 같은 역할 VM 을 다른 호스트에 분산"]) + code("bash", """openstack flavor create --vcpus 32 --ram 131072 --disk 100 --property aggregate_instance_extra_specs:pool=k8s m2.8xlarge
openstack aggregate create --zone pangyo-a k8s-a
openstack aggregate set --property pool=k8s k8s-a
openstack server group create --policy anti-affinity k8s-prod-a-workers""") + h(1, "유지보수 절차") + ol(["nova-compute 서비스 disable (사유 기록)", "라이브 마이그레이션으로 VM 이동 (openstack server migrate --live-migration)", "펌웨어·커널 패치 및 재부팅", "서비스 enable, 24시간 관찰"]) + h(1, "현재 사용률") + table(["풀", "vCPU 할당률", "메모리 할당률", "비고"], [["general", f"{rng.randint(60, 80)}%", f"{rng.randint(65, 85)}%", "G2 증설 예정"], ["k8s", f"{rng.randint(50, 70)}%", f"{rng.randint(55, 75)}%", ""], ["db", f"{rng.randint(40, 60)}%", f"{rng.randint(50, 70)}%", ""], ["gpu", f"{rng.randint(70, 95)}%", "-", "대기열 운영"]]), 25)

    add("Ceph 스토리지 클러스터 구성 및 운영", ["스토리지"], toc() + h(1, "클러스터 개요") + p("Ceph Quincy 17.2.7 을 cephadm 으로 운영한다. 판교 클러스터는 OSD 노드 32대, OSD 384개(노드당 12×7.68TB NVMe), 원시 용량 약 2.9PB, 3복제 기준 가용 약 950TB 이다. 부산 DR 클러스터는 별도이며 RBD 미러링(저널 기반)으로 핵심 볼륨을 복제한다.") + table(
        ["항목", "값"], [["버전", "Quincy 17.2.7"], ["MON", "5 (ctl-01~03, osd-01, osd-17)"], ["MGR", "3 (active/standby)"], ["OSD", "384 (NVMe 7.68TB)"], ["MDS", "3 (CephFS, active 2)"], ["RGW", "4 (HAProxy 뒤, S3 호환)"], ["퍼블릭 네트워크", "10.30.0.0/22 (100GbE)"], ["클러스터 네트워크", "10.31.0.0/22 (100GbE)"]]) + h(1, "풀 구성") + table(
        ["풀", "타입", "복제/EC", "PG", "용도"], [["volumes", "replicated", "3", "4096", "Cinder 볼륨 (ssd 타입)"], ["vms", "replicated", "3", "2048", "Nova 임시 디스크"], ["images", "replicated", "3", "256", "Glance"], ["k8s-rbd", "replicated", "3", "2048", "Kubernetes PV"], ["cephfs_data", "EC 4+2", "-", "1024", "공유 파일"], ["rgw.buckets.data", "EC 8+3", "-", "2048", "객체 스토리지, 백업"]]) + h(1, "CRUSH 규칙") + p("장애 도메인은 랙(rack) 이다. 복제 풀은 서로 다른 랙 3곳에 복제본을 두며, EC 풀은 호스트 단위로 분산한다. 랙은 존당 4개이며 각 랙에 OSD 노드 4대가 있다.") + code("bash", """ceph osd crush rule create-replicated rack-rule default rack nvme
ceph osd pool set volumes crush_rule rack-rule
ceph config set osd osd_max_backfills 1
ceph config set osd osd_recovery_max_active 2""") + h(1, "운영 기준") + ul(["사용률 70% 에서 증설 계획, 80% 에서 경고, 85% nearfull", "OSD 교체는 한 번에 랙당 1대, 복구 완료 후 다음", "scrub 은 업무 시간 외(22:00~06:00)", "RBD 스냅샷은 Cinder 백업 전 생성, 7일 보관"]) + h(1, "성능 기준치") + table(["워크로드", "IOPS", "지연", "측정"], [["4K 랜덤 읽기 (VM 1대)", f"{rng.randint(40, 80)}K", "0.4ms", "fio, 2026-02"], ["4K 랜덤 쓰기 (VM 1대)", f"{rng.randint(15, 30)}K", "1.1ms", "fio, 2026-02"], ["1M 순차 읽기", f"{rng.randint(3, 6)}GB/s", "-", "fio, 2026-02"]]) + h(1, "점검 명령") + code("bash", """ceph -s
ceph df
ceph osd df tree | sort -k17 -n | tail
ceph health detail
rbd mirror pool status volumes --verbose"""), 35)

    add("vSphere 클러스터 구성", ["VMware"], toc() + h(1, "구성") + table(["클러스터", "ESXi", "용도", "CPU", "메모리", "데이터스토어"], [
        ["prod-win", "10", "Windows 서버, AD, 파일 서버", "2×32C", "768GB", "Pure FC (ds-prod-01~04)"], ["prod-db", "8", "Oracle RAC, MSSQL", "2×32C", "1TB", "Pure FC (ds-db-01~02)"], ["prod-app", "12", "상용 솔루션(ERP, 그룹웨어)", "2×32C", "768GB", "Pure FC"], ["mgmt", "4", "vCenter, NSX Manager, Aria", "2×24C", "512GB", "NetApp NFS"], ["stg", "8", "스테이징", "2×32C", "512GB", "NetApp NFS"], ["dr-busan", "6", "DR (SRM)", "2×24C", "512GB", "Pure FC (복제)"]]) + h(1, "표준 설정") + ul([
        "DRS 완전 자동화(중간), HA 활성화, 승인 제어 25% 예약", "EVC 모드 Intel Ice Lake", "vMotion 전용 VMkernel (25GbE), 스토리지 FC 32Gb 듀얼 패브릭", "VM 하드웨어 버전 20, VMware Tools 자동 업데이트", "스냅샷은 72시간 이내 삭제, 3단계 초과 금지"]) + h(1, "NSX-T 구성") + p("NSX-T 4.1 로 오버레이 세그먼트와 분산 방화벽(DFW)을 운영한다. Tier-0 게이트웨이는 물리 코어와 BGP 피어링(AS 65010), Tier-1 은 테넌트(사업부)별로 둔다. DFW 는 존(zone) 태그 기반 정책을 적용한다.") + table(
        ["세그먼트", "VLAN/VNI", "서브넷", "용도"], [["seg-prod-web", "VNI 70001", "172.16.10.0/24", "웹 계층"], ["seg-prod-app", "VNI 70002", "172.16.20.0/24", "앱 계층"], ["seg-prod-db", "VNI 70003", "172.16.30.0/24", "DB 계층"], ["seg-mgmt", "VLAN 50", "10.50.0.0/24", "관리"]]) + h(1, "패치 정책") + p("ESXi 패치는 vLCM 베이스라인으로 분기 1회, 긴급 보안 패치는 2주 내 적용한다. 순서는 stg → mgmt → prod-app → prod-win → prod-db 이며, 호스트별 유지보수 모드 진입 후 적용한다.") + h(1, "라이선스") + table(["제품", "수량", "만료"], [["vSphere Enterprise Plus", "96 CPU", dstr(NOW + timedelta(days=rng.randint(100, 400)))], ["vCenter Standard", "2", "동일"], ["NSX Enterprise Plus", "96 CPU", "동일"], ["SRM", "75 VM", "동일"]]), 50, groups=["infra-admins"])

    add("테넌트 프로젝트 및 쿼터 정책", ["OpenStack"], toc() + h(1, "프로젝트 구조") + p("Keystone 도메인은 사업부 단위(biz-finance, biz-logistics, biz-platform, biz-rnd)로 두고, 프로젝트는 '<사업부>-<시스템>-<환경>' 으로 만든다. 사용자는 AD 그룹과 매핑되며 역할은 admin / member / reader 3종이다.") + h(1, "기본 쿼터") + table(["항목", "개발", "스테이징", "운영"], [
        ["인스턴스", "20", "30", "100"], ["vCPU", "80", "160", "800"], ["메모리", "256GB", "512GB", "3TB"], ["볼륨", "40", "60", "200"], ["볼륨 용량", "2TB", "5TB", "40TB"], ["Floating IP", "5", "10", "30"], ["보안 그룹", "20", "30", "100"], ["로드밸런서", "2", "5", "20"]]) + h(1, "쿼터 증설 절차") + ol(["서비스 데스크에 '쿼터 증설' 티켓 (사유, 기간, 수량)", "클라우드 플랫폼팀 용량 검토 (가용률 75% 미만이면 승인)", "운영 프로젝트는 사업부장 승인 추가", "적용 후 티켓에 명령 결과 첨부"]) + code("bash", """openstack quota set --cores 1200 --ram 4194304 --instances 150 biz-finance-corebank-prod
openstack quota show biz-finance-corebank-prod""") + h(1, "과금") + p("월 과금은 Gnocchi 지표 기반으로 vCPU·메모리·볼륨·Floating IP 를 시간 단위로 집계한다. 단가는 vCPU 시간당 12원, 메모리 GB 시간당 6원, SSD 볼륨 GB 월 90원이다. 사업부별 청구서는 매월 3일 발송된다.") + h(1, "현재 프로젝트 수") + table(["도메인", "프로젝트", "VM", "vCPU 할당"], [["biz-finance", str(rng.randint(8, 15)), str(rng.randint(150, 300)), f"{rng.randint(1200, 2400)}"], ["biz-logistics", str(rng.randint(5, 10)), str(rng.randint(80, 180)), f"{rng.randint(600, 1400)}"], ["biz-platform", str(rng.randint(10, 20)), str(rng.randint(200, 400)), f"{rng.randint(2000, 3600)}"], ["biz-rnd", str(rng.randint(10, 25)), str(rng.randint(100, 300)), f"{rng.randint(800, 2000)}"]]), 15)

    add("이미지 관리 정책 (Glance)", ["OpenStack"], toc() + h(1, "표준 이미지") + table(["이름", "OS", "갱신 주기", "비고"], [["ubuntu-22.04-YYYYMMDD", "Ubuntu 22.04 LTS", "월 1회", "기본, cloud-init, qemu-guest-agent"], ["ubuntu-24.04-YYYYMMDD", "Ubuntu 24.04 LTS", "월 1회", "신규 권장"], ["rocky-9-YYYYMMDD", "Rocky Linux 9", "월 1회", "RHEL 호환 필요 시"], ["windows-2022-YYYYMMDD", "Windows Server 2022", "분기 1회", "virtio 드라이버 포함, KMS 활성화"]]) + h(1, "빌드 파이프라인") + p("이미지는 Packer 로 빌드하고 CIS 벤치마크 Level 1 하드닝을 적용한다. 빌드 후 OpenSCAP 스캔과 부팅 테스트를 거쳐 Glance 에 서명(Barbican 키)하여 등록한다. 이전 이미지는 deactivated 상태로 3개월 보관 후 삭제한다.") + code("bash", """packer build -var "version=$(date +%Y%m%d)" ubuntu-22.04.pkr.hcl
openstack image create --disk-format qcow2 --container-format bare --file ubuntu-22.04-20260301.qcow2 \\
  --property os_distro=ubuntu --property os_version=22.04 --property hw_qemu_guest_agent=yes \\
  --property img_signature_hash_method=SHA-256 --property img_signature_key_type=RSA-PSS ubuntu-22.04-20260301""") + h(1, "이미지 속성 표준") + ul(["hw_disk_bus=scsi, hw_scsi_model=virtio-scsi", "hw_vif_multiqueue_enabled=true", "os_require_quiesce=yes (스냅샷 정합성)", "hw_machine_type=q35"]) + h(1, "사용자 이미지") + p("테넌트가 직접 올리는 이미지는 프로젝트 범위(private)로만 허용하며, 공유(shared/public)는 플랫폼팀 검토 후 가능하다. 최대 크기는 100GB 이다."), 70)

    add("용량 계획 2026 하반기", ["용량 계획"], toc() + h(1, "현황") + table(["자원", "총량", "할당", "할당률", "실사용률"], [["vCPU", "12,288", f"{rng.randint(8000, 9500):,}", "~75%", f"{rng.randint(35, 50)}%"], ["메모리", "72TB", f"{rng.randint(48, 58)}TB", "~75%", f"{rng.randint(50, 65)}%"], ["Ceph 가용", "950TB", f"{rng.randint(600, 720)}TB", "~70%", "-"], ["GPU (A30)", "32", str(rng.randint(26, 31)), "~90%", f"{rng.randint(60, 80)}%"]]) + h(1, "수요 예측") + p("하반기 신규 사업 4건(코어뱅킹, MES, EMR, 커머스)의 요청량을 합산하면 vCPU 2,400, 메모리 14TB, 스토리지 220TB 가 추가로 필요하다. 기존 성장률(월 2.5%)을 더하면 연말 할당률이 vCPU 95%, 스토리지 92% 에 도달한다.") + h(1, "증설 계획") + table(["항목", "수량", "사양", "예산", "납기"], [["컴퓨트 G2", "24대", "R760, 64C/1TB/2×100GbE", money(rng.randint(1800, 2600)), f"{rng.randint(6, 10)}주"], ["Ceph OSD 노드", "8대", "12×7.68TB NVMe", money(rng.randint(900, 1300)), f"{rng.randint(6, 10)}주"], ["GPU 노드", "4대", "R750xa, A30 ×4", money(rng.randint(600, 900)), f"{rng.randint(8, 14)}주"], ["ToR 스위치", "4대", "100GbE 32포트", money(rng.randint(200, 320)), "6주"]]) + h(1, "리스크") + ul(["GPU 납기 지연 시 R&D 워크로드 대기열 증가 — 클라우드 임차로 대체 검토", "존 C 전력 여유 15% — 랙 추가 전 전력 증설 필요", "Ceph 증설 시 리밸런싱으로 1~2주간 성능 저하 — 야간 backfill 제한"]) + h(1, "결정 사항") + p(f"{dstr(_dt(20))} 인프라 운영위원회에서 컴퓨트 G2 24대와 OSD 8대 발주를 승인했다. GPU 노드는 R&D 예산으로 분리 검토한다."), 20, groups=["infra-admins", "finance-dept"])

    add("DR 구성 및 전환 절차 (판교 → 부산)", ["DR"], toc() + h(1, "구성") + p("부산 DR 사이트는 판교 운영의 약 25% 규모로 핵심 시스템만 보호한다. OpenStack 은 별도 리전(busan)으로 운영하며, 볼륨은 RBD 미러링(저널, RPO 5분 이내), DB 는 애플리케이션 레벨 복제(PostgreSQL 스트리밍, Oracle Data Guard)로 동기화한다. vSphere 는 SRM + 어레이 복제(Pure ActiveDR)를 쓴다.") + table(
        ["계층", "복제 방식", "RPO", "RTO", "대상"], [["블록 스토리지", "RBD 저널 미러링", "5분", "1시간", "핵심 VM 볼륨 120개"], ["PostgreSQL", "스트리밍 복제(비동기)", "1분", "30분", "코어뱅킹, 커머스"], ["Oracle", "Data Guard (최대 성능)", "1분", "30분", "ERP"], ["vSphere VM", "SRM + ActiveDR", "15분", "2시간", "AD, 그룹웨어"], ["객체 스토리지", "RGW 멀티사이트", "15분", "-", "백업, 이미지"]]) + h(1, "전환 절차 (계획 전환)") + ol([
        "변경 관리 승인, 관계자 소집, 공지 (T-24h)", "판교 쓰기 중단: 애플리케이션 읽기 전용 모드 (T-0)", "DB 복제 지연 0 확인 후 부산 승격 (pg_ctl promote / Data Guard switchover)", "RBD 미러 demote(판교) → promote(부산)", "부산 리전에서 VM 기동 (Terraform envs/busan apply)", "DNS 전환 (TTL 60초, GSLB 가중치 변경)", "서비스 검증 체크리스트 수행, 공지"]) + code("bash", """# RBD 미러 승격
rbd mirror image demote volumes/volume-<id>     # 판교
rbd mirror image promote volumes/volume-<id>    # 부산
# PostgreSQL 승격
sudo -u postgres pg_ctl promote -D /var/lib/postgresql/16/main""") + h(1, "모의훈련 결과") + table(["일자", "범위", "RTO 목표", "실측", "이슈"], [[dstr(_dt(100)), "코어뱅킹 전체", "1시간", f"{rng.randint(45, 75)}분", "DNS 캐시로 일부 지점 10분 지연"], [dstr(_dt(280)), "커머스 DB", "30분", f"{rng.randint(20, 40)}분", "없음"], [dstr(_dt(460)), "vSphere AD", "2시간", f"{rng.randint(90, 150)}분", "SRM 복구 계획 IP 설정 누락"]]) + h(1, "복귀(failback)") + p("부산에서 판교로 복귀는 역방향 복제를 재설정한 뒤 동일 절차로 수행한다. 복귀 전 판교 데이터는 전량 폐기하고 부산 기준으로 재동기화한다."), 60, groups=["infra-admins"])

    add("하이퍼바이저 보안 패치 절차", ["운영 절차"], toc() + h(1, "적용 원칙") + ul(["CVSS 9.0 이상: 7일 내, 7.0~8.9: 30일 내, 그 외: 분기 패치", "컴퓨트 노드는 라이브 마이그레이션으로 무중단, 컨트롤러는 순차 재시작", "패치 전 Ceph HEALTH_OK, 노드 그룹당 1대씩"]) + h(1, "절차") + ol(["보안팀 취약점 통보 접수, 영향 노드 목록 작성", "스테이징 존(pangyo-c)에서 선적용 및 48시간 관찰", "운영 존 A → B 순으로 야간 적용", "패치 결과를 변경 관리 티켓에 기록"]) + code("bash", """# Ansible 플레이북
ansible-playbook -i inventories/pangyo-a playbooks/patch-compute.yml --limit 'cmp-a-0[1-4]' -e reboot=true
# 패치 후 검증
openstack hypervisor list --long | grep cmp-a-0
virsh version; uname -r""") + h(1, "최근 적용 이력") + table(["일자", "대상", "내용", "결과"], [[dstr(_dt(12)), "컴퓨트 120대", "커널 6.8.0-45 (CVE-2026-xxxx)", "완료, 이슈 없음"], [dstr(_dt(45)), "컨트롤러 3대", "OpenSSL 3.0.14", "완료"], [dstr(_dt(90)), "ESXi 48대", "ESXi 8.0 U2c", "완료, 1대 PSOD 후 재적용"]]), 12)

    add("Octavia 로드밸런서 사용 가이드", ["OpenStack"], toc() + h(1, "개요") + p("테넌트는 Octavia(Amphora 드라이버)로 L4/L7 로드밸런서를 직접 생성할 수 있다. Amphora 는 VM 2대(ACTIVE_STANDBY) 로 생성되며 프로젝트 쿼터에서 차감된다. 외부 노출은 Floating IP 를 VIP 에 연결한다.") + h(1, "생성 예시") + code("bash", """openstack loadbalancer create --name web-lb --vip-subnet-id prod-web-subnet
openstack loadbalancer listener create --name https --protocol TERMINATED_HTTPS --protocol-port 443 \\
  --default-tls-container-ref $(openstack secret list -f value -c "Secret href" --name web-cert) web-lb
openstack loadbalancer pool create --name web-pool --lb-algorithm ROUND_ROBIN --listener https --protocol HTTP
openstack loadbalancer member create --subnet-id prod-web-subnet --address 172.16.10.11 --protocol-port 8080 web-pool
openstack loadbalancer healthmonitor create --delay 5 --timeout 3 --max-retries 3 --type HTTP --url-path /healthz web-pool""") + h(1, "제약") + ul(["리스너당 최대 동시 연결 50,000 (Amphora 플레이버 기준)", "TLS 인증서는 Barbican 에 저장, 자체 서명은 개발만", "L7 정책은 리스너당 20개까지", "UDP 는 지원하나 헬스체크는 UDP-CONNECT 만"]) + h(1, "운영") + p("Amphora 이미지는 월 1회 갱신하며 갱신 시 failover 로 교체한다. 장애 시 'openstack loadbalancer failover' 로 재생성한다. 모니터링은 octavia-exporter 로 리스너별 연결 수와 상태를 수집한다."), 80)

    return pages[:n]


# ──────────────────────────────────────────────────────────────────────────────
# 네트워크 (NET 공간)
# ──────────────────────────────────────────────────────────────────────────────

def network_pages(n: int) -> List[SeedPage]:
    pages: List[SeedPage] = []
    sw = rng.choice(SWITCHES)
    fw = rng.choice(FIREWALLS)
    lb = rng.choice(LBS)

    def add(title, anc, html, days_ago, groups=None):
        pages.append(SeedPage("NET", title, anc, html, _dt(days_ago), version=rng.randint(1, 15), allowed_groups=groups or ["*"]))

    add("데이터센터 네트워크 아키텍처", ["아키텍처"], toc() + h(1, "개요") + p(f"판교 데이터센터는 스파인-리프 구조이며 스파인 4대, 리프 {rng.randint(24, 40)}대로 구성한다. 리프는 {sw} 를 사용하고 서버는 25GbE(G1)·100GbE(G2) 로 듀얼 홈(MLAG) 연결한다. 언더레이는 eBGP(AS 65001~65099), 오버레이는 EVPN-VXLAN 이다. 외부 연결은 코어 라우터 2대가 ISP 2곳과 BGP 로 이중화한다.") + h(1, "계층 구성") + table(
        ["계층", "장비", "수량", "역할"], [["코어/보더", "Cisco ASR 1006-X", "2", "ISP BGP, 데이터센터 간 연결"], ["방화벽(경계)", fw, "2 (HA)", "인터넷 경계, IPS"], ["스파인", "Cisco Nexus 9336C-FX2", "4", "100GbE 백본"], ["리프", sw, str(rng.randint(24, 40)), "서버 접속, VTEP"], ["관리 스위치", "Cisco Catalyst 9300", "12", "OOB 관리망(1GbE)"], ["로드밸런서", lb, "2 (HA)", "L4/L7, SSL 오프로드"]]) + h(1, "보안 존") + table(
        ["존", "설명", "대표 서브넷", "접근 정책"], [["DMZ", "외부 공개 서비스(웹, API GW)", "10.100.0.0/22", "인터넷 → 443 만, 내부 → 제한"], ["Internal-Web", "내부 웹 계층", "172.16.10.0/24", "DMZ → 8080"], ["Internal-App", "앱 계층", "172.16.20.0/24", "Web → App"], ["Internal-DB", "DB 계층", "172.16.30.0/24", "App → DB 포트만"], ["Mgmt", "관리망", "10.50.0.0/16", "점프 서버 경유"], ["Cloud-Underlay", "OpenStack/Ceph", "10.10.0.0/16, 10.30.0.0/16", "격리"]]) + h(1, "설계 원칙") + ul(["모든 서버는 2개 리프에 MLAG 로 이중 연결", "존 간 통신은 방화벽 또는 NSX DFW 를 반드시 경유", "관리 트래픽은 OOB 네트워크로 분리", "ECMP 로 스파인 4대에 부하 분산, 단일 장비 장애 시 25% 용량 감소"]) + h(1, "대역폭 현황") + table(["구간", "용량", "피크 사용률"], [["스파인-리프", "100GbE ×2/리프", f"{rng.randint(20, 45)}%"], ["인터넷 (ISP A)", "10Gbps", f"{rng.randint(30, 60)}%"], ["인터넷 (ISP B)", "10Gbps", f"{rng.randint(10, 30)}%"], ["판교-부산 전용선", "10Gbps ×2", f"{rng.randint(25, 55)}%"]]), 30)

    add("IP 주소 체계 및 VLAN 설계", ["설계"], toc() + h(1, "대역 할당 원칙") + p("사설 대역은 10.0.0.0/8 을 데이터센터·클라우드 인프라에, 172.16.0.0/12 를 서비스 워크로드에, 192.168.0.0/16 을 사무실·지사에 쓴다. 서브넷은 /24 를 기본으로 하고 DB 존은 /26 까지 세분한다.") + h(1, "VLAN 표") + table(["VLAN", "이름", "서브넷", "게이트웨이", "용도"], [
        ["10", "os-mgmt", "10.10.0.0/22", "10.10.0.1", "OpenStack 관리"], ["20", "os-tunnel", "10.20.0.0/22", "10.20.0.1", "Geneve 터널"], ["30", "ceph-public", "10.30.0.0/22", "10.30.0.1", "Ceph 클라이언트"], ["31", "ceph-cluster", "10.31.0.0/22", "10.31.0.1", "Ceph 복제"], ["50", "mgmt", "10.50.0.0/16", "10.50.0.1", "장비 관리, OOB"],
        ["100~199", "provider-*", "172.17.x.0/24", "172.17.x.1", "OpenStack 프로바이더"], ["200", "dmz", "10.100.0.0/22", "10.100.0.1", "DMZ"], ["210", "web", "172.16.10.0/24", "172.16.10.1", "웹"], ["220", "app", "172.16.20.0/24", "172.16.20.1", "앱"], ["230", "db", "172.16.30.0/24", "172.16.30.1", "DB"], ["300", "k8s-node", "10.60.0.0/22", "10.60.0.1", "k8s 노드"], ["900", "office", "192.168.10.0/23", "192.168.10.1", "사무실 유선"], ["910", "wifi-staff", "192.168.20.0/22", "192.168.20.1", "직원 무선"], ["920", "wifi-guest", "192.168.30.0/24", "192.168.30.1", "방문자"]]) + h(1, "예약 주소") + ul([".1 게이트웨이(VRRP/HSRP VIP), .2~.3 물리 게이트웨이", ".4~.19 네트워크 장비·로드밸런서 VIP", ".20~.49 정적 할당 서버", ".50~.250 DHCP 또는 동적 할당", ".251~.254 예비"]) + h(1, "IPAM") + p("주소 관리는 NetBox 3.7 을 단일 진실 원천으로 사용한다. 신규 할당은 NetBox 에서 예약 후 설정하며, Terraform 의 netbox 프로바이더로 OpenStack 서브넷과 동기화한다. 월 1회 스캔(nmap)으로 미등록 주소를 탐지한다.") + h(1, "IPv6") + p("IPv6 는 DMZ 와 인터넷 경계에서 듀얼 스택으로 제공한다. 할당 대역은 2001:db8:1000::/48 이며 서비스 존별 /64 를 부여한다. 내부 존은 아직 IPv4 단일 스택이다."), 60)

    add(f"방화벽 정책 표준 ({fw})", ["보안"], toc() + h(1, "정책 원칙") + ul(["기본 거부(deny all), 필요한 통신만 허용", "정책은 서비스 단위 애플리케이션 ID 사용 (포트 기반 최소화)", "모든 정책에 티켓 번호·만료일·담당자 태그", "임시 정책은 최대 30일, 만료 시 자동 비활성화", "변경은 주 2회(화·목) 정기 창, 긴급은 2인 승인"]) + h(1, "존 간 기본 허용") + table(["출발", "목적", "허용", "비고"], [["Internet", "DMZ", "HTTPS(443), HTTP(80→443 리다이렉트)", "WAF 경유"], ["DMZ", "Internal-Web", "8080", "API GW → 웹"], ["Internal-Web", "Internal-App", "8080, 9090(gRPC)", ""], ["Internal-App", "Internal-DB", "5432, 3306, 1521", "서비스 계정별"], ["Internal-App", "Internet", "443 (화이트리스트 FQDN)", "외부 API"], ["Mgmt", "All", "22, 3389, 443", "점프 서버 출발지만"], ["Office", "Internal-Web", "443", "SSO 경유"], ["Office", "Internal-DB", "거부", "DBA 는 점프 서버"]]) + h(1, "정책 요청 절차") + ol(["서비스 데스크 '방화벽 정책' 티켓 (출발·목적·포트·사유·기간)", "보안팀 검토 (24시간 내)", "네트워크팀 정기 창에 적용, 티켓에 룰 ID 기록", "요청자 통신 확인 후 종료"]) + h(1, "설정 예시") + code("text", """set rulebase security rules allow-app-to-db from Internal-App to Internal-DB source [ app-servers ] destination [ db-postgres ] application postgresql service application-default action allow
set rulebase security rules allow-app-to-db tag [ TKT-20260215-031 owner-platform exp-2027-02-15 ]
set rulebase security rules allow-app-to-db log-end yes""") + h(1, "로그와 감사") + p("방화벽 로그는 Syslog 로 SIEM(Splunk)에 전송하며 거부 로그는 90일, 허용 로그는 30일 보관한다. 분기마다 미사용 정책(90일 히트 0)을 정리한다. 최근 정리에서 " + str(rng.randint(40, 120)) + "건을 삭제했다.") + h(1, "IPS/위협 방어") + ul(["IPS 프로파일: DMZ 인바운드 strict, 내부 간 default", "URL 필터링: 사무실 → 인터넷에 적용 (악성·도박·P2P 차단)", "DNS 싱크홀 활성화", "시그니처 자동 업데이트 매일 02:00"]), 25, groups=["security-team", "infra-admins"])

    add("VPN 구성 (사이트 간 · 원격 접속)", ["보안"], toc() + h(1, "사이트 간 VPN") + table(["상대", "방식", "로컬 피어", "원격 피어", "암호화", "용도"], [["부산 DR", "IPsec (전용선 백업)", "203.0.113.10", "198.51.100.10", "IKEv2, AES-256-GCM, DH 20", "복제·관리 트래픽 백업 경로"], ["대외 기관 A(금융결제)", "IPsec", "203.0.113.11", "192.0.2.21", "IKEv2, AES-256, SHA-256, DH 14", "거래 연계"], ["대외 기관 B(공공)", "IPsec", "203.0.113.11", "192.0.2.45", "IKEv1, AES-128, SHA-1(기관 제약)", "자료 연계"], ["지사 3곳", "SD-WAN (Fortinet)", "-", "-", "AES-256", "사무 트래픽"]]) + h(1, "원격 접속 VPN") + p("직원 원격 접속은 GlobalProtect(SSL VPN) 를 쓰며 MFA(OTP) 가 필수이다. 동시 접속 한도는 1,000 이고 피크는 재택근무일 약 " + str(rng.randint(400, 800)) + " 세션이다. 접속 후 접근 가능한 대역은 AD 그룹별로 분리된다.") + table(["그룹", "접근 대역", "비고"], [["staff", "192.168.0.0/16, 172.16.10.0/24", "사무·웹"], ["dev", "staff + 10.60.0.0/22, 172.17.0.0/16", "개발 클러스터"], ["infra-admins", "dev + 10.50.0.0/16", "관리망(점프 서버)"], ["vendor", "지정 호스트만", "기간 제한 계정"]]) + h(1, "터널 설정 예시") + code("text", """set network ike crypto-profiles ike-crypto-profiles ike-busan encryption aes-256-gcm dh-group group20 lifetime hours 8
set network ike gateway gw-busan authentication pre-shared-key key <vault:net/vpn/busan>
set network ike gateway gw-busan local-address ip 203.0.113.10 peer-address ip 198.51.100.10 protocol ikev2
set network tunnel ipsec tun-busan auto-key ike-gateway gw-busan ipsec-crypto-profile ipsec-busan""") + h(1, "운영") + ul(["PSK 는 Vault 보관, 연 1회 교체", "터널 상태는 Zabbix 에서 ICMP + IKE SA 모니터링", "대외 기관 B 의 IKEv1/SHA-1 은 2027년까지 IKEv2 전환 요청 중"]), 90, groups=["security-team", "infra-admins"])

    add(f"로드밸런서 구성 표준 ({lb})", ["설계"], toc() + h(1, "구성") + p(f"{lb} 2대를 Active-Standby HA 로 운영하며 DMZ 와 내부 존 각각에 VIP 를 둔다. SSL 은 로드밸런서에서 종료(오프로드)하고 백엔드는 HTTP 또는 재암호화(민감 서비스)한다. Kubernetes 인그레스는 로드밸런서 → ingress-nginx NodePort 로 연결한다.") + h(1, "VIP 표준") + table(["VIP", "포트", "풀", "헬스체크", "지속성", "용도"], [["10.100.0.10", "443", "api-gateway (3)", "HTTPS GET /healthz 200", "없음", "외부 API"], ["10.100.0.11", "443", "web-portal (4)", "HTTPS GET /", "쿠키", "포털"], ["172.16.10.5", "443", "k8s-prod-ingress (24 노드:30443)", "HTTP GET /healthz", "없음", "내부 인그레스"], ["172.16.30.5", "5432", "pg-primary (1) + standby", "TCP", "소스 IP", "DB 쓰기 VIP (pgbouncer)"]]) + h(1, "SSL 정책") + ul(["TLS 1.2 이상, TLS 1.3 우선", "암호 스위트: ECDHE-ECDSA/RSA-AES256-GCM-SHA384, CHACHA20-POLY1305", "HSTS 1년, OCSP 스테이플링", "인증서는 사내 CA(내부) / 공인 CA(외부), 만료 30일 전 교체"]) + h(1, "iRule / 설정 예시") + code("text", """ltm virtual vs_api_443 {
    destination 10.100.0.10:443
    pool pool_api_gateway
    profiles { clientssl_api { context clientside } http { } tcp { } }
    rules { irule_x_forwarded_for }
    source-address-translation { type automap }
}
ltm pool pool_api_gateway {
    load-balancing-mode least-connections-member
    members { 172.16.10.11:8080 { } 172.16.10.12:8080 { } 172.16.10.13:8080 { } }
    monitor mon_https_healthz
}""") + h(1, "용량") + p(f"L7 처리 한도는 초당 {rng.randint(40, 80)}K 요청, SSL TPS {rng.randint(10, 25)}K 이다. 현재 피크 사용률은 {rng.randint(25, 50)}% 이며 70% 초과 시 증설을 검토한다."), 45)

    add("DNS · DHCP · NTP 구성", ["서비스"], toc() + h(1, "DNS") + p("내부 DNS 는 BIND 9.18 2대(마스터·슬레이브) + Infoblox 는 사용하지 않는다. 외부 공개 DNS 는 Cloudflare 에 두고 GSLB 는 F5 DNS 로 판교·부산 가중치를 제어한다. 내부 존은 corp.example.com, 서비스 존은 svc.example.com 이며 Kubernetes external-dns 가 svc 존에 레코드를 자동 등록한다.") + table(["서버", "IP", "역할"], [["dns-01", "10.50.1.11", "마스터, 내부 존"], ["dns-02", "10.50.1.12", "슬레이브"], ["dns-cache-01/02", "10.50.1.21/22", "리졸버(캐시), 사무실·서버 지정"], ["f5-gtm-01/02", "203.0.113.20/21", "GSLB"]]) + h(1, "DHCP") + p("Kea DHCP 2.4 를 HA(hot-standby) 로 운영한다. 사무실·무선 대역만 DHCP 를 쓰고 서버 대역은 정적 할당이다. 임대 시간은 유선 8시간, 무선 2시간, 방문자 1시간이다.") + code("json", """{"Dhcp4": {"subnet4": [{"subnet": "192.168.10.0/23", "pools": [{"pool": "192.168.10.50 - 192.168.11.250"}],
  "option-data": [{"name": "routers", "data": "192.168.10.1"}, {"name": "domain-name-servers", "data": "10.50.1.21, 10.50.1.22"}],
  "valid-lifetime": 28800}]}}""") + h(1, "NTP") + p("Stratum 1 GPS 수신기 1대와 KRISS(time.kriss.re.kr) 를 상위로 하는 chrony 서버 3대(ntp-01~03, 10.50.1.31~33)를 운영한다. 모든 서버·장비는 이 3대만 참조하며 외부 NTP 직접 접근은 방화벽에서 차단한다. 허용 오차는 10ms 이다.") + h(1, "변경 절차") + ul(["DNS 레코드 변경은 Git(infra/dns) MR → 파이프라인이 named-checkzone 후 반영", "TTL 은 기본 300초, 전환 예정 레코드는 60초로 사전 단축", "DHCP 예약은 NetBox 에 등록 후 Kea 설정 생성"]), 110)

    add("스위치 표준 설정 템플릿 (리프)", ["설정"], toc() + h(1, "적용 대상") + p(f"{sw} 리프 스위치의 기본 설정 템플릿이다. 신규 장비는 ZTP 로 본 템플릿을 받은 뒤 NetBox 의 변수(호스트명, ASN, 루프백, 업링크)로 Ansible 이 렌더링한다.") + h(1, "기본 설정") + code("text", """hostname leaf-a-07
feature bgp
feature nv overlay
feature vn-segment-vlan-based
feature lacp
feature vpc
!
interface loopback0
  ip address 10.0.255.17/32
interface loopback1
  ip address 10.0.254.17/32   ! VTEP
!
router bgp 65017
  router-id 10.0.255.17
  address-family l2vpn evpn
  neighbor 10.0.255.1 remote-as 65000   ! spine-1
  neighbor 10.0.255.2 remote-as 65000   ! spine-2
!
vpc domain 7
  peer-keepalive destination 10.50.2.18 source 10.50.2.17
  peer-gateway
!
interface port-channel11
  description srv-cmp-a-01
  switchport mode trunk
  switchport trunk allowed vlan 10,20,30,31,100-199
  vpc 11
  mtu 9216""") + h(1, "표준 항목") + table(["항목", "값"], [["MTU", "9216 (서버·스토리지), 1500 (관리)"], ["LACP", "active, rate fast"], ["STP", "edge trunk (서버 포트), BPDU guard"], ["Syslog", "10.50.1.41 (Splunk HF), severity 6"], ["SNMP", "v3 auth/priv, 10.50.1.42 (Zabbix)"], ["AAA", "TACACS+ (ISE) 2대, 로컬 fallback"], ["NTP", "10.50.1.31~33"], ["관리", "mgmt0 → OOB VLAN 50, SSH 만"]]) + h(1, "검증 체크리스트") + ol(["show vpc 에서 peer status OK, consistency 통과", "show bgp l2vpn evpn summary 에서 스파인 4대 Established", "show interface port-channel 에서 서버 포트 bundled", "NetBox 상태 'active' 로 변경"]) + h(1, "펌웨어") + p("표준 버전은 NX-OS 10.3(4a) 이며 연 1회 갱신한다. 업그레이드는 ISSU 로 수행하되 vPC 쌍의 한쪽씩 진행한다."), 140)

    add("BGP · OSPF 라우팅 설계", ["설계"], toc() + h(1, "외부 BGP") + p("코어 라우터 2대는 ISP A(AS 9318)·ISP B(AS 4766) 와 eBGP 피어링한다. 공인 대역 203.0.113.0/24 를 양쪽에 광고하며 ISP A 를 주경로(local-pref 200), ISP B 를 백업(local-pref 100, AS-path prepend ×2)으로 둔다. 인바운드는 full table 대신 default + 고객 대역만 받는다.") + table(["피어", "AS", "로컬 주소", "원격 주소", "정책"], [["ISP A", "9318", "203.0.113.1", "203.0.113.254", "primary, BFD 300ms"], ["ISP B", "4766", "203.0.113.2", "203.0.113.253", "backup, prepend"], ["부산 코어", "65002", "10.0.0.1", "10.0.0.2", "iBGP, 전용선"]]) + h(1, "언더레이 eBGP") + ul(["스파인 AS 65000, 리프 AS 65001~65099 (장비당 고유)", "ECMP 최대 4, BFD 활성화", "루프백 /32 만 광고, 서버 대역은 EVPN 으로"]) + h(1, "OSPF (레거시 캠퍼스)") + p("사무실 캠퍼스 네트워크는 OSPF Area 0(코어)과 Area 10(층별)로 운영한다. 데이터센터와는 코어에서 재분배(BGP ↔ OSPF)하며 route-map 으로 10.0.0.0/8 만 허용한다. 2027년까지 캠퍼스도 BGP 로 전환할 계획이다.") + code("text", """router bgp 65000
  neighbor 203.0.113.254 remote-as 9318
  address-family ipv4 unicast
    network 203.0.113.0/24
    neighbor 203.0.113.254 route-map ISP-A-IN in
    neighbor 203.0.113.254 route-map ISP-A-OUT out
route-map ISP-A-IN permit 10
  set local-preference 200
route-map ISP-B-OUT permit 10
  set as-path prepend 65000 65000""") + h(1, "장애 시나리오") + table(["장애", "수렴 시간", "영향"], [["ISP A 회선 단절", "BFD 1초 + BGP 수렴 ~5초", "ISP B 로 전환, 대역 10G 로 감소"], ["스파인 1대 장애", "BFD 1초", "ECMP 3경로, 용량 25% 감소"], ["코어 라우터 1대 장애", "~10초", "HSRP 전환, 세션 일부 재연결"]]), 200)

    add("무선 네트워크 구성 (사무실)", ["서비스"], toc() + h(1, "구성") + p(f"사무실 무선은 Cisco 9800 WLC 2대(HA SSO)와 AP {rng.randint(120, 220)}대(Catalyst 9130, Wi-Fi 6)로 운영한다. SSID 는 직원용(802.1X EAP-TLS), 방문자용(캡티브 포털), IoT 용(PSK, 격리) 3개이다.") + table(["SSID", "인증", "VLAN", "대역", "제한"], [["CORP-STAFF", "802.1X EAP-TLS (ISE, 기기 인증서)", "910", "5GHz 우선", "내부망"], ["CORP-GUEST", "캡티브 포털 (스폰서 승인, 24h)", "920", "2.4/5GHz", "인터넷만, 대역폭 10Mbps"], ["CORP-IOT", "WPA2-PSK (연 1회 교체)", "930", "2.4GHz", "프린터·센서, 서버 접근 불가"]]) + h(1, "RF 설계") + ul(["채널 폭 5GHz 40MHz, 2.4GHz 20MHz", "RRM 자동(DCA/TPC), 최소 전송 속도 12Mbps", "AP 밀도: 회의실 1대, 사무공간 15m 간격", "커버리지 목표 -67dBm 이상"]) + h(1, "운영 지표") + table(["지표", "값"], [["피크 동시 접속", str(rng.randint(800, 1500))], ["평균 클라이언트/AP", str(rng.randint(8, 20))], ["5GHz 비율", f"{rng.randint(80, 95)}%"], ["월 장애 티켓", str(rng.randint(2, 8))]]), 160)

    # 장애 사례
    net_incidents = [
        ("코어 스위치 MLAG 피어링크 단절로 일부 서버 통신 두절", "피어링크 광 모듈 불량으로 MLAG 가 split-brain 상태가 됐고, 세컨더리 스위치가 포트를 차단했다", "광 모듈 교체, 피어 keepalive 경로 이중화, 모듈 DOM 임계 알림 추가"),
        ("방화벽 세션 테이블 포화로 외부 API 간헐 실패", "대외 연계 서버의 커넥션 풀 설정 오류로 TIME_WAIT 세션이 폭증하여 세션 한도 200만을 초과했다", "커넥션 풀 수정, 세션 타임아웃 단축(TCP 3600→900초), 세션 80% 알림"),
        ("ISP A 회선 장애 시 BGP 수렴 지연", "BFD 가 설정되지 않은 피어에서 홀드 타임 180초까지 전환이 지연됐다", "모든 eBGP 피어에 BFD 적용, 홀드 타임 30초"),
        ("DHCP 고갈로 사무실 신규 접속 불가", "무선 임대 시간 24시간 설정과 방문자 증가로 920 VLAN 풀이 고갈됐다", "임대 시간 1시간으로 단축, 풀 /24 → /23 확장, 사용률 알림"),
        ("DNS 캐시 서버 1대 장애로 조회 지연", "리졸버 2대 중 1대 디스크 풀, 클라이언트가 타임아웃 후 2번째 서버로 재시도하면서 5초 지연", "디스크 알림, 리졸버 Anycast VIP 로 전환하여 장애 서버 자동 제외"),
    ]
    for title, cause, action in pick(net_incidents, 4):
        dt = _dt(rng.randint(30, 400))
        dur = rng.randint(20, 150)
        html = meta_table([("발생 일시", f"{dstr(dt)} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"), ("지속", f"{dur}분"), ("영향", rng.choice(["운영 서비스 일부", "외부 API", "사무실 전체", "인터넷 연결"])), ("담당", rng.choice(PEOPLE))]) + h(1, "현상") + p(title + ". 모니터링 알림과 사용자 신고가 동시에 접수됐다.") + h(1, "원인") + p(cause) + h(1, "조치") + ul(action.split(", ")) + h(1, "타임라인") + table(["시각", "내용"], [["T+0", "알림/신고 접수"], ["T+10분", "네트워크팀 원인 분석 착수"], [f"T+{dur // 2}분", "임시 조치"], [f"T+{dur}분", "복구 확인"]]) + h(1, "재발 방지") + p("조치 항목은 변경 관리 티켓으로 추적하며 " + dstr(dt + timedelta(days=14)) + " 까지 완료한다. 관련 표준 문서를 갱신했다.")
        pages.append(SeedPage("NET", f"장애 보고 {dstr(dt)} — {title}", ["장애 사례"], html, dt + timedelta(days=1), version=rng.randint(1, 3)))

    return pages[:n]


# ──────────────────────────────────────────────────────────────────────────────
# 첨부 파일 생성 (실제 바이너리 → 워커 파서를 거친다)
# ──────────────────────────────────────────────────────────────────────────────

def make_docx(title: str, sections: List[Tuple[str, List[str]]], tbl: Optional[Tuple[List[str], List[List[str]]]] = None) -> bytes:
    from docx import Document
    doc = Document()
    doc.add_heading(title, level=0)
    for head, paras in sections:
        doc.add_heading(head, level=1)
        for t in paras:
            doc.add_paragraph(t)
    if tbl:
        headers, rows = tbl
        doc.add_heading("표", level=1)
        t = doc.add_table(rows=1, cols=len(headers))
        for i, hd in enumerate(headers):
            t.rows[0].cells[i].text = hd
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = str(v)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_pptx(title: str, slides: List[Tuple[str, List[str]]], notes: bool = True) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = title
    s.placeholders[1].text = f"작성일 {dstr(NOW - timedelta(days=rng.randint(10, 400)))}"
    for head, bullets in slides:
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = head
        tf = s.placeholders[1].text_frame
        tf.text = bullets[0]
        for b in bullets[1:]:
            para = tf.add_paragraph()
            para.text = b
            para.font.size = Pt(16)
        if notes:
            s.notes_slide.notes_text_frame.text = rng.choice(["발표 시 수치 근거는 부록 참고", "질의 예상: 일정 리스크", "이 슬라이드는 2분 내 설명", ""])
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def make_xlsx(sheets: List[Tuple[str, List[str], List[List]]]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for name, headers, rows in sheets:
        ws = wb.create_sheet(title=name[:31])
        ws.append(headers)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_pdf(title: str, pages: List[List[str]]) -> bytes:
    """ASCII 전용 최소 PDF (Helvetica). 영문 벤더 문서·요약서 용도."""
    def asc(s: str) -> str:
        s = s.encode("ascii", "replace").decode()
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objs: List[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    pages_obj_index = len(objs) + 1 + 2 * len(pages)  # 나중에 추가될 Pages 객체 번호
    for pi, lines in enumerate(pages):
        content_lines = [f"BT /F1 16 Tf 50 790 Td ({asc(title if pi == 0 else title + ' (cont.)')}) Tj ET"]
        y = 760
        for ln in lines:
            if y < 50:
                break
            content_lines.append(f"BT /F1 10 Tf 50 {y} Td ({asc(ln[:100])}) Tj ET")
            y -= 14
        stream = "\n".join(content_lines).encode("latin-1", "replace")
        c = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        pg = add(f"<< /Type /Page /Parent {pages_obj_index} 0 R /MediaBox [0 0 595 842] /Contents {c} 0 R /Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        page_ids.append(pg)
    pages_obj = add(("<< /Type /Pages /Kids [" + " ".join(f"{i} 0 R" for i in page_ids) + f"] /Count {len(page_ids)} >>").encode())
    assert pages_obj == pages_obj_index
    catalog = add(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode())
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _long_paras(topic: str, k: int) -> List[str]:
    pool = [
        f"{topic}에 대한 본 절은 설계 결정의 배경과 대안 비교를 다룬다. 대안은 비용, 운영 복잡도, 팀 숙련도, 벤더 지원 기간 네 가지 축으로 평가했으며 각 축에 가중치를 두어 정량 점수를 산출했다.",
        f"{topic} 운영 시 가장 빈번한 문제는 설정 드리프트와 문서 불일치다. 이를 막기 위해 모든 변경은 코드 저장소를 거치고, 주 1회 실제 상태와 선언 상태를 비교하는 점검을 자동화한다.",
        f"{topic} 관련 성능 목표는 피크 부하의 1.5배를 기준으로 하며, 부하 테스트는 운영과 동일한 토폴로지의 스테이징에서 수행한다. 결과는 p50, p95, p99 지연과 오류율로 보고한다.",
        f"{topic}의 보안 요구사항은 사내 정보보호 규정 제4장을 따른다. 접근 통제, 암호화, 감사 로그, 취약점 관리 네 영역에서 각각 점검 항목을 두고 분기마다 자체 점검한다.",
        f"{topic} 장애 시 1차 대응은 온콜 담당이 15분 내 착수하며, 30분 내 완화되지 않으면 2차 담당과 관련 벤더에 에스컬레이션한다. 모든 장애는 48시간 내 보고서로 정리한다.",
        f"{topic} 비용은 초기 구축비와 3년 운영비를 합산한 TCO 로 비교했다. 라이선스 비용은 연 {rng.randint(5, 12)}% 인상을 가정했으며, 인건비는 운영 인력 {rng.randint(1, 4)}명 기준이다.",
        f"{topic}의 향후 과제는 자동화 범위 확대와 관측 가능성(Observability) 강화다. 특히 분산 추적을 전 서비스에 적용하고 SLO 기반 알림으로 전환하는 것을 다음 분기 목표로 둔다.",
    ]
    return pick(pool, k)


def build_attachments(page: SeedPage, kinds: List[str]) -> List[SeedAttachment]:
    out: List[SeedAttachment] = []
    short = page.title.replace("[", "").replace("]", "").replace("/", "-").replace(" ", "_")[:40]
    topic = page.title.split("]")[-1].strip().split(" — ")[0]
    for kind in kinds:
        if kind == "docx":
            secs = [("개요", _long_paras(topic, 2)), ("상세 내용", _long_paras(topic, 3)), ("결정 사항 및 후속 조치", _long_paras(topic, 2))]
            tbl = (["항목", "담당", "기한", "상태"], [[f"{topic} 관련 과제 {i+1}", rng.choice(PEOPLE), dstr(NOW + timedelta(days=rng.randint(-60, 60))), rng.choice(["완료", "진행중", "예정"])] for i in range(rng.randint(5, 10))])
            data = make_docx(f"{topic} 상세 문서", secs, tbl)
            out.append(SeedAttachment(f"{short}_상세.docx", data))
        elif kind == "pptx":
            slides = [("배경 및 목표", _long_paras(topic, 3)[:3]), ("현황 분석", [f"현행 지표 {i+1}: {rng.randint(10, 99)}%" for i in range(4)]), ("제안 방안", _long_paras(topic, 3)),
                      ("일정", [f"{i+1}단계: {dstr(NOW + timedelta(days=30 * i))} ~ {dstr(NOW + timedelta(days=30 * (i + 1)))}" for i in range(4)]), ("기대 효과", _long_paras(topic, 2)), ("리스크 및 대응", [f"{r}: {m}" for r, m in pick(RISKS, 3)])]
            out.append(SeedAttachment(f"{short}_발표자료.pptx", make_pptx(f"{topic} 보고", slides)))
        elif kind == "xlsx":
            rows1 = [[f"REQ-{i+1:03d}", rng.choice(REQ_AREAS), f"{topic} 요구사항 {i+1}: " + rng.choice(["권한 분리", "응답 2초 이내", "감사 로그", "이중화", "자동 복구", "알림 발송"]), rng.choice(["상", "중", "하"]), rng.choice(PEOPLE), rng.choice(["확정", "검토중", "보류"])] for i in range(rng.randint(25, 60))]
            rows2 = [[f"{topic} 항목 {i+1}", rng.randint(1, 48), rng.randint(5, 60) * 100, rng.choice(["인건비", "HW", "SW", "기타"])] for i in range(rng.randint(10, 25))]
            out.append(SeedAttachment(f"{short}_목록.xlsx", make_xlsx([("요구사항", ["ID", "영역", "내용", "우선순위", "담당", "상태"], rows1), ("비용", ["항목", "M/M 또는 수량", "금액(만원)", "구분"], rows2)])))
        elif kind == "pdf":
            vendor = rng.choice(VENDORS)
            model = rng.choice(SWITCHES + FIREWALLS + LBS + STORAGE)
            pages_txt = [[f"Vendor: {vendor}    Model: {model}", f"Document: Technical datasheet and sizing notes for {topic}", "",
                          "1. Overview", f"This document summarizes the specifications of {model} as evaluated for the project.",
                          f"Throughput: {rng.choice([10, 25, 40, 100])} Gbps per port, {rng.choice([32, 48, 64])} ports, latency under {rng.choice([1, 2, 5])} us.",
                          f"Power: {rng.randint(300, 1200)} W typical, redundant PSU, front-to-back airflow.", "",
                          "2. Sizing", f"Recommended for up to {rng.randint(2, 8)}000 concurrent sessions per unit with HA pair.",
                          f"Memory {rng.choice([32, 64, 128])} GB, storage {rng.choice([240, 480, 960])} GB SSD.", "",
                          "3. Support", f"Hardware warranty {rng.choice([3, 5])} years, software subscription renewed annually.",
                          "End of sale planned for " + str(2028 + rng.randint(0, 3)) + ", end of support 5 years later."],
                         ["4. Evaluation result", f"Evaluated by {rng.choice(['platform team', 'network team', 'architecture board'])} on {dstr(NOW - timedelta(days=rng.randint(10, 300)))}.",
                          "Score (out of 5): performance " + str(rng.randint(3, 5)) + ", cost " + str(rng.randint(2, 5)) + ", operability " + str(rng.randint(3, 5)) + ".",
                          "Decision: " + rng.choice(["selected as primary option", "kept as alternative", "rejected due to cost"]) + ".",
                          "", "5. Notes", "Firmware must be upgraded to the recommended release before production use.",
                          "Compatibility with existing MLAG/VPC configuration was verified in the lab."]]
            out.append(SeedAttachment(f"{short}_datasheet.pdf", make_pdf(f"{model} datasheet", pages_txt)))
        elif kind == "md":
            body = f"# {topic} README\n\n" + "\n\n".join(_long_paras(topic, 3)) + "\n\n## 설치\n\n```bash\nmake install\nmake deploy ENV=stg\n```\n\n## 설정\n\n| 키 | 기본값 | 설명 |\n|---|---|---|\n| TIMEOUT | 30 | 요청 타임아웃(초) |\n| RETRIES | 3 | 재시도 횟수 |\n| LOG_LEVEL | INFO | 로그 레벨 |\n\n## 운영 체크리스트\n\n" + "\n".join(f"- {x}" for x in _long_paras(topic, 3)) + "\n"
            out.append(SeedAttachment(f"{short}_README.md", body.encode()))
        elif kind == "txt":
            body = f"# {topic} 설정 백업 ({dstr(NOW - timedelta(days=rng.randint(1, 200)))})\n" + "\n".join(f"{k}={v}" for k, v in [
                ("hostname", f"srv-{rng.randint(1, 99):02d}"), ("mgmt_ip", f"10.50.{rng.randint(1, 20)}.{rng.randint(10, 250)}"), ("ntp", "10.50.1.31 10.50.1.32 10.50.1.33"),
                ("syslog", "10.50.1.41"), ("snmp_v3_user", "zabbix-ro"), ("mtu", "9216"), ("vlan_allowed", "10,20,30,31,100-199"), ("bgp_asn", str(65000 + rng.randint(1, 99))),
                ("firmware", rng.choice(["10.3(4a)", "4.31.2F", "22.4R2", "10.13.1010"]))]) + "\n\n# 변경 이력\n" + "\n".join(f"{dstr(NOW - timedelta(days=d))} {rng.choice(PEOPLE)} {rng.choice(['VLAN 추가', '펌웨어 업그레이드', 'ACL 수정', '포트 설명 갱신', 'BGP 피어 추가'])}" for d in sorted(rng.sample(range(5, 400), 6), reverse=True)) + "\n"
            out.append(SeedAttachment(f"{short}_config.txt", body.encode()))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 추가 페이지: 월간 운영 보고, 서비스별 가이드, 테넌트, 지사·장비
# ──────────────────────────────────────────────────────────────────────────────

MONTHS = [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 11)]


def monthly_report_pages(space: str, n: int) -> List[SeedPage]:
    pages: List[SeedPage] = []
    label = {"DEVOPS": "플랫폼 운영", "CLOUD": "클라우드 운영", "NET": "네트워크 운영"}[space]
    for (y, m) in MONTHS[-n:]:
        dt = datetime(y, m, 28, tzinfo=timezone.utc) if m != 2 else datetime(y, m, 27, tzinfo=timezone.utc)
        if space == "DEVOPS":
            metrics = [["배포 횟수", str(rng.randint(80, 220)), "+" + str(rng.randint(2, 20)) + "%"], ["배포 실패율", f"{rng.uniform(0.5, 4):.1f}%", ""], ["평균 파이프라인 시간", f"{rng.randint(14, 30)}분", ""],
                       ["Sev1/Sev2 장애", f"{rng.choice([0, 0, 1])}/{rng.randint(0, 4)}", ""], ["MTTR", f"{rng.randint(20, 90)}분", ""], ["클러스터 CPU 사용률(평균)", f"{rng.randint(45, 70)}%", ""], ["이미지 CRITICAL 취약점(미조치)", str(rng.randint(0, 5)), ""], ["온콜 호출 건수", str(rng.randint(5, 30)), ""]]
            works = ["Argo CD 2.11 업그레이드", "Trivy DB 오프라인 미러 구축", "k8s-stg 1.30 업그레이드", "Loki 보존 정책 90일 적용", "Vault 감사 로그 SIEM 연동", "Rollouts AnalysisTemplate 표준화", "러너 오토스케일(docker-machine → k8s executor) 전환", "노드 이미지 Ubuntu 24.04 전환 시범", "cert-manager 1.14 업그레이드", "비용 대시보드(OpenCost) 도입"]
        elif space == "CLOUD":
            metrics = [["VM 수", str(rng.randint(900, 1400)), "+" + str(rng.randint(10, 60))], ["vCPU 할당률", f"{rng.randint(65, 85)}%", ""], ["메모리 할당률", f"{rng.randint(65, 85)}%", ""], ["Ceph 사용률", f"{rng.randint(60, 75)}%", ""], ["신규 프로젝트", str(rng.randint(1, 6)), ""], ["쿼터 증설 요청", str(rng.randint(3, 15)), ""], ["라이브 마이그레이션", str(rng.randint(20, 120)), ""], ["장애(Sev2 이상)", str(rng.randint(0, 2)), ""]]
            works = ["컴퓨트 G2 8대 추가 투입", "Ceph OSD 노드 2대 교체", "Amphora 이미지 갱신", "Nova 보안 패치", "Glance 이미지 월간 빌드", "vSphere 패치(U2c)", "DR 모의훈련(코어뱅킹)", "GPU 노드 드라이버 업그레이드(550)", "Gnocchi 과금 집계 검증", "OVN 컨트롤러 메모리 튜닝"]
        else:
            metrics = [["인터넷 피크 사용률(ISP A)", f"{rng.randint(30, 65)}%", ""], ["방화벽 정책 변경", str(rng.randint(20, 80)), ""], ["정책 정리(미사용 삭제)", str(rng.randint(0, 40)), ""], ["VPN 피크 세션", str(rng.randint(400, 900)), ""], ["무선 피크 접속", str(rng.randint(800, 1500)), ""], ["장애(서비스 영향)", str(rng.randint(0, 2)), ""], ["장비 펌웨어 업데이트", str(rng.randint(0, 12)), ""], ["IPS 차단 이벤트", f"{rng.randint(10, 90)}K", ""]]
            works = ["리프 스위치 4대 추가(존 C)", "ISP B 회선 10G→20G 증속", "방화벽 세션 타임아웃 조정", "GlobalProtect 게이트웨이 증설", "DNS 리졸버 Anycast 전환", "NetBox 3.7 업그레이드", "코어 라우터 IOS-XE 패치", "무선 AP 20대 교체(Wi-Fi 6E)", "대외 기관 B IKEv2 전환 협의", "OOB 관리망 스위치 교체"]
        html = toc() + h(1, "요약") + p(
            f"{y}년 {m}월 {label} 월간 보고이다. 전반적으로 " + rng.choice(["안정적으로 운영되었으며 서비스 영향 장애는 없었다.", "계획된 작업이 모두 완료되었고 Sev2 장애 1건이 있었다.", "용량 증설 작업이 집중된 달이었다.", "보안 패치와 업그레이드 위주로 진행되었다."]) +
            f" 주요 지표는 아래 표와 같고, 상세 작업과 장애는 각 절에 기술한다. 보고자는 {rng.choice(PEOPLE)} 이며 운영위원회 보고일은 {y}-{m:02d}-{rng.randint(1, 5):02d} 이다.") + h(1, "주요 지표") + table(["지표", "값", "전월 대비"], metrics) + h(1, "완료 작업") + table(
            ["작업", "일자", "담당", "결과"], [[w, f"{y}-{m:02d}-{rng.randint(1, 27):02d}", rng.choice(PEOPLE), rng.choice(["완료", "완료", "완료(이슈 1건)", "부분 완료"])] for w in pick(works, rng.randint(4, 7))]) + h(1, "장애 및 이슈") + (p(
            rng.choice(["이달 서비스 영향 장애는 없었다. 경미한 알림 " + str(rng.randint(5, 30)) + "건은 모두 1시간 내 조치되었다.",
                        "Sev2 장애 1건: " + rng.choice(["배포 중 설정 누락", "스토리지 지연", "회선 플래핑", "인증서 갱신 실패"]) + "으로 약 " + str(rng.randint(20, 90)) + "분간 일부 서비스가 영향을 받았다. 포스트모템은 장애 보고서 공간에 있다.",
                        "반복 알림: " + rng.choice(["디스크 85% 경고", "컨슈머 랙", "BGP 플래핑", "OSD slow ops"]) + " 가 " + str(rng.randint(3, 9)) + "회 발생하여 근본 조치를 다음 달 계획에 포함했다."]))) + h(1, "용량 및 비용") + p(
            rng.choice([f"컴퓨트 할당률이 {rng.randint(70, 85)}% 로 증설 기준(75%)에 근접했다. 분기 증설 계획에 따라 발주를 진행 중이다.",
                        f"스토리지 사용률은 {rng.randint(60, 75)}% 이며 월 {rng.randint(8, 20)}TB 씩 증가하고 있다. 현재 추세면 {rng.randint(4, 9)}개월 후 80% 에 도달한다.",
                        f"인터넷 회선 피크가 {rng.randint(50, 70)}% 를 넘어 증속을 검토한다. 비용은 월 {rng.randint(200, 600)}만 원 증가 예상.",
                        f"이달 클라우드 과금 집계는 총 {rng.randint(80, 220):,}백만 원이며 사업부별 청구서를 발송했다."])) + h(1, "다음 달 계획") + ul(pick(works, 4)) + h(1, "리스크") + ul([
            rng.choice(["하드웨어 납기 지연 가능성 (벤더 리드타임 10주)", "주요 인력 휴가로 온콜 공백 — 대체 인력 지정", "벤더 지원 종료(EoS) 장비 " + str(rng.randint(2, 10)) + "대 교체 필요", "라이선스 갱신 협상 지연"]),
            rng.choice(["보안 패치 적용 창 부족", "DR 훈련 일정과 사업 오픈 일정 충돌", "전력 여유율 15% 미만(존 C)"])])
        pages.append(SeedPage(space, f"{y}년 {m:02d}월 {label} 월간 보고", ["월간 보고"], html, dt, version=rng.randint(1, 3)))
    return pages


SERVICES = [("order-svc", "주문", "Java 17 / Spring Boot 3.2", 8080), ("payment-svc", "결제", "Kotlin / Spring Boot 3.2", 8080), ("auth-svc", "인증", "Go 1.22", 8081),
            ("notification-svc", "알림", "Python 3.11 / FastAPI", 8000), ("search-svc", "검색", "Java 17 / Spring Boot 3.2", 8080), ("report-svc", "보고서", "Python 3.11 / FastAPI", 8000),
            ("api-gateway", "게이트웨이(Kong)", "Kong 3.6", 8000), ("batch-svc", "배치", "Java 17 / Spring Batch", 8080), ("file-svc", "파일", "Go 1.22", 8082), ("settlement-svc", "정산", "Java 17", 8080)]


def devops_service_pages(n: int) -> List[SeedPage]:
    pages: List[SeedPage] = []
    for name, ko, stack, port in SERVICES[:n]:
        ns = rng.choice(["hbf-2025", "dsl-2025", "smc-2025", "nsd-2026"])
        html = toc() + h(1, "서비스 개요") + meta_table([("서비스", name), ("업무", ko), ("기술 스택", stack), ("저장소", f"https://git.example.com/apps/{name}"), ("네임스페이스", f"{ns}-prod / {ns}-stg / {ns}-dev"), ("담당", f"{rng.choice(PEOPLE)} (개발), {rng.choice(PEOPLE)} (운영)"), ("온콜", "#oncall-" + ns)]) + p(
            f"{name} 는 {ko} 도메인을 담당하는 서비스로, {rng.choice(['REST API 와 Kafka 이벤트', 'gRPC 와 REST API', 'REST API'])} 를 제공한다. 의존 서비스는 " + ", ".join(s[0] for s in pick(SERVICES, 2)) + f" 이며 데이터베이스는 {rng.choice(DBS)[0]} 전용 스키마를 쓴다. 트래픽은 평시 {rng.randint(50, 400)} RPS, 피크 {rng.randint(500, 3000)} RPS 이다.") + h(1, "배포") + table(["환경", "방식", "승인", "레플리카", "리소스(요청/제한)"], [
            ["dev", "자동 (main 머지)", "없음", "1", "250m/1 CPU, 512Mi/1Gi"], ["stg", "자동 (태그)", "없음", "2", "500m/2 CPU, 1Gi/2Gi"], ["prod", rng.choice(["Canary 10→30→60→100", "Blue-Green"]), "2인", str(rng.choice([3, 4, 6])), "1/2 CPU, 2Gi/4Gi"]]) + code("bash", f"""# 운영 배포 (Argo CD)
argocd app sync {name}-prod --revision v{rng.randint(1, 3)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}
kubectl argo rollouts get rollout {name} -n {ns}-prod --watch
# 롤백
kubectl argo rollouts undo {name} -n {ns}-prod""") + h(1, "설정") + table(["키", "출처", "설명"], [
            ["DB_URL / DB_PASSWORD", "Vault (ExternalSecret)", "전용 스키마, 풀 max 30"], ["KAFKA_BOOTSTRAP", "ConfigMap", "kafka-0..2:9092"], ["REDIS_URL", "ConfigMap", rng.choice(CACHES)], ["LOG_LEVEL", "ConfigMap", "INFO (운영), DEBUG 금지"], ["JAVA_OPTS", "ConfigMap", "-XX:MaxRAMPercentage=75"], ["FEATURE_FLAGS", "Unleash", "기능 토글"]]) + h(1, "헬스체크와 프로브") + code("yaml", f"""livenessProbe:  {{ httpGet: {{ path: /actuator/health/liveness, port: {port} }}, initialDelaySeconds: 30, periodSeconds: 10 }}
readinessProbe: {{ httpGet: {{ path: /actuator/health/readiness, port: {port} }}, periodSeconds: 5, failureThreshold: 3 }}
startupProbe:   {{ httpGet: {{ path: /actuator/health, port: {port} }}, failureThreshold: 30, periodSeconds: 5 }}""") + h(1, "모니터링") + ul([
            f"대시보드: Grafana → Services → {name} (RED + JVM/런타임)", f"SLO: 가용성 {rng.choice(['99.9', '99.95'])}%, p95 {rng.choice([300, 500, 800])}ms", f"알림: HighErrorRate(P1), HighLatency(P2), KafkaConsumerLag(P2), PodRestart(P3)", f"로그: Loki {{service=\"{name}\"}}, trace_id 로 Tempo 연동"]) + h(1, "운영 절차") + h(2, "스케일링") + p(f"HPA 는 CPU 70% 기준 최소 {rng.choice([3, 4])} 최대 {rng.choice([10, 12, 20])} 이다. 프로모션 등 예상 트래픽은 하루 전 최소 레플리카를 2배로 올린다. 스케일 아웃 후 DB 커넥션 합계(레플리카 × 30)가 DB 한도(500)를 넘지 않는지 확인한다.") + h(2, "장애 시 점검") + ol([
            "최근 배포 여부 확인 (argocd app history)", "Grafana RED 대시보드에서 오류 유형 확인", "의존 서비스(" + ", ".join(s[0] for s in pick(SERVICES, 2)) + ") 상태 확인", "Kafka 컨슈머 랙·DB 커넥션 확인", "필요 시 롤백 또는 스케일 아웃"]) + h(2, "DB 마이그레이션") + p("Flyway 로 관리하며 배포 전 initContainer 에서 실행한다. 파괴적 변경(컬럼 삭제·타입 변경)은 expand-contract 로 2회 배포에 나눈다. 마이그레이션 실패 시 파드가 기동되지 않으므로 롤백 전 DB 상태를 확인한다.") + h(1, "변경 이력") + table(["버전", "일자", "내용"], [
            [f"v{rng.randint(1, 3)}.{i}.0", dstr(_dt(30 * (5 - i))), rng.choice(["Canary 전환", "JDK 21 업그레이드", "Kafka 멱등 프로듀서 적용", "읽기 전용 복제본 분리", "캐시 TTL 조정", "OpenTelemetry 계측 추가", "프로브 튜닝"])] for i in range(5)])
        pages.append(SeedPage("DEVOPS", f"서비스 운영 가이드 — {name}", ["서비스 가이드"], html, _dt(rng.randint(5, 150)), version=rng.randint(2, 12)))
    return pages


def cloud_tenant_pages(n: int) -> List[SeedPage]:
    pages: List[SeedPage] = []
    tenants = [("biz-finance", "corebank"), ("biz-finance", "insurance"), ("biz-logistics", "wms"), ("biz-platform", "commerce"), ("biz-platform", "k8s-prod"), ("biz-rnd", "ml-lab"), ("biz-logistics", "tms"), ("biz-platform", "cs-center"), ("biz-rnd", "data-lake"), ("biz-finance", "claims")]
    for dom, sysname in tenants[:n]:
        env = rng.choice(["prod", "prod", "stg"])
        proj = f"{dom}-{sysname}-{env}"
        vms = rng.randint(8, 40)
        html = toc() + h(1, "프로젝트 정보") + meta_table([("프로젝트", proj), ("도메인", dom), ("환경", env), ("담당(고객)", f"{rng.choice(PEOPLE)} / {rng.choice(PEOPLE)}"), ("플랫폼 담당", rng.choice(PEOPLE)), ("생성일", dstr(_dt(rng.randint(60, 500)))), ("존", rng.choice(["pangyo-a", "pangyo-b", "pangyo-a/b"]))]) + h(1, "네트워크") + table(
            ["네트워크", "서브넷", "라우터", "용도"], [[f"{proj}-web", f"192.168.{rng.randint(100, 200)}.0/24", f"{proj}-rt", "웹/API"], [f"{proj}-app", f"192.168.{rng.randint(100, 200)}.0/24", f"{proj}-rt", "앱"], [f"{proj}-db", f"192.168.{rng.randint(100, 200)}.0/26", f"{proj}-rt", "DB (외부 라우팅 없음)"]]) + p(f"외부 게이트웨이는 provider-{rng.randint(100, 199)} 이며 Floating IP {rng.randint(2, 8)}개를 사용한다. 보안 그룹은 web(443/80), app(8080 from web), db(5432 from app) 3종을 기본으로 한다.") + h(1, "쿼터와 사용량") + table(
            ["항목", "쿼터", "사용"], [["인스턴스", str(rng.choice([50, 100, 150])), str(vms)], ["vCPU", str(rng.choice([400, 800, 1200])), str(vms * rng.choice([4, 8]))], ["메모리", f"{rng.choice([1, 2, 3])}TB", f"{vms * rng.choice([8, 16, 32])}GB"], ["볼륨 용량", f"{rng.choice([10, 20, 40])}TB", f"{rng.randint(2, 15)}TB"], ["Floating IP", "10", str(rng.randint(2, 8))], ["로드밸런서", "10", str(rng.randint(1, 5))]]) + h(1, "VM 목록") + table(
            ["이름", "플레이버", "IP", "역할", "백업"], [[f"{sysname}-{r}-{i:02d}", f, f"192.168.{rng.randint(100, 200)}.{10 + i}", role, b] for r, f, role, b, cnt in [("web", "m2.large", "웹/API", "아니오", 3), ("app", "m2.large", "앱", "아니오", 4), ("db", "r1.2xlarge", "DB", "일 1회", 2), ("mq", "m1.medium", "Kafka", "아니오", 3)] for i in range(1, cnt + 1)]) + h(1, "운영 규칙") + ul([
            "VM 생성·삭제는 Terraform(apps/" + sysname + "/infra) 으로만, 콘솔 수동 변경 금지", "볼륨 스냅샷은 변경 작업 전 필수, 7일 후 삭제", f"백업: DB 볼륨 Cinder 백업 일 1회 02:00, 보존 {rng.choice([14, 30])}일", "보안 그룹 변경은 보안팀 검토 (티켓)", "월 과금은 사업부 코스트센터 " + f"CC-{rng.randint(1000, 9999)}"]) + h(1, "Terraform 요약") + code("hcl", f"""module "{sysname}_db" {{
  source       = "git::https://git.example.com/infra/tf-modules.git//openstack-vm?ref=v2.3.0"
  count        = 2
  name         = "{sysname}-db-${{count.index + 1}}"
  flavor       = "r1.2xlarge"
  image        = "ubuntu-22.04-20260301"
  network      = openstack_networking_network_v2.db.id
  server_group = openstack_compute_servergroup_v2.db_anti.id
  volumes      = [{{ size = 500, type = "ssd" }}]
}}""") + h(1, "변경 이력") + table(["일자", "내용", "담당"], [[dstr(_dt(rng.randint(5, 300))), rng.choice(["vCPU 쿼터 증설", "DB 볼륨 확장 500→1000GB", "Floating IP 추가", "로드밸런서 생성", "존 B 로 일부 VM 이동", "보안 그룹 규칙 추가"]), rng.choice(PEOPLE)] for _ in range(rng.randint(4, 7))])
        pages.append(SeedPage("CLOUD", f"테넌트 구성 — {proj}", ["테넌트"], html, _dt(rng.randint(5, 120)), version=rng.randint(1, 10)))
    return pages


def net_site_and_device_pages(n_sites: int, n_devices: int) -> List[SeedPage]:
    pages: List[SeedPage] = []
    sites = [("부산 DR 센터", "busan", "10.2"), ("서울 본사 사무실", "seoul-hq", "192.168.10"), ("대전 지사", "daejeon", "192.168.40"), ("광주 지사", "gwangju", "192.168.50"), ("판교 R&D 센터", "pangyo-rnd", "192.168.60"), ("인천 물류센터", "incheon", "192.168.70")]
    for name, key, prefix in sites[:n_sites]:
        html = toc() + h(1, "개요") + p(f"{name}({key}) 네트워크 구성이다. 본사/데이터센터와는 " + rng.choice(["전용선 1Gbps + SD-WAN 백업", "SD-WAN(인터넷 2회선)", "전용선 10Gbps ×2"]) + f" 으로 연결되며 사용자 약 {rng.randint(30, 400)}명, 장비 {rng.randint(4, 20)}대를 운영한다. 현장 담당은 {rng.choice(PEOPLE)} 이고 원격 관리는 네트워크팀이 수행한다.") + h(1, "장비") + table(["역할", "모델", "수량", "관리 IP"], [
            ["WAN 라우터/SD-WAN", rng.choice(["FortiGate 200F", "Cisco ISR 4451", "FortiGate 100F"]), "2", f"{prefix}.1~2"], ["코어 스위치", rng.choice(["Catalyst 9300-48P", "Aruba CX 6300"]), "2", f"{prefix}.3~4"], ["액세스 스위치", rng.choice(["Catalyst 9200-48P", "Aruba CX 6100"]), str(rng.randint(2, 10)), f"{prefix}.11~"], ["무선 AP", "Catalyst 9120", str(rng.randint(4, 30)), "DHCP"]]) + h(1, "VLAN") + table(["VLAN", "이름", "서브넷", "용도"], [
            ["10", "mgmt", f"{prefix}.0/24", "장비 관리"], ["100", "office", f"{prefix.rsplit('.', 1)[0]}.{rng.randint(100, 150)}.0/24", "유선 사용자"], ["110", "wifi", f"{prefix.rsplit('.', 1)[0]}.{rng.randint(151, 199)}.0/24", "무선"], ["120", "voip", f"{prefix.rsplit('.', 1)[0]}.{rng.randint(200, 230)}.0/24", "IP 전화"], ["900", "guest", f"{prefix.rsplit('.', 1)[0]}.{rng.randint(231, 250)}.0/24", "방문자(인터넷만)"]]) + h(1, "WAN 및 라우팅") + p(rng.choice([
            "전용선은 OSPF Area 10 으로 본사 코어와 연결되고, SD-WAN 터널은 백업 경로(코스트 200)이다. 전용선 단절 시 BFD 로 1초 내 감지하여 터널로 전환된다.",
            "SD-WAN 은 인터넷 2회선(KT 500M, LG 500M)으로 IPsec 터널을 본사 허브 2대에 맺는다. 업무 트래픽은 지연·손실 기준 SLA 로 경로를 자동 선택한다.",
            "전용선 2회선을 LACP 로 묶고 본사와 eBGP(AS 6500x) 로 피어링한다. 인터넷 브레이크아웃은 허용하지 않으며 모든 트래픽은 본사 방화벽을 경유한다."])) + code("text", f"""interface GigabitEthernet0/0/0
 description WAN-to-HQ
 ip address {prefix}.254 255.255.255.252
 ip ospf 1 area 10
 bfd interval 300 min_rx 300 multiplier 3
router ospf 1
 router-id {prefix}.1
 passive-interface default
 no passive-interface GigabitEthernet0/0/0""") + h(1, "보안") + ul(["지사 → 데이터센터 접근은 본사 방화벽 정책 적용 (지사 전용 존)", "방문자 VLAN 은 인터넷만, 대역폭 10Mbps 제한", "액세스 포트 802.1X (ISE), 실패 시 guest VLAN", "관리 접근은 OOB 또는 본사 점프 서버 경유만"]) + h(1, "운영 이력") + table(["일자", "내용", "담당"], [[dstr(_dt(rng.randint(10, 500))), rng.choice(["액세스 스위치 교체", "AP 추가 6대", "SD-WAN 펌웨어 업그레이드", "전용선 증속", "VoIP VLAN 추가", "전원 공사로 계획 중단 2시간"]), rng.choice(PEOPLE)] for _ in range(rng.randint(3, 6))]) + h(1, "연락처") + table(["구분", "담당", "비고"], [["현장", rng.choice(PEOPLE), "내선 " + str(rng.randint(1000, 9999))], ["회선 사업자", rng.choice(["KT 기업고객센터", "LG U+ 기업", "SK브로드밴드"]), "장애 신고 번호는 운영 포털"], ["네트워크팀", rng.choice(PEOPLE), "온콜"]])
        pages.append(SeedPage("NET", f"{name} 네트워크 구성", ["지사·원격지"], html, _dt(rng.randint(10, 200)), version=rng.randint(1, 8)))
    for i in range(1, n_devices + 1):
        zone = "a" if i % 2 else "b"
        name = f"leaf-{zone}-{(i + 1) // 2:02d}"
        html = h(1, "장비 정보") + meta_table([("호스트명", name), ("모델", rng.choice(SWITCHES)), ("시리얼", f"FDO{rng.randint(20000000, 29999999)}"), ("위치", f"판교 2층 {zone.upper()}열 랙 {rng.randint(1, 12):02d} U{rng.randint(38, 42)}"), ("관리 IP", f"10.50.2.{10 + i}"), ("루프백", f"10.0.255.{10 + i}/32"), ("BGP AS", str(65010 + i)), ("펌웨어", rng.choice(["NX-OS 10.3(4a)", "NX-OS 10.3(3)", "EOS 4.31.2F"])), ("vPC 피어", f"leaf-{'b' if zone == 'a' else 'a'}-{(i + 1) // 2:02d}"), ("도입일", dstr(_dt(rng.randint(200, 900)))), ("보증 만료", dstr(NOW + timedelta(days=rng.randint(100, 900))))]) + h(1, "업링크") + table(
            ["포트", "상대 장비", "상대 포트", "속도", "상태"], [[f"Eth1/{49 + k}", f"spine-{k + 1}", f"Eth1/{i}", "100G", "up"] for k in range(4)]) + h(1, "서버 포트 할당") + table(["포트", "서버", "VLAN", "포트채널", "비고"], [
            [f"Eth1/{k}", f"cmp-{zone}-{k:02d}" if k <= 20 else f"osd-{zone}-{k - 20:02d}", "10,20,30,31,100-199" if k <= 20 else "30,31", f"Po{k}", "MLAG"] for k in range(1, rng.randint(24, 40))]) + h(1, "설정 요약") + code("text", f"""hostname {name}
router bgp {65010 + i}
  router-id 10.0.255.{10 + i}
  neighbor 10.0.255.1 remote-as 65000
  neighbor 10.0.255.2 remote-as 65000
  neighbor 10.0.255.3 remote-as 65000
  neighbor 10.0.255.4 remote-as 65000
vpc domain {(i + 1) // 2}
  peer-keepalive destination 10.50.2.{10 + i + (1 if zone == 'a' else -1)} source 10.50.2.{10 + i}
interface nve1
  source-interface loopback1
  member vni 70001-70010 ingress-replication protocol bgp""") + h(1, "운영 이력") + table(["일자", "내용", "담당"], [[dstr(_dt(rng.randint(5, 600))), rng.choice(["펌웨어 업그레이드(ISSU)", "광 모듈 교체 Eth1/52", "서버 포트 추가 8개", "vPC 일관성 오류 조치", "SNMP v3 사용자 교체", "전원 모듈 교체"]), rng.choice(PEOPLE)] for _ in range(rng.randint(2, 5))]) + h(1, "모니터링") + ul(["Zabbix 템플릿: Cisco Nexus SNMPv3", "임계: CPU 70%, 메모리 80%, 포트 오류 100/분, 광 모듈 수신 -10dBm", "Syslog severity 4 이상 Splunk 알림"])
        pages.append(SeedPage("NET", f"장비 — {name}", ["장비 목록", "리프 스위치"], html, _dt(rng.randint(5, 300)), version=rng.randint(1, 20)))
    return pages


# ──────────────────────────────────────────────────────────────────────────────
# 본문 보강 — 모든 페이지에 주제별 상세 절을 덧붙여 분량을 늘린다
# ──────────────────────────────────────────────────────────────────────────────

_DETAIL = {
    "PROJ": [
        "{t} 관련 의사결정은 설계 검토 회의(주 1회, 목요일 14시)에서 이루어지며 결정 사항은 회의록과 본 페이지에 동시에 기록한다. 결정이 번복되면 사유와 영향 범위를 함께 남긴다.",
        "본 항목의 산출물은 고객 PMO 검수를 받는다. 검수 기준은 요구사항 추적표와의 정합성, 표준 템플릿 준수, 리뷰 코멘트 반영 여부 세 가지이며 검수 결과는 산출물 관리 대장에 기록한다.",
        "일정 영향이 있는 변경은 변경관리위원회(CCB)에 상정한다. CCB 는 격주로 열리며 PM, 고객 PMO, 아키텍트, 품질 담당이 참석한다. 영향도 분석서에는 공수, 일정, 비용, 리스크 네 항목을 반드시 포함한다.",
        "데이터 이관은 세 차례 리허설을 거친다. 1차는 구조 검증, 2차는 전수 데이터 정합성, 3차는 오픈 시나리오와 동일한 시간 제약 안에서의 수행이다. 각 리허설 결과는 건수 비교표와 체크섬으로 검증한다.",
        "테스트는 단위(개발자), 통합(QA), 사용자 인수(현업) 세 단계이며 결함은 심각도 S1~S4 로 분류한다. S1·S2 는 오픈 전 100% 조치, S3 는 90%, S4 는 안정화 기간 내 조치가 원칙이다.",
        "성능 목표는 피크 동시 사용자 기준으로 설정하며 부하 테스트는 운영과 동일한 구성의 스테이징에서 nGrinder 로 수행한다. 결과는 TPS, p95 응답 시간, 오류율, 자원 사용률로 보고한다.",
        "보안 요구사항은 설계 단계에서 보안팀 검토를 받고, 오픈 전 모의해킹 1회와 취약점 점검 1회를 수행한다. 발견된 '상' 등급 취약점은 오픈 전 조치하고 '중' 이하는 안정화 기간 중 조치한다.",
        "운영 이관은 안정화 기간 마지막 2주에 수행하며 운영 매뉴얼, 장애 대응 절차서, 모니터링 대시보드, 온콜 연락망을 인수인계 항목으로 한다. 인수 확인서는 고객 운영팀장이 서명한다.",
        "대외 연계는 기관별 인터페이스 정의서를 기준으로 구현하며, 기관 테스트 환경이 불안정한 경우 스텁 서버로 선행 검증한다. 연계 장애 시 재처리 정책(재시도 3회, 지수 백오프, DLQ)을 공통 모듈로 제공한다.",
        "교육은 관리자 과정(1일)과 사용자 과정(반일)으로 나누어 오픈 2주 전에 진행한다. 교육 자료는 화면 설계서를 기반으로 작성하고 동영상 매뉴얼을 포털에 게시한다.",
    ],
    "DEVOPS": [
        "{t} 에 대한 변경은 모두 Git 을 통해 이루어진다. 수동 변경이 불가피한 경우(장애 대응 등)에는 24시간 내 코드로 반영하고 드리프트 점검(주 1회) 에서 확인한다.",
        "알림은 '행동 가능한 것만' 보낸다는 원칙을 따른다. 담당자가 즉시 할 일이 없는 알림은 대시보드 지표로 내리고, 반복되는 알림은 2주 내 근본 원인을 조치하거나 임계값을 조정한다.",
        "모든 서비스는 SLO 를 정의하고 에러 버짓을 월 단위로 관리한다. 에러 버짓이 50% 이상 소진되면 신규 기능 배포보다 안정화 작업을 우선하며, 100% 소진 시 배포를 동결한다.",
        "배포 창은 평일 10시~16시이며 금요일 오후와 공휴일 전날은 피한다. 긴급 배포는 온콜과 팀 리드 승인 후 가능하고, 배포 직후 30분간 담당자가 대시보드를 관찰한다.",
        "컨테이너 이미지는 distroless 또는 alpine 베이스를 쓰고 루트가 아닌 사용자로 실행한다. 이미지에 시크릿을 포함하지 않으며 빌드 인자로 전달된 값도 레이어에 남지 않도록 멀티스테이지 빌드를 사용한다.",
        "리소스 요청(request)은 실제 사용량의 p95, 제한(limit)은 요청의 2배를 기본으로 한다. 메모리 제한 초과로 OOMKilled 가 반복되면 프로파일링 후 조정하며 무작정 제한을 올리지 않는다.",
        "로그·메트릭·추적은 OpenTelemetry 로 통일한다. trace_id 가 로그에 포함되어 Grafana 에서 로그 → 추적 → 메트릭을 오갈 수 있어야 하며, 신규 서비스는 계측 없이는 운영 배포를 허용하지 않는다.",
        "백업은 복구 테스트가 있어야 유효하다. 분기 1회 실제 복구를 수행하여 RTO 를 측정하고, 결과가 목표를 넘으면 백업 방식이나 인프라를 조정한다.",
        "접근 권한은 최소 권한 원칙을 따른다. 운영 클러스터의 kubectl 권한은 읽기 전용이 기본이며, 쓰기 권한은 배포 파이프라인과 온콜 임시 권한(4시간, 감사 로그)으로만 부여한다.",
        "비용은 네임스페이스 라벨(팀, 서비스, 환경)로 집계하여 월간 보고한다. 유휴 리소스(7일간 CPU 5% 미만)는 자동으로 식별하여 담당 팀에 통보한다.",
    ],
    "CLOUD": [
        "{t} 의 변경은 변경 관리 절차를 따른다. 표준 변경(사전 승인된 반복 작업)은 티켓만으로 수행하고, 일반 변경은 주간 변경 회의 승인, 긴급 변경은 2인 승인 후 사후 보고한다.",
        "용량은 할당률(쿼터 기준)과 실사용률 두 가지로 관리한다. 할당률 75% 에서 증설을 계획하고 85% 에서 신규 프로젝트 생성을 제한한다. 실사용률이 낮은 프로젝트는 분기마다 쿼터 조정을 권고한다.",
        "라이브 마이그레이션은 업무 시간 외에 수행하며, 메모리 사용량이 큰 VM(128GB 이상)은 사전에 담당 팀에 통보한다. 마이그레이션 실패 시 자동 롤백되며 원인은 nova-compute 로그에서 확인한다.",
        "모든 VM 은 qemu-guest-agent 를 설치해야 스냅샷 정합성(quiesce)과 비밀번호 재설정이 가능하다. 표준 이미지에는 기본 포함되어 있으며, 사용자 이미지는 등록 시 확인한다.",
        "스토리지 성능 등급은 ssd(NVMe 3복제)와 hdd(EC) 두 가지다. DB 와 큐는 ssd, 로그·백업·아카이브는 hdd 를 쓰며 볼륨 타입 변경은 retype 으로 온라인 수행 가능하다.",
        "하이퍼바이저 장애 시 VM 은 자동 복구되지 않는다(운영 정책). 담당 팀이 안티어피니티와 애플리케이션 레벨 HA 로 대비해야 하며, 플랫폼팀은 장애 노드의 VM 목록을 15분 내 통보한다.",
        "보안 그룹은 기본 거부이며 프로젝트 간 통신은 라우터와 방화벽을 통해서만 가능하다. 0.0.0.0/0 에 대한 인바운드 허용은 Floating IP 가 붙은 로드밸런서에만 예외적으로 허용한다.",
        "과금 지표는 Ceilometer 가 10분 간격으로 수집하여 Gnocchi 에 저장한다. 월 집계는 매월 1일 새벽에 수행하며 사업부별 청구서는 3일 발송, 이의 신청은 10일까지 받는다.",
        "DR 대상 시스템은 사업 영향도 분석(BIA)에 따라 1등급(RTO 1시간), 2등급(4시간), 3등급(24시간) 으로 분류하며 등급별로 복제 방식과 훈련 주기가 다르다.",
        "플랫폼 업그레이드는 N-1 버전 유지 원칙을 따른다. 업스트림 릴리스 후 3개월 내 스테이징 적용, 6개월 내 운영 적용을 목표로 하며 EoL 버전은 운영하지 않는다.",
    ],
    "NET": [
        "{t} 에 대한 변경은 주 2회(화·목 야간) 정기 변경 창에서 수행한다. 변경 전 설정 백업과 롤백 절차를 티켓에 기록하고, 변경 후 30분간 모니터링 지표를 확인한다.",
        "모든 네트워크 장비 설정은 Oxidized 로 매일 백업되어 Git 에 저장된다. 설정 차이는 Slack 으로 통보되며 승인되지 않은 변경은 담당자가 확인해야 한다.",
        "장비 관리 접근은 OOB 관리망과 TACACS+ 인증으로만 가능하다. 로컬 계정은 TACACS 장애 시 fallback 용이며 비밀번호는 Vault 에 보관하고 분기마다 교체한다.",
        "링크 이중화는 서로 다른 장비·서로 다른 경로(광 케이블 트레이)로 구성한다. 단일 장애점이 있는 구간은 자산 대장에 표시하고 연간 계획에서 해소한다.",
        "QoS 는 VoIP(EF), 업무 중요(AF31), 일반(BE), 백업·복제(AF11) 4개 클래스로 운영한다. WAN 구간에서는 VoIP 에 최소 10% 대역을 보장하고 백업 트래픽은 업무 시간에 30% 로 제한한다.",
        "펌웨어는 벤더 권장 '골든' 버전을 표준으로 하며 연 1회 갱신한다. 보안 취약점(CVSS 9 이상)은 7일 내 패치하고, 패치 전 스테이징 장비에서 48시간 검증한다.",
        "모니터링은 Zabbix(SNMP, ICMP)와 Splunk(Syslog, NetFlow)로 이원화한다. 포트 오류·광 모듈 수신 레벨·CPU·메모리·온도를 임계 기반으로 알리고 NetFlow 로 상위 토커를 분석한다.",
        "방화벽 정책은 분기마다 미사용 규칙(90일 히트 0)을 정리하고, 연 1회 전체 정책을 보안팀과 검토한다. 임시 정책은 만료일을 넘기면 자동 비활성화된다.",
        "케이블은 구조화 배선 표준(TIA-568)을 따르며 라벨은 '랙-U-포트' 형식으로 양 끝에 부착한다. 패치 변경은 NetBox 의 케이블 정보를 먼저 갱신한 뒤 수행한다.",
        "장애 대응 1차는 네트워크팀 온콜이 15분 내 착수하며, 회선 장애는 사업자 고객센터에 즉시 신고하고 신고 번호를 티켓에 기록한다. 복구 후 24시간 내 간단 보고, Sev2 이상은 1주 내 상세 보고서를 작성한다.",
    ],
}

_FAQ = {
    "PROJ": [("이 문서의 최신 버전은 어디서 확인하나?", "본 Confluence 페이지가 최신이며, 산출물 저장소의 docx 는 검수 시점 스냅샷이다."), ("변경 요청은 어떻게 제출하나?", "변경 요청서 템플릿을 작성하여 PM 에게 전달하면 CCB 안건으로 등록된다."), ("일정이 지연되면 어떻게 보고되나?", "주간 보고에서 계획 대비 5%p 이상 지연 시 만회 계획과 함께 보고한다."), ("테스트 환경 접근 권한은 누가 주나?", "PL 이 승인하고 DevOps 담당이 계정을 발급한다. 보통 1영업일 소요."), ("고객 검수 기준은 무엇인가?", "요구사항 추적표 정합성, 표준 템플릿 준수, 리뷰 코멘트 반영 여부이다.")],
    "DEVOPS": [("운영 배포 승인자는 누구인가?", "팀 리드와 운영 담당 2인이며, 둘 중 한 명은 온콜이어야 한다."), ("파이프라인이 scan 단계에서 실패하면?", "Trivy CRITICAL 이 원인이다. 베이스 이미지를 갱신하거나 예외 승인을 보안팀에 요청한다."), ("롤백은 얼마나 걸리나?", "Argo Rollouts undo 기준 1~2분, DB 마이그레이션이 포함되면 별도 절차가 필요하다."), ("운영 kubectl 쓰기 권한이 필요하면?", "온콜 임시 권한(4시간)을 요청하며 모든 명령은 감사 로그에 남는다."), ("알림이 너무 많다.", "행동 불가능한 알림은 대시보드로 내리고 임계값 조정을 PR 로 제안한다.")],
    "CLOUD": [("VM 생성 요청은 어디에 하나?", "Terraform 저장소에 MR 을 올리면 파이프라인이 적용한다. 콘솔 생성은 개발 환경만 허용."), ("쿼터가 부족하면?", "서비스 데스크 '쿼터 증설' 티켓을 올린다. 할당률 75% 미만이면 1영업일 내 승인된다."), ("GPU VM 은 어떻게 받나?", "gpu 애그리게이트는 대기열로 운영한다. R&D 포털에서 예약 후 플레이버 g1.a30 으로 생성."), ("볼륨 성능이 느리다.", "볼륨 타입이 hdd 인지 확인하고 ssd 로 retype 한다. 그래도 느리면 Ceph slow ops 여부를 플랫폼팀에 문의."), ("DR 사이트에서 내 VM 이 기동되나?", "BIA 등급 1~2 만 DR 대상이다. 등급은 테넌트 페이지에 표시된다.")],
    "NET": [("방화벽 정책 적용까지 얼마나 걸리나?", "보안 검토 24시간 + 정기 변경 창(화·목) 이므로 보통 2~4일이다."), ("VPN 접속이 안 된다.", "MFA 등록 여부와 AD 그룹을 먼저 확인한다. 그룹이 맞으면 서비스 데스크에 접속 로그와 함께 문의."), ("새 서버 포트가 필요하다.", "NetBox 에 서버와 케이블을 등록하고 티켓을 올리면 정기 창에 설정된다."), ("특정 사이트가 차단된다.", "URL 필터링 카테고리 때문일 수 있다. 업무 사유와 함께 예외 요청을 보안팀에 제출."), ("회선 장애는 누가 신고하나?", "네트워크팀 온콜이 사업자에 신고하고 신고 번호를 티켓에 기록한다.")],
}

_GLOSSARY = {
    "PROJ": [("CCB", "변경관리위원회. 범위·일정·비용 변경을 심의"), ("M/M", "Man-Month, 1인이 1개월 투입하는 공수"), ("RPO/RTO", "복구 시점 목표 / 복구 시간 목표"), ("UAT", "사용자 인수 테스트"), ("PMO", "프로젝트 관리 조직")],
    "DEVOPS": [("SLO", "서비스 수준 목표, 에러 버짓의 기준"), ("Canary", "일부 트래픽으로 신규 버전을 검증하는 점진적 배포"), ("GitOps", "Git 을 단일 진실 원천으로 하는 배포 방식"), ("PDB", "PodDisruptionBudget, 동시 중단 허용 파드 수"), ("MTTR", "평균 복구 시간")],
    "CLOUD": [("애그리게이트", "컴퓨트 노드를 용도별로 묶은 그룹"), ("플레이버", "VM 사양 템플릿"), ("Floating IP", "외부에서 접근 가능한 공인/사설 IP"), ("OSD", "Ceph 의 디스크 단위 데몬"), ("PG", "Placement Group, Ceph 데이터 분산 단위")],
    "NET": [("MLAG/vPC", "두 스위치를 하나처럼 묶는 링크 집선"), ("VTEP", "VXLAN 터널 종단점"), ("BFD", "링크 장애를 밀리초 단위로 감지하는 프로토콜"), ("OOB", "업무망과 분리된 관리 전용 네트워크"), ("DFW", "NSX 분산 방화벽")],
}


def enrich(pg: SeedPage) -> None:
    t = pg.title.split("]")[-1].strip().split(" — ")[0]
    space = pg.space_key
    details = [d.format(t=t) for d in pick(_DETAIL[space], rng.randint(5, 7))]
    extra = h(1, "상세 설명") + "".join(p(d) for d in details)
    extra += h(1, "운영 체크리스트") + ol(pick([
        "관련 티켓 번호와 변경 창 확인", "설정 백업 및 롤백 절차 준비", "영향 받는 서비스 담당자에게 사전 공지", "변경 후 30분 모니터링 지표 확인", "문서(본 페이지·NetBox·CMDB) 갱신", "회고 항목이 있으면 팀 회의에 등록",
        "테스트 환경에서 선적용 및 검증", "보안팀 검토 필요 여부 확인", "용량·비용 영향 산정", "담당자 부재 시 대체 담당 지정"], rng.randint(5, 8)))
    extra += h(1, "자주 묻는 질문") + "".join(h(2, q) + p(a) for q, a in pick(_FAQ[space], rng.randint(3, 5)))
    extra += h(1, "용어") + table(["용어", "설명"], [[k, v] for k, v in pick(_GLOSSARY[space], rng.randint(3, 5))])
    hist = sorted(rng.sample(range(1, 400), rng.randint(3, 6)), reverse=True)
    extra += h(1, "문서 변경 이력") + table(["일자", "버전", "변경 내용", "작성자"], [[dstr(pg.updated_at - timedelta(days=d)), f"v{len(hist) - i}", rng.choice(["초안 작성", "검토 의견 반영", "표 수정", "절차 보강", "수치 갱신", "용어 정리", "관련 문서 링크 추가"]), rng.choice(PEOPLE)] for i, d in enumerate(hist)])
    extra += h(1, "관련 문서") + ul(pick(["운영 표준 및 절차 모음", "장애 대응 절차서", "변경 관리 절차", "보안 정책(정보보호 규정 제4장)", "용량 계획", "모니터링 표준", "백업 및 복구 정책", "온콜 연락망"], 3))
    pg.html = pg.html + extra


# ──────────────────────────────────────────────────────────────────────────────
# 계획 수립
# ──────────────────────────────────────────────────────────────────────────────

ATT_KINDS_BY_SPACE = {
    "PROJ": ["docx", "pptx", "xlsx", "xlsx", "docx", "pdf"],
    "DEVOPS": ["md", "txt", "xlsx", "docx", "md"],
    "CLOUD": ["xlsx", "pdf", "pptx", "docx", "txt"],
    "NET": ["xlsx", "txt", "pdf", "txt", "docx"],
}


def build_plan(n_pages: int, n_attachments: int) -> List[SeedPage]:
    others = (devops_pages(22) + devops_service_pages(8) + monthly_report_pages("DEVOPS", 10)
              + cloud_pages(10) + cloud_tenant_pages(8) + monthly_report_pages("CLOUD", 12)
              + network_pages(14) + net_site_and_device_pages(5, 8) + monthly_report_pages("NET", 11))
    remaining = max(12, n_pages - len(others))
    n_proj = max(2, min(12, remaining // 15))
    projects = make_projects(n_proj)
    proj_pages: List[SeedPage] = []
    for pj in projects:
        proj_pages += proposal_pages(pj)
    exec_budget = remaining - len(proj_pages)
    per = max(7, exec_budget // n_proj)
    for pj in projects:
        proj_pages += execution_pages(pj, weeks=max(2, per - 5))
    pages = proj_pages + others
    if len(pages) > n_pages:
        weekly = [p for p in pages if "주간 보고" in p.title]
        drop = set(id(p) for p in rng.sample(weekly, min(len(weekly), len(pages) - n_pages)))
        pages = [p for p in pages if id(p) not in drop][:n_pages]
    elif len(pages) < n_pages:
        pages += monthly_report_pages("DEVOPS", 13)[: n_pages - len(pages)]

    for pg in pages:
        enrich(pg)

    pid = 10000000
    for pg in pages:
        pid += rng.randint(3, 40)
        pg.page_id = str(pid)
    order = pages[:]
    rng.shuffle(order)
    aid = 50000000
    assigned = 0
    i = 0
    while assigned < n_attachments and i < len(order) * 3:
        pg = order[i % len(order)]
        kind = rng.choice(ATT_KINDS_BY_SPACE[pg.space_key])
        for att in build_attachments(pg, [kind]):
            aid += rng.randint(1, 9)
            att.att_id = str(aid)
            att.version = rng.randint(1, 4)
            pg.attachments.append(att)
            assigned += 1
        i += 1
    return pages


# ──────────────────────────────────────────────────────────────────────────────
# 적재
# ──────────────────────────────────────────────────────────────────────────────

def _page_path(pg: SeedPage) -> str:
    return " > ".join([pg.space_key] + pg.ancestors + [pg.title])


def _page_url(pg: SeedPage) -> str:
    return f"{BASE_URL}/spaces/{pg.space_key}/pages/{pg.page_id}"


async def index_page(pg: SeedPage, run: SyncRun) -> Tuple[int, int]:
    path = _page_path(pg)
    body_hash = indexer.content_hash(pg.title, path, pg.html, ",".join(sorted(pg.allowed_groups)))
    sections = parse_storage_html(pg.html)
    drafts = chunk_sections(sections, path)
    n_chunks = 0
    n_att = 0
    async with AsyncSessionLocal() as db:
        n_chunks = await indexer.upsert_document(
            db, space_key=pg.space_key, page_id=pg.page_id, attachment_id=None, title=pg.title, path=path, url=_page_url(pg),
            kind="page", file_name=None, version=pg.version, c_hash=body_hash, updated_at=pg.updated_at, allowed_groups=pg.allowed_groups, drafts=drafts,
        )
        await db.commit()
    run.pages_seen += 1
    run.pages_indexed += 1
    for att in pg.attachments:
        try:
            secs = parse_attachment(att.file_name, att.data)
            apath = f"{path} > {att.file_name}"
            adrafts = chunk_sections(secs, apath)
            if not adrafts:
                logger.warning("attachment produced no text: %s", att.file_name)
                continue
            c_hash = indexer.content_hash(att.file_name, str(att.version), str(len(att.data)))
            async with AsyncSessionLocal() as db:
                n = await indexer.upsert_document(
                    db, space_key=pg.space_key, page_id=pg.page_id, attachment_id=att.att_id, title=f"{pg.title} — {att.file_name}", path=apath,
                    url=f"{_page_url(pg)}/attachments/{att.att_id}", kind="attachment", file_name=att.file_name, version=att.version, c_hash=c_hash,
                    updated_at=pg.updated_at + timedelta(hours=rng.randint(1, 48)), allowed_groups=pg.allowed_groups, drafts=adrafts,
                )
                await db.commit()
            n_chunks += n
            n_att += 1
            run.attachments_indexed += 1
        except Exception as e:  # noqa: BLE001
            run.errors += 1
            logger.warning("attachment failed %s: %s", att.file_name, e)
    async with AsyncSessionLocal() as db:
        await indexer.set_sync_state(db, pg.page_id, pg.space_key, pg.version, body_hash, None)
        await db.commit()
    return n_chunks, n_att


async def reset_schema() -> None:
    from app.db import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("schema reset: embedding dim=%d", settings.embedding_dim)


async def check_dim() -> None:
    from sqlalchemy import text as sqltext
    async with engine.connect() as conn:
        r = (await conn.execute(sqltext("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"))).scalar()
    if r is not None and r != settings.embedding_dim:
        raise SystemExit(f"DB 의 embedding 차원({r})과 EMBEDDING_DIM({settings.embedding_dim})이 다릅니다. --reset 으로 테이블을 다시 만드세요.")


async def run_seed(pages: List[SeedPage]) -> None:
    from app.db.session import ensure_schema
    await ensure_schema()
    await check_dim()
    by_space: Dict[str, List[SeedPage]] = {}
    for pg in pages:
        by_space.setdefault(pg.space_key, []).append(pg)
    total_chunks = 0
    for space, plist in by_space.items():
        async with AsyncSessionLocal() as db:
            run = SyncRun(space_key=space, mode="full")
            db.add(run)
            await db.commit()
            await db.refresh(run)
        t0 = datetime.now()
        for i, pg in enumerate(plist, 1):
            try:
                n, a = await index_page(pg, run)
                total_chunks += n
                logger.info("[%s] %d/%d '%s' -> %d chunks, %d attachments", space, i, len(plist), pg.title[:50], n, a)
            except Exception as e:  # noqa: BLE001
                run.errors += 1
                logger.error("[%s] page '%s' failed: %s", space, pg.title, e, exc_info=True)
                async with AsyncSessionLocal() as db:
                    await indexer.set_sync_state(db, pg.page_id, space, pg.version, "seed", str(e)[:2000])
                    await db.commit()
        run.status = "success" if run.errors == 0 else "success"
        run.finished_at = datetime.now(timezone.utc)
        run.message = f"seed_data.py ({(datetime.now() - t0).seconds}s)"
        async with AsyncSessionLocal() as db:
            await db.merge(run)
            await db.commit()
        logger.info("[%s] done: pages=%d attachments=%d errors=%d", space, run.pages_indexed, run.attachments_indexed, run.errors)
    logger.info("TOTAL pages=%d attachments=%d chunks=%d", len(pages), sum(len(p.attachments) for p in pages), total_chunks)
    await engine.dispose()


def dump(pages: List[SeedPage], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    total_chars = 0
    for pg in pages:
        d = out_dir / pg.space_key
        d.mkdir(exist_ok=True)
        safe = pg.title.replace("/", "-").replace(" ", "_")[:80]
        (d / f"{pg.page_id}_{safe}.html").write_text(pg.html, encoding="utf-8")
        text_len = sum(len(s.text) for s in parse_storage_html(pg.html))
        total_chars += text_len
        for att in pg.attachments:
            (d / f"{pg.page_id}_{att.file_name}").write_bytes(att.data)
    n_att = sum(len(p.attachments) for p in pages)
    print(f"pages={len(pages)} attachments={n_att} avg_text_chars/page={total_chars // max(1, len(pages))} -> {out_dir}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description="confluence-kb 테스트 시드 데이터 생성")
    ap.add_argument("--pages", type=int, default=200)
    ap.add_argument("--attachments", type=int, default=100)
    ap.add_argument("--reset", action="store_true", help="테이블을 모두 지우고 다시 만든 뒤 적재 (EMBEDDING_DIM 변경 시 필수)")
    ap.add_argument("--dump", metavar="DIR", help="DB 대신 디렉터리에 HTML·첨부 파일로 저장 (확인용)")
    args = ap.parse_args()

    pages = build_plan(args.pages, args.attachments)
    if args.dump:
        dump(pages, Path(args.dump))
        return
    if args.reset:
        asyncio.run(reset_schema())
    logger.info("embedding: %s %s dim=%d", settings.embedding_base_url, settings.embedding_model, settings.embedding_dim)
    asyncio.run(run_seed(pages))


if __name__ == "__main__":
    main()
