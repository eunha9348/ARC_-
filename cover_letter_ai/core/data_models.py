"""
core/data_models.py
============================================================================
프로그램 전체에서 주고받는 데이터 구조 정의.

핵심 개념(환각 방지의 뼈대):
  * UserProfile      : 자소서 "내용의 유일한 사실 출처". 여기 없는 사실은
                       생성문에 절대 등장하면 안 된다.
  * ReferenceExample : DB에서 가져온 "모범 자소서(문체/구조 참조용)".
                       내용을 베끼는 용도가 아니라 '스타일'만 참고한다.
  * JobProfile       : 직무별 스타일/양식/HR 평가 포인트.

사용자 데이터(UserProfile)는 다른 코드/DB에서 채워 넣으므로,
여기서는 '구조'만 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# --------------------------------------------------------------------------
#  1) 사용자 데이터 (자소서 내용의 유일한 사실 출처)
# --------------------------------------------------------------------------
@dataclass
class UserProfile:
    """
    자소서를 만들 '지원자 본인'의 사실 데이터.

    - 모든 필드는 선택적이며, 비어 있으면 생성문에서 다루지 않는다.
    - 리스트 형태의 필드는 자유 문자열의 나열이어도 되고,
      dict(예: {"name": "...", "period": "...", "detail": "..."}) 여도 된다.
    """
    name: str = ""                              # 이름(선택)
    target_company: str = ""                    # 지원 회사
    target_job: str = ""                        # 지원 직무(원문 표현)
    education: list[Any] = field(default_factory=list)          # 학력
    experiences: list[Any] = field(default_factory=list)        # 경력/인턴
    projects: list[Any] = field(default_factory=list)           # 프로젝트
    skills: list[Any] = field(default_factory=list)             # 보유 역량/기술
    certifications: list[Any] = field(default_factory=list)     # 자격증
    awards: list[Any] = field(default_factory=list)             # 수상
    activities: list[Any] = field(default_factory=list)         # 대외활동/동아리
    achievements: list[Any] = field(default_factory=list)       # 정량적 성과(수치)
    strengths: list[Any] = field(default_factory=list)          # 강점/성향
    motivation: str = ""                        # 지원동기(사용자가 직접 쓴 메모)
    career_goal: str = ""                       # 입사 후 포부/목표
    extra_notes: str = ""                       # 기타 자유 메모(반드시 사실만)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_empty(self) -> bool:
        """유의미한 사실이 하나도 없는지 검사(빈 입력 방지용)."""
        d = self.to_dict()
        for k, v in d.items():
            if isinstance(v, str) and v.strip():
                return False
            if isinstance(v, list) and len(v) > 0:
                return False
        return True


# --------------------------------------------------------------------------
#  2) 모범 자소서 (DB에서 로드, 문체/구조 참조 전용)
# --------------------------------------------------------------------------
@dataclass
class ReferenceExample:
    """
    '학습'에 쓰이는 모범 자소서 1건.

    region : "KR"(한국형) 또는 "US"(미국형)
    job_key: 어떤 직무 계열의 예시인지 (JOB_PROFILES 의 key)
    text   : 모범 자소서 본문 (스타일 참조용 — 내용 복붙 금지)
    tags   : 검색/필터용 태그
    """
    region: str = "KR"
    job_key: str = "general"
    text: str = ""
    source: str = ""                    # 출처(사람인/링크드인 등) 메모
    tags: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
#  3) 경험 선별 (회사 리서치 기반 적합도 채점 → 시간순 배치)
# --------------------------------------------------------------------------
#  자소서가 '경험 1개'만 얕게 반영하던 문제를 고치기 위한 구조.
#  UserProfile 의 이력을 '사건 단위'로 쪼개(ExperienceItem), 지원 회사가
#  관심 있게 볼 만한 순서로 채점하고(ScoredExperience), 분량에 맞는 개수를
#  골라 시간 순으로 배열한 결과가 ExperienceSelection 이다.
# --------------------------------------------------------------------------
@dataclass
class ExperienceItem:
    """UserProfile 에서 평탄화한 이력 1건(경력/프로젝트/활동/수상)."""
    key: str = ""                       # 프롬프트에서 참조할 식별자(예: "pro1")
    field: str = ""                     # 원본 필드명(experiences/projects/...)
    label: str = ""                     # 한글 라벨(경력/인턴, 프로젝트 등)
    text: str = ""                      # 직렬화된 내용
    year: int = 9999                    # 정렬용 연도(추출 실패 시 9999 → 맨 뒤)


@dataclass
class ScoredExperience:
    """적합도 채점이 끝난 이력 1건."""
    key: str = ""
    field: str = ""
    label: str = ""
    text: str = ""
    year: int = 9999
    score: int = 0                      # 0~100 종합 적합도
    company_fit: str = ""               # 이 회사가 이 경험을 볼 이유(연결점)
    rationale: str = ""                 # 채점 근거 한 줄
    role: str = "excluded"              # "core" | "supporting" | "excluded"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExperienceSelection:
    """문항 1개에 대한 경험 선별·배치 결과.

    두 가지 순서를 구분해서 담는다(혼동 주의).
      by_relevance : 적합도 순 — '무엇을 중심에 둘지'를 정하는 1순위 기준
      ordered      : 시간 순 — 서술 도중 시계열이 역행하지 않게 하는 배치 제약
    """
    strategy: str = ""                            # 이 문항을 어떤 줄기로 엮을지
    ordered: list[ScoredExperience] = field(default_factory=list)   # 채택분(시간순)
    excluded: list[ScoredExperience] = field(default_factory=list)  # 미채택분(점수순)
    fallback_used: bool = False                   # LLM 채점 실패 → 키워드 폴백 여부

    @property
    def by_relevance(self) -> list[ScoredExperience]:
        """적합도 높은 순. '무엇을 중심에 둘지'는 항상 이 순서가 정한다.

        ordered(시간순)와 헷갈리면 안 된다. ordered 는 '늘어놓는 순서'일 뿐이고,
        비중·중심은 이 by_relevance 가 결정한다.
        """
        return sorted(self.ordered, key=lambda e: -e.score)

    @property
    def core(self) -> list[ScoredExperience]:
        return [e for e in self.ordered if e.role == "core"]

    @property
    def supporting(self) -> list[ScoredExperience]:
        return [e for e in self.ordered if e.role == "supporting"]

    def is_empty(self) -> bool:
        return not self.ordered

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "fallback_used": self.fallback_used,
            "ordered": [e.to_dict() for e in self.ordered],
            "excluded": [e.to_dict() for e in self.excluded],
            "num_core": len(self.core),
            "num_supporting": len(self.supporting),
        }


# --------------------------------------------------------------------------
#  4) 생성 요청 옵션
# --------------------------------------------------------------------------
@dataclass
class GenerationRequest:
    """자소서 문항 1개 생성에 필요한 파라미터 묶음."""
    user: UserProfile
    job_key: str = "general"            # JOB_PROFILES key
    region: str = "KR"                  # "KR" | "US"
    question: str = ""                  # 자소서 문항(예: "지원동기를 기술하시오")
    max_chars: int = 1000               # 한국형 문항 글자수 제한 (0이면 제한 없음)
    tone: str = ""                      # 추가 톤 요청(선택). 비우면 직무 기본 톤 사용
    industry: str = ""                  # 업계 key(finance/it/manufacturing/...).
                                        # 비우면 회사명·직무명에서 자동 추정
    selection: ExperienceSelection | None = None   # 회사 리서치 기반 경험 선별 결과.
                                        # None 이면 선별 없이(구 동작) 생성한다.


# --------------------------------------------------------------------------
#  5) 결과 컨테이너
# --------------------------------------------------------------------------
@dataclass
class GroundingReport:
    """근거 검증(환각 탐지) 결과."""
    grounded: bool = True                        # 전체가 사실 기반인가
    unsupported_claims: list[str] = field(default_factory=list)  # 근거 없는 문장
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerResult:
    """문항 1개에 대한 완성형 자소서 + 부속 정보."""
    question: str = ""                            # 자소서 문항
    cover_letter: str = ""                        # ★ 주 결과물: 완성형 자소서 본문
    grounding: GroundingReport = field(default_factory=GroundingReport)
    writing_guide: str = ""                       # 이 자소서를 내 것으로 만드는 가이드
    experience_selection: ExperienceSelection = field(
        default_factory=ExperienceSelection)      # 어떤 경험을 왜 골랐는지(투명성)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicationResult:
    """지원서 전체(여러 문항) 산출물 묶음."""
    answers: list[AnswerResult] = field(default_factory=list)   # 문항별 자소서
    company_research: str = ""                    # 지원 회사 리서치 요약(참고용)
    action_plan: str = ""                         # (부가) HR 관점 액션플랜
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
