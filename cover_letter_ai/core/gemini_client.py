"""
core/gemini_client.py
============================================================================
Gemini(Google AI Studio) 호출을 감싸는 얇은 래퍼.

- 요청하신 대로 API 키/모델은 config.py 에서만 관리한다.
- 신형 SDK(google-genai, `from google import genai`)를 우선 사용하고,
  없으면 구형 SDK(google-generativeai)로 자동 폴백한다.
  (둘 중 아무거나 설치돼 있으면 동작한다.)

pip:
    pip install google-genai          # 권장(신형)
  또는
    pip install google-generativeai   # 구형
"""

from __future__ import annotations

from typing import Any

from .. import config


class GeminiClient:
    """Gemini 텍스트 생성용 최소 래퍼."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.api_key = api_key if api_key is not None else config.resolve_api_key()
        self.model_name = model_name or config.GEMINI_MODEL_NAME
        self._backend = None      # "genai" | "generativeai"
        self._client = None       # 신형 client
        self._model = None        # 구형 GenerativeModel

        if not self.api_key:
            raise ValueError(
                "API 키가 비어 있습니다. config.py 의 GOOGLE_AI_STUDIO_API_KEY 에 "
                "키를 넣거나 환경변수 GOOGLE_AI_STUDIO_API_KEY 를 설정하세요."
            )
        self._init_backend()

    # ---- 백엔드 초기화 -------------------------------------------------
    def _init_backend(self) -> None:
        # 1) 신형 SDK 시도
        try:
            from google import genai  # type: ignore

            self._client = genai.Client(api_key=self.api_key)
            self._backend = "genai"
            return
        except Exception:
            pass

        # 2) 구형 SDK 폴백
        try:
            import google.generativeai as genai_old  # type: ignore

            genai_old.configure(api_key=self.api_key)
            self._model = genai_old.GenerativeModel(self.model_name)
            self._backend = "generativeai"
            return
        except Exception as exc:  # pragma: no cover
            raise ImportError(
                "google-genai 또는 google-generativeai 패키지가 필요합니다.\n"
                "  pip install google-genai\n"
                f"원본 오류: {exc}"
            ) from exc

    # ---- 텍스트 생성 ---------------------------------------------------
    def generate(self, prompt: str, generation_config: dict[str, Any] | None = None) -> str:
        """
        prompt 를 넣어 모델 응답 텍스트를 반환한다.
        generation_config 예: config.GENERATION_CONFIG
        """
        cfg = generation_config or config.GENERATION_CONFIG

        if self._backend == "genai":
            return self._generate_new(prompt, cfg)
        return self._generate_old(prompt, cfg)

    def generate_with_search(self, prompt: str,
                             generation_config: dict[str, Any] | None = None) -> str:
        """
        Google 검색 그라운딩을 켜고 생성한다 (지원 회사 리서치용).

        신형 SDK(google-genai)에서만 검색이 동작하며, 실패하거나 구형 SDK인
        경우 일반 생성으로 폴백한다(이때 '모르면 지어내지 말 것'을 프롬프트로
        강제하고 있어야 함).
        """
        cfg = generation_config or config.GENERATION_CONFIG
        if self._backend == "genai":
            try:
                from google.genai import types  # type: ignore
                gen_cfg = types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=cfg.get("max_output_tokens", 2048),
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                )
                resp = self._client.models.generate_content(
                    model=self.model_name, contents=prompt, config=gen_cfg,
                )
                text = (getattr(resp, "text", "") or "").strip()
                if text:
                    return text
            except Exception:
                pass
        return self.generate(prompt, cfg)

    def _generate_new(self, prompt: str, cfg: dict[str, Any]) -> str:
        from google.genai import types  # type: ignore

        gen_cfg = types.GenerateContentConfig(
            temperature=cfg.get("temperature", 0.25),
            top_p=cfg.get("top_p", 0.9),
            top_k=cfg.get("top_k", 40),
            max_output_tokens=cfg.get("max_output_tokens", 4096),
        )
        resp = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=gen_cfg,
        )
        return (getattr(resp, "text", "") or "").strip()

    def _generate_old(self, prompt: str, cfg: dict[str, Any]) -> str:
        resp = self._model.generate_content(
            prompt,
            generation_config={
                "temperature": cfg.get("temperature", 0.25),
                "top_p": cfg.get("top_p", 0.9),
                "top_k": cfg.get("top_k", 40),
                "max_output_tokens": cfg.get("max_output_tokens", 4096),
            },
        )
        return (getattr(resp, "text", "") or "").strip()
