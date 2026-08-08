"""
core/pipeline.py
============================================================================
전체 오케스트레이션.

★ 이 서비스의 정체성: "자소서를 대신 써 주는" 생성 서비스.
  주 결과물은 문항별 '완성형 자소서'이며, 나머지(작성 가이드, 액션플랜)는
  사용자가 그 완성본을 잘 활용하도록 돕는 부속물이다.

generate_application() 하나만 호출하면:
  0) 지원 회사 리서치(Google 검색) — 회사 가치를 글에 은은하게 반영
  1) 모범 자소서(레퍼런스)에서 문체 예시 선별
  2) 문항별로: 완성형 자소서 생성 → 근거 검증(환각 탐지)/교정 → 최종 다듬기
  3) 문항별 '이 자소서를 내 것으로 만드는 가이드' 생성
  4) (부가) HR 관점 액션플랜
  을 모두 수행하고 ApplicationResult 로 반환한다.
"""

from __future__ import annotations

import re
from typing import Any

from .data_models import (
    UserProfile, GenerationRequest, AnswerResult, ApplicationResult,
)
from .gemini_client import GeminiClient
from .reference_store import ReferenceStore
from . import generator, writing_guide, action_plan, prompt_builder
from .job_profiles import (
    get_job_profile, normalize_job_key, get_industry_profile, infer_industry,
)


def generate_application(
    client: GeminiClient,
    user: UserProfile,
    job_key: str = "general",
    region: str = "KR",
    questions: list[dict[str, Any]] | None = None,
    tone: str = "",
    store: ReferenceStore | None = None,
    num_style_examples: int = 3,
    reference_max_chars_each: int = 1400,
    use_company_research: bool = True,
    include_writing_guide: bool = True,
    include_action_plan: bool = True,
    max_grounding_iterations: int = 2,
    polish: bool = True,
    industry: str = "",
) -> ApplicationResult:
    """
    지원서 전체(여러 문항)의 완성형 자소서를 생성한다.

    client               : GeminiClient (API 키/모델 주입됨)
    user                 : 사용자 사실 데이터 (자소서 내용의 유일한 출처)
    questions            : 문항 목록. 각 항목은 {"question": str, "max_chars": int}.
                           비어 있으면 자유 형식 1건을 생성한다.
    store                : ReferenceStore (모범 자소서 DB). None 이면 예시 없이 진행.
    use_company_research : True 면 user.target_company 를 Google 검색으로 조사해
                           회사 가치/지향점을 글에 은은하게 반영한다.
    industry             : 업계 key("finance"/"it"/"manufacturing"/"public"/
                           "consulting"/"commerce"/"bio"). 비우면 회사명·직무명에서
                           자동 추정한다. 업계별로 통하는 문체가 달라 결과 품질에
                           큰 영향을 준다.
    """
    if not questions:
        questions = [{"question": "", "max_chars": 1000}]

    # 업계 확정 (미지정이면 회사명/직무명에서 결정적으로 추정)
    industry_key = industry or infer_industry(user.target_company, user.target_job)

    # 지원 회사 리서치 (문항 전체에 공통 반영)
    company_research = ""
    if use_company_research and (user.target_company or "").strip():
        company_research = prompt_builder.strip_markdown(
            generator.research_company(client, user.target_company)
        )

    # 문체 예시 선별 (모든 문항에 공통 사용)
    examples = []
    if store is not None and len(store) > 0:
        examples = store.select_examples(
            job_key=job_key, region=region, k=num_style_examples,
            max_chars_each=reference_max_chars_each,
        )

    answers: list[AnswerResult] = []
    for q in questions:
        # 문항을 문자열("...")로 넣거나 {"question": "...", "max_chars": N}
        # 딕셔너리로 넣거나 둘 다 허용한다.
        if isinstance(q, str):
            question_text = q
            max_chars = 1000
        else:
            question_text = str(q.get("question", "") or "")
            max_chars = int(q.get("max_chars", 1000) or 0)

        req = GenerationRequest(
            user=user, job_key=job_key, region=region,
            question=question_text, max_chars=max_chars, tone=tone,
            industry=industry_key,
        )

        # 생성 → 근거검증/교정 → 최종 다듬기 = 완성형 자소서
        cover_letter, grounding = generator.generate_grounded_cover_letter(
            client=client, req=req, examples=examples,
            max_iterations=max_grounding_iterations, polish=polish,
            company_research=company_research,
        )

        answer = AnswerResult(
            question=question_text or "(자유 형식)",
            cover_letter=cover_letter,
            grounding=grounding,
        )

        # 이 자소서를 내 것으로 만드는 가이드
        if include_writing_guide:
            answer.writing_guide = writing_guide.build_writing_guide(
                client=client, cover_letter_text=cover_letter,
                question=question_text, user=user, job_key=job_key,
                industry=industry_key,
            )

        answers.append(answer)

    result = ApplicationResult(answers=answers, company_research=company_research)

    # (부가) HR 관점 액션플랜 — 다음 지원까지 이력을 보강하는 제안
    if include_action_plan:
        result.action_plan = action_plan.suggest_action_plan(
            client=client, user=user, job_key=job_key, industry=industry_key,
        )

    profile = get_job_profile(job_key)
    industry_profile = get_industry_profile(industry_key)
    result.meta = {
        "job_key": normalize_job_key(job_key),
        "job_label": profile["label"],
        "industry_key": industry_profile["key"],
        "industry_label": industry_profile["label"],
        "region": (region or "KR").upper(),
        "num_questions": len(answers),
        "num_style_examples": len(examples),
        "company_research_used": bool(company_research),
        "all_grounded": all(a.grounding.grounded for a in answers),
    }
    return result


