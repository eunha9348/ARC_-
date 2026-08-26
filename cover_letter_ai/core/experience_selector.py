"""
core/experience_selector.py
============================================================================
'지원 회사 리서치 기반 경험 선별·배치' 파트.

────────────────────────────────────────────────────────────────────────
이 모듈이 생긴 이유 (해결한 문제)
────────────────────────────────────────────────────────────────────────
기존 집필 프롬프트는 "경험 1개(많아야 2개)만 골라 깊게 서술할 것,
여러 경험을 나열하는 글은 실패작"이라고 강제하고 있었다. 그 결과
사용자가 경력·프로젝트·활동·수상을 아무리 많이 입력해도 자소서에는
기본 정보와 경험 '하나'만 반영됐다.

게다가 그 하나를 무엇으로 고를지는 모델의 즉흥 판단에 맡겨져 있었고,
지원 회사 리서치는 '문체와 포부의 방향'에만 은은하게 쓰일 뿐 경험 선택
자체에는 개입하지 못했다. 지원 회사가 정작 관심 있게 볼 경험이 통째로
누락되는 일이 잦았던 원인이다.

────────────────────────────────────────────────────────────────────────
이 모듈이 하는 일
────────────────────────────────────────────────────────────────────────
  1) 평탄화 : UserProfile 의 이력을 '사건 단위'(ExperienceItem)로 쪼갠다.
  2) 채점   : ★ 1순위 기준. 지원 회사 리서치 + 직무/업계 프로필 + 자소서 문항을
              기준으로 각 경험의 적합도를 0~100 으로 채점하고, "이 회사가 이
              경험을 왜 볼 만한가"(company_fit)를 함께 뽑는다. 무엇을 쓸지와
              무엇을 크게 다룰지는 오직 이 점수가 정한다.
  3) 배치   : 분량에 맞는 개수만큼 핵심(core)/보조(supporting)로 나눈 뒤,
              시간 순(과거→현재)으로 늘어놓아 집필에 넘긴다.

★ 적합도와 시계열의 관계 (혼동 주의)
  시간은 '선별 기준'이 아니라 '배치 제약'이다. 오래됐다는 이유로 비중이
  커지거나 최근이라는 이유로 핵심이 바뀌는 일은 없다. 적합도 1순위 경험이
  언제 것이든 그것이 글의 중심이며, 시계열은 단지 그렇게 고른 경험들을
  서술할 때 앞선 시점으로 되돌아가지 않게 하는 역할만 한다.
  ExperienceSelection 은 이 둘을 by_relevance(비중) / ordered(배치)로
  분리해 담고, 프롬프트에도 그 순서대로 제시한다.

채점은 LLM 판단을 우선 사용하되, 응답 파싱이 실패해도 파이프라인이 멈추지
않도록 키워드 겹침 기반의 결정적(deterministic) 폴백 스코어러를 둔다.

★ 제1원칙(환각 방지)과의 관계
  이 모듈은 사실을 '만들지' 않는다. 원장에 이미 있는 항목의 순서를 정하고
  무엇을 쓸지 고를 뿐이다. 채점 결과에 없는 경험은 프롬프트에서 아예
  제외되므로, 오히려 근거 없는 서술이 끼어들 여지가 줄어든다.
"""

from __future__ import annotations

import re
from typing import Any

from .. import config
from .data_models import (
    UserProfile, ExperienceItem, ScoredExperience, ExperienceSelection,
)
from .gemini_client import GeminiClient
from .job_profiles import get_job_profile, get_industry_profile, infer_industry
from . import prompt_builder as pb


# --------------------------------------------------------------------------
#  대상 필드
# --------------------------------------------------------------------------
#  RANKABLE : '언제 무엇을 했다'는 사건 — 채점해서 고르고 배치할 대상
#  COMMON   : 사건이 아니라 지원자의 상시 속성 — 채점 없이 모든 문항에서
#             근거로 자유롭게 끌어 쓸 수 있는 공통 재료
# --------------------------------------------------------------------------
RANKABLE_FIELDS: dict[str, str] = {
    "experiences": "경력/인턴",
    "projects": "프로젝트",
    "activities": "대외활동/동아리",
    "awards": "수상",
}

COMMON_FIELDS: dict[str, str] = {
    "education": "학력",
    "skills": "보유역량/기술",
    "certifications": "자격증",
    "achievements": "정량성과",
    "strengths": "강점/성향",
}

#  채택 최저 점수 — 이 미만은 억지로 끼워 넣지 않는다(글이 산만해짐)
MIN_SUPPORTING_SCORE = 35


def _render_item(item: Any) -> str:
    """원장 항목(문자열 또는 dict)을 한 줄 텍스트로 직렬화."""
    if isinstance(item, dict):
        return ", ".join(
            f"{k}: {v}" for k, v in item.items() if str(v).strip()
        )
    return str(item).strip()


