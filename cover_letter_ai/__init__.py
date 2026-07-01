"""
cover_letter_ai
============================================================================
Google AI Studio(Gemini)를 이용한 데이터 기반 자기소개서 생성기.

설계 원칙
  제1원칙: Hallucination 방지 — 자소서 내용은 오직 '사용자 데이터'에서만.
  제2원칙: 맞춤법/문맥/자소서 문체의 자연스러움.
  + 직무별 스타일/양식 구분, 직무 맞춤 수정 제안, HR 관점 액션플랜.

빠른 사용:
    from cover_letter_ai import GeminiClient, GenerationRequest, UserProfile
    from cover_letter_ai import generate_cover_letter_package
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
    CoverLetterResult,
)
from .core.gemini_client import GeminiClient
from .core.reference_store import ReferenceStore
from .core.pipeline import generate_cover_letter_package, format_result
from .core.job_profiles import list_job_keys, get_job_profile

__all__ = [
    "GEMINI_MODEL_NAME",
    "GENERATION_CONFIG",
    "VERIFICATION_CONFIG",
    "resolve_api_key",
    "UserProfile",
    "ReferenceExample",
    "GenerationRequest",
    "GroundingReport",
    "CoverLetterResult",
    "GeminiClient",
    "ReferenceStore",
    "generate_cover_letter_package",
    "format_result",
    "list_job_keys",
    "get_job_profile",
]
