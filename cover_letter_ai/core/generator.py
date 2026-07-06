"""
core/generator.py
============================================================================
자소서 '생성' + '근거 검증(환각 탐지)' + '자동 교정' + '최종 다듬기' 로직.

흐름 (★ 완성형 자소서를 만들어내는 것이 목표):
  0) research_company()    : Google 검색 그라운딩으로 지원 회사 가치 리서치
  1) generate_draft()      : 사용자 사실 + 직무 스타일 + 회사 방향으로 집필
  2) verify_grounding()    : 근거 없는 주장(환각)이 있는지 검사
  3) correct_draft()       : 근거 없는 문장을 제거/수정 (필요시 반복)
  4) polish_draft()        : 어미·반복·맞춤법 최종 다듬기 → 제출 가능한 완성본
  → generate_grounded_cover_letter() 가 위 1~4 과정을 자동 수행
"""

from __future__ import annotations

from .. import config
from .data_models import (
    UserProfile, ReferenceExample, GroundingReport, GenerationRequest,
)
from .gemini_client import GeminiClient
from . import prompt_builder as pb


# --------------------------------------------------------------------------
#  0) 지원 회사 리서치 — Google 검색 그라운딩으로 가치/지향점 조사
# --------------------------------------------------------------------------
def research_company(client: GeminiClient, company_name: str) -> str:
    """지원 회사의 미션/가치/인재상을 검색으로 조사해 요약 반환.

    결과는 자소서에 '노골적 인용 없이 은은하게만' 반영되도록
    프롬프트(build_company_block)에서 제어된다.
    """
    name = (company_name or "").strip()
    if not name:
        return ""
    prompt = pb.build_company_research_prompt(name)
    try:
        return client.generate_with_search(prompt)
    except Exception:
        return ""


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
    company_research: str = "",
) -> str:
    prompt = pb.build_generation_prompt(
        user=user, job_key=job_key, region=region, question=question,
        examples=examples, max_chars=max_chars, tone=tone,
        company_research=company_research,
    )
    return client.generate(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  2) 근거 검증 (환각 탐지) — 제1원칙의 핵심 안전장치
# --------------------------------------------------------------------------
def verify_grounding(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
    company_research: str = "",
) -> GroundingReport:
    prompt = pb.build_verification_prompt(generated_text, user, company_research)
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
    company_research: str = "",
) -> str:
    prompt = pb.build_correction_prompt(
        generated_text, user, unsupported_claims, company_research)
    return client.generate(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  4) 최종 다듬기 — 어미·반복·맞춤법을 제출본 수준으로 (제2원칙의 마무리)
# --------------------------------------------------------------------------
def polish_draft(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
    max_chars: int = 1000,
) -> str:
    prompt = pb.build_polish_prompt(generated_text, user, max_chars)
    return client.generate(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  통합: 생성 → 검증/교정 반복 → 최종 다듬기 = 제출 가능한 완성형 자소서
# --------------------------------------------------------------------------
def generate_grounded_cover_letter(
    client: GeminiClient,
    req: GenerationRequest,
    examples: list[ReferenceExample],
    max_iterations: int = 2,
    polish: bool = True,
    company_research: str = "",
) -> tuple[str, GroundingReport]:
    """
    (완성형 자소서 본문, 최종 근거검증 리포트) 반환.

    max_iterations   : 검증→교정 재시도 최대 횟수.
    polish           : True 면 마지막에 어미·반복·맞춤법 최종 다듬기 수행.
    company_research : research_company() 결과. 있으면 글의 방향에 은은하게 반영.
    """
    if req.user.is_empty():
        raise ValueError(
            "사용자 데이터(UserProfile)가 비어 있습니다. "
            "환각 방지를 위해 최소 1개 이상의 사실을 입력해야 합니다."
        )

    text = generate_draft(
        client=client, user=req.user, job_key=req.job_key, region=req.region,
        question=req.question, examples=examples, max_chars=req.max_chars,
        tone=req.tone, company_research=company_research,
    )
    report = verify_grounding(client, text, req.user, company_research)

    iterations = 0
    while (not report.grounded) and report.unsupported_claims and iterations < max_iterations:
        text = correct_draft(client, text, req.user, report.unsupported_claims,
                             company_research)
        report = verify_grounding(client, text, req.user, company_research)
        iterations += 1

    if polish:
        text = polish_draft(client, text, req.user, req.max_chars)

    report.notes = (report.notes + f" (교정 반복 {iterations}회)").strip()
    return text, report