# --------------------------------------------------------------------------
#  1) 평탄화 — 이력을 '사건 단위'로 쪼갠다
# --------------------------------------------------------------------------
def flatten_experiences(user: UserProfile) -> list[ExperienceItem]:
    """UserProfile 의 경력/프로젝트/활동/수상을 채점 가능한 단위로 편다."""
    data = user.to_dict()
    items: list[ExperienceItem] = []
    for fkey, label in RANKABLE_FIELDS.items():
        for i, raw in enumerate(data.get(fkey) or [], 1):
            text = _render_item(raw)
            if not text:
                continue
            items.append(ExperienceItem(
                key=f"{fkey[:3]}{i}",
                field=fkey,
                label=label,
                text=text,
                year=pb._first_year(raw),
            ))
    return items


def build_common_material(user: UserProfile) -> str:
    """채점 대상은 아니지만 모든 문항에서 근거로 쓸 수 있는 공통 재료."""
    data = user.to_dict()
    lines: list[str] = []
    for fkey, label in COMMON_FIELDS.items():
        vals = data.get(fkey) or []
        rendered = [_render_item(v) for v in vals]
        rendered = [r for r in rendered if r]
        if rendered:
            lines.append(f"- {label}: {'; '.join(rendered)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#  2) 분량 → 채택 개수 (핵심 / 보조)
# --------------------------------------------------------------------------
def plan_capacity(max_chars: int) -> tuple[int, int]:
    """글자수 제한에 맞는 (핵심 개수, 보조 개수)를 정한다.

    500자에 경험 4개를 밀어 넣으면 전부 얕아지고, 2000자에 경험 1개만
    쓰면 분량을 못 채운다. 분량과 경험 수를 비례시켜 '깊이'와 '종합성'이
    동시에 성립하는 지점을 잡는다.
    """
    n = int(max_chars or 0)
    if n and n <= 500:
        return 1, 1
    if n and n <= 800:
        return 1, 2
    if n and n <= 1200:
        return 1, 3
    if n and n <= 2000:
        return 2, 3
    return 2, 4


# --------------------------------------------------------------------------
#  3-a) LLM 채점 프롬프트
# --------------------------------------------------------------------------
def build_ranking_prompt(
    items: list[ExperienceItem],
    question: str,
    job_key: str,
    industry_key: str,
    company_research: str = "",
    company_name: str = "",
    target_job: str = "",
) -> str:
    profile = get_job_profile(job_key)
    ind = get_industry_profile(industry_key)

    listing = "\n".join(
        f"- {it.key} | {it.label} | 연도 {it.year if it.year != 9999 else '미상'} | {it.text}"
        for it in items
    )
    question_line = question.strip() or "자유 형식의 자기소개서(핵심 강점과 지원동기 중심)"
    company_line = (company_name or "").strip() or "(회사명 미지정)"
    company_block = (company_research or "").strip() or (
        "(회사 리서치 정보 없음 — 직무·업계 기준으로만 판단할 것)"
    )

    return f"""\
당신은 '{company_line}'의 채용 담당자입니다. 아래 지원자의 이력 항목들을
읽고, 이번 자소서 문항에 어떤 경험을 쓰는 것이 이 회사에 가장 설득력
있을지 냉정하게 채점하세요.

[자소서 문항]
{question_line}

[지원 직무]
- {profile['label']} / 지원자가 적은 직무 표현: {target_job or "(미지정)"}
- 이 직무에서 인사팀이 중점적으로 보는 것: {", ".join(profile['hr_focus'])}
- 핵심 역량: {", ".join(profile['competencies'])}

[지원 업계 — {ind['label']}]
- 이 업계가 사람에게서 확인하려는 가치: {", ".join(ind['values'])}
- 이 업계에서 설득력을 갖는 근거의 형태: {ind['evidence']}

[지원 회사 리서치]
{company_block}

[채점할 이력 항목]
{listing}

[채점 기준 — 100점 만점]
- 문항 적합성 40점: 이 문항이 묻는 것에 직접 답이 되는 경험인가.
- 회사·업계 부합 35점: 위 회사 리서치와 업계 가치에 비추어, 이 회사가
  특히 관심 있게 볼 만한 경험인가. 회사가 가는 방향과 맞닿아 있는가.
- 직무 역량 증명 25점: 지원 직무의 핵심 역량을 실제로 증명하는가.
  정량적 결과가 있으면 가산.

[판정 규칙]
- 지원자를 좋게 봐 주려 하지 말 것. 문항·회사와 무관한 경험은 과감히 낮은
  점수를 줄 것(그래야 자소서가 산만해지지 않는다).
- company_fit 은 "이 회사가 이 경험을 볼 이유"를 한 문장으로. 회사 리서치에
  없는 회사 정보를 지어내지 말 것. 근거가 없으면 직무·업계 기준으로 쓸 것.
- 이력에 없는 내용을 상상해서 채점하지 말 것. 적힌 사실만으로 판단한다.
- strategy 는 "선정된 경험들을 어떤 하나의 줄기로 엮을지"를 한 문장으로.
  (예: "데이터로 위험을 먼저 발견해 온 사람이라는 줄기로 학부 프로젝트에서
   인턴 실무까지 이어 붙인다")

[출력 — 반드시 아래 JSON 만 출력]
{{
  "strategy": "한 문장",
  "items": [
    {{"key": "pro1", "score": 0~100, "company_fit": "한 문장", "rationale": "한 문장"}}
  ]
}}
- items 에는 위 이력 항목 전부를 빠짐없이 포함할 것.
"""


# --------------------------------------------------------------------------
#  3-b) 결정적 폴백 스코어러 (LLM 실패 시)
# --------------------------------------------------------------------------
_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_NUMERIC = re.compile(r"\d+\s*(%|퍼센트|배|건|명|억|만|천|초|분|시간|일|개월|년)")

#  의미 없는 고빈도 토큰(불용어) — 겹쳐도 관련성의 증거가 못 된다
_STOPWORDS = {
    "그리고", "하지만", "그러나", "위해", "통해", "대한", "있는", "있습니다",
    "합니다", "했습니다", "지원", "회사", "경험", "활동", "확인", "불가",
    "기업", "우리", "자소서", "자기소개서", "대해", "가장", "매우", "다양한",
}


def _tokens(text: str) -> set[str]:
    return {
        t.lower() for t in _TOKEN.findall(text or "")
        if t.lower() not in _STOPWORDS
    }


def score_fallback(
    items: list[ExperienceItem],
    question: str,
    job_key: str,
    industry_key: str,
    company_research: str = "",
) -> tuple[list[ScoredExperience], str]:
    """LLM 채점이 실패했을 때 쓰는 키워드 겹침 기반 결정적 채점.

    회사 리서치 본문·직무 키워드·업계 어휘·문항 텍스트에서 키워드를 모아
    각 경험과의 겹침 정도로 점수를 낸다. LLM 만큼 정교하지는 않지만,
    '아무 경험이나 하나 고르는' 기존 동작보다는 훨씬 낫고 재현 가능하다.
    """
    profile = get_job_profile(job_key)
    ind = get_industry_profile(industry_key)

    # 가중치를 다르게 주기 위해 출처별로 키워드 집합을 분리한다
    q_kw = _tokens(question)
    company_kw = _tokens(company_research)
    job_kw = _tokens(
        " ".join(profile["keywords"] + profile["competencies"] + profile["hr_focus"])
    )
    ind_kw = _tokens(" ".join(ind["values"]) + " " + ind["vocabulary"])

    scored: list[ScoredExperience] = []
    for it in items:
        toks = _tokens(it.text)
        s = 0
        s += min(len(toks & q_kw), 4) * 10        # 문항 적합성 (최대 40)
        s += min(len(toks & company_kw), 5) * 7   # 회사 부합 (최대 35)
        s += min(len(toks & ind_kw), 3) * 5       # 업계 부합 (위와 합산해 35 근처)
        s += min(len(toks & job_kw), 5) * 5       # 직무 역량 (최대 25)
        if _NUMERIC.search(it.text):
            s += 12                                # 정량 성과 가산
        if it.field in ("experiences", "projects"):
            s += 8                                 # 실무성 가산
        score = max(0, min(100, s))

        scored.append(ScoredExperience(
            key=it.key, field=it.field, label=it.label, text=it.text,
            year=it.year, score=score,
            company_fit=(
                f"{ind['label']} 관점에서 {profile['label']} 직무의 "
                f"{profile['hr_focus'][0]}을(를) 보여줄 수 있는 이력"
            ),
            rationale="키워드 겹침 기반 자동 채점(LLM 판정 실패 폴백).",
        ))
    strategy = (
        f"{profile['label']} 직무에서 {profile['hr_focus'][0]}을(를) 증명하는 "
        f"흐름으로, 선정된 경험을 시간 순으로 엮는다."
    )
    return scored, strategy


# --------------------------------------------------------------------------
#  3-c) LLM 채점 실행
# --------------------------------------------------------------------------
def score_with_llm(
    client: GeminiClient,
    items: list[ExperienceItem],
    question: str,
    job_key: str,
    industry_key: str,
    company_research: str = "",
    company_name: str = "",
    target_job: str = "",
) -> tuple[list[ScoredExperience], str] | None:
    """LLM 으로 이력 항목을 채점한다. 실패하면 None 을 돌려준다."""
    prompt = build_ranking_prompt(
        items=items, question=question, job_key=job_key,
        industry_key=industry_key, company_research=company_research,
        company_name=company_name, target_job=target_job,
    )
    try:
        raw = client.generate(prompt, config.VERIFICATION_CONFIG)
    except Exception:
        return None

    parsed = pb.safe_parse_json(raw)
    if not parsed or not isinstance(parsed.get("items"), list):
        return None

    by_key = {it.key: it for it in items}
    result: dict[str, ScoredExperience] = {}
    for row in parsed["items"]:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "")).strip()
        src = by_key.get(key)
        if src is None:
            continue
        try:
            score = int(float(row.get("score", 0)))
        except (TypeError, ValueError):
            score = 0
        result[key] = ScoredExperience(
            key=src.key, field=src.field, label=src.label, text=src.text,
            year=src.year, score=max(0, min(100, score)),
            company_fit=str(row.get("company_fit", "") or "").strip(),
            rationale=str(row.get("rationale", "") or "").strip(),
        )

    if not result:
        return None

    # 모델이 빠뜨린 항목은 0점으로 채워 넣어 목록을 완전하게 유지한다
    for it in items:
        if it.key not in result:
            result[it.key] = ScoredExperience(
                key=it.key, field=it.field, label=it.label, text=it.text,
                year=it.year, score=0,
                rationale="채점 응답에서 누락된 항목.",
            )

    strategy = str(parsed.get("strategy", "") or "").strip()
    return list(result.values()), strategy


