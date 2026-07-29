"""
hallucination_guard.py — Career Analysis AI 환각 차단 공용 가드 (v3.0)

설계 전제
─────────
이 모듈은 **LLM 의 자기 보고를 일절 신뢰하지 않는다**는 전제 위에 만들어졌다.

v2.0 의 검증 로직은 "LLM 이 만든 항목"을 "같은 LLM 에게 물어봐서" 검증했다.
이는 검증이 아니라 확증편향 증폭기다. 생성자와 검증자가 같은 파라메트릭 메모리를
공유하므로, 존재하지 않는 자격증·동아리·URL 은 두 번 모두 동일하게 '확신'된다.

v3.0 의 가드는 세 종류의 신뢰 원천만 인정한다.

  (1) 사용자 입력 원문         — STAR / 강점 / 약점 근거의 유일한 출처
  (2) 검색 그라운딩 메타데이터 — 모델 주장이 아니라 실제 검색 결과 chunk
  (3) 실제 HTTP 응답           — URL 은 살아있는 것만 부착

위 셋 중 어느 것으로도 뒷받침되지 않는 값은 코드가 **기계적으로 제거**한다.
모델에게 "하지 마세요"라고 부탁하는 방식(프롬프트 규칙)은 보조 수단일 뿐이며,
최종 방어선은 전부 이 모듈의 결정론적 함수들이다.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable

# ══════════════════════════════════════════════════════════════
#  0. 공통 정규화
# ══════════════════════════════════════════════════════════════

_PUNCT_RE = re.compile(r"[\s　()\[\]{}<>·・,.;:!?'\"`~\-–—_/\\|+*&#@^]+")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def norm_name(s: str) -> str:
    """항목명 매칭용 정규화 — 공백/괄호/구두점 제거 후 소문자화.

    v2.0 의 vmap 은 `{r["name"]: r}` 처럼 원문 문자열을 키로 썼다.
    검증 모델이 '(사)한국OO협회' → '한국 OO 협회' 처럼 살짝 다르게 되돌려주면
    매칭이 실패하고, 그 실패가 그대로 '검증 실패 → 제외' 또는 반대로
    '기본값 통과'로 흘러가 결과가 요동쳤다.
    """
    if not s:
        return ""
    return _PUNCT_RE.sub("", str(s)).lower()


def norm_text(s: str) -> str:
    """인용문 대조용 정규화 — 공백/구두점을 모두 제거한 연속 문자열."""
    return _PUNCT_RE.sub("", str(s or "")).lower()


def name_tokens(s: str, min_len: int = 2) -> set[str]:
    """항목명에서 의미 토큰 추출 (그라운딩 대조·URL 콘텐츠 대조용)."""
    if not s:
        return set()
    parts = re.split(r"[\s　()\[\]{}<>·・,.;:!?'\"`~\-–—_/\\|+*&#@^]+", str(s))
    return {p.lower() for p in parts if len(p) >= min_len}


def extract_numbers(s: str) -> set[str]:
    """텍스트에 등장하는 모든 수치를 정규화된 문자열 집합으로."""
    out = set()
    for m in _NUM_RE.finditer(str(s or "")):
        raw = m.group(0).replace(",", "")
        if raw.endswith(".0"):
            raw = raw[:-2]
        out.add(raw)
    return out


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ══════════════════════════════════════════════════════════════
#  1. 감사 추적 (Verification Audit)
# ══════════════════════════════════════════════════════════════

@dataclass
class AuditRecord:
    stage: str          # certifications / clubs / contests / jobs / star / url
    item: str
    outcome: str        # kept / dropped / degraded
    reason: str

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "item": self.item,
            "outcome": self.outcome,
            "reason": self.reason,
        }


@dataclass
class VerificationAudit:
    """무엇이 왜 제거되었는지 전부 기록한다.

    v2.0 은 드롭 사유를 stdout 에만 print 했기 때문에, 최종 산출물만 보면
    '환각이 얼마나 걸러졌는지 / 왜 추천이 비었는지'를 알 수 없었다.
    측정할 수 없는 환각은 고칠 수도 없다.
    """
    records: list[AuditRecord] = field(default_factory=list)

    def log(self, stage: str, item: str, outcome: str, reason: str) -> None:
        self.records.append(AuditRecord(stage, item, outcome, reason))

    def kept(self, stage: str, item: str, reason: str = "") -> None:
        self.log(stage, item, "kept", reason)

    def dropped(self, stage: str, item: str, reason: str) -> None:
        self.log(stage, item, "dropped", reason)

    def degraded(self, stage: str, item: str, reason: str) -> None:
        self.log(stage, item, "degraded", reason)

    def summary(self) -> dict:
        by_stage: dict[str, dict[str, int]] = {}
        for r in self.records:
            bucket = by_stage.setdefault(r.stage, {"kept": 0, "dropped": 0, "degraded": 0})
            bucket[r.outcome] = bucket.get(r.outcome, 0) + 1
        total_drop = sum(1 for r in self.records if r.outcome == "dropped")
        return {
            "by_stage": by_stage,
            "total_dropped": total_drop,
            "total_degraded": sum(1 for r in self.records if r.outcome == "degraded"),
            "total_kept": sum(1 for r in self.records if r.outcome == "kept"),
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "records": [r.to_dict() for r in self.records],
        }


# ══════════════════════════════════════════════════════════════
#  2. URL 실재성 검증 (Zero-Trust URL)
# ══════════════════════════════════════════════════════════════
#
#  원칙: 모델은 URL 을 '출력할 수 없다'.
#        URL 은 오직 아래 두 경로로만 결과물에 들어온다.
#          A) 검색 그라운딩 메타데이터가 실제로 반환한 소스 URI
#          B) 사용자 입력 원문에 이미 포함되어 있던 URL
#        그리고 A/B 모두 아래 probe_url() 의 HTTP 검사를 통과해야 한다.

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# HTTP 200 을 주면서 실제로는 '없는 페이지'를 보여주는 soft-404 마커.
# v2.0 의 _verify_url_content 는 status<400 만 확인했기 때문에 soft-404 를
# 전부 '살아있는 링크'로 통과시켰다. 죽은 링크 신고의 상당수가 이 경로였다.
_SOFT_404_MARKERS = (
    "페이지를 찾을 수 없", "요청하신 페이지", "존재하지 않는 페이지",
    "삭제되었거나", "잘못된 접근", "이동되었거나", "서비스가 종료",
    "마감된 공고", "종료된 채용", "page not found", "not found",
    "404 error", "error 404", "no longer available", "has expired",
    "this page isn", "went wrong",
)

# 링크 실재성과 무관하게 어떤 질의든 200 을 돌려주는 '만능 URL'.
# 모델이 가장 흔히 지어내는 형태이므로 URL 후보에서 원천 배제한다.
_GENERIC_URL_HOSTS = (
    "google.com", "www.google.com", "search.naver.com", "naver.me",
    "bing.com", "duckduckgo.com", "example.com", "localhost",
)

_BLOCKED_SCHEMES = ("javascript", "data", "file", "ftp", "mailto", "tel")


@dataclass
class UrlProbe:
    ok: bool
    url: str | None = None
    final_url: str | None = None
    status: int | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "reason": self.reason,
        }


def _host_is_public(host: str) -> bool:
    """SSRF 방지 — 사설/루프백/링크로컬 주소로 향하는 URL 은 프로브하지 않는다."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def is_plausible_url(url: Any) -> bool:
    """구조적으로 부적격한 URL 후보를 사전 배제."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    if not u or u.lower() in ("null", "none", "n/a", "-", "미정", "확인 불가"):
        return False
    parsed = urllib.parse.urlparse(u)
    if parsed.scheme.lower() in _BLOCKED_SCHEMES:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    host = (parsed.netloc or "").split("@")[-1].split(":")[0].lower()
    if not host or "." not in host:
        return False
    if host in _GENERIC_URL_HOSTS:
        return False
    return True


def probe_url(
    url: str,
    expect_tokens: Iterable[str] = (),
    timeout: int = 10,
    max_bytes: int = 120_000,
    min_token_hits: int = 1,
) -> UrlProbe:
    """URL 이 (a) 실제로 200 을 주고 (b) soft-404 가 아니며
    (c) 기대 토큰이 본문에 등장하는지를 실제 HTTP 요청으로 확인한다.

    세 조건을 모두 만족해야만 ok=True. 하나라도 불확실하면 fail-closed.
    """
    tokens = [t for t in {str(t).lower().strip() for t in expect_tokens} if len(t) >= 2]

    if not is_plausible_url(url):
        return UrlProbe(False, url, reason="URL 형식 부적격 또는 범용 검색 URL")

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.split("@")[-1].split(":")[0]
    if not _host_is_public(host):
        return UrlProbe(False, url, reason=f"호스트 해석 실패 또는 비공개 주소({host})")

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            final_url = resp.geturl()
            body = resp.read(max_bytes).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return UrlProbe(False, url, status=e.code, reason=f"HTTP {e.code}")
    except Exception as e:  # DNS 실패, 타임아웃, TLS 오류 등
        return UrlProbe(False, url, reason=f"접근 실패: {str(e)[:100]}")

    if status is None or status >= 400:
        return UrlProbe(False, url, final_url, status, f"HTTP {status}")

    low = body.lower()
    for marker in _SOFT_404_MARKERS:
        if marker in low:
            return UrlProbe(False, url, final_url, status, f"soft-404 감지('{marker}')")

    if tokens:
        flat = norm_text(body)
        hits = [t for t in tokens if norm_text(t) and norm_text(t) in flat]
        if len(hits) < min_token_hits:
            return UrlProbe(
                False, url, final_url, status,
                f"본문에서 기대 키워드 미발견({', '.join(tokens[:4])})",
            )

    return UrlProbe(True, url, final_url, status, "OK")


def pick_verified_url(
    candidates: Iterable[str],
    expect_tokens: Iterable[str],
    audit: VerificationAudit | None = None,
    stage: str = "url",
    label: str = "",
    timeout: int = 10,
) -> tuple[str | None, str]:
    """후보 URL 들을 순서대로 프로브해 최초로 통과한 것만 채택.

    통과하는 것이 없으면 (None, 사유) — 빈 문자열이 아니라 명시적 None.
    """
    reasons: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        if not is_plausible_url(cand):
            continue
        key = str(cand).strip().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        res = probe_url(key, expect_tokens, timeout=timeout)
        if res.ok:
            if audit:
                audit.kept(stage, label or key, f"URL 검증 통과({res.final_url})")
            return res.final_url or key, "verified"
        reasons.append(f"{key} → {res.reason}")
    reason = "; ".join(reasons) if reasons else "검증 가능한 URL 후보 없음"
    if audit:
        audit.degraded(stage, label or "(무명)", f"URL 미부착: {reason}")
    return None, reason


_URL_KEYS = ("url", "official_url", "link", "homepage", "site", "correct_url", "apply_url")


def scrub_model_urls(obj: Any, allowlist: set[str] | None = None) -> int:
    """모델 산출물 전체를 훑어 검증되지 않은 URL 필드를 None 으로 만든다.

    프롬프트로 'URL 을 출력하지 마라'고 지시해도 모델은 종종 출력한다.
    그래서 파이프라인 진입 직후 한 번, 최종 직렬화 직전에 한 번 더 훑는다.
    (defense in depth — 프롬프트는 요청, 이 함수는 강제)
    """
    allow = allowlist or set()
    removed = 0
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in _URL_KEYS and isinstance(v, str):
                if v.strip().rstrip("/") not in allow:
                    obj[k] = None
                    removed += 1
            else:
                removed += scrub_model_urls(v, allow)
    elif isinstance(obj, list):
        for v in obj:
            removed += scrub_model_urls(v, allow)
    return removed


# ══════════════════════════════════════════════════════════════
#  3. 검색 그라운딩 증거 추출·대조
# ══════════════════════════════════════════════════════════════
#
#  v2.0 은 tools=[GoogleSearch] 를 넘기기만 하고, 모델이 실제로 검색했는지
#  전혀 확인하지 않았다. Gemini 는 검색 도구가 붙어 있어도 '검색 없이'
#  파라메트릭 메모리로 답할 수 있고, 그 답에 "verified": true 를 붙인다.
#  → 검색 검증처럼 보이지만 실제로는 기억 기반 자기확신이었다.

@dataclass
class GroundingEvidence:
    uris: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        """실제 검색 결과 chunk 가 하나라도 있었는가."""
        return bool(self.uris or self.snippets)

    def haystack(self) -> str:
        parts = self.titles + self.snippets + [urllib.parse.unquote(u) for u in self.uris]
        return norm_text(" ".join(parts))

    def to_dict(self) -> dict:
        return {
            "grounded": self.grounded,
            "source_count": len(self.uris),
            "queries": self.queries[:10],
            "sources": self.uris[:20],
        }


def extract_grounding(resp: Any) -> GroundingEvidence:
    """google-genai 응답에서 실제 검색 근거를 뽑아낸다.

    SDK 버전에 따라 필드가 달라질 수 있으므로 전부 getattr 방어.
    """
    ev = GroundingEvidence()
    candidates = getattr(resp, "candidates", None) or []
    for cand in candidates:
        gm = getattr(cand, "grounding_metadata", None)
        if gm is None:
            continue
        for q in (getattr(gm, "web_search_queries", None) or []):
            if q:
                ev.queries.append(str(q))
        for chunk in (getattr(gm, "grounding_chunks", None) or []):
            web = getattr(chunk, "web", None)
            if web is None:
                continue
            uri = getattr(web, "uri", None)
            title = getattr(web, "title", None)
            if uri:
                ev.uris.append(str(uri))
            if title:
                ev.titles.append(str(title))
        for sup in (getattr(gm, "grounding_supports", None) or []):
            seg = getattr(sup, "segment", None)
            text = getattr(seg, "text", None) if seg is not None else None
            if text:
                ev.snippets.append(str(text))
    return ev


def grounding_mentions(name: str, ev: GroundingEvidence, min_ratio: float = 0.6) -> bool:
    """항목명이 실제 검색 근거(제목/스니펫/URI)에 등장하는지 코드가 직접 대조.

    모델이 "verified": true 라고 말해도, 그 이름이 검색 근거 어디에도 없으면
    통과시키지 않는다. 이것이 v3.0 검증의 핵심 관문이다.
    """
    if not ev.grounded:
        return False
    hay = ev.haystack()
    flat = norm_text(name)
    if flat and flat in hay:
        return True
    toks = [t for t in name_tokens(name) if len(t) >= 2]
    if not toks:
        return False
    hits = sum(1 for t in toks if norm_text(t) in hay)
    return (hits / len(toks)) >= min_ratio


# ══════════════════════════════════════════════════════════════
#  4. 자격증 실재성 검증 (레지스트리 + 등급 문법)
# ══════════════════════════════════════════════════════════════
#
#  "없는 자격증을 추천한다"의 실제 양상은 두 가지였다.
#    (A) 완전 허구      : '데이터마케팅전문가 1급' 같은 존재하지 않는 이름
#    (B) 등급 환각      : 실재 자격증 + 존재하지 않는 등급 조합
#                         (예: 빅데이터분석기사는 등급이 없는데 '2급'을 붙임,
#                              정보처리기사에 '1급'을 붙임)
#  (B) 는 검색해도 상위 결과에 원본 자격증이 잡히기 때문에 LLM 검증이
#  가장 잘 속는 유형이다. 그래서 등급 문법은 코드가 직접 검사한다.

_GRADE_RE = re.compile(
    r"\s*(?:(\d)\s*급|(특급|고급|중급|초급|심화|기본|전문가|준전문가|마스터|1종|2종))\s*$"
)

# canonical 자격증 → 허용 등급 집합 (빈 집합 = 등급 표기 자체가 존재하지 않음)
_CERT_REGISTRY: dict[str, set[str]] = {
    # ── 국가기술자격 (등급이 종목명에 내장되어 별도 급수 없음) ──
    "정보처리기사": set(), "정보처리산업기사": set(), "정보처리기능사": set(),
    "빅데이터분석기사": set(), "정보보안기사": set(), "정보보안산업기사": set(),
    "전자계산기조직응용기사": set(), "산업안전기사": set(), "산업안전산업기사": set(),
    "전기기사": set(), "전기산업기사": set(), "전기공사기사": set(),
    "화공기사": set(), "위험물산업기사": set(), "위험물기능사": set(),
    "품질경영기사": set(), "품질경영산업기사": set(),
    "건축기사": set(), "토목기사": set(), "기계설계산업기사": set(),
    "에너지관리기사": set(), "소방설비기사": set(),
    "컨벤션기획사": {"1급", "2급"},
    "사회조사분석사": {"1급", "2급"},
    "직업상담사": {"1급", "2급"},
    "임상심리사": {"1급", "2급"},
    "스포츠경영관리사": set(), "텔레마케팅관리사": set(),
    "전자상거래관리사": {"1급", "2급"}, "전자상거래운용사": set(),
    "컴퓨터활용능력": {"1급", "2급"},
    "워드프로세서": set(),
    "정보기기운용기능사": set(),
    # ── 국가전문자격 ──
    "공인회계사": set(), "세무사": set(), "관세사": set(), "노무사": set(),
    "공인노무사": set(), "변리사": set(), "감정평가사": set(),
    "공인중개사": set(), "주택관리사": set(), "손해평가사": set(),
    "손해사정사": set(), "보험계리사": set(), "물류관리사": set(),
    "국제무역사": {"1급"}, "원산지관리사": set(),
    "사회복지사": {"1급", "2급"}, "보육교사": {"1급", "2급", "3급"},
    "청소년상담사": {"1급", "2급", "3급"}, "평생교육사": {"1급", "2급", "3급"},
    "한국사능력검정시험": {"심화", "기본", "1급", "2급", "3급", "4급", "5급", "6급"},
    # ── 공인 민간/협회 자격 ──
    "sqld": set(), "sqlp": set(), "adsp": set(), "adp": set(),
    "데이터분석준전문가": set(), "데이터분석전문가": set(),
    "sql개발자": set(), "sql전문가": set(),
    "dap": set(), "dasp": set(),
    "유통관리사": {"1급", "2급", "3급"},
    "무역영어": {"1급", "2급", "3급"},
    "전산세무": {"1급", "2급"}, "전산회계": {"1급", "2급"},
    "재경관리사": set(), "회계관리": {"1급", "2급"},
    "erp정보관리사": {"1급", "2급"},
    "네트워크관리사": {"1급", "2급"}, "리눅스마스터": {"1급", "2급"},
    "정보통신기사": set(),
    "gtq": {"1급", "2급", "3급"}, "gtqi": {"1급", "2급"},
    "itq": set(), "mos": set(), "e-test": set(),
    "tesat": set(), "매경test": set(), "한경test": set(),
    "kbs한국어능력시험": set(), "국어능력인증시험": set(),
    "브랜드매니저": set(), "경영지도사": set(), "기술지도사": set(),
    # ── 국제 자격 ──
    "pmp": set(), "cfa": set(), "frm": set(), "cpa": set(), "aicpa": set(),
    "cisa": set(), "cissp": set(), "ceh": set(), "ccna": set(), "ccnp": set(),
    "toeic": set(), "toefl": set(), "opic": set(), "ielts": set(),
    "toeicspeaking": set(), "jlpt": set(), "hsk": set(), "delf": set(),
    "awscertifiedcloudpractitioner": set(),
    "awscertifiedsolutionsarchitectassociate": set(),
    "awscertifieddeveloperassociate": set(),
    "googleanalyticscertification": set(), "gaiq": set(),
    "googleadscertification": set(),
    "azurefundamentals": set(), "az900": set(),
    "tableaudesktopspecialist": set(),
}

# 별칭 → canonical
_CERT_ALIASES = {
    "sql개발자": "sqld", "sql전문가": "sqlp",
    "데이터분석준전문가": "adsp", "데이터분석전문가": "adp",
    "구글애널리틱스": "googleanalyticscertification",
    "구글애널리틱스자격증": "googleanalyticscertification",
    "토익": "toeic", "토플": "toefl", "오픽": "opic",
    "토익스피킹": "toeicspeaking",
    "컴활": "컴퓨터활용능력",
    "한국사": "한국사능력검정시험",
    "정보처리기사자격증": "정보처리기사",
    "aws솔루션스아키텍트": "awscertifiedsolutionsarchitectassociate",
}


@dataclass
class CertCheck:
    verdict: str        # known / grade_invalid / unknown
    canonical: str
    grade: str | None
    reason: str

    @property
    def rejected(self) -> bool:
        return self.verdict == "grade_invalid"

    @property
    def needs_search(self) -> bool:
        return self.verdict == "unknown"


def split_cert_grade(name: str) -> tuple[str, str | None]:
    """'컴퓨터활용능력 1급' → ('컴퓨터활용능력', '1급')"""
    raw = str(name or "").strip()
    m = _GRADE_RE.search(raw)
    if not m:
        return raw, None
    grade = f"{m.group(1)}급" if m.group(1) else m.group(2)
    base = raw[: m.start()].strip()
    return base, grade


def check_certification_name(name: str) -> CertCheck:
    """자격증명을 레지스트리·등급 문법으로 검사한다 (네트워크 불필요, 결정론적).

    - known         : 레지스트리에 있고 등급 표기도 유효 → 통과 (검색 검증 생략 가능)
    - grade_invalid : 실재 자격증이지만 존재하지 않는 등급 → 즉시 제외
    - unknown       : 레지스트리에 없음 → 검색 그라운딩 검증 필수
    """
    base, grade = split_cert_grade(name)
    key = norm_name(base)
    key = _CERT_ALIASES.get(key, key)

    if key not in _CERT_REGISTRY:
        return CertCheck("unknown", base, grade, "공식 자격증 레지스트리 미등재 → 검색 검증 필요")

    allowed = _CERT_REGISTRY[key]
    if grade is None:
        if allowed:
            return CertCheck("known", base, None,
                             f"등급 미표기(유효 등급: {'/'.join(sorted(allowed))})")
        return CertCheck("known", base, None, "레지스트리 등재 자격증")

    if not allowed:
        return CertCheck(
            "grade_invalid", base, grade,
            f"'{base}'는 등급 체계가 없는 자격증인데 '{grade}' 표기가 붙음 (등급 환각)",
        )
    if grade not in allowed:
        return CertCheck(
            "grade_invalid", base, grade,
            f"'{base}'의 유효 등급은 {'/'.join(sorted(allowed))} — '{grade}'는 존재하지 않음",
        )
    return CertCheck("known", base, grade, "레지스트리 등재 자격증 + 유효 등급")


# ══════════════════════════════════════════════════════════════
#  5. STAR 근거 결속 (Evidence-bound STAR)
# ══════════════════════════════════════════════════════════════
#
#  v2.0 의 STAR 문제는 두 가지가 겹친 결과였다.
#    (1) 데이터가 충분해도 STAR 가 '사용자 문장 재배치'에 그침
#        → S/T/A/R 네 슬롯이 같은 한 문장을 네 번 바꿔 쓴 것
#    (2) 데이터가 부족하면 없는 이야기를 지어냄
#        → 규칙 7 이 "지어내지 말라"고 했지만, 출력 스키마에
#          resume_star_format 이 예시 객체와 함께 항상 존재했다.
#          모델에게 "빈 값을 반환하라"는 구조적 통로가 없으면
#          스키마가 규칙을 이긴다.
#
#  v3.0:
#    - 생성 전에 코드가 입력의 STAR 적합성을 판정하고, 미달이면
#      LLM 에 STAR 생성을 아예 요청하지 않는다.
#    - 생성한 경우에도 각 슬롯에 source_quote 를 강제하고,
#      그 인용문이 원문에 실제로 있는지 코드가 대조한다.
#    - 슬롯 간 인용문이 과도하게 겹치면 '재구조화'로 판정해 강등한다.
#    - 결과(R)의 모든 수치가 원문에 있는지 확인한다.

_ACTION_VERBS = (
    "개발", "구축", "설계", "구현", "분석", "운영", "기획", "주도", "리드", "리딩",
    "개선", "도입", "작성", "제작", "협업", "수행", "담당", "조사", "발표", "관리",
    "최적화", "자동화", "배포", "테스트", "모집", "교육", "상담", "번역", "조율",
    "제안", "설득", "유치", "달성", "출시", "런칭", "진행", "총괄", "구성", "정리",
)

_ROLE_MARKERS = (
    "담당", "역할", "팀장", "리더", "파트장", "조장", "회장", "부회장", "총무",
    "pm", "po", "기획자", "개발자", "디자이너", "운영진", "인턴", "매니저", "대표",
)

_METRIC_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|퍼센트|배|명|건|회|개|팀|위|등|점|억|천만|백만|만원|천원|"
    r"원|달러|시간|분|일|주|개월|년|주차|차|kb|mb|gb|ms|초)"
)
_PERIOD_RE = re.compile(
    r"(20\d{2}\s*[.\-/년]\s*\d{1,2}|20\d{2}\s*년|\d+\s*(?:개월|년|주|학기)\s*(?:간|동안)?)"
)


@dataclass
class ExperienceBlock:
    raw: str
    score: int
    signals: dict[str, bool]

    @property
    def eligible(self) -> bool:
        return self.score >= 4


@dataclass
class StarReadiness:
    ready: bool
    blocks: list[ExperienceBlock]
    reason: str
    coaching: list[str]

    @property
    def eligible_blocks(self) -> list[ExperienceBlock]:
        return [b for b in self.blocks if b.eligible]

    def to_dict(self) -> dict:
        return {
            "generated": self.ready,
            "reason": self.reason,
            "experience_block_count": len(self.blocks),
            "star_eligible_block_count": len(self.eligible_blocks),
            "coaching": self.coaching,
        }


def split_experience_blocks(text: str) -> list[str]:
    """입력 원문을 경험 단위 블록으로 분해."""
    if not text:
        return []
    body = re.sub(r"^\[SOURCE_URL:[^\]]*\]\s*", "", text).strip()
    chunks = re.split(r"\n\s*\n+", body)
    blocks: list[str] = []
    for chunk in chunks:
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        if not lines:
            continue
        # 불릿이 여러 개인 덩어리는 불릿 단위로 다시 쪼갠다.
        bullets = [l for l in lines if re.match(r"^[-*·•▪◦●•]|^\d+[.)]", l)]
        if len(bullets) >= 2 and len(lines) - len(bullets) <= 1:
            header = next((l for l in lines if l not in bullets), "")
            for b in bullets:
                blocks.append((header + " " + b).strip() if header else b)
        else:
            blocks.append(" ".join(lines))
    return [b for b in blocks if len(b) >= 10]


def _score_block(block: str) -> ExperienceBlock:
    signals = {
        "length": len(block) >= 60,
        "action_verb": any(v in block for v in _ACTION_VERBS),
        "metric": bool(_METRIC_RE.search(block)),
        "period": bool(_PERIOD_RE.search(block)),
        "role": any(r in block.lower() for r in _ROLE_MARKERS),
    }
    return ExperienceBlock(block, sum(signals.values()), signals)


def assess_star_readiness(user_text: str) -> StarReadiness:
    """STAR 생성을 시도해도 되는 입력인지 코드가 먼저 판정한다.

    '부족하면 지어내지 마세요'를 LLM 판단에 맡기지 않는 것이 핵심이다.
    부족의 정의(길이/행동동사/수치/기간/역할 5개 신호 중 4개)를 코드가 갖는다.
    """
    blocks = [_score_block(b) for b in split_experience_blocks(user_text)]
    eligible = [b for b in blocks if b.eligible]

    if not blocks:
        return StarReadiness(
            False, blocks,
            "입력에서 경험 단위를 하나도 식별하지 못했습니다.",
            [
                "경험 1건당 한 문단씩, 빈 줄로 구분해 작성하십시오.",
                "예) 2024.03~2024.08 / OO동아리 데이터팀 / 회원 이탈 분석 담당 / "
                "SQL 로 3년치 로그 12만 건 집계 → 이탈 원인 3가지 도출 → 재등록률 18% 개선",
            ],
        )

    if not eligible:
        missing_counts = {
            "기간": sum(1 for b in blocks if not b.signals["period"]),
            "역할": sum(1 for b in blocks if not b.signals["role"]),
            "수치 성과": sum(1 for b in blocks if not b.signals["metric"]),
            "구체적 행동": sum(1 for b in blocks if not b.signals["action_verb"]),
            "서술 분량": sum(1 for b in blocks if not b.signals["length"]),
        }
        worst = sorted(missing_counts.items(), key=lambda kv: -kv[1])[:3]
        lacking = ", ".join(f"{k}(누락 {v}/{len(blocks)}건)" for k, v in worst if v)
        return StarReadiness(
            False, blocks,
            f"경험 {len(blocks)}건 중 STAR 작성 기준(5개 신호 중 4개 이상)을 "
            f"충족하는 항목이 0건입니다. 주요 결손: {lacking}. "
            f"근거 없는 Situation·Task 를 지어내지 않기 위해 STAR 초안을 생성하지 않았습니다.",
            [
                "각 경험에 '언제(기간) / 어디서(조직) / 내 역할' 을 한 줄로 먼저 적으십시오.",
                "행동은 '무엇을 어떻게 했는지' 동사로 적으십시오. (예: 'SQL 로 로그 12만 건 집계')",
                "결과는 반드시 숫자로 적으십시오. (예: '재등록률 18% 개선', '처리 시간 4시간→30분')",
                "이 세 가지가 채워지면 STAR 4개 항목이 근거를 갖고 자동 생성됩니다.",
            ],
        )

    return StarReadiness(
        True, blocks,
        f"경험 {len(blocks)}건 중 {len(eligible)}건이 STAR 작성 기준을 충족했습니다.",
        [],
    )


def quote_supported(quote: str, source_text: str, min_len: int = 8) -> bool:
    """인용문이 원문에 실제로 존재하는지 대조 (공백·구두점 무시)."""
    q = norm_text(quote)
    if len(q) < min_len:
        return False
    return q in norm_text(source_text)


def numbers_grounded(text: str, source_text: str) -> tuple[bool, set[str]]:
    """생성 문장의 모든 수치가 원문에 존재하는지 검사.

    '성과를 수치로 각색'하는 환각은 이 검사 하나로 대부분 잡힌다.
    """
    gen = extract_numbers(text)
    src = extract_numbers(source_text)
    invented = {n for n in gen if n not in src}
    return (not invented), invented


_STAR_SLOTS = ("S", "T", "A", "R")
_SLOT_LABEL = {"S": "Situation", "T": "Task", "A": "Action", "R": "Result"}


def validate_star_entries(
    entries: list[dict],
    source_text: str,
    audit: VerificationAudit | None = None,
    overlap_threshold: float = 0.6,
) -> tuple[list[dict], list[dict]]:
    """생성된 STAR 항목을 원문 대조로 검증한다.

    반환: (검증 통과 항목, 제외된 항목 리포트)

    검사 항목
      1. 각 슬롯에 source_quote 가 있고 그것이 원문에 실제로 존재하는가
      2. 슬롯 본문의 수치가 전부 원문에 있는가 (수치 각색 차단)
      3. 슬롯끼리 같은 문장을 재활용하지 않았는가 (단순 재구조화 차단)
      4. 최소 Action + Result 두 슬롯이 근거를 갖는가
    """
    kept: list[dict] = []
    rejected: list[dict] = []

    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "(제목 없음)")
        quotes: dict[str, set[str]] = {}
        supported: list[str] = []
        unsupported: list[dict] = []

        for slot in _STAR_SLOTS:
            body = str(entry.get(slot) or "").strip()
            quote = str(entry.get(f"{slot}_source_quote") or "").strip()

            if not body:
                unsupported.append({"slot": slot, "label": _SLOT_LABEL[slot],
                                    "reason": "내용 없음"})
                entry[slot] = None
                continue

            if not quote_supported(quote, source_text):
                unsupported.append({
                    "slot": slot, "label": _SLOT_LABEL[slot],
                    "reason": "원문에서 확인되지 않는 근거 인용 → 삭제",
                    "claimed_quote": quote[:120],
                })
                entry[slot] = None
                entry[f"{slot}_source_quote"] = None
                continue

            ok_num, invented = numbers_grounded(body, source_text)
            if not ok_num:
                unsupported.append({
                    "slot": slot, "label": _SLOT_LABEL[slot],
                    "reason": f"원문에 없는 수치 생성({', '.join(sorted(invented))}) → 삭제",
                })
                entry[slot] = None
                entry[f"{slot}_source_quote"] = None
                continue

            quotes[slot] = name_tokens(quote, min_len=2)
            supported.append(slot)

        # 3. 재구조화 판정 — 서로 다른 슬롯이 같은 원문 문장을 돌려쓰는 경우
        restructuring = False
        overlaps: list[str] = []
        slots = list(quotes.keys())
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                sim = jaccard(quotes[slots[i]], quotes[slots[j]])
                if sim >= overlap_threshold:
                    restructuring = True
                    overlaps.append(f"{slots[i]}↔{slots[j]} ({sim:.0%} 중복)")

        entry.pop("_raw", None)
        entry["evidence_status"] = {
            "supported_slots": supported,
            "unsupported_slots": unsupported,
            "restructuring_only": restructuring,
            "restructuring_detail": overlaps,
        }

        if "A" not in supported or "R" not in supported:
            reason = (
                "Action·Result 중 원문 근거를 갖는 슬롯이 부족합니다 "
                f"(근거 확보 슬롯: {', '.join(supported) or '없음'}). "
                "없는 이야기를 채워 넣지 않기 위해 이 경험의 STAR 초안을 생성하지 않았습니다."
            )
            rejected.append({
                "title": title,
                "reason": reason,
                "unsupported_slots": unsupported,
                "coaching": (
                    "이 경험에 대해 ① 본인이 직접 한 행동(동사)과 ② 그 결과를 수치로 "
                    "한 줄씩 추가하면 STAR 초안이 근거를 갖고 생성됩니다."
                ),
            })
            if audit:
                audit.dropped("star", title, reason)
            continue

        if restructuring:
            entry["quality_warning"] = (
                "입력 문장을 슬롯별로 재배치한 수준입니다("
                + ", ".join(overlaps)
                + "). Situation/Task 를 별도 문장으로 보강하면 실제 STAR 구조가 됩니다."
            )
            if audit:
                audit.degraded("star", title, "슬롯 간 근거 중복 — 단순 재구조화로 표시")
        elif audit:
            audit.kept("star", title, f"근거 확보 슬롯 {'/'.join(supported)}")

        kept.append(entry)

    return kept, rejected
