"""
core/generator.py
============================================================================
자소서 '생성' + '근거 검증(환각 탐지)' + '자동 교정' 로직.

흐름:
  1) generate_draft()      : 사용자 사실 + 직무 스타일로 초안 생성
  2) verify_grounding()    : 초안에 근거 없는 주장(환각)이 있는지 검사
  3) correct_draft()       : 근거 없는 문장을 제거/수정
  → generate_grounded_cover_letter() 가 위 과정을 자동 반복(최대 N회)
"""

from __future__ import annotations

from .. import config
from .data_models import (
    UserProfile, ReferenceExample, GroundingReport, GenerationRequest,
)
from .gemini_client import GeminiClient
from . import prompt_builder as pb


# --------------------------------------------------------------------------
#  1) 초안 생성
# --------------------------------------------------------------------------
def generate_draft(
    client: GeminiClient,
    user: UserProfile,
    job_key: str,
    region: str,
    question: str,
    examples: list[ReferenceExample],
    max_chars: int = 1000,
    tone: str = "",
) -> str:
    prompt = pb.build_generation_prompt(
        user=user, job_key=job_key, region=region, question=question,
        examples=examples, max_chars=max_chars, tone=tone,
    )
    return client.generate(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  2) 근거 검증 (환각 탐지) — 제1원칙의 핵심 안전장치
# --------------------------------------------------------------------------
def verify_grounding(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
) -> GroundingReport:
    prompt = pb.build_verification_prompt(generated_text, user)
    raw = client.generate(prompt, config.VERIFICATION_CONFIG)
    parsed = pb.safe_parse_json(raw)

    if not parsed:
        # 파싱 실패 시 보수적으로 '검증 불가'로 처리(사람 확인 유도)
        return GroundingReport(
            grounded=False,
            unsupported_claims=[],
            notes="검증 응답 파싱 실패 — 사람이 직접 사실 확인 권장.",
        )

    return GroundingReport(
        grounded=bool(parsed.get("grounded", False)),
        unsupported_claims=list(parsed.get("unsupported_claims", []) or []),
        notes=str(parsed.get("notes", "")),
    )


# --------------------------------------------------------------------------
#  3) 근거 없는 문장 교정
# --------------------------------------------------------------------------
def correct_draft(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
    unsupported_claims: list[str],
) -> str:
    prompt = pb.build_correction_prompt(generated_text, user, unsupported_claims)
    return client.generate(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  통합: 근거가 확보될 때까지 생성→검증→교정 반복
# --------------------------------------------------------------------------
def generate_grounded_cover_letter(
    client: GeminiClient,
    req: GenerationRequest,
    examples: list[ReferenceExample],
    max_iterations: int = 2,
) -> tuple[str, GroundingReport]:
    """
    (자소서 본문, 최종 근거검증 리포트) 반환.

    max_iterations: 검증→교정 재시도 최대 횟수.
    """
    if req.user.is_empty():
        raise ValueError(
            "사용자 데이터(UserProfile)가 비어 있습니다. "
            "환각 방지를 위해 최소 1개 이상의 사실을 입력해야 합니다."
        )

    text = generate_draft(
        client=client, user=req.user, job_key=req.job_key, region=req.region,
        question=req.question, examples=examples, max_chars=req.max_chars,
        tone=req.tone,
    )
    report = verify_grounding(client, text, req.user)

    iterations = 0
    while (not report.grounded) and report.unsupported_claims and iterations < max_iterations:
        text = correct_draft(client, text, req.user, report.unsupported_claims)
        report = verify_grounding(client, text, req.user)
        iterations += 1

    report.notes = (report.notes + f" (교정 반복 {iterations}회)").strip()
    return text, report
