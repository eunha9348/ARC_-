"""
core/reviewer.py
============================================================================
'직무별 맞춤 수정 제안' 파트.

기능:
  - 이미 작성된(또는 다른 직무용) 자소서를, 특정 직무에 맞게 고칠 때
    "어떤 부분을 어떻게 고치면 좋을지" 구체적으로 제안한다.
  - 사실을 새로 만들지 않고(제1원칙), '표현/강조/구조'의 개선안을 제시.
"""

from __future__ import annotations

from .. import config
from .data_models import UserProfile
from .gemini_client import GeminiClient
from .job_profiles import get_job_profile, get_region_style
from . import prompt_builder as pb


def build_revision_prompt(
    cover_letter_text: str,
    target_job_key: str,
    region: str,
    user: UserProfile,
) -> str:
    profile = get_job_profile(target_job_key)
    region_style = get_region_style(region)
    fact_sheet = pb.build_fact_sheet(user)

    return f"""\
당신은 자기소개서 첨삭 전문가입니다. 아래 자소서를 '{profile['label']}' 직무에
맞게 개선하기 위한 구체적 수정 제안을 작성하세요.

[중요 원칙]
- 없는 사실을 지어내라고 제안하지 말 것(사실은 아래 원장 범위 내에서만).
- '표현 방식, 강조점, 구조, 키워드 반영, 톤'을 어떻게 바꿀지 제안.
- 각 제안은 [현재 → 개선방향 → 이유] 형태로 근거를 붙일 것.

[목표 직무 특성]
- 인사팀 평가 포인트: {", ".join(profile['hr_focus'])}
- 핵심 역량: {", ".join(profile['competencies'])}
- 권장 톤/구성: {profile['tone']} / {" → ".join(profile['structure'])}
- 선호 키워드: {", ".join(profile['keywords'])}

[지역 스타일]
{region_style['guidance']}

[사용자 사실 원장(제안 시 사실 범위)]
{fact_sheet}

[현재 자기소개서]
{cover_letter_text}

[출력 형식]
1) 총평 (2~3문장)
2) 문항/문단별 수정 제안 (각 항목: 현재 → 개선방향 → 이유)
3) 직무 키워드 반영 체크 (반영됨/보강 필요 구분)
4) 맞춤법·문체 관점 지적(있다면)
"""


def suggest_revisions_for_job(
    client: GeminiClient,
    cover_letter_text: str,
    target_job_key: str,
    region: str,
    user: UserProfile,
) -> str:
    """직무 맞춤 수정 제안 텍스트 반환."""
    prompt = build_revision_prompt(cover_letter_text, target_job_key, region, user)
    return client.generate(prompt, config.GENERATION_CONFIG)
