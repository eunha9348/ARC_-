"""
core/prompt_builder.py
============================================================================
프롬프트 조립. 프로그램의 '두뇌'에 해당하며, 두 원칙을 프롬프트로 강제한다.

  제1원칙(환각 방지): 오직 '사용자 데이터'의 사실만 사용.
                      없는 사실은 만들지 않고, 필요하면 [보완필요] 로 표시.
  제2원칙(문체/맞춤법): 자소서 문체·맞춤법·문맥 자연스러움 확보.
  + 직무별 스타일/양식/HR 관점을 프롬프트에 주입.
"""

from __future__ import annotations

import json
from typing import Any

from .data_models import UserProfile, ReferenceExample
from .job_profiles import get_job_profile, get_region_style


# --------------------------------------------------------------------------
#  사용자 데이터 → "사실 원장(fact sheet)" 문자열
# --------------------------------------------------------------------------
def build_fact_sheet(user: UserProfile) -> str:
    """
    UserProfile 을 '사실 원장' 텍스트로 직렬화.
    이 원장이 자소서 내용의 유일한 근거이며, 근거 검증 때도 이걸 기준으로 판단한다.
    """
    data = user.to_dict()
    lines: list[str] = []
    label = {
        "name": "이름", "target_company": "지원회사", "target_job": "지원직무",
        "education": "학력", "experiences": "경력/인턴", "projects": "프로젝트",
        "skills": "보유역량/기술", "certifications": "자격증", "awards": "수상",
        "activities": "대외활동/동아리", "achievements": "정량성과",
        "strengths": "강점/성향", "motivation": "지원동기 메모",
        "career_goal": "입사후 포부", "extra_notes": "기타 메모",
    }
    for key, kor in label.items():
        val = data.get(key)
        if not val:
            continue
        if isinstance(val, list):
            rendered = []
            for item in val:
                if isinstance(item, dict):
                    rendered.append(", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    rendered.append(str(item))
            lines.append(f"- {kor}:")
            for r in rendered:
                lines.append(f"    · {r}")
        else:
            lines.append(f"- {kor}: {val}")
    return "\n".join(lines) if lines else "(제공된 사실 데이터 없음)"


# --------------------------------------------------------------------------
#  few-shot 스타일 예시 → 프롬프트 블록
# --------------------------------------------------------------------------
def build_style_examples_block(examples: list[ReferenceExample]) -> str:
    if not examples:
        return "(스타일 참고용 예시 없음 — 아래 직무 스타일 가이드만 따르세요.)"
    blocks = []
    for i, ex in enumerate(examples, 1):
        blocks.append(
            f"[스타일 예시 {i} | {ex.region} | {ex.job_key}]\n{ex.text}"
        )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
#  공통 시스템 규칙(두 원칙)
# --------------------------------------------------------------------------
ANTI_HALLUCINATION_RULES = """\
[절대 규칙 — 반드시 지킬 것]
1) (제1원칙) 아래 '사용자 사실 원장'에 있는 내용만 근거로 사용한다.
   - 원장에 없는 회사명, 수치, 경험, 자격, 기술, 직함을 새로 만들어내지 말 것.
   - 어떤 사실도 추측/과장/윤색하지 말 것. 특히 숫자는 원장에 있는 값만 사용.
   - 내용을 더 채우고 싶어도 근거가 없으면 만들지 말고, 그 자리에
     "[보완필요: 무엇이 필요한지]" 형태로 표시할 것.
   - '스타일 예시'의 문장/사실을 절대 그대로 가져오지 말 것(문체만 참고).
2) (제2원칙) 한국어 맞춤법·띄어쓰기·문맥을 자연스럽게. 자소서 특유의
   담백하고 신뢰감 있는 문어체를 사용하고, 문장 간 논리가 매끄럽게 이어질 것.
3) 진부한 상투어(예: "저는 어릴 적부터", "귀사의 무궁한 발전")는 지양하고,
   구체적 사실과 성과 중심으로 서술할 것.
"""


# --------------------------------------------------------------------------
#  자소서 생성 프롬프트
# --------------------------------------------------------------------------
def build_generation_prompt(
    user: UserProfile,
    job_key: str,
    region: str,
    question: str,
    examples: list[ReferenceExample],
    max_chars: int = 1000,
    tone: str = "",
) -> str:
    profile = get_job_profile(job_key)
    region_style = get_region_style(region)

    fact_sheet = build_fact_sheet(user)
    style_block = build_style_examples_block(examples)

    tone_line = tone.strip() or profile["tone"]
    length_line = (
        f"- 분량: 공백 포함 약 {max_chars}자 이내로 작성."
        if max_chars else "- 분량: 문항에 적절한 길이로 작성."
    )
    question_line = question.strip() or "자유 형식의 자기소개서(핵심 강점과 지원동기 중심)"

    prompt = f"""\
당신은 {region_style['label']} 작성을 돕는 전문 커리어 코치이자 교정 전문가입니다.
지원자의 사실 데이터만을 근거로, 직무에 최적화된 자기소개서를 작성하세요.

{ANTI_HALLUCINATION_RULES}

[지원 직무 프로필]
- 직무: {profile['label']} (key={profile['key']})
- 이 직무에서 인사팀이 중점적으로 보는 것: {", ".join(profile['hr_focus'])}
- 핵심 역량 키워드: {", ".join(profile['competencies'])}
- 권장 문체/톤: {tone_line}
- 권장 구성 흐름: {" → ".join(profile['structure'])}
- 자연스럽게 녹이면 좋은 키워드(단, 사실과 무관하면 억지로 넣지 말 것):
  {", ".join(profile['keywords'])}

[지역(문화) 스타일 가이드]
{region_style['guidance']}

[사용자 사실 원장 — 유일한 사실 출처]
{fact_sheet}

[문체 참고용 스타일 예시 — 내용 복붙 금지, 전개/톤만 참고]
{style_block}

[작성 요청]
- 자소서 문항: {question_line}
{length_line}
- 위 '권장 구성 흐름'을 기본 골격으로 하되, 문항 성격에 맞게 자연스럽게 조정.
- 두괄식으로 핵심을 먼저 제시하고, 사용자 원장의 구체적 경험/수치로 뒷받침.
- 마지막에 직무·회사와의 연결 및 기여 포부로 마무리.

[출력 형식]
- 완성된 자소서 본문만 출력(머리말/설명/사족 없이).
- 근거가 부족해 채우지 못한 부분은 문장 안에 "[보완필요: ...]"로만 표시.
"""
    return prompt


# --------------------------------------------------------------------------
#  근거 검증(환각 탐지) 프롬프트
# --------------------------------------------------------------------------
def build_verification_prompt(generated_text: str, user: UserProfile) -> str:
    fact_sheet = build_fact_sheet(user)
    return f"""\
당신은 자기소개서 팩트체커입니다. 아래 '사용자 사실 원장'에 근거가 없는
문장/주장(지어낸 회사·수치·경험·자격·기술 등)을 찾아내세요.

[사용자 사실 원장 — 유일하게 허용되는 사실]
{fact_sheet}

[검사할 자기소개서]
{generated_text}

[판정 규칙]
- 원장으로 뒷받침되지 않는 구체적 사실 주장만 문제 삼는다.
- 일반적 다짐/포부/의지 표현(구체 사실 아님)이나 "[보완필요:...]" 표시는 문제 아님.
- 원장 내용을 자연스럽게 바꿔 쓴 것은 문제 아님(의미가 같으면 OK).

[출력 — 반드시 아래 JSON 만 출력]
{{
  "grounded": true 또는 false,
  "unsupported_claims": ["문제 문장 1", "문제 문장 2"],
  "notes": "간단한 총평(한 문장)"
}}
"""


# --------------------------------------------------------------------------
#  교정/재작성 프롬프트 (근거 없는 문장 제거)
# --------------------------------------------------------------------------
def build_correction_prompt(
    generated_text: str,
    user: UserProfile,
    unsupported_claims: list[str],
) -> str:
    fact_sheet = build_fact_sheet(user)
    claims = "\n".join(f"- {c}" for c in unsupported_claims) or "- (없음)"
    return f"""\
아래 자기소개서에서 '근거 없는 문장'들을 제거하거나, 사실 원장에 맞게
고쳐 쓰세요. 새로운 사실을 추가하지 말고, 문맥이 매끄럽도록 다듬으세요.

[사용자 사실 원장 — 유일한 사실 출처]
{fact_sheet}

[제거/수정 대상(근거 없는 문장)]
{claims}

[원본 자기소개서]
{generated_text}

[요구사항]
- 근거 없는 사실은 삭제하거나, 원장에 있는 사실로 대체.
- 삭제로 빈 곳이 생기면 원장의 다른 사실로 자연스럽게 연결.
- 정 채울 근거가 없으면 "[보완필요: ...]"로 표시.
- 맞춤법·문맥·자소서 문체를 자연스럽게 유지.
- 완성된 본문만 출력.
"""


def safe_parse_json(text: str) -> dict[str, Any]:
    """
    모델이 준 응답에서 JSON 블록만 안전하게 파싱한다.
    코드펜스(```json ... ```)나 앞뒤 텍스트가 섞여 있어도 처리.
    """
    if not text:
        return {}
    t = text.strip()
    # 코드펜스 제거
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    # 가장 바깥 중괄호 범위 추출
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    try:
        return json.loads(t)
    except Exception:
        return {}
