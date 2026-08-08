"""
core/gemini_client.py
============================================================================
Gemini(Google AI Studio) 호출을 감싸는 얇은 래퍼.

- 요청하신 대로 API 키/모델은 config.py 에서만 관리한다.
- 신형 SDK(google-genai, `from google import genai`)를 우선 사용하고,
  없으면 구형 SDK(google-generativeai)로 자동 폴백한다.
  (둘 중 아무거나 설치돼 있으면 동작한다.)

★ 응답 중간 절단(truncation) 대응
  gemini-2.5-flash 는 thinking 토큰이 max_output_tokens 를 함께 소모해
  본문이 문장 중간에서 끊기는 일이 잦다. 이 래퍼는
    1) thinking_budget 을 설정해 추론 예산을 통제하고
    2) finish_reason 을 읽어 "토큰 한도로 잘렸는지"를 판별하며
    3) 잘렸으면 generate_complete() 가 자동으로 이어쓰기를 수행한다.

pip:
    pip install google-genai          # 권장(신형)
  또는
    pip install google-generativeai   # 구형
"""

from __future__ import annotations

from typing import Any

from .. import config


#  단어 끝에 오는 대표적인 한국어 조사.
#  앞 조각이 이런 조사로 끝났다면 다음 단어와의 사이에 띄어쓰기가 필요하다.
#  (반대로 '개선했' 처럼 어간 중간에서 끊겼다면 붙여 써야 한다)
_TRAILING_PARTICLES = (
    "를", "을", "는", "은", "이", "가", "에", "의", "로", "으로",
    "와", "과", "도", "만", "부터", "까지", "에서", "에게", "보다",
)


def _needs_space(head: str, tail: str) -> bool:
    """문장 중간 이어쓰기에서 두 조각 사이에 공백이 필요한지 판단한다."""
    if not head or not tail:
        return False
    # 한글이 아닌 문자로 이어지면(영문·숫자 등) 공백을 넣는 편이 안전하다
    if not ("가" <= tail[0] <= "힣"):
        return True
    return head.endswith(_TRAILING_PARTICLES)


