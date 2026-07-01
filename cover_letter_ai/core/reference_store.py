"""
core/reference_store.py
============================================================================
'모범 자소서 학습' 파트.

요청 맥락:
  - 사람인/링커리어/링크드인 등에서 모은 모범 자소서 약 1000개
    (한국형 750 + 미국형 250)를 '학습'해서 좋은 자소서를 생성.
  - 실제 데이터는 다른 코드/DB 에서 주입한다고 하셨으므로,
    여기서는 "DB 를 꽂을 수 있는 인터페이스 + few-shot 예시 선별기"만 만든다.

★ 환각 방지 관점의 중요한 설계 결정 ★
  모범 자소서는 '문체/구조/논리 전개'를 배우기 위한 스타일 레퍼런스로만 쓴다.
  절대 그 내용(사실)을 사용자 자소서에 옮겨 담지 않는다.
  → LLM 파인튜닝 대신 "few-shot 스타일 예시" 방식을 사용해,
    내용은 사용자 데이터, 문체만 레퍼런스에서 오도록 강제한다.
"""

from __future__ import annotations

from typing import Callable

from .data_models import ReferenceExample
from .job_profiles import normalize_job_key


# 한국형/미국형 목표 비율 (750 : 250 = 3 : 1)
TARGET_RATIO = {"KR": 0.75, "US": 0.25}


class ReferenceStore:
    """
    모범 자소서 저장소.

    사용법(택1):
      1) 메모리에 직접 add() 로 넣기
      2) loader 함수를 주입해 DB 에서 lazy-load
         loader() -> list[ReferenceExample]
    """

    def __init__(self, loader: Callable[[], list[ReferenceExample]] | None = None):
        self._items: list[ReferenceExample] = []
        self._loader = loader
        self._loaded = False

    # ---- 적재 ---------------------------------------------------------
    def add(self, example: ReferenceExample) -> None:
        example.job_key = normalize_job_key(example.job_key)
        example.region = (example.region or "KR").upper()
        self._items.append(example)

    def add_many(self, examples: list[ReferenceExample]) -> None:
        for e in examples:
            self.add(e)

    def _ensure_loaded(self) -> None:
        if not self._loaded and self._loader is not None:
            loaded = self._loader() or []
            self.add_many(loaded)
        self._loaded = True

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._items)

    # ---- few-shot 예시 선별 -------------------------------------------
    def select_examples(
        self,
        job_key: str,
        region: str,
        k: int = 3,
        max_chars_each: int = 1400,
    ) -> list[ReferenceExample]:
        """
        생성 프롬프트에 넣을 few-shot 스타일 예시를 고른다.

        우선순위:
          1) (같은 직무 & 같은 region)
          2) 같은 region 의 일반(general)/타 직무
          3) 그래도 부족하면 아무거나
        너무 길면 앞부분만 잘라 토큰을 아낀다.
        """
        self._ensure_loaded()
        job_key = normalize_job_key(job_key)
        region = (region or "KR").upper()

        same_job_region = [e for e in self._items
                           if e.job_key == job_key and e.region == region]
        same_region = [e for e in self._items
                       if e.region == region and e not in same_job_region]
        others = [e for e in self._items
                  if e not in same_job_region and e not in same_region]

        ordered: list[ReferenceExample] = []
        for bucket in (same_job_region, same_region, others):
            for e in bucket:
                if len(ordered) >= k:
                    break
                ordered.append(e)
            if len(ordered) >= k:
                break

        # 길이 컷
        trimmed: list[ReferenceExample] = []
        for e in ordered:
            text = e.text.strip()
            if max_chars_each and len(text) > max_chars_each:
                text = text[:max_chars_each] + " …(이하 생략)"
            trimmed.append(ReferenceExample(
                region=e.region, job_key=e.job_key, text=text,
                source=e.source, tags=e.tags,
            ))
        return trimmed

    # ---- 통계 (750/250 균형 점검용) -----------------------------------
    def distribution(self) -> dict[str, int]:
        self._ensure_loaded()
        dist = {"KR": 0, "US": 0, "total": 0}
        for e in self._items:
            dist[e.region] = dist.get(e.region, 0) + 1
            dist["total"] += 1
        return dist

    def balance_report(self) -> str:
        """현재 적재된 데이터가 목표 비율(KR750:US250)에 부합하는지 리포트."""
        dist = self.distribution()
        total = dist["total"] or 1
        kr_ratio = dist.get("KR", 0) / total
        us_ratio = dist.get("US", 0) / total
        return (
            f"[레퍼런스 분포] 총 {dist['total']}건 "
            f"(KR {dist.get('KR', 0)} / US {dist.get('US', 0)})\n"
            f" - 현재 비율  KR {kr_ratio:.0%} : US {us_ratio:.0%}\n"
            f" - 목표 비율  KR {TARGET_RATIO['KR']:.0%} : US {TARGET_RATIO['US']:.0%}"
        )
