"""
cover_letter_ai
============================================================================
Google AI Studio(Gemini)를 이용한 데이터 기반 '완성형 자기소개서 생성' 서비스.

이 서비스가 하는 일:
  ★ 사용자의 사실 데이터를 재료로, 그대로 제출 가능한 수준의 자소서를
    문항별로 '대신 써 준다'. (첨삭 도구가 아니라 생성 도구)
  + 생성된 자소서를 사용자가 자기 것으로 소화하도록 돕는 '작성 가이드'와
    (부가) HR 관점 커리어 액션플랜을 함께 제공한다.

설계 원칙
  제1원칙: Hallucination 방지 — 자소서 내용은 오직 '사용자 데이터'에서만.
           생성 후 근거 검증 → 자동 교정 패스로 이중 확인.
  제2원칙: 맞춤법/문맥/자소서 문체 — 생성 후 최종 다듬기(polish) 패스 수행.
  + 직무별 스타일/양식/HR 평가 포인트 구분(KR/US 문화 차이 포함).

빠른 사용:
    from cover_letter_ai import GeminiClient, UserProfile
    from cover_letter_ai import generate_application, format_application
"""

from .config import (
    GEMINI_MODEL_NAME,
    GENERATION_CONFIG,
    VERIFICATION_CONFIG,
    resolve_api_key,
)
from .core.data_models import (
    UserProfile,
    ReferenceExample,
    GenerationRequest,
    GroundingReport,
    AnswerResult,
    ApplicationResult,
    ExperienceItem,
    ScoredExperience,
    ExperienceSelection,
)
from .core.gemini_client import GeminiClient
from .core.reference_store import ReferenceStore
from .core.pipeline import (
    generate_application, format_application,
    result_to_json, split_into_sentences,
)
from .core.job_profiles import list_job_keys, get_job_profile
from .core.experience_selector import select_experiences, plan_capacity

__all__ = [
    "GEMINI_MODEL_NAME",
    "GENERATION_CONFIG",
    "VERIFICATION_CONFIG",
    "resolve_api_key",
    "UserProfile",
    "ReferenceExample",
    "GenerationRequest",
    "GroundingReport",
    "AnswerResult",
    "ApplicationResult",
    "ExperienceItem",
    "ScoredExperience",
    "ExperienceSelection",
    "select_experiences",
    "plan_capacity",
    "GeminiClient",
    "ReferenceStore",
    "generate_application",
    "format_application",
    "result_to_json",
    "split_into_sentences",
    "list_job_keys",
    "get_job_profile",
]