# --------------------------------------------------------------------------
#  4) 통합: 채점 → 역할 배정 → 시간순 배치
# --------------------------------------------------------------------------
def select_experiences(
    client: GeminiClient,
    user: UserProfile,
    question: str = "",
    job_key: str = "general",
    industry: str = "",
    company_research: str = "",
    max_chars: int = 1000,
    max_core: int | None = None,
    max_supporting: int | None = None,
) -> ExperienceSelection:
    """이 문항에 쓸 경험을 고르고 시간 순으로 배치한 결과를 돌려준다.

    max_core / max_supporting 을 주지 않으면 max_chars 에서 자동 산정한다.
    이력 항목이 하나도 없으면 빈 Selection 을 돌려주며, 이 경우 집필
    프롬프트는 기존과 동일하게(선별 블록 없이) 동작한다.
    """
    items = flatten_experiences(user)
    if not items:
        return ExperienceSelection()

    industry_key = industry or infer_industry(user.target_company, user.target_job)

    plan_core, plan_supporting = plan_capacity(max_chars)
    n_core = plan_core if max_core is None else max(0, int(max_core))
    n_supporting = plan_supporting if max_supporting is None else max(0, int(max_supporting))

    fallback_used = False
    outcome = score_with_llm(
        client=client, items=items, question=question, job_key=job_key,
        industry_key=industry_key, company_research=company_research,
        company_name=user.target_company, target_job=user.target_job,
    )
    if outcome is None:
        outcome = score_fallback(
            items=items, question=question, job_key=job_key,
            industry_key=industry_key, company_research=company_research,
        )
        fallback_used = True

    scored, strategy = outcome

    # 점수 내림차순 → 동점이면 최신 경험 우선(연도 내림차순)
    ranked = sorted(scored, key=lambda e: (-e.score, -e.year))

    chosen: list[ScoredExperience] = []
    for i, e in enumerate(ranked):
        if i < n_core:
            e.role = "core"
            chosen.append(e)
        elif len(chosen) < n_core + n_supporting and e.score >= MIN_SUPPORTING_SCORE:
            e.role = "supporting"
            chosen.append(e)
        else:
            e.role = "excluded"

    # 채택분이 하나도 없으면(전부 저점) 최소한 최고점 1건은 핵심으로 살린다
    if not chosen and ranked:
        ranked[0].role = "core"
        chosen = [ranked[0]]

    # 배치 제약: 채택이 끝난 뒤에만 시간 순으로 늘어놓는다.
    # (선별·비중은 위 점수 단계에서 이미 확정됐고, 여기서는 바뀌지 않는다.
    #  role 은 그대로 유지되므로 핵심 축이 목록 중간이나 끝에 놓일 수 있으며
    #  그것이 정상이다 — 프롬프트가 위치와 비중을 구분하도록 지시한다.)
    ordered = sorted(chosen, key=lambda e: (e.year, -e.score))
    excluded = [e for e in ranked if e.role == "excluded"]

    return ExperienceSelection(
        strategy=strategy,
        ordered=ordered,
        excluded=excluded,
        fallback_used=fallback_used,
    )