# --------------------------------------------------------------------------
#  결과 출력 헬퍼 — 완성형 자소서가 주인공이 되도록 구성
# --------------------------------------------------------------------------
def format_application(result: ApplicationResult) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(
        f" AI 자기소개서 생성 결과 | 직무: {result.meta.get('job_label')}"
        f" / 업계: {result.meta.get('industry_label')}"
        f" / 지역: {result.meta.get('region')}"
        f" | 문항 {result.meta.get('num_questions')}개"
    )
    if result.meta.get("company_research_used"):
        lines.append("  ▸ 지원 회사 리서치가 글의 방향에 은은하게 반영되었습니다.")
    lines.append("=" * 70)

    for i, ans in enumerate(result.answers, 1):
        lines.append(f"\n【문항 {i}】 {ans.question}")
        lines.append("-" * 70)
        lines.append(ans.cover_letter)
        lines.append("")

        g = ans.grounding
        if g.grounded:
            lines.append("  ▸ 근거 검증: 통과 ✅ — 사용자 데이터에 없는 내용이 발견되지 않았습니다.")
        else:
            lines.append("  ▸ 근거 검증: 확인 필요 ⚠️")
            for c in g.unsupported_claims:
                lines.append(f"      · {c}")
            if g.notes:
                lines.append(f"      ({g.notes})")

        if ans.writing_guide:
            lines.append("")
            lines.append("  ── 이 자소서를 내 것으로 만드는 가이드 ──")
            lines.append(ans.writing_guide)

    if result.company_research:
        lines.append("\n" + "=" * 70)
        lines.append("■ (참고) 지원 회사 리서치 요약 — 글에는 은은하게만 반영됨")
        lines.append("-" * 70)
        lines.append(result.company_research)

    if result.action_plan:
        lines.append("\n" + "=" * 70)
        lines.append("■ (부가) HR 관점 커리어 액션플랜 — 다음 지원까지 준비하면 좋은 것")
        lines.append("-" * 70)
        lines.append(result.action_plan)

    lines.append("=" * 70)
    return "\n".join(lines)


# --------------------------------------------------------------------------
#  프론트엔드 연동용 출력 헬퍼
#    - split_into_sentences() : 자소서 본문을 '문장 단위'로 분해(편집 UI용)
#    - result_to_json()       : ApplicationResult 를 JSON 직렬화 가능한 dict 로
# --------------------------------------------------------------------------
def split_into_sentences(text: str) -> list[dict[str, Any]]:
    """자소서 본문을 문장 단위로 분해한다 (프론트 문장별 편집/하이라이트용).

    각 문장은 {"id", "paragraph", "text", "needs_input"} 형태.
    ※ 한국어 문장 분리는 best-effort(종결부호 . ! ? + 개행 기준)입니다.
    """
    sentences: list[dict[str, Any]] = []
    idx = 0
    for para_idx, para in enumerate((text or "").split("\n")):
        if not para.strip():
            continue
        parts = re.split(r"(?<=[.!?])\s+", para.strip())
        for p in parts:
            p = p.strip()
            if not p:
                continue
            idx += 1
            sentences.append({
                "id": f"s{idx}",
                "paragraph": para_idx,
                "text": p,
                "needs_input": ("[보완필요" in p),
            })
    return sentences


def result_to_json(result: ApplicationResult) -> dict[str, Any]:
    """ApplicationResult 를 프론트엔드/ API 용 JSON 직렬화 가능한 dict 로 변환.

    문항별로 char_count / char_count_no_space / sentences / grounding /
    writing_guide 를 포함한다. (구조는 프로젝트 문서 참고)
    """
    answers = []
    for i, ans in enumerate(result.answers, 1):
        text = ans.cover_letter or ""
        sentences = split_into_sentences(text)
        answers.append({
            "index": i,
            "question": ans.question,
            "cover_letter": text,
            "char_count": len(text),
            "char_count_no_space": len(text.replace(" ", "").replace("\n", "")),
            "sentences": sentences,
            "needs_input": any(s["needs_input"] for s in sentences),
            "grounding": {
                "grounded": bool(ans.grounding.grounded),
                "unsupported_claims": list(ans.grounding.unsupported_claims or []),
                "notes": ans.grounding.notes or "",
            },
            "writing_guide": ans.writing_guide or "",
        })
    return {
        "meta": dict(result.meta or {}),
        "company_research": result.company_research or "",
        "action_plan": result.action_plan or "",
        "answers": answers,
    }
