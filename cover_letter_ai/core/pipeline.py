"""
core/pipeline.py
============================================================================
전체 오케스트레이션.

generate_cover_letter_package() 하나만 호출하면:
  1) 모범 자소서(레퍼런스)에서 문체 예시 선별
  2) 사용자 사실 기반으로 자소서 생성
  3) 근거 검증(환각 탐지) + 자동 교정
  4) 직무 맞춤 수정 제안
  5) HR 관점 액션플랜
  을 모두 수행하고 CoverLetterResult 로 반환한다.
"""

from __future__ import annotations

from .data_models import GenerationRequest, CoverLetterResult
from .gemini_client import GeminiClient
from .reference_store import ReferenceStore
from . import generator, reviewer, action_plan
from .job_profiles import get_job_profile, normalize_job_key


def generate_cover_letter_package(
    client: GeminiClient,
    req: GenerationRequest,
    store: ReferenceStore | None = None,
    num_style_examples: int = 3,
    include_revision: bool = True,
    include_action_plan: bool = True,
    max_grounding_iterations: int = 2,
) -> CoverLetterResult:
    """
    자소서 생성 + 검증 + 제안 + 액션플랜을 한 번에 수행.

    client : GeminiClient (API 키/모델 주입됨)
    req    : GenerationRequest (사용자 데이터/직무/지역/문항 등)
    store  : ReferenceStore (모범 자소서 DB). None 이면 예시 없이 진행.
    """
    # 1) 문체 예시 선별
    examples = []
    if store is not None and len(store) > 0:
        examples = store.select_examples(
            job_key=req.job_key, region=req.region, k=num_style_examples,
        )

    # 2~3) 근거 기반 자소서 생성 + 환각 검증/교정
    cover_letter, grounding = generator.generate_grounded_cover_letter(
        client=client, req=req, examples=examples,
        max_iterations=max_grounding_iterations,
    )

    result = CoverLetterResult(
        cover_letter=cover_letter,
        grounding=grounding,
    )

    # 4) 직무 맞춤 수정 제안
    if include_revision:
        result.revision_suggestions = reviewer.suggest_revisions_for_job(
            client=client, cover_letter_text=cover_letter,
            target_job_key=req.job_key, region=req.region, user=req.user,
        )

    # 5) HR 관점 액션플랜
    if include_action_plan:
        result.action_plan = action_plan.suggest_action_plan(
            client=client, user=req.user, job_key=req.job_key,
        )

    profile = get_job_profile(req.job_key)
    result.meta = {
        "job_key": normalize_job_key(req.job_key),
        "job_label": profile["label"],
        "region": req.region.upper(),
        "num_style_examples": len(examples),
        "grounded": grounding.grounded,
    }
    return result


# --------------------------------------------------------------------------
#  결과 예쁘게 출력하는 헬퍼(콘솔용)
# --------------------------------------------------------------------------
def format_result(result: CoverLetterResult) -> str:
    g = result.grounding
    lines = []
    lines.append("=" * 70)
    lines.append(f" 직무: {result.meta.get('job_label')} / 지역: {result.meta.get('region')}")
    lines.append("=" * 70)
    lines.append("\n■ 생성된 자기소개서\n")
    lines.append(result.cover_letter)
    lines.append("\n" + "-" * 70)
    lines.append("■ 근거 검증(환각 탐지) 결과")
    lines.append(f"  - 전부 사실 기반인가: {'예 ✅' if g.grounded else '아니오 ⚠️'}")
    if g.unsupported_claims:
        lines.append("  - 근거 없는(의심) 문장:")
        for c in g.unsupported_claims:
            lines.append(f"      · {c}")
    if g.notes:
        lines.append(f"  - 총평: {g.notes}")

    if result.revision_suggestions:
        lines.append("\n" + "-" * 70)
        lines.append("■ 직무 맞춤 수정 제안\n")
        lines.append(result.revision_suggestions)

    if result.action_plan:
        lines.append("\n" + "-" * 70)
        lines.append("■ HR 관점 액션플랜\n")
        lines.append(result.action_plan)

    lines.append("=" * 70)
    return "\n".join(lines)
