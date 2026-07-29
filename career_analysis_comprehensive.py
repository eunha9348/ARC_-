"""
Career Analysis AI - COMPREHENSIVE Edition v3.0 (Anti-Hallucination Rebuild)
종합 커리어 분석 모듈

════════════════════════════════════════════════════════════════════════════
v2.0 에서 실제로 발생한 장애
════════════════════════════════════════════════════════════════════════════
  H-1  동아리·학회 추천에 접속되지 않는 URL 이 포함됨 (죽은 링크 / 지어낸 링크)
  H-2  STAR 분석이 사용자가 적은 문장의 재배치에 불과함
  H-3  존재하지 않는 자격증(특히 '실재 자격증 + 없는 등급' 조합)을 추천함

v2.0 은 이를 막기 위해 프롬프트에 9개 규칙을 넣었지만 실패했다.
실패 원인은 "규칙이 부족해서"가 아니라 **아키텍처가 규칙과 반대로 설계**되어
있었기 때문이다. 상세는 docs/field_report_hallucination_v3.html 참조.

핵심 원인 3가지
  C-1 (쿼터 강제)  "동아리 최소 3개"라는 정량 목표가 "확실하지 않으면 제외"
                   규칙과 정면 충돌했다. 쿼터가 있으면 모델은 반드시 채운다.
  C-2 (자기 검증)  생성자와 검증자가 같은 모델·같은 메모리였다. 게다가
                   tools=[GoogleSearch] 를 붙이기만 하고 '실제로 검색했는지'는
                   확인하지 않아, 검색 검증처럼 보이지만 기억 기반 자기확신이었다.
                   URL 은 단 한 번도 HTTP 요청으로 확인하지 않았다(채용공고 제외).
  C-3 (스키마 우위) 규칙 7 이 "STAR 데이터가 부족하면 생성하지 말라"고 했지만,
                   출력 스키마에는 resume_star_format 이 예시 객체와 함께 항상
                   존재했다. 빈 값을 표현할 구조적 통로가 없으면 스키마가 규칙을 이긴다.

════════════════════════════════════════════════════════════════════════════
v3.0 의 대응
════════════════════════════════════════════════════════════════════════════
  F-1 쿼터 전면 폐지        최소 개수 요구 삭제. 0개도 정상 결과로 취급하고,
                            대신 사용자가 직접 확인할 검색어를 제공한다.
  F-2 URL 무생성 원칙        모델은 URL 필드를 출력하지 않는다. URL 은 검색
                            그라운딩이 반환한 실제 소스 URI 만 후보가 되고,
                            HTTP 200 + soft-404 검사 + 본문 키워드 대조를
                            통과해야만 부착된다. (hallucination_guard.probe_url)
  F-3 그라운딩 강제          검증 호출은 grounding_metadata 를 파싱해 실제 검색
                            여부를 확인하고, 항목명이 검색 근거에 등장하는지
                            코드가 직접 대조한다. 모델의 "verified": true 는
                            그 자체로는 아무 효력이 없다.
  F-4 반증형 이중 검증       검증 프롬프트를 "존재 증명"이 아닌 "부재 증거 탐색"
                            으로 뒤집고, 온도가 다른 2회 호출이 모두 통과해야
                            인정한다(agreement gate). 추천 이유는 검증 프롬프트에
                            넣지 않아 확증편향을 차단한다.
  F-5 자격증 레지스트리      국가/공인 자격증 표준 목록과 등급 문법을 코드가
                            보유하여 '빅데이터분석기사 2급' 류 등급 환각을
                            네트워크 없이 즉시 차단한다.
  F-6 STAR 근거 결속         생성 전 코드가 입력의 STAR 적합성을 판정하고,
                            미달이면 LLM 에 요청 자체를 하지 않는다. 생성한
                            경우에도 슬롯별 source_quote 를 원문과 대조하고,
                            원문에 없는 수치를 삭제하며, 슬롯 간 인용 중복이
                            크면 '단순 재구조화'로 강등 표시한다.
  F-7 fail-closed 일관화     누락 필드의 기본값을 전부 '불합격'으로 통일.
  F-8 감사 추적              무엇이 왜 제거되었는지 verification_audit 로 출력.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import date, datetime
from html.parser import HTMLParser

import pypdf
from google import genai
from google.genai import types

from analysis_response import ErrorResponse, VectorSuccessResponse
from hallucination_guard import (
    VerificationAudit,
    assess_star_readiness,
    check_certification_name,
    extract_grounding,
    grounding_mentions,
    is_plausible_url,
    name_tokens,
    norm_name,
    pick_verified_url,
    probe_url,
    scrub_model_urls,
    validate_star_entries,
)
from star_quality import evaluate_star_entries, score_star_entry  # noqa: F401

# ──────────────────────────────────────────────
#  Config
# ──────────────────────────────────────────────
# v2.0 은 API 키를 소스에 하드코딩했고(빈 문자열), import 시점에 클라이언트를
# 생성해 키가 없으면 모듈 import 자체가 실패했다. 키는 환경변수로만 받는다.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

_ANALYSIS_MODEL = "gemini-2.5-pro"
_EMBEDDING_MODEL = "gemini-embedding-001"

# 크롤러 설정
_MAX_PAGES = 30
_MAX_PDFS = 5
_FETCH_TIMEOUT = 15
_MAX_CONTENT_MB = 1
_MIN_CRAWL_CHARS = 200

# 재시도 설정
_MAX_RETRIES = 4
_RETRY_BASE_SEC = 5

# 검증 설정
_DUAL_PASS_VERIFY = True     # 반증형 이중 검증 (F-4)
_URL_PROBE_TIMEOUT = 10
_MAX_URL_PROBES = 40         # 실행당 HTTP 프로브 상한

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """지연 초기화 — 키가 없으면 명확한 에러로 실패한다."""
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY 환경변수가 설정되지 않았습니다. "
                "export GEMINI_API_KEY='...' 후 다시 실행하십시오."
            )
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ══════════════════════════════════════════════
#  1  LLM 호출 헬퍼
# ══════════════════════════════════════════════

def _is_rate_limit(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in
               ("429", "quota", "rate_limit", "rate limit", "resource_exhausted"))


def _call_with_retry(fn, *args, **kwargs):
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if _is_rate_limit(e) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BASE_SEC * (2 ** attempt)
                print(f"  [Rate Limit] {wait}초 후 재시도 "
                      f"({attempt + 1}/{_MAX_RETRIES - 1})...", flush=True)
                time.sleep(wait)
            else:
                raise


def _response_text(resp) -> str:
    """resp.text 는 tool-call part 가 섞이면 예외를 던질 수 있어 방어적으로 추출."""
    try:
        txt = resp.text
        if txt:
            return txt.strip()
    except Exception:
        pass
    parts_text: list[str] = []
    for cand in (getattr(resp, "candidates", None) or []):
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            t = getattr(part, "text", None)
            if t:
                parts_text.append(str(t))
    return "\n".join(parts_text).strip()


def _generate(user_prompt: str, system_prompt: str = "",
              use_google_search: bool = False, temperature: float = 0.1):
    tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None

    def _do():
        return get_client().models.generate_content(
            model=_ANALYSIS_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt or None,
                temperature=temperature,
                tools=tools,
            ),
        )

    return _call_with_retry(_do)


def _call_model(system_prompt: str, user_prompt: str,
                use_google_search: bool = False, temperature: float = 0.1) -> dict:
    raw_text = ""
    try:
        resp = _generate(user_prompt, system_prompt, use_google_search, temperature)
        raw_text = _response_text(resp)
        return json.loads(clean_json_response(raw_text))
    except json.JSONDecodeError as e:
        return {"status": "error",
                "message": f"JSON parse failed: {e.msg}",
                "raw_response": raw_text[:1000]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _call_model_grounded(user_prompt: str, system_prompt: str = "",
                         temperature: float = 0.0) -> tuple[list | dict, object]:
    """검색 그라운딩 호출 — 파싱 결과와 **실제 검색 근거**를 함께 반환한다.

    v2.0 과의 결정적 차이: 호출자는 모델의 답변만이 아니라
    grounding evidence 를 받아, 그 근거로 코드가 직접 재검증한다.
    """
    try:
        resp = _generate(user_prompt, system_prompt,
                         use_google_search=True, temperature=temperature)
    except Exception as e:
        print(f"    WARNING: 그라운딩 호출 실패 ({e})", flush=True)
        from hallucination_guard import GroundingEvidence
        return [], GroundingEvidence()

    evidence = extract_grounding(resp)
    raw = _response_text(resp)
    try:
        parsed = json.loads(clean_json_response(raw))
    except Exception as e:
        print(f"    WARNING: 검증 응답 파싱 실패 ({e})", flush=True)
        parsed = []
    return parsed, evidence


# ══════════════════════════════════════════════
#  2  JSON 정제
# ══════════════════════════════════════════════

def clean_json_response(raw_text: str) -> str:
    raw_text = (raw_text or "").strip()

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if m:
        raw_text = m.group(1).strip()

    for opener, closer in (("{", "}"), ("[", "]")):
        depth, start = 0, -1
        for i, ch in enumerate(raw_text):
            if ch == opener:
                if depth == 0:
                    start = i
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0 and start != -1:
                    return raw_text[start:i + 1].strip()
    return raw_text


# ══════════════════════════════════════════════
#  3  학교 정보
# ══════════════════════════════════════════════

_SCHOOL_ALIASES = {
    "서울대": "서울대학교", "연세대": "연세대학교", "고려대": "고려대학교",
    "성균관대": "성균관대학교", "한양대": "한양대학교", "서강대": "서강대학교",
    "중앙대": "중앙대학교", "경희대": "경희대학교", "이화여대": "이화여자대학교",
    "한국외대": "한국외국어대학교", "외대": "한국외국어대학교",
    "시립대": "서울시립대학교", "건국대": "건국대학교", "동국대": "동국대학교",
    "홍익대": "홍익대학교", "숭실대": "숭실대학교", "국민대": "국민대학교",
    "세종대": "세종대학교", "광운대": "광운대학교", "명지대": "명지대학교",
    "인하대": "인하대학교", "아주대": "아주대학교", "부산대": "부산대학교",
    "경북대": "경북대학교", "전남대": "전남대학교", "충남대": "충남대학교",
    "충북대": "충북대학교", "전북대": "전북대학교", "강원대": "강원대학교",
    "제주대": "제주대학교", "울산대": "울산대학교", "한림대": "한림대학교",
    "단국대": "단국대학교", "상명대": "상명대학교", "가톨릭대": "가톨릭대학교",
    "카이스트": "KAIST", "포항공대": "POSTECH",
}


def normalize_school_name(name: str) -> str:
    if not name:
        return ""
    return _SCHOOL_ALIASES.get(name.strip(), name.strip())


def get_user_profile(raw_school: str, raw_dept: str) -> tuple[str, str]:
    print("\n[학교 / 학과 정보 입력]")
    print("─" * 45)
    school = normalize_school_name(raw_school) if raw_school else ""
    print(f"  -> 학교: {school}" if school else "  -> 학교 정보 없이 진행합니다.")
    department = raw_dept.strip() if raw_dept else ""
    print(f"  -> 학과: {department}" if department else "  -> 학과 정보 없이 진행합니다.")
    print("─" * 45)
    return school, department


# ══════════════════════════════════════════════
#  4  HTML 파서
# ══════════════════════════════════════════════

class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "meta", "link", "head"}

    def __init__(self, base_url: str = ""):
        super().__init__()
        self._skip = 0
        self._parts: list[str] = []
        self._links: list[str] = []
        self._base = base_url

    def handle_starttag(self, tag, attrs):
        tl = tag.lower()
        if tl in self.SKIP_TAGS:
            self._skip += 1
        if tl == "a":
            href = dict(attrs).get("href", "")
            if href and not href.startswith(("javascript:", "mailto:", "tel:")):
                self._links.append(urllib.parse.urljoin(self._base, href))

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0:
            s = data.strip()
            if s:
                self._parts.append(s)

    @property
    def text(self) -> str:
        return "\n".join(self._parts)

    @property
    def links(self) -> list[str]:
        return self._links


def _is_spa(html: str) -> bool:
    visible = len(re.sub(r"<[^>]+>", " ", html).strip())
    return visible < 2000 and html.lower().count("<script") >= 2


def _extract_links_from_raw_html(raw_html: str, base_url: str) -> list[str]:
    found = []
    for m in re.finditer(
        r"""(?:href|src|data-href|data-src)\s*=\s*["']([^"']+)["']""",
        raw_html, re.IGNORECASE,
    ):
        href = m.group(1).strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        found.append(urllib.parse.urljoin(base_url, href))
    return list(dict.fromkeys(found))


# ══════════════════════════════════════════════
#  5  Notion 전용 크롤러
# ══════════════════════════════════════════════

def _is_notion_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return "notion.site" in host or "notion.so" in host


def _parse_notion_blocks(blocks: dict) -> str:
    lines: list[str] = []

    def _rich_text_to_str(rt) -> str:
        if not isinstance(rt, list):
            return ""
        parts = []
        for chunk in rt:
            if isinstance(chunk, list) and chunk:
                parts.append(str(chunk[0]))
            elif isinstance(chunk, str):
                parts.append(chunk)
        return "".join(parts).strip()

    TEXT_PROPS = ["title", "caption", "description"]
    SKIP_TYPES = {"image", "video", "file", "audio", "pdf", "embed", "bookmark",
                  "divider", "table_of_contents", "breadcrumb", "unsupported"}

    for _block_id, block_wrapper in blocks.items():
        val = block_wrapper.get("value", {})
        if not isinstance(val, dict):
            continue
        if val.get("type", "") in SKIP_TYPES:
            continue
        props = val.get("properties", {})
        if not isinstance(props, dict):
            continue
        for prop_key in TEXT_PROPS:
            if prop_key in props:
                text = _rich_text_to_str(props[prop_key])
                if text:
                    lines.append(text)
                break

    return "\n".join(lines)


def _extract_from_next_data(html: str) -> str:
    m = re.search(
        r"""<script[^>]+id=["']__NEXT_DATA__["'][^>]*>\s*(.*?)\s*</script>""",
        html, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return ""
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return ""

    page_props = data.get("props", {}).get("pageProps", {})
    record_map = page_props.get("recordMap", {}) or page_props
    blocks = record_map.get("block", {})
    if not blocks:
        return ""

    text = _parse_notion_blocks(blocks)
    print(f"    __NEXT_DATA__ 파싱 성공: {len(blocks)}개 블록, {len(text)} chars", flush=True)
    return text


def _unescape_basic(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&#39;", "'").replace("&quot;", '"'))


def _extract_og_meta(html: str, url: str) -> str:
    parts, seen = [], set()
    patterns = [
        (r"<title[^>]*>(.*?)</title>", "페이지 제목"),
        (r"""<meta[^>]+property=["']og:title["'][^>]+content=["'](.*?)["']""", "OG 제목"),
        (r"""<meta[^>]+property=["']og:description["'][^>]+content=["'](.*?)["']""", "OG 설명"),
        (r"""<meta[^>]+name=["']description["'][^>]+content=["'](.*?)["']""", "메타 설명"),
    ]
    for pattern, label in patterns:
        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if m:
            val = _unescape_basic(m.group(1).strip())
            if val and val not in seen:
                parts.append(f"{label}: {val}")
                seen.add(val)

    slug = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    slug_clean = re.sub(r"[-_]", " ", re.sub(r"-[0-9a-f]{20,}$", "", slug)).strip()
    if slug_clean:
        parts.append(f"URL 슬러그(페이지명 힌트): {slug_clean}")
    return "\n".join(parts)


def crawl_notion_page(url: str) -> str:
    print(f"  [Notion 크롤러] 시작: {url}", flush=True)
    collected_parts: list[str] = []

    raw_bytes = _fetch_bytes(url)
    html = ""
    if raw_bytes:
        try:
            html = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            html = raw_bytes.decode("euc-kr", errors="replace")

    if html:
        next_data_text = _extract_from_next_data(html)
        if next_data_text.strip():
            collected_parts.append(f"[Notion 블록 콘텐츠: {url}]\n{next_data_text}")

        og_text = _extract_og_meta(html, url)
        if og_text.strip():
            collected_parts.append(f"[Notion 메타정보: {url}]\n{og_text}")

        parser = _TextExtractor(base_url=url)
        parser.feed(html)
        plain_text = parser.text.strip()
        if plain_text and len(plain_text) > 100:
            collected_parts.append(f"[Notion HTML 텍스트: {url}]\n{plain_text}")

    combined = "\n\n".join(collected_parts).strip()
    print(f"    추출 결과: {len(combined)} chars", flush=True)

    # v2.0 은 크롤링이 빈약하면 "URL 슬러그로 최대한 추론하십시오"라고 지시했다.
    # 이는 근거 없는 경력 서술을 만들어내라는 요청과 같아 환각의 직접 원인이었다.
    # v3.0 은 추론을 금지하고, 부족하다는 사실을 그대로 하류로 전달한다.
    if len(combined) < _MIN_CRAWL_CHARS:
        print("    WARNING: 크롤링 결과 빈약 → 데이터 부족 사실을 그대로 전달", flush=True)
        notice = (
            "[크롤링 제한 안내]\n"
            f"Notion 페이지 URL: {url}\n"
            "JavaScript 렌더링 제약으로 본문을 충분히 수집하지 못했습니다.\n"
            "수집되지 않은 내용은 **추론하지 마십시오**. URL 슬러그나 페이지 제목으로부터 "
            "경력·활동 내용을 유추하는 것은 금지됩니다. 확인되지 않은 항목은 빈 배열로 "
            "반환하고, 데이터 부족 사실을 missing_info_warning 에 명시하십시오.\n"
        )
        combined = notice + "\n" + combined

    print(f"  [Notion 크롤러 완료] 총 {len(combined)} chars", flush=True)
    return combined


# ══════════════════════════════════════════════
#  6  딥 크롤러 (일반 웹사이트)
# ══════════════════════════════════════════════

def _fetch_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            return resp.read(int(_MAX_CONTENT_MB * 1024 * 1024))
    except Exception as e:
        print(f"  WARNING fetch failed [{url}]: {e}", flush=True)
        return None


def _parse_pdf_bytes(data: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        print(f"  OK PDF parsed ({len(reader.pages)} pages, {len(text)} chars)", flush=True)
        return text
    except Exception as e:
        print(f"  WARNING PDF parse error: {e}", flush=True)
        return ""


def _parse_html_bytes(data: bytes, url: str) -> tuple[str, list[str], str]:
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError:
        html = data.decode("euc-kr", errors="replace")
    parser = _TextExtractor(base_url=url)
    parser.feed(html)
    return parser.text, parser.links, html


def _same_origin(a: str, b: str) -> bool:
    return urllib.parse.urlparse(a).netloc == urllib.parse.urlparse(b).netloc


def _is_pdf_url(url: str, data: bytes | None = None) -> bool:
    if url.lower().split("?")[0].endswith(".pdf"):
        return True
    return bool(data and data[:4] == b"%PDF")


def deep_crawl_site(start_url: str) -> str:
    print(f"  [딥 크롤러] 시작: {start_url}", flush=True)
    collected: list[str] = []
    visited: set[str] = set()
    pdf_count = 0

    raw = _fetch_bytes(start_url)
    if raw is None:
        return ""
    if _is_pdf_url(start_url, raw):
        text = _parse_pdf_bytes(raw)
        return f"[PDF: {start_url}]\n{text}" if text else ""

    main_text, main_links, main_html = _parse_html_bytes(raw, start_url)
    visited.add(start_url)
    if main_text.strip():
        collected.append(f"[Main: {start_url}]\n{main_text}")
        print(f"    Main page: {len(main_text)} chars", flush=True)

    if _is_spa(main_html):
        print("    SPA detected — using raw HTML link extraction", flush=True)

    raw_links = _extract_links_from_raw_html(main_html, start_url)
    queue: deque[str] = deque()
    seen: set[str] = set()

    def _enqueue(links: list[str], base: str) -> None:
        for lnk in links:
            clean = lnk.split("#")[0].rstrip("/")
            if not clean or clean in seen or clean in visited:
                continue
            if clean.startswith(("mailto:", "tel:", "javascript:")):
                continue
            seen.add(clean)
            if _is_pdf_url(clean):
                queue.appendleft(clean)
            elif _same_origin(base, clean):
                queue.append(clean)

    _enqueue(list(dict.fromkeys(main_links + raw_links)), start_url)
    print(f"    큐 초기 크기: {len(queue)}개 링크", flush=True)

    page_count = 0
    while queue and (page_count < _MAX_PAGES or pdf_count < _MAX_PDFS):
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        sub_raw = _fetch_bytes(url)
        if sub_raw is None:
            continue

        if _is_pdf_url(url, sub_raw):
            if pdf_count >= _MAX_PDFS:
                continue
            text = _parse_pdf_bytes(sub_raw)
            if text.strip():
                collected.append(f"[PDF: {url}]\n{text}")
                pdf_count += 1
                print(f"    PDF collected ({pdf_count}/{_MAX_PDFS}): {url}", flush=True)
            continue

        if page_count >= _MAX_PAGES:
            continue
        sub_text, sub_links, sub_html = _parse_html_bytes(sub_raw, url)
        page_count += 1
        if sub_text.strip():
            collected.append(f"[Page: {url}]\n{sub_text}")
            print(f"    Page {page_count}: {url} ({len(sub_text)} chars)", flush=True)

        _enqueue(list(dict.fromkeys(sub_links +
                                    _extract_links_from_raw_html(sub_html, url))), start_url)

    result = "\n\n".join(collected)
    print(f"  [딥 크롤러 완료] {len(collected)}개 소스, {len(result)} chars", flush=True)
    return result


# ══════════════════════════════════════════════
#  7  파일 리더 / 입력 수집
# ══════════════════════════════════════════════

def read_file(path: str) -> str:
    if not os.path.isfile(path):
        print(f"  ERROR file not found: {path}", flush=True)
        return ""
    if path.lower().endswith(".pdf"):
        with open(path, "rb") as f:
            return _parse_pdf_bytes(f.read())
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        print(f"  OK file read ({len(content)} chars)", flush=True)
        return content
    except Exception as e:
        print(f"  ERROR reading file: {e}", flush=True)
        return ""


def _looks_like_url(s: str) -> bool:
    return bool(re.match(r"^https?://\S+$", s) or re.match(r"^www\.\S+$", s))


def _looks_like_filepath(s: str) -> bool:
    return "\n" not in s and os.path.isfile(s.strip())


def get_user_input(lines: list[str]) -> str:
    raw = "\n".join(lines).strip()
    if not raw:
        return ""

    first_line = lines[0].strip() if lines else ""

    if len(lines) == 1 and _looks_like_url(first_line):
        url = first_line if first_line.startswith("http") else "https://" + first_line
        if _is_notion_url(url):
            print("\n  [자동 감지] Notion URL → Notion 전용 크롤러 시작", flush=True)
            content = crawl_notion_page(url)
        else:
            print("\n  [자동 감지] URL → 딥 크롤링 시작", flush=True)
            content = deep_crawl_site(url)

        if content.strip():
            return f"[SOURCE_URL: {url}]\n\n{content}"

        # v2.0 은 크롤링 실패 시 "URL 경로명과 도메인으로 내용을 추론하십시오"라고
        # 지시했다. 이것은 환각 생성 지시였다. v3.0 은 실패를 실패로 보고한다.
        print("  WARNING: 크롤링 실패 → 데이터 없음으로 처리", flush=True)
        return (
            f"[SOURCE_URL: {url}]\n"
            f"[크롤링 실패 — 본문을 전혀 수집하지 못했습니다]\n"
            f"URL 경로명이나 도메인으로 경력·활동 내용을 추론하는 것은 금지됩니다.\n"
            f"분석 가능한 사용자 데이터가 없으므로 모든 분석 항목을 빈 값으로 반환하고 "
            f"missing_info_warning 에 데이터 부재 사실을 기재하십시오.\n"
        )

    if len(lines) == 1 and _looks_like_filepath(first_line):
        print(f"\n  [자동 감지] 파일 경로 → 읽는 중: {first_line}", flush=True)
        content = read_file(first_line.strip())
        return content if content.strip() else raw

    print(f"\n  [자동 감지] 텍스트 직접 입력 ({len(raw)}자)", flush=True)
    return raw


# ══════════════════════════════════════════════
#  8  Embedding
# ══════════════════════════════════════════════

def get_embedding(text: str):
    if not text:
        return None
    truncated = text[:10000]
    for kwargs in [
        {"content": truncated,
         "config": types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")},
        {"content": truncated},
        {"contents": truncated,
         "config": types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")},
    ]:
        try:
            result = get_client().models.embed_content(model=_EMBEDDING_MODEL, **kwargs)
            if getattr(result, "embeddings", None):
                return result.embeddings[0].values
            if getattr(result, "embedding", None):
                return result.embedding.values
        except Exception:
            continue
    print("  WARNING embedding all fallbacks failed", flush=True)
    return None


# ══════════════════════════════════════════════
#  9  Hallucination 방지 규칙 (v3.0)
# ══════════════════════════════════════════════
#
#  v2.0 규칙과의 차이
#   - 규칙 3(동아리 최소 3개) 삭제 → 쿼터가 환각의 1차 원인이었다.
#   - URL 관련 규칙을 "확실한 것만 허용"에서 "출력 자체 금지"로 강화.
#   - STAR 규칙에 대응하는 출력 필드를 스키마에 실제로 만들었다.

_STRICT_HALLUCINATION_RULES = """
=== STRICT MODE v3: 검증 불가 = 출력 금지 ===

[규칙 1] URL 출력 전면 금지
- 어떤 항목에도 URL·링크·도메인을 출력하지 마십시오. url 필드 자체가 스키마에 없습니다.
- 링크는 시스템이 검색 근거와 HTTP 응답을 확인한 뒤에만 부착합니다.
- URL 을 문장(description, reason 등) 안에 적는 것도 금지입니다.

[규칙 2] 후보 제출 원칙 (추천이 아니라 '검증 대상 후보')
- 이 단계에서 당신이 내는 자격증·동아리·공모전은 최종 추천이 아니라 **검증 후보**입니다.
- 후보에는 반드시 `verification_query`(그 항목의 실재를 확인할 검색어)를 붙이십시오.
- 실재가 의심스러우면 후보에서 빼십시오. 시스템이 어차피 걸러내며, 걸러진 항목은
  '모델이 지어냈다'는 기록으로 남습니다.

[규칙 3] 개수 쿼터 없음
- 최소 개수 요구는 존재하지 않습니다. 0개도 완전히 정상적인 결과입니다.
- 개수를 채우기 위해 확신 없는 항목을 넣는 것은 가장 나쁜 실패입니다.
- 확실한 항목이 1개뿐이면 1개만 내십시오.

[규칙 4] 자격증 정확성
- 자격증명은 공식 명칭 그대로 쓰십시오.
- **등급을 임의로 붙이지 마십시오.** 등급 체계가 없는 자격증에 '1급/2급'을 붙이는 것은
  가장 자주 발생하는 환각 유형이며 시스템이 자동 검출합니다.
- 확실하지 않으면 certifications: [] 를 반환하십시오.

[규칙 5] 연도·마감일 날조 금지
- 모르면 null. 추측 금지. "2025년 하반기" 같은 추정 표현도 금지.

[규칙 6] STAR 는 근거 인용이 필수
- STAR 각 항목(S/T/A/R)에는 그 내용의 출처가 되는 **사용자 입력 원문 문장을
  그대로(변형 없이) `S_source_quote` 등에 복사**해 넣어야 합니다.
- 원문에 없는 내용은 슬롯을 null 로 두십시오. 창작 금지.
- **원문에 없는 수치를 만들지 마십시오.** 시스템이 원문과 대조해 자동 삭제합니다.
- S/T/A/R 네 슬롯이 같은 한 문장을 바꿔 쓴 것이면 '단순 재구조화'로 판정되어
  품질 경고가 붙습니다. 각 슬롯은 서로 다른 원문 근거를 가져야 합니다.

[규칙 7] 출력은 순수 JSON만
- 마크다운 코드블록, 설명 텍스트, 주석 금지.

[규칙 8] strength_diagnosis 환각 금지
- 입력 데이터에 없는 강점 생성 금지. 강점이 없으면 strengths: [] 후
  no_strength_diagnosis 에 이유·개선 방향만 기재.
- 모든 경험에 의례적으로 강점을 부여하지 마십시오.

[규칙 9] critical_diagnosis 약점 보존 의무
- strength_diagnosis 를 먼저 출력했다는 이유로 약점을 축소·은폐하지 마십시오.
- 강점의 존재가 약점의 severity 를 낮출 근거가 되지 않습니다.
- 약점을 긍정적으로 포장하거나 "~이지만 괜찮다" 식 완화 표현 금지.
"""


# ══════════════════════════════════════════════
#  10  시스템 프롬프트 빌더 (v3.0)
# ══════════════════════════════════════════════

def _star_section(star_ready: bool, readiness_reason: str) -> str:
    """STAR 지시를 준비도에 따라 **구조적으로** 분기한다.

    v2.0 은 '부족하면 만들지 마세요'라고 말하면서도 스키마에는 STAR 예시 객체를
    항상 넣었다. v3.0 은 준비도 미달이면 스키마에서 STAR 필드를 아예 제거하여
    모델이 채울 자리 자체를 없앤다.
    """
    if not star_ready:
        return (
            "=== STAR 분석: 이번 요청에서는 생성하지 않습니다 ===\n"
            f"시스템 사전 판정 결과: {readiness_reason}\n"
            "resume_star_format 필드를 출력하지 마십시오. 출력 시 무시됩니다.\n"
            "대신 사용자가 무엇을 더 적어야 STAR 가 가능해지는지에 대한 조언은 "
            "critical_diagnosis 의 content_quality_issues 에 담으십시오.\n\n"
        )
    return (
        "=== STAR 분석 작성 지침 ===\n"
        "당신의 STAR 는 두 단계 검사를 통과해야 합니다: (1) 근거 결속, (2) 작성 품질.\n"
        "둘 다 시스템이 자동 채점하며, 결과는 사용자에게 등급으로 노출됩니다.\n\n"
        "── [1단계] 근거 결속 (위반 시 항목 폐기) ──\n"
        "- 각 슬롯(S/T/A/R)마다 `<슬롯>_source_quote` 에 **사용자 입력 원문 문장을 "
        "그대로 복사**해 넣으십시오. 요약·의역·재작성 금지 — 글자 그대로여야 합니다.\n"
        "- 원문 근거가 없는 슬롯은 본문과 인용 모두 null 로 두십시오.\n"
        "- 원문에 없는 숫자(비율·인원·기간·금액)를 쓰지 마십시오.\n"
        "- 네 슬롯이 같은 원문 문장을 나눠 쓴 것이면 의미가 없습니다. "
        "**서로 다른 원문 근거**를 가져야 합니다.\n"
        "- 근거를 갖춘 경험만 배열에 넣으십시오. 하나도 없으면 빈 배열.\n\n"
        "── [2단계] 작성 품질 루브릭 (10개 항목 자동 채점) ──\n"
        "중요: 품질을 높이려고 **없는 사실을 덧붙이지 마십시오.** 품질은 사실을 늘려서가\n"
        "아니라, 있는 사실을 어떻게 배치·표현하는가로 만듭니다. 원문에 없는 요소는\n"
        "채우지 말고 비워 두십시오 — 시스템이 '무엇이 비었는지'를 사용자에게 안내합니다.\n\n"
        "  [분량 배분] Action 이 전체의 40~50% 를 차지해야 합니다.\n"
        "    Situation+Task 는 합쳐서 30% 이하로 압축하십시오.\n"
        "    배경을 길게 쓰고 행동을 짧게 쓰는 것이 가장 흔한 실패입니다.\n"
        "  [개인 기여] Action 은 1인칭으로 쓰십시오 — '우리가'가 아니라 '제가'.\n"
        "    팀의 성과는 평가되지 않습니다. 공동 작업이었다면 역할을 갈라 쓰십시오.\n"
        "    예: '팀은 3개 축으로 나눴고, 저는 데이터 수집과 전처리를 맡았습니다.'\n"
        "    단, 원문에 본인 역할이 없으면 만들어내지 말고 Action 을 null 로 두십시오.\n"
        "  [방법 구체성] Action 에 '무엇을' 뿐 아니라 '어떻게'가 들어가야 합니다 —\n"
        "    사용한 도구, 접근 방식, 판단 기준 중 하나. 원문에 있는 것만.\n"
        "  [성취 동사] '참여했습니다·도왔습니다·경험했습니다' 같은 약한 서술 대신\n"
        "    '설계했습니다·개선했습니다·도출했습니다' 같은 성취 동사를 쓰십시오.\n"
        "    이는 사실 변경이 아니라 같은 사실의 정확한 표현입니다.\n"
        "  [결과 정량화] Result 에는 원문에 있는 수치를 반드시 끌어올리십시오.\n"
        "    원문에 수치가 없으면 지어내지 말고 Result 를 사실 그대로 두십시오.\n"
        "  [결과 파급] 수치 뒤에 그 결과가 만든 변화가 원문에 있다면 함께 쓰십시오.\n"
        "  [모호 표현] '성공적으로·크게·많이·효과적으로' 는 수치 없이 쓰지 마십시오.\n"
        "  [슬롯 분리] Situation(상황)과 Task(내가 해내야 했던 것)는 다른 내용입니다.\n"
        "  [맥락 규모] 기간·인원·규모 중 원문에 있는 것을 S/T/A 어딘가에 넣으십시오.\n\n"
        "── [요약 계층] 각 항목에 아래 세 필드를 추가하십시오 ──\n"
        "  headline: 이 경험을 한 줄 성취문으로 압축. '강한 동사 + 맥락 + 결과' 공식.\n"
        "    예: 'Python 크롤러로 리뷰 8,000건을 수집·분석해 이탈 원인 3가지를 규명하고\n"
        "         재등록률을 18% 개선' — 이력서에 그대로 넣을 수 있는 한 줄.\n"
        "    반드시 S/T/A/R 에 이미 담긴 사실만으로 구성하십시오. 새 수치 금지.\n"
        "  competency_evidence: 이 경험이 **증명하는** 역량 1~2개와, 그렇게 판단한 이유.\n"
        "    (사실이 아니라 해석이므로 창작이 아닙니다. 단 근거는 S/T/A/R 안에 있어야 합니다.)\n"
        "  L / L_source_quote: 원문에 배움·회고가 **명시되어 있을 때만** 작성.\n"
        "    표준 STAR 에 회고 한 겹을 더한 형태입니다. 원문에 없으면 둘 다 null —\n"
        "    '무엇을 느꼈을 것이다'라는 추측은 절대 금지이며 시스템이 삭제합니다.\n\n"
    )


def build_system_prompt_comprehensive(
    ref_date: date, school: str, department: str = "",
    star_ready: bool = True, readiness_reason: str = "",
) -> str:
    rd = ref_date.strftime("%Y-%m-%d")
    school_str = school or "정보 없음"
    dept_str = department or "정보 없음"

    if school:
        club_rule = (
            f"- 동아리·학회 후보는 '{school}'에 실재하는 것만 제출하십시오.\n"
            f"- 다른 학교 동아리·학회 제출 금지. 연합동아리는 '{school}' 지부가 확인된 것만.\n"
            f"- **최소 개수 요구는 없습니다.** 확실한 것이 없으면 빈 배열을 내십시오.\n"
        )
    else:
        club_rule = (
            "- 학교 정보 없음: 교내 동아리·학회 제출 금지. 전국 단위 연합·외부만.\n"
            "- **최소 개수 요구는 없습니다.** 확실한 것이 없으면 빈 배열을 내십시오.\n"
        )

    dept_rule = (
        f"- 자격증·공모전·동아리 후보는 '{dept_str}' 전공·커리어 경로를 우선 반영\n"
        if department else ""
    )

    star_schema = (
        '  "resume_star_format": [\n'
        "    {\n"
        '      "title": "경험명",\n'
        '      "headline": "한 줄 성취문 (강한 동사 + 맥락 + 결과, 새 수치 금지)",\n'
        '      "S": "상황 — 배경·규모 (원문 근거 없으면 null)",\n'
        '      "S_source_quote": "위 S 의 근거가 되는 사용자 입력 원문 문장 그대로",\n'
        '      "T": "과제 — 내가 해내야 했던 것 (S 와 다른 내용, 없으면 null)",\n'
        '      "T_source_quote": "원문 문장 그대로",\n'
        '      "A": "행동 — 1인칭, 방법 포함, 전체의 40~50% (없으면 null)",\n'
        '      "A_source_quote": "원문 문장 그대로",\n'
        '      "R": "결과 — 원문의 수치를 끌어올리고, 파급이 있으면 함께 (없으면 null)",\n'
        '      "R_source_quote": "원문 문장 그대로",\n'
        '      "L": "배움·회고 — 원문에 명시된 경우만, 없으면 null",\n'
        '      "L_source_quote": "원문 문장 그대로 (L 이 null 이면 null)",\n'
        '      "competency_evidence": [\n'
        '        {"competency":"이 경험이 증명하는 역량",'
        '"why":"S/T/A/R 안의 어떤 사실이 그것을 증명하는지"}\n'
        "      ]\n"
        "    }\n"
        "  ],\n"
    ) if star_ready else ""

    return (
        "당신은 대한민국 최고의 커리어 컨설턴트이자 데이터 분석가입니다.\n"
        "당신의 산출물은 전부 자동 검증 파이프라인을 통과합니다. 검증에 실패한 항목은\n"
        "제거되고 '모델이 근거 없이 생성함'으로 기록됩니다. 확신 없는 항목을 넣는 것은\n"
        "이득이 없습니다.\n"
        f"코드 실행(분석) 기준일: {rd} — 이 날짜를 '오늘'로 간주하십시오.\n"
        f"\n=== 사용자 프로필 ===\n학교: {school_str}\n학과: {dept_str}\n"
        f"{club_rule}{dept_rule}"
        f"{_STRICT_HALLUCINATION_RULES}\n"
        "=== 분석 항목 ===\n"
        "A. 역량 클러스터링\n"
        "B. 보유 항목 간 시너지 조합 (2~5개)\n"
        "C. 검증 후보 제출: 자격증 / 동아리·학회 / 공모전\n"
        "D. STAR 이력서 초안 (아래 지침 참조)\n"
        "E. 단기·중기·장기 액션 플랜\n"
        "F. 강점 진단 (strength_diagnosis)\n"
        "G. 냉정한 보완점 진단 (critical_diagnosis)\n"
        "※ 채용공고는 이 단계에서 생성하지 않습니다. 별도의 검색 그라운딩 단계가 담당합니다.\n\n"
        + _star_section(star_ready, readiness_reason) +
        # ── 강점 진단(F) ─────────────────────────────────────────
        "=== 강점 진단(F) 작성 지침 ===\n"
        "목적: 입력 데이터에서 실제로 확인되는 진짜 강점만을 객관적으로 도출한다.\n"
        "절대 금지:\n"
        "  - 위로·칭찬 목적의 과장, 없는 내용으로 강점 창작\n"
        "  - 모든 경험에 의례적으로 강점을 부여하는 행위\n"
        "  - strengths 배열을 채우기 위해 근거 없는 항목을 생성하는 행위\n"
        "판단 기준 (해당하는 항목만 포함):\n"
        "  [활동_수량] 직군 평균 대비 활동 총 개수가 풍부한가?\n"
        "  [활동_깊이] 각 항목의 서술이 구체적이고 수치·성과가 명확한가?\n"
        "  [직무_연관성] 지원 직군과 연관된 핵심 활동이 있는가?\n"
        "  [스킬_보유] 해당 직군에서 요구하는 기술·자격을 보유하고 있는가?\n"
        "  [기간_연속성] 경력이 일관되고 성장 흐름이 있는가?\n"
        "  [서류_품질] 입력된 내용이 이력서로서 설득력 있게 작성되어 있는가?\n"
        "  [경쟁력_우위] 동일 직군·학교 수준 경쟁자 대비 차별화 포인트가 있는가?\n"
        "level 기준: outstanding(서류 합격 가능성을 크게 높임) / strong(뚜렷한 실질 강점) /\n"
        "            notable(긍정 인상이나 결정적이지는 않음)\n"
        "evidence 에는 **입력 원문 문장을 그대로 인용**하십시오. 요약 인용 금지.\n"
        "[강점이 없거나 식별이 어려운 경우] strengths: [] + no_strength_diagnosis 에\n"
        "  has_issue=true, reason, improvement_direction 을 솔직하게 기재.\n\n"
        # ── 보완점 진단(G) ───────────────────────────────────────
        "=== 냉정한 보완점 진단(G) 작성 지침 ===\n"
        "목적: 사용자가 듣기 불편하더라도 반드시 알아야 할 진짜 약점을 직시하게 하는 것.\n"
        "절대 금지:\n"
        "  - 칭찬·위로·긍정적 포장 — G 섹션에는 단 한 줄의 좋은 말도 하지 말 것\n"
        "  - strength_diagnosis 를 먼저 작성했다는 이유로 약점을 축소·생략하는 행위\n"
        "  - 입력 데이터에 없는 약점을 창작하는 행위\n"
        "  - '~이지만 괜찮습니다', '~에도 불구하고' 등의 완화 표현\n"
        "판단 기준: [활동_수량] [활동_깊이] [직무_연관성] [스킬_공백] [기간_연속성]\n"
        "           [서류_품질] [경쟁력_격차] — 해당하는 항목만 포함\n"
        "severity 기준: critical(이 상태로 지원하면 서류 탈락 가능성 높음) /\n"
        "               major(합격 가능성을 뚜렷이 낮춤) / minor(치명적이지는 않은 부족함)\n"
        "[앵커링 저항 원칙] 앞서 작성한 강점은 이 섹션 판단에 영향을 주지 않는다.\n"
        "  강점이 많다고 느껴질수록 약점을 더 의식적으로 냉정하게 기재할 것.\n"
        "minor 수준이라도 발견되면 반드시 포함 — 생략은 사용자에게 불이익이다.\n\n"
        "[출력] 순수 JSON만 (코드블록·설명 금지)\n\n"
        "{\n"
        '  "status": "success",\n'
        f'  "user_school": "{school_str}",\n'
        f'  "user_department": "{dept_str}",\n'
        '  "brief_summary": "핵심 한 줄 요약",\n'
        '  "detailed_summary": "심층 요약",\n'
        '  "keyword_clustering": {\n'
        '    "personality_tendency": ["성향"],\n'
        '    "core_competency": ["역량"],\n'
        '    "job_industry": ["직군"]\n'
        "  },\n"
        '  "target_job_keywords": ["채용 검색에 쓸 직무 키워드 2~4개"],\n'
        '  "experience_insights": {"motivation": "동기", "learning_points": "배움"},\n'
        '  "synergy_combinations": [\n'
        '    {"combination_title":"조합명","items":["항목1","항목2"],'
        '"synergy_reason":"이유","expected_effect":"효과","applicable_roles":["직무"]}\n'
        "  ],\n"
        '  "additional_recommendations": {\n'
        '    "certifications": [\n'
        '      {"name":"자격증 공식 명칭(등급 임의 부착 금지)","reason":"연계 이유",'
        '"expected_effect":"기대 효과","estimated_duration":"취득 소요 기간",'
        '"verification_query":"실재 확인용 검색어"}\n'
        "    ],\n"
        '    "clubs_and_societies": [\n'
        "      {\n"
        '        "name": "동아리/학회명",\n'
        '        "type": "교내동아리/교내학회/연합동아리/연합학회/외부학회",\n'
        f'        "school_affiliation": "{school_str}",\n'
        '        "description": "실제 알고 있는 활동 내용 (불확실하면 빈 문자열)",\n'
        '        "reason": "추천 이유",\n'
        '        "expected_effect": "기대 효과",\n'
        '        "verification_query": "실재 확인용 검색어"\n'
        "      }\n"
        "    ],\n"
        '    "projects_and_contests": [\n'
        "      {\n"
        '        "name": "공모전명 (주관기관이 확인된 것만)",\n'
        '        "organizer": "주관기관명",\n'
        '        "reason": "추천 이유",\n'
        '        "expected_effect": "기대 효과",\n'
        '        "is_regular": true,\n'
        '        "verification_query": "실재 확인용 검색어"\n'
        "      }\n"
        "    ]\n"
        "  },\n"
        + star_schema +
        '  "action_plan": {"단기":"3개월 이내","중기":"6개월~1년","장기":"1년 이상"},\n'
        '  "strength_diagnosis": {\n'
        '    "one_line_verdict": "현재 이력 강점의 전반적 상태를 한 문장으로",\n'
        '    "strengths": [\n'
        "      {\n"
        '        "id": 1,\n'
        '        "category": "활동_수량|활동_깊이|직무_연관성|스킬_보유|기간_연속성|서류_품질|경쟁력_우위",\n'
        '        "level": "outstanding|strong|notable",\n'
        '        "title": "강점 제목 (10자 이내)",\n'
        '        "diagnosis": "왜 강점인지 냉정하고 구체적인 근거",\n'
        '        "evidence": "입력 원문 문장 그대로 인용",\n'
        '        "impact": "취업·커리어에 미치는 실질적 긍정 영향",\n'
        '        "leverage_action": "지금 당장 해야 할 한 가지 행동 (동사로 시작)"\n'
        "      }\n"
        "    ],\n"
        '    "no_strength_diagnosis": {\n'
        '      "has_issue": false,\n'
        '      "reason": "강점 없음·식별 불가 이유 (강점이 있으면 빈 문자열)",\n'
        '      "improvement_direction": "강점을 만들기 위한 개선 방향 (강점이 있으면 빈 문자열)"\n'
        "    },\n"
        '    "standout_experience_types": ["돋보이는 경험 유형 (없으면 빈 배열)"],\n'
        '    "content_quality_highlights": [\n'
        '      {"item":"잘 작성된 항목명","highlight":"무엇이 강한가",'
        '"why_effective":"채용담당자에게 설득력 있는 이유"}\n'
        "    ],\n"
        '    "competitor_advantage": "경쟁자 대비 결정적 차별점 '
        "(없으면 '현재 데이터 기준 명확한 차별점 식별 불가')\"\n"
        "  },\n"
        '  "critical_diagnosis": {\n'
        '    "one_line_verdict": "현재 이력 전반의 상태를 냉정하게 한 문장으로",\n'
        '    "weaknesses": [\n'
        "      {\n"
        '        "id": 1,\n'
        '        "category": "활동_수량|활동_깊이|직무_연관성|스킬_공백|기간_연속성|서류_품질|경쟁력_격차",\n'
        '        "severity": "critical|major|minor",\n'
        '        "title": "약점 제목 (10자 이내)",\n'
        '        "diagnosis": "왜 약점인지 냉정하고 구체적인 근거",\n'
        '        "evidence": "입력에서 이 약점을 판단한 구체적 근거 (인용 또는 \'없음\')",\n'
        '        "impact": "취업/커리어에 미치는 실질적 영향",\n'
        '        "priority_action": "지금 당장 해야 할 한 가지 행동 (동사로 시작)"\n'
        "      }\n"
        "    ],\n"
        '    "missing_experience_types": ["완전히 빠진 경험 유형"],\n'
        '    "content_quality_issues": [\n'
        '      {"item":"문제가 있는 항목명","issue":"무엇이 부실한가",'
        '"improvement_hint":"이렇게 바꾸면 설득력이 생긴다 — 구체적 표현 예시"}\n'
        "    ],\n"
        '    "competitor_gap": "경쟁자 대비 갖지 못한 결정적 차이점"\n'
        "  },\n"
        '  "missing_info_warning": null\n'
        "}"
    )


# ══════════════════════════════════════════════
#  11  반증형 검증 프롬프트 (F-4)
# ══════════════════════════════════════════════
#
#  v2.0 의 검증 프롬프트는 "이것이 존재하는지 확인하라"(존재 증명 요청)였고,
#  추천 이유까지 함께 넘겨 확증편향을 키웠다.
#  v3.0 은 "존재하지 않는다는 증거를 찾아라"(반증 요청)로 뒤집고,
#  항목명 외 맥락은 일절 넘기지 않는다.

_FALSIFY_PREFIX = (
    "당신은 팩트체커입니다. 당신의 임무는 아래 항목들이 **실재하지 않는다는 증거를 찾는 것**입니다.\n"
    "기억에 의존하지 말고 반드시 Google Search 를 사용해 실제로 검색하십시오.\n"
    "검색 결과에서 그 항목을 직접 확인하지 못했다면 exists=false 입니다.\n"
    "'있을 법하다', '아마 존재할 것이다'는 exists=false 로 처리하십시오.\n"
    "확인의 기준은 '검색 결과에 그 이름이 실제로 나왔는가' 하나뿐입니다.\n\n"
)


def build_prompt_falsify_clubs(school: str, clubs: list) -> str:
    listing = "\n".join(f"  {i+1}. {c.get('name','?')} (유형: {c.get('type','?')})"
                        for i, c in enumerate(clubs))
    scope = f"'{school}' 소속" if school else "전국 단위"
    return (
        _FALSIFY_PREFIX +
        f"[검증 대상: {scope} 동아리·학회]\n{listing}\n\n"
        "각 항목에 대해 검색 후 판정하십시오.\n"
        "- exists: 검색 결과에서 이 동아리/학회의 실재를 직접 확인했는가\n"
        "- school_match: 확인된 소속 학교가 대상 학교와 일치하는가 (외부학회는 true)\n"
        "- actual_school: 검색으로 확인된 실제 소속 학교 (모르면 \"\")\n"
        "- source_title: 근거가 된 검색 결과의 제목\n"
        "- description: 검색으로 확인한 실제 활동 내용 (미확인이면 \"\")\n\n"
        "순수 JSON 배열만 출력:\n"
        '[{"name":"동아리명","exists":false,"school_match":false,'
        '"actual_school":"","source_title":"","description":""}]'
    )


def build_prompt_falsify_contests(contests: list, ref_date: date) -> str:
    rd = ref_date.strftime("%Y-%m-%d")
    listing = "\n".join(f"  {i+1}. [{c.get('organizer','?')}] {c.get('name','?')}"
                        for i, c in enumerate(contests))
    return (
        _FALSIFY_PREFIX +
        f"오늘 날짜: {rd}\n\n[검증 대상 공모전]\n{listing}\n\n"
        "각 항목에 대해 검색 후 판정하십시오.\n"
        "- exists: 검색 결과에서 이 공모전의 실재를 직접 확인했는가\n"
        "- organizer_confirmed: 명시된 주관기관이 실제 주관기관과 일치하는가\n"
        f"- upcoming: {rd} 기준 접수 중이거나 이후 개최 예정임을 확인했는가 "
        "(과거 회차만 확인되면 false)\n"
        f"- deadline: 확인된 마감일 (YYYY-MM-DD). 확인 못 하면 null\n"
        "- source_title: 근거가 된 검색 결과의 제목\n\n"
        "순수 JSON 배열만 출력:\n"
        '[{"name":"공모전명","exists":false,"organizer_confirmed":false,'
        '"upcoming":false,"deadline":null,"source_title":""}]'
    )


def build_prompt_falsify_certifications(certs: list) -> str:
    listing = "\n".join(f"  {i+1}. {c.get('name','?')}" for i, c in enumerate(certs))
    return (
        _FALSIFY_PREFIX +
        f"[검증 대상 자격증]\n{listing}\n\n"
        "각 항목에 대해 검색 후 판정하십시오.\n"
        "- exists: 현재 실제로 시행 중인 자격증임을 검색으로 확인했는가\n"
        "- exact_name: 검색으로 확인된 **공식 명칭**. 대상 이름이 틀렸으면 올바른 이름을 적으십시오.\n"
        "- name_matches: 대상 이름이 공식 명칭과 일치하는가 "
        "(등급 표기가 임의로 붙었으면 false)\n"
        "- issuer: 시행/주관 기관\n"
        "- source_title: 근거가 된 검색 결과의 제목\n\n"
        "순수 JSON 배열만 출력:\n"
        '[{"name":"자격증명","exists":false,"exact_name":"","name_matches":false,'
        '"issuer":"","source_title":""}]'
    )


def build_prompt_search_jobs(keywords: list, ref_date: date,
                             school: str, department: str) -> str:
    rd = ref_date.strftime("%Y-%m-%d")
    kw = ", ".join(str(k) for k in keywords if k) or "신입 채용"
    ctx = " / ".join(x for x in [school, department] if x)
    return (
        "당신은 채용 정보 리서처입니다. 반드시 Google Search 를 사용하십시오.\n"
        f"오늘 날짜: {rd}\n"
        f"대상 직무 키워드: {kw}\n"
        + (f"지원자 배경: {ctx}\n" if ctx else "") +
        "\n실제 검색 결과에서 확인한 채용공고만 반환하십시오.\n"
        "규칙:\n"
        f"- {rd} 이후 마감이거나 상시채용인 공고만\n"
        "- 검색 결과에 실제로 나온 공고만. 기억에 의존한 추정 금지\n"
        "- URL 은 적지 마십시오. 시스템이 검색 근거에서 직접 가져와 접속 확인합니다\n"
        "- 확인된 공고가 없으면 빈 배열 [] 을 반환하십시오. 이는 정상 결과입니다\n\n"
        "순수 JSON 배열만 출력:\n"
        '[{"company":"회사명","role":"직무","deadline":"YYYY-MM-DD 또는 상시채용",'
        '"why_match":"매칭 근거","source_title":"근거가 된 검색 결과 제목"}]'
    )


# ══════════════════════════════════════════════
#  12  검증 공통 엔진 (그라운딩 대조 + 이중 통과)
# ══════════════════════════════════════════════

def _vmap(parsed) -> dict[str, dict]:
    """검증 응답을 정규화된 이름 키로 매핑 (F-7: 이름 표기 흔들림 방어)."""
    out: dict[str, dict] = {}
    if isinstance(parsed, dict):
        parsed = [parsed]
    for r in (parsed or []):
        if isinstance(r, dict) and r.get("name"):
            out[norm_name(r["name"])] = r
    return out


def _run_falsification(prompt: str, system: str) -> tuple[dict[str, dict], object, bool]:
    """반증 검증 1회 실행 → (판정맵, 그라운딩 근거, 그라운딩 성립 여부)"""
    parsed, evidence = _call_model_grounded(prompt, system, temperature=0.0)
    return _vmap(parsed), evidence, evidence.grounded


def _dual_falsify(prompt: str, system: str) -> tuple[list[dict[str, dict]], list]:
    """반증 검증을 온도를 달리해 2회 실행한다 (agreement gate).

    한 번은 결정론적(0.0), 한 번은 약간의 탐색성(0.4)으로 돌려 두 결과가
    **모두** 통과한 항목만 인정한다. 환각은 재현성이 낮으므로 이중 통과 요구가
    비용 대비 효과가 가장 큰 필터다.
    """
    maps, evidences = [], []
    m1, e1, _ = _run_falsification(prompt, system)
    maps.append(m1)
    evidences.append(e1)

    if _DUAL_PASS_VERIFY:
        parsed2, e2 = _call_model_grounded(prompt, system, temperature=0.4)
        maps.append(_vmap(parsed2))
        evidences.append(e2)

    return maps, evidences


def _all_pass(maps: list[dict[str, dict]], key: str,
              predicate) -> tuple[bool, str]:
    """모든 검증 패스가 predicate 를 만족해야 통과 (fail-closed)."""
    for idx, m in enumerate(maps, 1):
        vr = m.get(key)
        if vr is None:
            return False, f"{idx}차 검증 응답에 항목 누락 (판정 불가)"
        ok, why = predicate(vr)
        if not ok:
            return False, f"{idx}차 검증 실패: {why}"
    return True, ""


def _grounded_in_any(name: str, evidences: list) -> bool:
    return any(grounding_mentions(name, ev) for ev in evidences)


def _collect_source_urls(name: str, evidences: list) -> list[str]:
    """항목명이 실제로 등장한 검색 근거의 URI 만 URL 후보로 모은다."""
    out: list[str] = []
    toks = {t for t in name_tokens(name) if len(t) >= 2}
    for ev in evidences:
        for uri in ev.uris:
            if is_plausible_url(uri):
                out.append(uri)
    # 이름 토큰이 URI 에 들어간 것을 우선 순위로
    def _rank(u: str) -> int:
        low = urllib.parse.unquote(u).lower()
        return -sum(1 for t in toks if t in low)
    return sorted(dict.fromkeys(out), key=_rank)


# ══════════════════════════════════════════════
#  13  자격증 검증
# ══════════════════════════════════════════════

def verify_certifications(certs: list, audit: VerificationAudit) -> tuple[list, list]:
    """자격증 실재성 검증 — 레지스트리 → 등급 문법 → 반증형 이중 검색.

    반환: (통과 목록, 제외 리포트)
    """
    if not certs:
        return [], []

    print(f"\n  [자격증 검증 — 레지스트리 + 반증 검색: {len(certs)}건]", flush=True)

    rejected: list[dict] = []
    need_search: list[dict] = []
    registry_ok: list[dict] = []

    # 1단계 — 네트워크 없이 즉시 판정 (등급 환각 차단)
    for cert in certs:
        name = str(cert.get("name", "")).strip()
        if not name:
            continue
        check = check_certification_name(name)
        if check.rejected:
            print(f"    [{name}] -> REJECT: {check.reason}", flush=True)
            audit.dropped("certifications", name, check.reason)
            rejected.append({"name": name, "reason": check.reason,
                             "detected_by": "registry_grade_rule"})
            continue
        cert["_check"] = check
        if check.needs_search:
            need_search.append(cert)
        else:
            registry_ok.append(cert)

    verified: list[dict] = []

    # 2단계 — 레지스트리 등재 항목: 공식 명칭으로 정리 후 통과
    for cert in registry_ok:
        check = cert.pop("_check")
        name = cert.get("name", "")
        cert["verified_by"] = "official_registry"
        cert["issuer"] = cert.get("issuer", "")
        cert["url"] = None
        print(f"    [{name}] -> OK (레지스트리 등재)", flush=True)
        audit.kept("certifications", name, check.reason)
        verified.append(cert)

    # 3단계 — 미등재 항목: 반증형 이중 검색 검증
    if need_search:
        names = [c.get("name", "") for c in need_search]
        print(f"    레지스트리 미등재 {len(names)}건 → 반증 검색 검증", flush=True)
        system = ("당신은 한국 자격증 제도 팩트체커입니다. "
                  "반드시 Google Search 로 검색한 결과만 근거로 삼으십시오.")
        maps, evidences = _dual_falsify(
            build_prompt_falsify_certifications(need_search), system)

        for cert in need_search:
            cert.pop("_check", None)
            name = cert.get("name", "")
            key = norm_name(name)

            if not any(ev.grounded for ev in evidences):
                reason = "검색 그라운딩이 발생하지 않음 (모델이 실제 검색을 수행하지 않음)"
                print(f"    [{name}] -> DROP: {reason}", flush=True)
                audit.dropped("certifications", name, reason)
                rejected.append({"name": name, "reason": reason,
                                 "detected_by": "grounding_absent"})
                continue

            ok, why = _all_pass(
                maps, key,
                lambda vr: (
                    (bool(vr.get("exists")) and bool(vr.get("name_matches")),
                     "검색으로 실재 미확인" if not vr.get("exists")
                     else f"공식 명칭 불일치(정확한 명칭: {vr.get('exact_name') or '미확인'})")
                ),
            )
            if not ok:
                print(f"    [{name}] -> DROP: {why}", flush=True)
                audit.dropped("certifications", name, why)
                rejected.append({"name": name, "reason": why,
                                 "detected_by": "falsification_search"})
                continue

            if not _grounded_in_any(name, evidences):
                reason = "검색 근거(제목·스니펫)에서 자격증명을 확인할 수 없음"
                print(f"    [{name}] -> DROP: {reason}", flush=True)
                audit.dropped("certifications", name, reason)
                rejected.append({"name": name, "reason": reason,
                                 "detected_by": "grounding_name_mismatch"})
                continue

            first = maps[0].get(key, {})
            cert["issuer"] = first.get("issuer", "")
            cert["verified_by"] = "grounded_search_dual_pass"
            cert["url"], _ = pick_verified_url(
                _collect_source_urls(name, evidences)[:4],
                expect_tokens=name_tokens(name),
                audit=audit, stage="certifications", label=name,
                timeout=_URL_PROBE_TIMEOUT,
            )
            print(f"    [{name}] -> OK ({cert['issuer'] or '주관기관 미확인'})", flush=True)
            audit.kept("certifications", name, "반증 이중 검증 통과")
            verified.append(cert)

    for c in verified:
        c.pop("verification_query", None)
    return verified, rejected


# ══════════════════════════════════════════════
#  14  동아리·학회 검증
# ══════════════════════════════════════════════

def _club_school_ok(club: dict, user_school: str) -> bool:
    ctype = str(club.get("type", "")).lower()
    if "외부" in ctype:
        return True
    if not user_school:
        return "연합" in ctype
    affil = normalize_school_name(str(club.get("school_affiliation", "")))
    return affil == normalize_school_name(user_school)


def verify_clubs(clubs: list, school: str, audit: VerificationAudit) -> tuple[list, list]:
    """동아리·학회 검증.

    v2.0 대비 결정적 변경
      - '최소 3개' 쿼터와 그에 딸린 재추천 루프(_request_broader_clubs)를 삭제했다.
        재추천 루프는 검증 실패 → 더 지어내기 → 다시 검증 실패의 악순환이었고,
        보충 경로에서는 URL 을 검증 없이 그대로 부착했다.
      - URL 은 검색 근거 URI 를 HTTP 프로브한 뒤에만 붙인다.
    """
    if not clubs:
        return [], []

    rejected: list[dict] = []

    print(f"\n  [동아리 검증 1단계: 학교 매칭 — {len(clubs)}건]", flush=True)
    stage1 = []
    for c in clubs:
        name = c.get("name", "?")
        if _club_school_ok(c, school):
            print(f"    [{name}] OK", flush=True)
            stage1.append(c)
        else:
            reason = (f"소속 학교 불일치(주장: {c.get('school_affiliation','?')}, "
                      f"사용자: {school or '정보 없음'})")
            print(f"    [{name}] -> DROP: {reason}", flush=True)
            audit.dropped("clubs", name, reason)
            rejected.append({"name": name, "reason": reason,
                             "detected_by": "school_match_rule"})

    if not stage1:
        return [], rejected

    print(f"\n  [동아리 검증 2단계: 반증 검색 — {len(stage1)}건]", flush=True)
    system = ("당신은 한국 대학 동아리·학회 정보 팩트체커입니다. "
              "반드시 Google Search 결과만 근거로 삼으십시오.")
    maps, evidences = _dual_falsify(build_prompt_falsify_clubs(school, stage1), system)

    if not any(ev.grounded for ev in evidences):
        reason = "검색 그라운딩이 발생하지 않아 실재 확인 불가 (전체 제외)"
        print(f"    -> {reason}", flush=True)
        for c in stage1:
            audit.dropped("clubs", c.get("name", "?"), reason)
            rejected.append({"name": c.get("name", "?"), "reason": reason,
                             "detected_by": "grounding_absent"})
        return [], rejected

    verified: list[dict] = []
    for club in stage1:
        name = club.get("name", "")
        key = norm_name(name)

        ok, why = _all_pass(
            maps, key,
            lambda vr: (
                (bool(vr.get("exists")) and bool(vr.get("school_match")),
                 "검색으로 실재 미확인" if not vr.get("exists")
                 else f"소속 학교 불일치(확인된 학교: {vr.get('actual_school') or '미확인'})")
            ),
        )
        if not ok:
            print(f"    [{name}] -> DROP: {why}", flush=True)
            audit.dropped("clubs", name, why)
            rejected.append({"name": name, "reason": why,
                             "detected_by": "falsification_search"})
            continue

        if not _grounded_in_any(name, evidences):
            reason = "검색 근거에서 동아리명을 확인할 수 없음 (모델 주장만 존재)"
            print(f"    [{name}] -> DROP: {reason}", flush=True)
            audit.dropped("clubs", name, reason)
            rejected.append({"name": name, "reason": reason,
                             "detected_by": "grounding_name_mismatch"})
            continue

        first = maps[0].get(key, {})
        club["description"] = str(first.get("description", "")).strip()
        club["verified_by"] = "grounded_search_dual_pass"
        club["url"], url_reason = pick_verified_url(
            _collect_source_urls(name, evidences)[:4],
            expect_tokens=name_tokens(name),
            audit=audit, stage="clubs", label=name, timeout=_URL_PROBE_TIMEOUT,
        )
        if club["url"] is None:
            club["url_note"] = (
                "접속 가능한 공식 링크를 확인하지 못해 링크를 제공하지 않습니다. "
                f"아래 검색어로 직접 확인하십시오: {club.get('verification_query') or name}"
            )
        club.pop("verification_query", None)
        print(f"    [{name}] -> OK"
              + (f" (링크 부착)" if club["url"] else " (링크 없음 — 검증 실패)"), flush=True)
        audit.kept("clubs", name, "반증 이중 검증 통과")
        verified.append(club)

    return verified, rejected


# ══════════════════════════════════════════════
#  15  공모전 검증
# ══════════════════════════════════════════════

def verify_contests(contests: list, ref_date: date,
                    audit: VerificationAudit) -> tuple[list, list]:
    if not contests:
        return [], []

    print(f"\n  [공모전 검증: 반증 검색 — {len(contests)}건]", flush=True)
    system = ("당신은 한국 공모전·대회 정보 팩트체커입니다. "
              "반드시 Google Search 결과만 근거로 삼으십시오.")
    maps, evidences = _dual_falsify(
        build_prompt_falsify_contests(contests, ref_date), system)

    rejected: list[dict] = []
    if not any(ev.grounded for ev in evidences):
        reason = "검색 그라운딩이 발생하지 않아 실재 확인 불가 (전체 제외)"
        print(f"    -> {reason}", flush=True)
        for c in contests:
            audit.dropped("contests", c.get("name", "?"), reason)
            rejected.append({"name": c.get("name", "?"), "reason": reason,
                             "detected_by": "grounding_absent"})
        return [], rejected

    verified: list[dict] = []
    for contest in contests:
        name = contest.get("name", "")
        key = norm_name(name)
        label = f"{contest.get('organizer','?')} | {name}"

        # v2.0 은 deadline_ok 의 기본값을 True 로 두고 upcoming 은 아예 검사하지
        # 않았다(fail-open). v3.0 은 모든 플래그를 fail-closed 로 요구한다.
        def _pred(vr):
            if not vr.get("exists"):
                return False, "검색으로 실재 미확인"
            if not vr.get("organizer_confirmed"):
                return False, "주관기관 불일치"
            if not vr.get("upcoming"):
                return False, f"{ref_date} 기준 진행/예정 확인 불가 (종료된 회차로 판단)"
            return True, ""

        ok, why = _all_pass(maps, key, _pred)
        if not ok:
            print(f"    [{label}] -> DROP: {why}", flush=True)
            audit.dropped("contests", name, why)
            rejected.append({"name": name, "reason": why,
                             "detected_by": "falsification_search"})
            continue

        if not _grounded_in_any(name, evidences):
            reason = "검색 근거에서 공모전명을 확인할 수 없음"
            print(f"    [{label}] -> DROP: {reason}", flush=True)
            audit.dropped("contests", name, reason)
            rejected.append({"name": name, "reason": reason,
                             "detected_by": "grounding_name_mismatch"})
            continue

        deadline = maps[0].get(key, {}).get("deadline")
        contest["deadline"] = deadline if deadline and str(deadline) != "null" else None
        contest["verified_by"] = "grounded_search_dual_pass"
        contest["url"], _ = pick_verified_url(
            _collect_source_urls(name, evidences)[:4],
            expect_tokens=name_tokens(name),
            audit=audit, stage="contests", label=name, timeout=_URL_PROBE_TIMEOUT,
        )
        contest.pop("verification_query", None)
        print(f"    [{label}] -> OK", flush=True)
        audit.kept("contests", name, "반증 이중 검증 통과")
        verified.append(contest)

    return verified, rejected


# ══════════════════════════════════════════════
#  16  채용공고 — 검색 그라운딩 단계에서만 생성
# ══════════════════════════════════════════════

def _parse_deadline(dl) -> tuple[bool, str]:
    """마감일 판정 — 파싱 실패는 fail-closed(무효)로 처리.

    v2.0 의 filter_valid_jobs 는 ValueError 시 valid 에 넣었다(fail-open).
    '2025년 말', '추후 공지' 같은 값이 유효 공고로 통과하던 경로다.
    """
    if dl is None:
        return False, "마감일 미확인"
    s = str(dl).strip()
    if s in ("상시채용", "상시", "채용시 마감", "수시채용"):
        return True, "상시채용"
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True, s
    except ValueError:
        return False, f"마감일 형식 확인 불가('{s}')"


def search_and_verify_jobs(keywords: list, ref_date: date, school: str,
                           department: str, audit: VerificationAudit) -> tuple[list, list]:
    """채용공고는 모델 기억이 아니라 검색 근거에서만 만들어진다.

    v2.0 은 채용공고를 (검색 없는) 본 분석 단계에서 생성한 뒤 사후 검증했다.
    존재하지 않는 공고를 먼저 만들어 놓고 지우는 구조라, 검증이 조금만
    느슨해도 그대로 새어 나갔다. v3.0 은 생성 자체를 그라운딩 단계로 옮겼다.
    """
    print("\n  [채용공고: 검색 그라운딩 단계]", flush=True)
    system = ("당신은 채용 정보 리서처입니다. Google Search 로 확인한 공고만 반환하십시오. "
              "확인되지 않으면 빈 배열을 반환하는 것이 정답입니다.")
    parsed, evidence = _call_model_grounded(
        build_prompt_search_jobs(keywords, ref_date, school, department),
        system, temperature=0.0,
    )

    rejected: list[dict] = []
    if not evidence.grounded:
        print("    -> 검색 그라운딩 없음 → 채용공고 추천 생략", flush=True)
        audit.dropped("jobs", "(전체)", "검색 그라운딩 미발생")
        return [], rejected

    jobs = [j for j in (parsed if isinstance(parsed, list) else []) if isinstance(j, dict)]
    if not jobs:
        print("    -> 검색으로 확인된 공고 없음", flush=True)
        return [], rejected

    verified: list[dict] = []
    probes = 0
    for job in jobs:
        company = str(job.get("company", "")).strip()
        role = str(job.get("role", "")).strip()
        label = f"{company} | {role}"
        if not company:
            continue

        ok_dl, dl_note = _parse_deadline(job.get("deadline"))
        if not ok_dl:
            print(f"    [{label}] -> DROP: {dl_note}", flush=True)
            audit.dropped("jobs", label, dl_note)
            rejected.append({"company": company, "role": role, "reason": dl_note})
            continue

        if dl_note != "상시채용":
            if datetime.strptime(dl_note, "%Y-%m-%d").date() < ref_date:
                reason = f"마감 경과({dl_note})"
                print(f"    [{label}] -> DROP: {reason}", flush=True)
                audit.dropped("jobs", label, reason)
                rejected.append({"company": company, "role": role, "reason": reason})
                continue

        if not grounding_mentions(company, evidence):
            reason = "검색 근거에서 회사명을 확인할 수 없음"
            print(f"    [{label}] -> DROP: {reason}", flush=True)
            audit.dropped("jobs", label, reason)
            rejected.append({"company": company, "role": role, "reason": reason})
            continue

        if probes >= _MAX_URL_PROBES:
            audit.dropped("jobs", label, "URL 프로브 상한 도달")
            continue

        candidates = _collect_source_urls(company, [evidence])[:5]
        probes += len(candidates)
        url, url_reason = pick_verified_url(
            candidates,
            expect_tokens=set(name_tokens(company)) | {"채용", "모집", "지원", "recruit"},
            audit=audit, stage="jobs", label=label, timeout=_URL_PROBE_TIMEOUT,
        )
        if not url:
            # 채용공고는 링크 없이는 실행 불가능한 추천이므로 제외한다.
            reason = f"접속 확인 가능한 공고 URL 없음 ({url_reason[:120]})"
            print(f"    [{label}] -> DROP: {reason}", flush=True)
            audit.dropped("jobs", label, reason)
            rejected.append({"company": company, "role": role, "reason": reason})
            continue

        job["url"] = url
        job["deadline"] = dl_note
        job["verified_by"] = "grounded_search + http_probe"
        print(f"    [{label}] -> OK ({url})", flush=True)
        audit.kept("jobs", label, "그라운딩 + URL 접속 검증 통과")
        verified.append(job)

    return verified, rejected


# ══════════════════════════════════════════════
#  17  핵심 분석 함수
# ══════════════════════════════════════════════

def analyze_career_comprehensive(user_text: str, ref_date: date, school: str,
                                 department: str, star_ready: bool,
                                 readiness_reason: str) -> dict:
    system_prompt = build_system_prompt_comprehensive(
        ref_date, school, department, star_ready, readiness_reason)
    rd = ref_date.strftime("%Y-%m-%d")

    profile_parts = []
    if school:
        profile_parts.append(f"학교: {school}")
        profile_parts.append(f"동아리·학회 후보는 '{school}' 소속만 제출하십시오.")
    if department:
        profile_parts.append(f"학과: {department}")
    profile_ctx = ("\n[사용자 프로필]\n" + "\n".join(profile_parts) + "\n") if profile_parts else ""

    source_hint = ""
    if user_text.startswith("[SOURCE_URL:"):
        end = user_text.find("\n")
        source_hint = (
            f"\n[입력 소스 안내]\n사용자가 URL 을 제출했고, 아래는 크롤링 결과입니다: "
            f"{user_text[:end] if end > 0 else user_text[:100]}\n"
            f"크롤링되지 않은 내용을 URL 슬러그·도메인으로 추론하지 마십시오. "
            f"수집된 텍스트에 없는 것은 존재하지 않는 것으로 취급하십시오.\n"
        )

    star_line = (
        "STAR: 각 슬롯에 원문 인용(<슬롯>_source_quote)을 반드시 포함. "
        "원문에 없는 내용·수치 생성 금지.\n"
        if star_ready else
        f"STAR: 시스템 판정으로 이번 분석에서는 생성하지 않습니다. ({readiness_reason}) "
        "resume_star_format 을 출력하지 마십시오.\n"
    )

    user_prompt = (
        f"아래 사용자 데이터를 분석하십시오.\n"
        f"오늘 날짜: {rd} — 모든 기준은 이 날짜 기준.\n"
        f"자격증·동아리·공모전은 '최종 추천'이 아니라 '검증 후보'입니다. "
        f"확신 없는 항목은 후보에서 제외하십시오. 최소 개수 요구는 없습니다.\n"
        f"URL 은 어떤 필드에도 쓰지 마십시오.\n"
        f"{star_line}"
        f"critical_diagnosis: 입력 데이터에서 실제 확인된 사실에만 근거하여 냉정하게 작성.\n"
        f"strength_diagnosis: 입력 데이터에서 실제 확인된 강점만 기재. "
        f"없으면 strengths: [] 후 no_strength_diagnosis 에 이유·개선 방향 기재.\n"
        f"{source_hint}{profile_ctx}\n"
        f"[사용자 데이터]\n{user_text}"
    )
    return _call_model(system_prompt, user_prompt,
                       use_google_search=False, temperature=0.2)


# ══════════════════════════════════════════════
#  18  로그 헬퍼
# ══════════════════════════════════════════════

def _log_strength_summary(result: dict) -> None:
    sd = result.get("strength_diagnosis", {})
    if not sd:
        print("  [강점 진단] strength_diagnosis 키 없음", file=sys.stderr)
        return

    if sd.get("one_line_verdict"):
        print(f"  [강점 진단] {sd['one_line_verdict']}", file=sys.stderr)

    strengths = sd.get("strengths", [])
    if strengths:
        counts = {lvl: sum(1 for s in strengths if s.get("level") == lvl)
                  for lvl in ("outstanding", "strong", "notable")}
        print(f"  [강점 진단] 강점 — outstanding:{counts['outstanding']}  "
              f"strong:{counts['strong']}  notable:{counts['notable']}", file=sys.stderr)
    else:
        no_str = sd.get("no_strength_diagnosis", {})
        print("  [강점 진단] 식별 가능한 강점 없음", file=sys.stderr)
        if no_str.get("reason"):
            print(f"             이유: {no_str['reason']}", file=sys.stderr)
        if no_str.get("improvement_direction"):
            print(f"             개선 방향: {no_str['improvement_direction']}", file=sys.stderr)


def _log_critical_summary(result: dict) -> None:
    diag = result.get("critical_diagnosis", {})
    if not diag:
        return
    if diag.get("one_line_verdict"):
        print(f"  [냉정 진단] {diag['one_line_verdict']}", file=sys.stderr)
    weaknesses = diag.get("weaknesses", [])
    counts = {sev: sum(1 for w in weaknesses if w.get("severity") == sev)
              for sev in ("critical", "major", "minor")}
    print(f"  [냉정 진단] 약점 — critical:{counts['critical']}  "
          f"major:{counts['major']}  minor:{counts['minor']}", file=sys.stderr)


def _log_audit_summary(audit: VerificationAudit) -> None:
    s = audit.summary()
    print(f"  [환각 가드] 통과 {s['total_kept']}건 / 제거 {s['total_dropped']}건 / "
          f"강등 {s['total_degraded']}건", file=sys.stderr)
    for stage, counts in s["by_stage"].items():
        print(f"             {stage}: kept={counts.get('kept',0)} "
              f"dropped={counts.get('dropped',0)} degraded={counts.get('degraded',0)}",
              file=sys.stderr)


# ══════════════════════════════════════════════
#  19  Main
# ══════════════════════════════════════════════

def main(user_input: list[str] | None = None, school: str = "", department: str = ""):
    ref_date = date.today()
    rd = ref_date.strftime("%Y-%m-%d")
    audit = VerificationAudit()

    print("=" * 65)
    print("  Career Analysis AI - COMPREHENSIVE Edition v3.0")
    print(f"  모델: {_ANALYSIS_MODEL}  |  임베딩: {_EMBEDDING_MODEL}")
    print(f"  기준일: {rd} (자동)")
    print("  환각 가드: URL 무생성 / 그라운딩 강제 / 반증 이중 검증 / STAR 근거 결속")
    print("=" * 65)

    school, department = get_user_profile(school, department)
    raw_content = get_user_input(user_input or [])

    if len(raw_content.strip()) < 10:
        resp = ErrorResponse(message="입력 데이터가 너무 짧습니다. 최소 10자 이상 입력하세요.")
        print(resp.model_dump_json(indent=2, exclude_none=True))
        return resp

    # ── [1] STAR 사전 판정 (LLM 호출 전, 결정론적) ──────────────────
    print("\n[1] 입력 데이터 STAR 적합성 사전 판정...", flush=True)
    readiness = assess_star_readiness(raw_content)
    print(f"  경험 블록 {len(readiness.blocks)}개 중 STAR 기준 충족 "
          f"{len(readiness.eligible_blocks)}개 → "
          f"{'생성 진행' if readiness.ready else '생성 생략'}", flush=True)
    if not readiness.ready:
        print(f"  사유: {readiness.reason}", flush=True)

    # ── [2] 임베딩 ────────────────────────────────────────────────
    print("\n[2] 임베딩 벡터 생성 중...", flush=True)
    vector = get_embedding(raw_content)
    print(f"  OK (dim: {len(vector)})" if vector
          else "  WARNING: embedding skipped (분석은 계속 진행)", flush=True)

    # ── [3] 본 분석 ───────────────────────────────────────────────
    print("\n[3] 종합 커리어 분석 (강점 → 보완점) 중...", flush=True)
    result = analyze_career_comprehensive(
        raw_content, ref_date, school, department,
        readiness.ready, readiness.reason)

    if not isinstance(result, dict) or result.get("status") == "error":
        msg = result.get("message", "분석에 실패했습니다.") if isinstance(result, dict) \
            else "분석에 실패했습니다."
        resp = ErrorResponse(message=msg)
        print(resp.model_dump_json(indent=2, exclude_none=True))
        return resp

    # 모델이 규칙을 어기고 URL 을 넣었을 경우를 대비한 1차 스크럽 (defense in depth)
    stripped = scrub_model_urls(result)
    if stripped:
        print(f"  [환각 가드] 모델이 출력한 미검증 URL {stripped}건 제거", flush=True)
        audit.dropped("url", "(모델 생성 URL)", f"검증 없이 생성된 URL {stripped}건 제거")

    # ── [4] 후보 검증 ─────────────────────────────────────────────
    print("\n[4] 추천 후보 검증 중...", flush=True)
    additional = result.get("additional_recommendations") or {}

    certs, cert_rejected = verify_certifications(
        additional.get("certifications") or [], audit)
    clubs, club_rejected = verify_clubs(
        additional.get("clubs_and_societies") or [], school, audit)
    contests, contest_rejected = verify_contests(
        additional.get("projects_and_contests") or [], ref_date, audit)

    result["additional_recommendations"] = {
        "certifications": certs,
        "clubs_and_societies": clubs,
        "projects_and_contests": contests,
    }

    # 쿼터를 없앤 대신, 결과가 비었을 때 '왜 비었는지'를 사용자에게 설명한다.
    notices = []
    if not certs:
        notices.append("자격증: 실재가 확인된 항목이 없어 추천하지 않았습니다. "
                       "확인되지 않은 자격증을 채워 넣지 않습니다.")
    if not clubs:
        notices.append(
            "동아리·학회: 검색으로 실재가 확인된 항목이 없어 추천하지 않았습니다."
            + (f" '{school} 동아리 모집', '{school} 학회' 로 직접 검색해 보십시오."
               if school else ""))
    if not contests:
        notices.append("공모전: 현재 진행/예정임이 확인된 항목이 없어 추천하지 않았습니다.")
    result["recommendation_notices"] = notices

    # ── [5] STAR 근거 검증 + 품질 채점 ────────────────────────────
    print("\n[5] STAR 근거 검증 및 품질 채점 중...", flush=True)
    star_status = readiness.to_dict()
    if readiness.ready:
        kept_star, rejected_star = validate_star_entries(
            result.get("resume_star_format") or [], raw_content, audit)
        result["resume_star_format"] = kept_star
        star_status["generated"] = bool(kept_star)
        star_status["rejected_entries"] = rejected_star
        # 근거를 통과한 항목만 품질 채점 — 환각 검사와 품질 검사는 별개 관문이다.
        star_status["quality_review"] = evaluate_star_entries(
            kept_star, raw_content, audit)
        if not kept_star:
            star_status["reason"] = (
                "STAR 초안을 생성했으나 모든 항목이 원문 근거 검증을 통과하지 못해 "
                "폐기했습니다. 근거 없는 STAR 를 제공하는 것보다 제공하지 않는 것이 낫습니다."
            )
            star_status["coaching"] = [
                "각 경험에 '본인이 한 행동'과 '결과 수치'를 원문에 직접 적어 주십시오.",
                "예) 'Python 으로 크롤러를 만들어 리뷰 8,000건을 수집했고, "
                "수작업 대비 조사 시간을 3일 → 4시간으로 줄였습니다.'",
            ]
        qr = star_status["quality_review"]
        print(f"  STAR 항목 {len(kept_star)}건 통과 / {len(rejected_star)}건 폐기", flush=True)
        if qr.get("evaluated"):
            print(f"  품질 등급 분포: {qr['grade_distribution']}", flush=True)
    else:
        result["resume_star_format"] = []
        star_status["rejected_entries"] = []
        star_status["quality_review"] = evaluate_star_entries([], raw_content, audit)
        print("  사전 판정에 따라 STAR 를 생성하지 않았습니다.", flush=True)

    result["star_analysis_status"] = star_status

    # ── [6] 채용공고 ──────────────────────────────────────────────
    keywords = result.get("target_job_keywords") or \
        (result.get("keyword_clustering") or {}).get("job_industry") or []
    jobs, job_rejected = search_and_verify_jobs(
        keywords, ref_date, school, department, audit)
    result["verified_jobs"] = jobs
    result.pop("valid_job_recommendations", None)
    result.pop("target_job_keywords", None)

    # ── [7] 최종 스크럽 + 감사 ────────────────────────────────────
    allow = {j["url"].rstrip("/") for j in jobs if j.get("url")}
    allow |= {c["url"].rstrip("/") for c in clubs + contests + certs if c.get("url")}
    leaked = scrub_model_urls(result, allow)
    if leaked:
        audit.dropped("url", "(최종 스크럽)", f"미검증 URL {leaked}건 제거")

    result["verification_audit"] = audit.to_dict()
    result["rejected_by_guard"] = {
        "certifications": cert_rejected,
        "clubs_and_societies": club_rejected,
        "projects_and_contests": contest_rejected,
        "jobs": job_rejected,
    }
    result["embedding_dim"] = len(vector) if vector else None
    result["guard_version"] = "v3.0"

    print("\n[8] 분석 완료!\n", flush=True)
    _log_strength_summary(result)
    _log_critical_summary(result)
    _log_audit_summary(audit)

    payload = {k: v for k, v in result.items() if k not in ("status", "vector")}
    resp = VectorSuccessResponse(result=payload, vector=vector)
    print(resp.model_dump_json(indent=2, exclude_none=True))
    return resp


if __name__ == "__main__":
    _lines = [l.rstrip("\n") for l in sys.stdin] if not sys.stdin.isatty() else []
    main(_lines, os.environ.get("USER_SCHOOL", ""), os.environ.get("USER_DEPARTMENT", ""))
