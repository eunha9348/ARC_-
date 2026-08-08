"""
core/writing_guide.py
============================================================================
'이 자소서를 내 것으로 만드는 가이드' 파트.

이 서비스의 주 결과물은 '완성형 자소서'다. 이 모듈은 그 완성본을 받은
사용자가 글을 자기 것으로 소화하고, 마지막 디테일을 직접 채워 넣고,
면접까지 대비할 수 있도록 돕는 부속 가이드를 생성한다.

(첨삭 리포트가 아니라, 생성된 글을 '잘 활용하게 하는' 설명서에 가깝다.)

★ 액션플랜과 동일하게, 중간 절단 방지를 위해 분량 상한 + GUIDE_CONFIG +
  generate_complete() 를 사용하고 마크다운 기호는 후처리로 제거한다.
"""

from __future__ import annotations

from .. import config
from .data_models import UserProfile
from .gemini_client import GeminiClient
from .job_profiles import get_job_profile, get_industry_profile, infer_industry
from . import prompt_builder as pb


def build_writing_guide_prompt(
    cover_letter_text: str,
    question: str,
    user: UserProfile,
    job_key: str,
    industry: str = "",
) -> str:
    profile = get_job_profile(job_key)
    industry_key = industry or infer_industry(user.target_company, user.target_job)
    ind = get_industry_profile(industry_key)
    fact_sheet = pb.build_fact_sheet(user)
    question_line = question.strip() or "자유 형식의 자기소개서"

    return f"""\
당신은 자기소개서 코치입니다. 아래는 지원자의 사실 데이터로 AI가 대신 작성한
완성형 자기소개서입니다. 지원자가 이 글을 '자기 것'으로 소화해 최종 제출본을
완성하고, 면접까지 대비할 수 있도록 돕는 가이드를 작성하세요.

[지원 직무]
- {profile['label']} — 인사팀 평가 포인트: {", ".join(profile['hr_focus'])}

[지원 업계]
- {ind['label']} — 이 업계에서 통하는 글의 결: {ind['voice']}
- 이 업계에서 감점되는 표현/태도: {ind['taboo']}

[사용자 사실 원장]
{fact_sheet}

[자소서 문항]
{question_line}

[완성된 자기소개서]
{cover_letter_text}

{pb.NO_MARKDOWN_RULES_SOFT}

[작성 규칙]
- 새로운 사실을 지어내라고 제안하지 말 것.
- 이 글을 '고쳐야 할 초안'이 아니라 '완성본'으로 대하되, 지원자 본인만이
  더할 수 있는 것(디테일, 감정, 당시의 판단)을 짚어줄 것.
- 위 업계 특성을 근거로, 이 글이 그 업계 인사담당자에게 어떻게 읽힐지
  구체적으로 설명할 것.

[분량 상한 — 반드시 지킬 것]
- 각 섹션은 짧고 밀도 있게. 2)는 문단당 1~2문장, 3)은 3개 이내,
  4)는 5개 이내, 5)는 질문 3개 각각 2문장 이내.
- 길게 쓰다가 중간에 끊기는 것이 가장 나쁘다. 항목을 줄여서라도
  반드시 5)까지 도달해 끝맺을 것.

[출력 형식]
1) 이 자소서의 전략 (2~3문장): 어떤 강점을 어떤 순서로 배치했고, 왜 이 구성이
   이 업계·직무 인사담당자에게 효과적인지.
2) 문단별 해설: 각 문단의 역할(후킹/근거/직무연결/포부)과 활용된 지원자 경험.
3) 직접 손보면 더 좋아지는 포인트: "[보완필요]" 표시가 있다면 채우는 법,
   지원자 본인만 아는 디테일(당시의 판단, 감정, 대화, 시행착오)을 추가하면
   좋은 위치와 방법.
4) 제출 전 최종 체크리스트 (5개 내외).
5) 이 자소서 기반 예상 면접 질문 3개와 답변 포인트.

- 위 섹션 제목 앞에는 관련 이모지를 1개까지 붙여도 좋다(선택).
- 마지막 문장은 반드시 종결어미로 끝낼 것.
"""


def build_writing_guide(
    client: GeminiClient,
    cover_letter_text: str,
    question: str,
    user: UserProfile,
    job_key: str,
    industry: str = "",
) -> str:
    """완성형 자소서에 대한 활용 가이드 텍스트 반환."""
    prompt = build_writing_guide_prompt(
        cover_letter_text, question, user, job_key, industry)
    text = client.generate_complete(prompt, config.GUIDE_CONFIG)
    return pb.strip_markdown(text)
