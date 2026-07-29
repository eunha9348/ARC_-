"""
star_quality.py — STAR 품질 채점 엔진 (v3.1)

배경
────
v3.0 은 STAR 의 **환각**을 잡았다(원문에 없는 내용·수치 차단). 그러나 환각이
없다고 좋은 STAR 가 되지는 않는다. 근거만 지키면 STAR 는 쉽게
"사용자 문장을 네 칸에 나눠 담은 것"에 머문다.

이 모듈은 그 다음 단계 — **작성 품질**을 채점한다.

설계 원칙: 전문성은 사실을 늘려서 만들지 않는다
──────────────────────────────────────────────
"전문적인 STAR"를 만드는 흔한 방법은 그럴듯한 배경과 성과를 덧붙이는 것이고,
그것이 바로 v2.0 이 실패한 방식이다. v3.1 은 정반대 경로를 쓴다.

  선택(selection)  — 어떤 경험을 STAR 로 쓸지 고르는 판단
  배분(allocation) — Action 이 절반을 차지하도록 분량을 재배치
  표현(framing)    — "~를 했습니다" 를 '강한 동사 + 맥락 + 결과' 성취문으로
  진단(diagnosis)  — 부족한 요소는 지어내지 않고 '무엇이 비었는지' + 채우는 법

즉 이 모듈은 새 사실을 만들지 않는다. 이미 근거가 검증된 문장을
**어떻게 쓰였는가**만 평가하고, 미달 항목마다 구체적 개선 지시를 붙인다.

채점 기준의 출처
────────────────
공개된 커리어 센터·채용 가이드에서 반복적으로 확인되는 규칙을 코드화했다.

  · Action 이 답변의 약 50% — S/T 에 시간을 쓰고 A/R 을 서두르는 것이
    가장 흔한 실패 유형
  · Action 은 1인칭("제가")으로 — "우리가"는 가장 흔하고 가장 고치기 쉬운 실수.
    면접관은 팀의 성과를 채점할 수 없다. 공동 작업이면 역할 분담을 명시할 것
  · Result 는 최소 하나의 수치를 포함 — 수치 없는 결과는 감점 대상
  · Result 는 수치에 더해 그 수치가 만든 변화까지
  · 이력서 성취문 공식: 강한 동사 + 맥락(기간·인원·규모) = 결과
  · STARR / STAR-L — 표준 STAR 에 회고(Reflection) 한 겹을 추가하는 것이
    현재 권장 방향

참고 출처는 README 의 'STAR 품질 기준 출처' 절에 정리되어 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hallucination_guard import (
    VerificationAudit,
    name_tokens,
    numbers_grounded,
    overlap_ratio,
)

# ══════════════════════════════════════════════
#  어휘 사전
# ══════════════════════════════════════════════

# 성취를 드러내는 강한 동사 (이력서 성취문에서 권장)
_STRONG_VERBS = (
    "구축", "설계", "개발", "구현", "주도", "리드", "총괄", "창설", "도입",
    "개선", "최적화", "자동화", "재설계", "전환", "정립", "확립", "표준화",
    "분석", "규명", "도출", "검증", "설득", "협상", "조율", "유치", "확보",
    "달성", "출시", "런칭", "배포", "확대", "단축", "절감", "증대", "제안",
)

# 주체·성과가 드러나지 않는 약한 서술 (감점 대상)
_WEAK_VERBS = (
    "참여했", "참가했", "도왔", "보조했", "관련 업무", "업무를 진행",
    "경험했", "배웠", "알게 되었", "함께했", "활동했", "임했", "노력했",
    "맡아서 했", "일을 했", "수행하였고",
)

# 수치 없이 쓰이면 무의미한 모호 표현
_VAGUE_TERMS = (
    "성공적", "크게", "많이", "대폭", "상당히", "효과적으로", "긍정적",
    "좋은 반응", "원활하게", "잘 마무리", "큰 도움", "많은 관심", "높은 평가",
)

# 공동 주어 — Action 에서 개인 기여를 가린다
_COMMUNAL_SUBJECTS = ("우리는", "우리가", "우리 팀", "저희는", "저희가", "저희 팀",
                      "팀이 ", "팀은 ", "다같이", "다 함께", "모두가")

# 1인칭·소유권 표지
_OWNERSHIP_MARKERS = ("제가", "저는", "내가", "나는", "본인이", "직접", "단독으로",
                      "담당하여", "담당해", "주도하여", "주도해", "맡아", "책임지고")

# 역할 분담을 명시한 경우 — 공동 주어가 있어도 감점하지 않는다
_ROLE_SPLIT_MARKERS = ("제가 맡은", "저는 이 중", "역할 분담", "나누어", "나눠",
                       "담당했고", "제 몫", "저의 역할", "제 역할", "이 중 저는")

# Action 에 '어떻게'가 들어있는지 판단하는 방법 표지
_METHOD_WORDS = ("방식", "방법", "프로세스", "절차", "기준", "체계", "프레임워크",
                 "지표", "모델", "알고리즘", "템플릿", "가이드", "매뉴얼")

# 수치 외 파급을 나타내는 표현
_IMPACT_MARKERS = ("이어졌", "이어져", "채택", "정식", "도입", "확대", "지속",
                   "표준", "이후", "덕분에", "기반으로", "발전", "전사", "재사용",
                   "수상", "선정", "인정", "호평", "재계약", "연장")

_METRIC_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|퍼센트|배|명|건|회|개|팀|위|등|점|억|천만|백만|만원|"
    r"천원|원|달러|시간|분|일|주|개월|년|주차|차|kb|mb|gb|ms|초)"
)
_SCALE_RE = re.compile(
    r"(20\d{2}\s*[.\-/년]|\d+\s*(?:개월|년|주|학기|명|건|개|팀))"
)
_LATIN_TOOL_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+#.\-]{1,}\b")
_INSTRUMENTAL_RE = re.compile(r"[가-힣A-Za-z0-9]+(?:으로|로)\s")

_STAR_SLOTS = ("S", "T", "A", "R")


# ══════════════════════════════════════════════
#  채점 결과 자료구조
# ══════════════════════════════════════════════

@dataclass
class Criterion:
    key: str
    label: str
    passed: bool
    detail: str
    coaching: str = ""

    def to_dict(self) -> dict:
        d = {"key": self.key, "label": self.label,
             "passed": self.passed, "detail": self.detail}
        if not self.passed and self.coaching:
            d["coaching"] = self.coaching
        return d


@dataclass
class StarQuality:
    score: int
    max_score: int
    grade: str
    criteria: list[Criterion] = field(default_factory=list)

    @property
    def failed(self) -> list[Criterion]:
        return [c for c in self.criteria if not c.passed]

    def to_dict(self) -> dict:
        return {
            "grade": self.grade,
            "score": f"{self.score}/{self.max_score}",
            "verdict": _GRADE_VERDICT[self.grade],
            "criteria": [c.to_dict() for c in self.criteria],
            "priority_fixes": [c.coaching for c in self.failed if c.coaching][:3],
        }


_GRADE_VERDICT = {
    "A": "제출 가능한 수준. 구조·주체·수치가 모두 갖춰져 있습니다.",
    "B": "기본 구조는 갖췄으나 한두 가지 보완이 필요합니다.",
    "C": "STAR 형식만 갖춘 상태입니다. 아래 항목을 고치지 않으면 설득력이 약합니다.",
    "D": "사실상 경험 나열에 가깝습니다. 구조적 재작성이 필요합니다.",
}


def _grade(score: int, max_score: int) -> str:
    if max_score <= 0:
        return "D"
    ratio = score / max_score
    if ratio >= 0.85:
        return "A"
    if ratio >= 0.65:
        return "B"
    if ratio >= 0.45:
        return "C"
    return "D"


# ══════════════════════════════════════════════
#  개별 판정 헬퍼
# ══════════════════════════════════════════════

def _txt(entry: dict, slot: str) -> str:
    return str(entry.get(slot) or "").strip()


def _has_any(text: str, needles) -> bool:
    return any(n in text for n in needles)


def _count_any(text: str, needles) -> int:
    return sum(text.count(n) for n in needles)


def _has_method(action: str) -> bool:
    """Action 에 '어떻게'가 드러나는가 — 도구·수단·방법론 중 하나라도."""
    if _has_any(action, _METHOD_WORDS):
        return True
    if _LATIN_TOOL_RE.search(action):          # Python, SQL, Figma 등
        return True
    if _INSTRUMENTAL_RE.search(action):        # 'OO으로/로' 수단 표현
        return True
    return False


# ══════════════════════════════════════════════
#  채점 본체
# ══════════════════════════════════════════════

def score_star_entry(entry: dict) -> StarQuality:
    """근거 검증을 통과한 STAR 항목의 **작성 품질**을 채점한다.

    이 함수는 사실을 검증하지 않는다(그건 hallucination_guard 의 몫).
    오직 '이렇게 쓴 것이 채용담당자에게 통하는가'만 본다.
    """
    S, T, A, R = (_txt(entry, s) for s in _STAR_SLOTS)
    total = len(S) + len(T) + len(A) + len(R)
    criteria: list[Criterion] = []

    def add(key, label, passed, detail, coaching=""):
        criteria.append(Criterion(key, label, passed, detail, coaching))

    # ── 1. 분량 배분: Action 이 중심인가 ──────────────────────────
    a_ratio = (len(A) / total) if total else 0.0
    add(
        "action_dominant", "Action 비중",
        a_ratio >= 0.35,
        f"Action 이 전체의 {a_ratio:.0%} (권장 40~50%)",
        "Action 을 늘리십시오. 본인이 무엇을 어떤 순서로 했는지 2~3단계로 "
        "쪼개 쓰면 자연히 절반을 차지합니다. Situation 은 줄이십시오.",
    )

    # ── 2. 분량 배분: 배경이 과하지 않은가 ───────────────────────
    st_ratio = ((len(S) + len(T)) / total) if total else 0.0
    add(
        "context_concise", "배경 간결성",
        st_ratio <= 0.45,
        f"Situation+Task 가 전체의 {st_ratio:.0%} (권장 30% 이하)",
        "배경 설명을 2문장 이내로 줄이십시오. 면접관은 상황이 아니라 "
        "당신의 행동을 평가합니다.",
    )

    # ── 3. 주체: 1인칭인가 ───────────────────────────────────────
    communal = _count_any(A, _COMMUNAL_SUBJECTS)
    owned = _has_any(A, _OWNERSHIP_MARKERS)
    role_split = _has_any(A, _ROLE_SPLIT_MARKERS)
    add(
        "first_person", "개인 기여 명시",
        communal == 0 or owned or role_split,
        (f"Action 에 공동 주어 {communal}회, 개인 주체 표현 "
         f"{'있음' if owned else '없음'}"),
        "'우리가'를 '제가'로 바꾸십시오. 공동 작업이었다면 역할을 갈라 쓰십시오 — "
        "예: '팀은 3개 축으로 나눴고, 저는 데이터 수집과 전처리를 맡았습니다.' "
        "팀의 성과는 채점되지 않습니다.",
    )

    # ── 4. Action 에 '어떻게'가 있는가 ───────────────────────────
    add(
        "action_method", "방법 구체성",
        _has_method(A),
        "Action 에 사용한 도구·방법·접근이 드러나는지",
        "무엇을 했는지만이 아니라 '어떻게' 했는지를 쓰십시오. "
        "사용한 도구, 접근 방식, 판단 기준 중 하나는 반드시 들어가야 합니다.",
    )

    # ── 5. 강한 동사 ─────────────────────────────────────────────
    strong = _count_any(A, _STRONG_VERBS)
    weak = _count_any(A, _WEAK_VERBS)
    add(
        "strong_verb", "성취 동사",
        strong > 0 and weak == 0,
        f"강한 동사 {strong}개, 약한 서술 {weak}개",
        "'참여했습니다·도왔습니다·경험했습니다'를 '설계했습니다·개선했습니다·"
        "도출했습니다' 같은 성취 동사로 바꾸십시오. 동사가 기여도를 말해줍니다.",
    )

    # ── 6. Result 정량화 ────────────────────────────────────────
    add(
        "result_quantified", "결과 정량화",
        bool(_METRIC_RE.search(R)),
        "Result 에 수치 지표가 있는지",
        "결과에 숫자를 하나 이상 넣으십시오 — 비율·금액·시간 단축·인원·"
        "처리 건수·순위 무엇이든. 수치 없는 결과는 감점됩니다.",
    )

    # ── 7. Result 파급 ──────────────────────────────────────────
    add(
        "result_impact", "결과의 파급",
        _has_any(R, _IMPACT_MARKERS),
        "수치 외에 그 결과가 만든 변화가 서술되는지",
        "숫자 다음에 '그래서 무엇이 달라졌는지'를 한 문장 붙이십시오 — "
        "예: '이 방식이 이후 정기 운영에 그대로 채택되었습니다.'",
    )

    # ── 8. 모호 표현 ────────────────────────────────────────────
    vague_hits = [v for v in _VAGUE_TERMS if v in (R + A)]
    vague_bad = bool(vague_hits) and not _METRIC_RE.search(R)
    add(
        "no_vague", "모호 표현 배제",
        not vague_bad,
        (f"수치 없이 모호 표현 사용: {', '.join(vague_hits)}"
         if vague_bad else "모호 표현 없음 또는 수치로 뒷받침됨"),
        f"'{', '.join(vague_hits[:2])}' 같은 표현은 근거가 없으면 무의미합니다. "
        "수치로 바꾸거나 삭제하십시오.",
    )

    # ── 9. Situation·Task 역할 분리 ─────────────────────────────
    # 포함도까지 보는 이유: Task 가 Situation 의 축약본인 경우 Jaccard 는
    # 합집합이 커져 낮게 나오지만, 실제로는 완전한 중복이다.
    st_overlap = overlap_ratio(name_tokens(S), name_tokens(T))
    add(
        "slots_distinct", "슬롯 역할 분리",
        st_overlap < 0.5,
        f"Situation·Task 내용 중복도 {st_overlap:.0%}",
        "Situation 은 '어떤 상황이었는지', Task 는 '내가 무엇을 해내야 했는지'로 "
        "역할이 다릅니다. 같은 말을 두 번 쓰지 마십시오.",
    )

    # ── 10. 맥락 규모 ───────────────────────────────────────────
    add(
        "context_scale", "맥락 규모",
        bool(_SCALE_RE.search(S + T + A)),
        "기간·인원·규모 중 하나라도 명시되는지",
        "언제(기간), 몇 명 규모에서, 어느 정도 크기의 일이었는지 중 하나는 "
        "넣으십시오. 규모가 없으면 성과의 크기를 가늠할 수 없습니다.",
    )

    score = sum(1 for c in criteria if c.passed)
    return StarQuality(score, len(criteria), _grade(score, len(criteria)), criteria)


# ══════════════════════════════════════════════
#  파생 필드 검증 (headline · competency · lesson)
# ══════════════════════════════════════════════

def validate_derived_fields(entry: dict, source_text: str,
                            audit: VerificationAudit | None = None) -> list[str]:
    """headline / competency_evidence / L(회고) 의 안전성을 검사한다.

    이 세 필드는 '새 사실'이 아니라 이미 검증된 S/T/A/R 로부터의 **해석**이다.
    따라서 원문 인용은 요구하지 않되, 두 가지는 강제한다.
      1. 원문에 없는 수치를 쓸 수 없다 (headline 은 성과를 압축하므로 특히 위험)
      2. 회고(L)는 원문 근거가 있을 때만 남긴다 — 없으면 통째로 삭제
    """
    notes: list[str] = []
    title = str(entry.get("title") or "(제목 없음)")

    headline = str(entry.get("headline") or "").strip()
    if headline:
        ok, invented = numbers_grounded(headline, source_text)
        if not ok:
            entry["headline"] = None
            notes.append(f"headline 에 원문에 없는 수치({', '.join(sorted(invented))}) → 삭제")
            if audit:
                audit.degraded("star", title, "headline 수치 환각 → 삭제")

    lesson = str(entry.get("L") or "").strip()
    if lesson:
        quote = str(entry.get("L_source_quote") or "").strip()
        from hallucination_guard import quote_supported
        if not quote_supported(quote, source_text):
            entry["L"] = None
            entry["L_source_quote"] = None
            notes.append("회고(L)의 근거 인용이 원문에서 확인되지 않음 → 삭제")
            if audit:
                audit.degraded("star", title, "회고 근거 미확인 → 삭제")
        else:
            ok, invented = numbers_grounded(lesson, source_text)
            if not ok:
                entry["L"] = None
                entry["L_source_quote"] = None
                notes.append("회고(L)에 원문에 없는 수치 → 삭제")

    return notes


# ══════════════════════════════════════════════
#  전체 평가
# ══════════════════════════════════════════════

def evaluate_star_entries(entries: list[dict], source_text: str,
                          audit: VerificationAudit | None = None) -> dict:
    """근거 검증을 통과한 STAR 항목 전체에 품질 채점을 적용한다.

    품질 미달이라고 항목을 버리지는 않는다 — 버리면 사용자가 무엇을 고쳐야
    하는지 알 수 없다. 대신 등급과 우선 개선 지시를 붙인다.
    """
    if not entries:
        return {"evaluated": 0, "grade_distribution": {},
                "portfolio_verdict": "평가할 STAR 항목이 없습니다.", "top_fixes": []}

    dist: dict[str, int] = {}
    all_failed: dict[str, int] = {}

    for entry in entries:
        derived_notes = validate_derived_fields(entry, source_text, audit)
        quality = score_star_entry(entry)
        entry["quality"] = quality.to_dict()
        if derived_notes:
            entry["quality"]["derived_field_notes"] = derived_notes

        dist[quality.grade] = dist.get(quality.grade, 0) + 1
        for c in quality.failed:
            all_failed[c.label] = all_failed.get(c.label, 0) + 1

        if audit:
            audit.kept("star_quality", str(entry.get("title") or "?"),
                       f"품질 {quality.grade} ({quality.score}/{quality.max_score})")

    n = len(entries)
    weak = dist.get("C", 0) + dist.get("D", 0)
    if weak == 0:
        verdict = (f"STAR {n}건 모두 제출 가능한 수준입니다. "
                   "표현을 다듬는 수준의 보완만 남았습니다.")
    elif weak == n:
        verdict = (f"STAR {n}건 전부가 구조적 보완이 필요합니다. "
                   "원문 기록 자체가 '무엇을 했다'에 머물러 있어, "
                   "행동의 방법과 결과의 수치를 추가로 적어야 합니다.")
    else:
        verdict = (f"STAR {n}건 중 {weak}건이 보완 대상입니다. "
                   "아래 공통 결손 항목부터 고치는 것이 효율적입니다.")

    top_fixes = [f"{label} — {cnt}/{n}건에서 미달"
                 for label, cnt in sorted(all_failed.items(), key=lambda kv: -kv[1])[:3]]

    return {
        "evaluated": n,
        "grade_distribution": dist,
        "portfolio_verdict": verdict,
        "top_fixes": top_fixes,
    }
