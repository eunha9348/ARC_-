"""
core/pipeline.py
============================================================================
전체 오케스트레이션.

★ 이 서비스의 정체성: "자소서를 대신 써 주는" 생성 서비스.
  주 결과물은 문항별 '완성형 자소서'이며, 나머지(작성 가이드, 액션플랜)는
  사용자가 그 완성본을 잘 활용하도록 돕는 부속물이다.

generate_application() 하나만 호출하면:
  1) 모범 자소서(레퍼런스)에서 문체 예시 선별
  2) 문항별로: 완성형 자소서 생성 → 근거 검증(환각 탐지)/교정 → 최종 다듬기
  3) 문항별 '이 자소서를 내 것으로 만드는 가이드' 생성
  4) (부가) HR 관점 액션플랜
  을 모두 수행하고 ApplicationResult 로 반환한다.
"""

from __future__ import annotations

from typing import Any

from .data_models import (
    UserProfile, GenerationRequest, AnswerResult, ApplicationResult,
)
from .gemini_client import GeminiClient
from .reference_store import ReferenceStore
from . import generator, writing_guide, action_plan
from .job_profiles import get_job_profile, normalize_job_key


def generate_application(
    client: GeminiClient,
    user: UserProfile,
    job_key: str = "general",
    region: str = "KR",
    questions: list[dict[str, Any]] | None = None,
    tone: str = "",
    store: ReferenceStore | None = None,
    num_style_examples: int = 3,
    include_writing_guide: bool = True,
    include_action_plan: bool = True,
    max_grounding_iterations: int = 2,
    polish: bool = True,
) -> ApplicationResult:
    """
    지원서 전체(여러 문항)의 완성형 자소서를 생성한다.

    client    : GeminiClient (API 키/모델 주입됨)
    user      : 사용자 사실 데이터 (자소서 내용의 유일한 출처)
    questions : 문항 목록. 각 항목은 {"question": str, "max_chars": int}.
                비어 있으면 자유 형식 1건을 생성한다.
    store     : ReferenceStore (모범 자소서 DB). None 이면 예시 없이 진행.
    """
    if not questions:
        questions = [{"question": "", "max_chars": 1000}]

    # 문체 예시 선별 (모든 문항에 공통 사용)
    examples = []
    if store is not None and len(store) > 0:
        examples = store.select_examples(
            job_key=job_key, region=region, k=num_style_examples,
        )

    answers: list[AnswerResult] = []
    for q in questions:
        question_text = str(q.get("question", "") or "")
        max_chars = int(q.get("max_chars", 1000) or 0)

        req = GenerationRequest(
            user=user, job_key=job_key, region=region,
            question=question_text, max_chars=max_chars, tone=tone,
        )

        # 생성 → 근거검증/교정 → 최종 다듬기 = 완성형 자소서
        cover_letter, grounding = generator.generate_grounded_cover_letter(
            client=client, req=req, examples=examples,
            max_iterations=max_grounding_iterations, polish=polish,
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
            )

        answers.append(answer)

    result = ApplicationResult(answers=answers)

    # (부가) HR 관점 액션플랜 — 다음 지원까지 이력을 보강하는 제안
    if include_action_plan:
        result.action_plan = action_plan.suggest_action_plan(
            client=client, user=user, job_key=job_key,
        )

    profile = get_job_profile(job_key)
    result.meta = {
        "job_key": normalize_job_key(job_key),
        "job_label": profile["label"],
        "region": (region or "KR").upper(),
        "num_questions": len(answers),
        "num_style_examples": len(examples),
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
        f" / 지역: {result.meta.get('region')}"
        f" | 문항 {result.meta.get('num_questions')}개"
    )
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

    if result.action_plan:
        lines.append("\n" + "=" * 70)
        lines.append("■ (부가) HR 관점 커리어 액션플랜 — 다음 지원까지 준비하면 좋은 것")
        lines.append("-" * 70)
        lines.append(result.action_plan)

    lines.append("=" * 70)
    return "\n".join(lines)
