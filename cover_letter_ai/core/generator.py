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
    industry: str = "",
    selection=None,
    common_material: str = "",
) -> str:
    prompt = pb.build_generation_prompt(
        user=user, job_key=job_key, region=region, question=question,
        examples=examples, max_chars=max_chars, tone=tone,
        company_research=company_research, industry=industry,
        selection=selection, common_material=common_material,
    )
    # generate_complete: 토큰 한도로 잘리면 자동으로 이어써서 끝까지 받아온다.
    return client.generate_complete(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  1-1) 완결성 검사 + 보완 — "어이없게 끝나는" 글을 막는 안전장치
# --------------------------------------------------------------------------
#  종결부호 없이 조사/어미 중간에서 끝나거나(잘림), 목표 분량에 크게 못 미치면
#  글이 부자연스럽게 끝난 것으로 보고 한 번 더 다듬어 완결시킨다.
# --------------------------------------------------------------------------
_SENTENCE_END = ("다.", "요.", "음.", "됨.", "함.", ".", "!", "?", "]", "”", "\"")

#  목표 글자수 대비 이 비율 미만이면 '너무 짧게 끝났다'고 판단
MIN_LENGTH_RATIO = 0.75

#  목표 글자수 대비 이 비율을 넘으면 '분량 초과'로 판단해 줄인다.
#  자소서 문항의 글자수 제한은 대부분 하드 제한(초과분은 잘리거나 감점)이라,
#  넘치는 것은 모자란 것보다 위험하다. 경험을 여러 건 엮게 되면서 분량이
#  쉽게 부풀 수 있어(1000자 문항에 1970자가 나온 사례) 상한 검사를 둔다.
MAX_LENGTH_RATIO = 1.15


def looks_truncated(text: str) -> bool:
    """문장이 끝맺지 못한 채 끊겼는지 판별한다."""
    t = (text or "").strip()
    if not t:
        return True
    return not t.endswith(_SENTENCE_END)


def looks_too_short(text: str, max_chars: int) -> bool:
    """목표 분량에 크게 못 미치는지 판별한다(max_chars=0이면 검사 안 함)."""
    if not max_chars:
        return False
    return len((text or "").strip()) < int(max_chars * MIN_LENGTH_RATIO)


def looks_too_long(text: str, max_chars: int) -> bool:
    """목표 분량을 크게 넘겼는지 판별한다(max_chars=0이면 검사 안 함)."""
    if not max_chars:
        return False
    return len((text or "").strip()) > int(max_chars * MAX_LENGTH_RATIO)


def complete_draft(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
    max_chars: int = 1000,
    question: str = "",
    reason: str = "",
    selection=None,
) -> str:
    """끊기거나 너무 짧은 글을 '완결된 한 편'으로 마무리시킨다.

    새로운 사실을 추가하지 않고, 이미 원장에 있는 사실을 더 깊게 풀어
    쓰는 방식으로만 채운다(제1원칙 유지).
    """
    prompt = pb.build_completion_prompt(
        generated_text=generated_text, user=user,
        max_chars=max_chars, question=question, reason=reason,
        selection=selection,
    )
    return client.generate_complete(prompt, config.GENERATION_CONFIG)


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
    selection=None,
) -> str:
    prompt = pb.build_correction_prompt(
        generated_text, user, unsupported_claims, company_research,
        selection=selection)
    return client.generate(prompt, config.GENERATION_CONFIG)


# --------------------------------------------------------------------------
#  4) 최종 다듬기 — 어미·반복·맞춤법을 제출본 수준으로 (제2원칙의 마무리)
# --------------------------------------------------------------------------
def trim_draft(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
    max_chars: int,
    selection=None,
) -> str:
    """분량을 초과한 글을 목표 글자수에 맞게 압축한다.

    보조 경험의 세부 묘사와 수식어부터 깎고, 핵심 축과 마무리 문단은
    지키도록 프롬프트로 통제한다.
    """
    prompt = pb.build_trim_prompt(generated_text, user, max_chars,
                                  selection=selection)
    return client.generate(prompt, config.GENERATION_CONFIG)