def _join_continuation(head: str, tail: str) -> str:
    """이어쓰기 조각을 원문 뒤에 자연스럽게 붙인다.

    모델이 앞부분을 일부 반복해서 돌려주는 경우가 있어, 겹치는 구간을
    찾아 제거한 뒤 이어 붙인다.
    """
    head = (head or "").rstrip()
    raw_tail = tail or ""
    # 이어쓰기 조각이 공백으로 시작했는지 기억해 둔다(한국어 띄어쓰기 보존용).
    tail_had_leading_space = raw_tail[:1].isspace()
    tail = raw_tail.strip()

    if not tail:
        return head
    if not head:
        return tail

    # 뒤 조각의 앞부분이 앞 조각의 끝과 겹치면(모델이 앞부분을 반복한 경우)
    # 그만큼 잘라낸다. 한국어는 8자 정도만 겹쳐도 중복으로 볼 수 있다.
    max_overlap = min(len(head), len(tail), 300)
    for size in range(max_overlap, 7, -1):
        if head.endswith(tail[:size]):
            tail = tail[size:].strip()
            tail_had_leading_space = True   # 잘라낸 자리는 단어 경계로 본다
            break

    if not tail:
        return head

    # 문장이 끝난 뒤라면 새 줄로, 문장 중간에서 끊겼다면 같은 줄로 이어 붙인다.
    if head[-1] in ".!?\n]”\"'":
        return head + "\n" + tail

    # 문장 중간 이어쓰기: 원래 공백이 있었거나 조사 뒤라면 한 칸을 살려 준다.
    # (없애 버리면 '목표로대회에' 처럼 띄어쓰기가 깨진다)
    separator = " " if (tail_had_leading_space or _needs_space(head, tail)) else ""
    return head + separator + tail


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
        text, _ = self.generate_detailed(prompt, generation_config)
        return text

    def generate_detailed(
        self,
        prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """(응답 텍스트, finish_reason) 을 함께 반환한다.

        finish_reason 이 "MAX_TOKENS" 면 토큰 한도로 잘렸다는 뜻이다.
        (SDK/버전에 따라 값을 못 읽으면 빈 문자열을 돌려준다.)
        """
        cfg = generation_config or config.GENERATION_CONFIG
        if self._backend == "genai":
            return self._generate_new(prompt, cfg)
        return self._generate_old(prompt, cfg)

    def generate_complete(
        self,
        prompt: str,
        generation_config: dict[str, Any] | None = None,
        max_continuations: int | None = None,
    ) -> str:
        """토큰 한도로 잘리면 자동으로 이어써서 '끝까지' 받아낸다.

        액션플랜처럼 길이가 긴 텍스트가 문장 중간에서 끊기는 것을 막는
        범용 안전장치. 잘리지 않았다면 generate() 와 동일하게 1회 호출로 끝난다.
        """
        cfg = generation_config or config.GENERATION_CONFIG
        limit = config.MAX_CONTINUATIONS if max_continuations is None else max_continuations

        text, finish = self.generate_detailed(prompt, cfg)

        rounds = 0
        while finish == "MAX_TOKENS" and rounds < limit:
            cont_prompt = f"""\
{prompt}

[여기까지 작성된 내용 — 토큰 한도로 문장 중간에서 끊겼습니다]
{text}

[이어쓰기 지시]
- 위 글이 끊긴 지점부터 '이어서만' 작성하세요.
- 이미 쓴 내용을 다시 반복하거나 처음부터 새로 시작하지 말 것.
- 끊긴 문장을 먼저 자연스럽게 완성한 뒤, 남은 내용을 끝까지 마무리할 것.
- 이어붙일 텍스트만 출력할 것(머리말·설명·사족 금지)."""
            more, finish = self.generate_detailed(cont_prompt, cfg)
            if not (more or "").strip():
                break
            text = _join_continuation(text, more)
            rounds += 1

        return text

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

    # ---- 내부 구현 -----------------------------------------------------
    @staticmethod
    def _read_finish_reason(resp: Any) -> str:
        """응답에서 finish_reason 을 최대한 안전하게 문자열로 뽑아낸다."""
        try:
            candidates = getattr(resp, "candidates", None) or []
            if not candidates:
                return ""
            raw = getattr(candidates[0], "finish_reason", None)
            if raw is None:
                return ""
            # Enum 이면 .name, 아니면 문자열화
            return str(getattr(raw, "name", raw)).upper()
        except Exception:
            return ""

    def _build_new_config(self, cfg: dict[str, Any]):
        from google.genai import types  # type: ignore

        kwargs: dict[str, Any] = {
            "temperature": cfg.get("temperature", 0.25),
            "top_p": cfg.get("top_p", 0.9),
            "top_k": cfg.get("top_k", 40),
            "max_output_tokens": cfg.get("max_output_tokens", 8192),
        }

        # thinking_budget: gemini-2.5 계열에서 추론 예산을 통제한다.
        # 구버전 SDK에는 ThinkingConfig 가 없을 수 있으므로 실패해도 무시한다.
        budget = cfg.get("thinking_budget")
        if budget is not None:
            try:
                kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=budget)
            except Exception:
                pass

        return types.GenerateContentConfig(**kwargs)

    def _generate_new(self, prompt: str, cfg: dict[str, Any]) -> tuple[str, str]:
        gen_cfg = self._build_new_config(cfg)
        resp = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=gen_cfg,
        )
        text = (getattr(resp, "text", "") or "").strip()
        return text, self._read_finish_reason(resp)

    def _generate_old(self, prompt: str, cfg: dict[str, Any]) -> tuple[str, str]:
        resp = self._model.generate_content(
            prompt,
            generation_config={
                "temperature": cfg.get("temperature", 0.25),
                "top_p": cfg.get("top_p", 0.9),
                "top_k": cfg.get("top_k", 40),
                "max_output_tokens": cfg.get("max_output_tokens", 8192),
            },
        )
        text = (getattr(resp, "text", "") or "").strip()
        return text, self._read_finish_reason(resp)
