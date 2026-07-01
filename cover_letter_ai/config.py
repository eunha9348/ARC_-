"""
config.py
============================================================================
  Gemini(Google AI Studio) 연결 설정 + 모델 선택
============================================================================

이 파일은 "API 키 입력 / 모델 선택"만 따로 모아 둔 곳입니다.
  - GOOGLE_AI_STUDIO_API_KEY : Google AI Studio에서 발급받은 API 키
  - GEMINI_MODEL_NAME        : 사용할 모델 이름

주의)
  * 코드를 배포하거나 커밋할 때 실제 키를 넣지 마세요.
  * 가장 안전한 방법은 환경변수(GOOGLE_AI_STUDIO_API_KEY)를 사용하는 것이며,
    환경변수가 없으면 아래 상수값을 사용합니다.
"""

import os


# ==========================================================================
#  ↓↓↓  [ 여기에 API 키를 입력하세요 / ENTER YOUR API KEY HERE ]  ↓↓↓
# ==========================================================================
#  Google AI Studio (https://aistudio.google.com/apikey) 에서 발급.
#  실행 시 직접 채워 넣으세요. (공란으로 둔 상태)
GOOGLE_AI_STUDIO_API_KEY = ""          # 예: "AIza...."

#  사용할 모델 (요청하신 gemini-2.5-flash 로 고정)
GEMINI_MODEL_NAME = "gemini-2.5-flash"
# ==========================================================================
#  ↑↑↑  [ API 키 / 모델 선택 구역 끝 ]  ↑↑↑
# ==========================================================================


# --------------------------------------------------------------------------
#  생성 파라미터 (환각 방지를 위해 낮은 temperature 를 기본값으로 사용)
# --------------------------------------------------------------------------
#  temperature 가 낮을수록 모델이 "지어내는" 경향이 줄고, 주어진 사실에
#  더 충실하게 문장을 만듭니다. (제1원칙: Hallucination 방지)
GENERATION_CONFIG = {
    "temperature": 0.25,     # 창의성 최소화 → 사실 충실도 ↑
    "top_p": 0.9,
    "top_k": 40,
    "max_output_tokens": 4096,
}

#  근거 검증(사실 확인) 단계에서 쓰는 더 엄격한 설정
VERIFICATION_CONFIG = {
    "temperature": 0.0,      # 판정은 결정적으로
    "top_p": 1.0,
    "max_output_tokens": 2048,
}


def resolve_api_key() -> str:
    """
    실제로 사용할 API 키를 반환한다.

    우선순위:
      1) 환경변수 GOOGLE_AI_STUDIO_API_KEY
      2) 이 파일 상단의 GOOGLE_AI_STUDIO_API_KEY 상수
    """
    return os.environ.get("GOOGLE_AI_STUDIO_API_KEY", "") or GOOGLE_AI_STUDIO_API_KEY
