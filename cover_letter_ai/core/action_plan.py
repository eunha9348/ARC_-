"""
core/action_plan.py
============================================================================
'HR 관점 액션플랜' 파트.

기능:
  - 직무/업계별로 인사팀(HR)이 무엇을 중심으로 보는지에 근거해,
    "지금 사용자 이력에서 부족한 부분"과
    "무엇을 더 하면 더 좋은 인재/자소서가 될지" 액션플랜을 제안한다.
  - 이건 '미래 계획 제안'이므로 새 활동을 권유하는 것은 허용되지만,
    "이미 했다"고 사실을 지어내는 것은 금지(제안과 사실을 명확히 구분).

★ 출력이 중간에 끊기던 문제 대응
  - 항목 수/문장 수 상한을 프롬프트에 명시해 애초에 예산을 넘기지 않게 하고
  - 조언 텍스트 전용 GUIDE_CONFIG(넉넉한 토큰 예산)를 사용하며
  - generate_complete() 로 잘렸을 때 자동 이어쓰기까지 수행한다.
"""

from __future__ import annotations

from .. import config
from .data_models import UserProfile
from .gemini_client import GeminiClient
from .job_profiles import get_job_profile, get_industry_profile, infer_industry
from . import prompt_builder as pb


def build_action_plan_prompt(
    user: UserProfile,
    job_key: str,
    industry: str = "",
) -> str:
    profile = get_job_profile(job_key)
    industry_key = industry or infer_industry(user.target_company, user.target_job)
    ind = get_industry_profile(industry_key)
    fact_sheet = pb.build_fact_sheet(user)

    return f"""\
당신은 채용 담당자(HR) 관점을 잘 아는 커리어 멘토입니다.
'{ind['label']}' 업계의 '{profile['label']}' 직무 지원자를 위해, 현재 이력을
진단하고 '더 좋은 인재/자소서가 되기 위한 액션플랜'을 제안하세요.

[이 직무에서 HR이 중점적으로 보는 것]
{", ".join(profile['hr_focus'])}

[이 업계가 사람에게서 확인하려는 가치]
{", ".join(ind['values'])}

[이 업계에서 설득력을 갖는 근거의 형태]
{ind['evidence']}

[강한 인상을 주는 활동/경험(참고)]
{", ".join(profile['good_signals'])}

[핵심 역량]
{", ".join(profile['competencies'])}

[사용자 사실 원장 — 현재 보유 이력]
{fact_sheet}

{pb.NO_MARKDOWN_RULES_SOFT}

[작성 규칙]
- 먼저, 원장에 '이미 있는 강점'과 '비어 있는 부분(gap)'을 구분해서 진단.
- 진단은 반드시 원장에 있는 사실만 근거로 할 것(없는 경력을 가정하지 말 것).
- 액션플랜은 '앞으로 하면 좋을 것'으로 명확히 미래형 제안(사실로 단정 금지).
- 각 액션은 (무엇을 / 왜 HR이 좋아하는지 / 자소서에 어떻게 쓸지) 포함.
- 실행 난이도/기간 감각(단기 1~3개월 / 중기 3~6개월)을 함께 제시.
- 위 업계 특성을 반영할 것. 같은 직무라도 이 업계에서 특히 중요한 보완점을
  우선순위 앞쪽에 배치할 것.

[분량 상한 — 반드시 지킬 것]
- 1) 현재 강점 진단: 항목 4개 이내, 각 항목 2문장 이내.
- 2) 부족한 부분: 항목 3개 이내, 각 항목 2문장 이내.
- 3) 액션플랜: 항목 4개 이내, 각 항목 3문장 이내.
- 4) 한 줄 요약: 1문장.
- 상한을 넘겨 길게 쓰다가 중간에 끊기는 것이 가장 나쁘다.
  항목 수를 줄여서라도 반드시 '4) 한 줄 요약'까지 도달해 끝맺을 것.

[출력 형식]
1) 현재 강점 진단
2) 부족한 부분(HR 관점 gap)
3) 액션플랜 (우선순위 순, 각 항목: 활동 / HR이 좋아하는 이유 / 자소서 활용법 / 기간)
4) 한 줄 요약

- 위 4개 섹션 제목 앞에는 관련 이모지를 1개까지 붙여도 좋다(선택).
- 마지막 문장은 반드시 종결어미로 끝낼 것.
"""


def suggest_action_plan(
    client: GeminiClient,
    user: UserProfile,
    job_key: str,
    industry: str = "",
) -> str:
    """HR 관점 액션플랜 텍스트 반환.

    GUIDE_CONFIG(넉넉한 토큰 예산) + generate_complete(자동 이어쓰기)로
    중간 절단을 막고, 남은 마크다운 기호는 후처리로 제거한다.
    """
    prompt = build_action_plan_prompt(user, job_key, industry)
    text = client.generate_complete(prompt, config.GUIDE_CONFIG)
    return pb.strip_markdown(text)