def polish_draft(
    client: GeminiClient,
    generated_text: str,
    user: UserProfile,
    max_chars: int = 1000,
    selection=None,
) -> str:
    prompt = pb.build_polish_prompt(generated_text, user, max_chars,
                                    selection=selection)
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
    common_material: str = "",
) -> tuple[str, GroundingReport]:
    """
    (완성형 자소서 본문, 최종 근거검증 리포트) 반환.

    max_iterations   : 검증→교정 재시도 최대 횟수.
    polish           : True 면 마지막에 어미·반복·맞춤법 최종 다듬기 수행.
    company_research : research_company() 결과. 있으면 글의 방향에 은은하게 반영.
    common_material  : 채점 대상이 아닌 공통 재료(학력/기술/자격증/정량성과/강점).

    req.selection 이 있으면 그 경험들만, 제시된 시간 순서대로 서술하도록
    집필·교정·다듬기 전 단계에 일관되게 전달한다.
    """
    if req.user.is_empty():
        raise ValueError(
            "사용자 데이터(UserProfile)가 비어 있습니다. "
            "환각 방지를 위해 최소 1개 이상의 사실을 입력해야 합니다."
        )

    selection = req.selection

    text = generate_draft(
        client=client, user=req.user, job_key=req.job_key, region=req.region,
        question=req.question, examples=examples, max_chars=req.max_chars,
        tone=req.tone, company_research=company_research, industry=req.industry,
        selection=selection, common_material=common_material,
    )
    report = verify_grounding(client, text, req.user, company_research)

    iterations = 0
    while (not report.grounded) and report.unsupported_claims and iterations < max_iterations:
        text = correct_draft(client, text, req.user, report.unsupported_claims,
                             company_research, selection=selection)
        report = verify_grounding(client, text, req.user, company_research)
        iterations += 1

    if polish:
        text = polish_draft(client, text, req.user, req.max_chars,
                            selection=selection)

    # ---- 완결성 보정 -------------------------------------------------
    # 교정 과정에서 문장이 깎여 나가거나 토큰 한도로 잘려 '어이없게 끝나는'
    # 결과를 막는다. 문제가 있을 때만 1회 보완한다(불필요한 호출 방지).
    completion_note = ""
    truncated = looks_truncated(text)
    too_short = looks_too_short(text, req.max_chars)
    if truncated or too_short:
        reason = (
            "문장이 끝맺지 못한 채 중간에서 끊겼습니다."
            if truncated else
            f"목표 분량({req.max_chars}자)에 크게 못 미치는 {len(text.strip())}자로 짧게 끝났습니다."
        )
        repaired = complete_draft(
            client=client, generated_text=text, user=req.user,
            max_chars=req.max_chars, question=req.question, reason=reason,
            selection=selection,
        )
        if repaired and len(repaired.strip()) >= len(text.strip()) * 0.8:
            text = repaired

        # 보완 후에도 분량이 크게 모자라면, 억지로 늘리는 대신
        # '경험 데이터가 부족하다'는 사실을 사용자에게 알린다.
        if looks_too_short(text, req.max_chars):
            completion_note = (
                f" 관련 경험 데이터가 부족해 목표 분량({req.max_chars}자)을 채우지 "
                f"못했습니다(현재 {len(text.strip())}자). 이 문항과 연관된 경험을 "
                f"더 입력하면 글이 깊어집니다."
            )

    # ---- 분량 초과 보정 -----------------------------------------------
    # 자소서 문항의 글자수 제한은 대부분 하드 제한이라, 넘치는 것은 모자란
    # 것보다 위험하다(초과분이 잘리거나 감점). 여러 경험을 엮게 되면서
    # 분량이 부풀기 쉬워졌으므로 상한을 넘으면 압축 패스를 태운다.
    # 압축 결과가 오히려 더 길거나 마무리를 잃었다면 원문을 유지한다.
    if looks_too_long(text, req.max_chars):
        before = len(text.strip())
        trimmed = trim_draft(client, text, req.user, req.max_chars,
                             selection=selection)
        trimmed_clean = (trimmed or "").strip()
        if (
            trimmed_clean
            and len(trimmed_clean) < before
            and not looks_truncated(trimmed_clean)
            and not looks_too_short(trimmed_clean, req.max_chars)
        ):
            text = trimmed_clean
        if looks_too_long(text, req.max_chars):
            completion_note += (
                f" 목표 분량({req.max_chars}자)을 넘긴 {len(text.strip())}자로 "
                f"생성되었습니다. 제출 전 직접 줄이거나, 반영할 경험 수를 "
                f"max_supporting_experiences 로 줄여 보세요."
            )

    # 마크다운 잔여 기호 제거(프롬프트로 금지했지만 이중 안전장치)
    text = pb.strip_markdown(text)

    report.notes = (report.notes + f" (교정 반복 {iterations}회)" + completion_note).strip()
    return text, report
