"""
core/action_plan.py
============================================================================
'HR 관점 액션플랜' 파트.

기능:
  - 직무별로 인사팀(HR)이 무엇을 중심으로 보는지에 근거해,
    "지금 사용자 이력에서 부족한 부분"과
    "무엇을 더 하면 더 좋은 인재/자소서가 될지" 액션플랜을 제안한다.
  - 이건 '미래 계획 제안'이므로 새 활동을 권유하는 것은 허용되지만,
    "이미 했다"고 사실을 지어내는 것은 금지(제안과 사실을 명확히 구분).
"""

from __future__ import annotations

from .. import config
from .data_models import UserProfile
from .gemini_client import GeminiClient
from .job_profiles import get_job_profile
from . import prompt_builder as pb


def build_action_plan_prompt(
    user: UserProfile,
    job_key: str,
) -> str:
    profile = get_job_profile(job_key)
    fact_sheet = pb.build_fact_sheet(user)

    return f"""\
당신은 채용 담당자(HR) 관점을 잘 아는 커리어 멘토입니다.
'{profile['label']}' 직무 지원자를 위해, 현재 이력을 진단하고
'더 좋은 인재/자소서가 되기 위한 액션플랜'을 제안하세요.

[이 직무에서 HR이 중점적으로 보는 것]
{", ".join(profile['hr_focus'])}

[강한 인상을 주는 활동/경험(참고)]
{", ".join(profile['good_signals'])}

[핵심 역량]
{", ".join(profile['competencies'])}

[사용자 사실 원장 — 현재 보유 이력]
{fact_sheet}

[작성 규칙]
- 먼저, 원장에 '이미 있는 강점'과 '비어 있는 부분(gap)'을 구분해서 진단.
- 액션플랜은 '앞으로 하면 좋을 것'으로 명확히 미래형 제안(사실로 단정 금지).
- 각 액션은 (무엇을 / 왜 HR이 좋아하는지 / 자소서에 어떻게 쓸지) 포함.
- 실행 난이도/기간 감각(단기 1~3개월 / 중기 3~6개월)을 함께 제시.

[출력 형식]
1) 현재 강점 진단
2) 부족한 부분(HR 관점 gap)
3) 액션플랜 (우선순위 순, 각 항목: 활동 / HR이 좋아하는 이유 / 자소서 활용법 / 기간)
4) 한 줄 요약
"""


def suggest_action_plan(
    client: GeminiClient,
    user: UserProfile,
    job_key: str,
) -> str:
    """HR 관점 액션플랜 텍스트 반환."""
    prompt = build_action_plan_prompt(user, job_key)
    return client.generate(prompt, config.GENERATION_CONFIG)
