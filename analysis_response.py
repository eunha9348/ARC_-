"""
analysis_response.py — 분석 결과 응답 모델 (API Endpoint 계약 §3.3)

계약
────
성공: { "status": "success", "vector": [...], "result": { ...payload... } }
실패: { "status": "error",   "message": "..." }

규약(§3.6 #25·#26): result(payload) 안에는 status·vector 를 넣지 않는다.

pydantic 이 설치된 환경에서는 pydantic BaseModel 을, 없으면 동일 인터페이스
(`model_dump()` / `model_dump_json()`)를 제공하는 경량 대체 구현을 사용한다.
분석 파이프라인의 환각 가드 단위 테스트가 외부 의존성 없이 돌아가야 하기
때문이다.
"""

from __future__ import annotations

import json
from typing import Any

try:  # pragma: no cover - 환경 의존
    from pydantic import BaseModel, Field

    _HAS_PYDANTIC = True
except ImportError:  # pragma: no cover - 환경 의존
    _HAS_PYDANTIC = False


def _prune_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _prune_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_prune_none(v) for v in obj]
    return obj


if _HAS_PYDANTIC:

    class VectorSuccessResponse(BaseModel):
        status: str = "success"
        result: dict = Field(default_factory=dict)
        vector: list[float] | None = None

    class ErrorResponse(BaseModel):
        status: str = "error"
        message: str = ""

else:

    class _BaseResponse:
        _fields: tuple[str, ...] = ()

        def model_dump(self, exclude_none: bool = False) -> dict:
            data = {f: getattr(self, f) for f in self._fields}
            return _prune_none(data) if exclude_none else data

        def model_dump_json(self, indent: int | None = None,
                            exclude_none: bool = False) -> str:
            return json.dumps(
                self.model_dump(exclude_none=exclude_none),
                ensure_ascii=False,
                indent=indent,
            )

    class VectorSuccessResponse(_BaseResponse):
        _fields = ("status", "result", "vector")

        def __init__(self, result: dict | None = None,
                     vector: list | None = None, status: str = "success"):
            self.status = status
            self.result = result or {}
            self.vector = vector

    class ErrorResponse(_BaseResponse):
        _fields = ("status", "message")

        def __init__(self, message: str = "", status: str = "error"):
            self.status = status
            self.message = message


__all__ = ["VectorSuccessResponse", "ErrorResponse"]
