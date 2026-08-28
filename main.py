"""
main.py
============================================================================
AI 자기소개서 '생성' 서비스 — 실행 진입점 + 백엔드 연동 엔트리포인트.

★ 이 프로그램은 자소서를 '대신 써 주는' 서비스입니다.
  사용자의 사실 데이터만을 재료로, 문항별로 그대로 제출 가능한 수준의
  완성형 자소서를 생성하고, 그 글을 사용자가 자기 것으로 소화하도록
  돕는 '작성 가이드'를 함께 제공합니다.

────────────────────────────────────────────────────────────────────────
 사용법 1) CLI — 혼자 돌려볼 때
────────────────────────────────────────────────────────────────────────
  1) 환경변수 GOOGLE_AI_STUDIO_API_KEY 에 키 설정
     (또는 cover_letter_ai/config.py 의 GOOGLE_AI_STUDIO_API_KEY 에 입력)
  2) 아래 (C) 구역의 build_user_profile() 에 본인 사실 데이터 입력
  3) 아래 (D) 구역의 QUESTIONS 에 지원할 회사의 자소서 문항 입력
  4) python main.py 실행

────────────────────────────────────────────────────────────────────────
 사용법 2) 백엔드 연동 — 서버에서 호출할 때  ★
────────────────────────────────────────────────────────────────────────
  main() 을 호출하면 JSON 직렬화 가능한 dict(envelope) 가 반환됩니다.
  파일 안의 (C)/(D) 구역은 '기본값'일 뿐이며, 인자를 넘기면 전부 덮어씁니다.

      from main import main

      response = main(
          user={                       # dict 그대로 넘겨도 됩니다(JSON 그대로)
              "name": "홍길동",
              "target_company": "네이버",
              "target_job": "백엔드 개발자",
              "experiences": [...],
              "projects": [...],
          },
          questions=[
              {"question": "지원동기를 기술하시오.", "max_chars": 1000},
          ],
          job_key="backend",
          region="KR",
          api_key="AIza...",           # 미지정 시 환경변수/config.py 사용
          verbose=False,               # 서버에서는 False 권장(표준출력 안 씀)
      )

      if response["status"] == "success":
          payload = response["result"]     # 프론트엔드로 그대로 내려주면 됨
      else:
          log.error(response["message"])   # response["error_type"] 로 분기 가능

  반환 형식
      성공: {"status": "success", "result": { ...9-1 참고... }}
      실패: {"status": "error", "message": "...", "error_type": "ValueError"}

  result 안에는 meta / company_research / action_plan / answers[] 가 들어가며,
  answers[] 각 항목에는 cover_letter(주 결과물), char_count, sentences[],
  grounding, writing_guide, experience_selection 이 포함됩니다.
  (구조 상세는 cover_letter_ai/core/pipeline.py 의 result_to_json() 참고)

  ※ error_type 활용 예 — HTTP 상태코드 매핑
      "ValueError"  → 입력 데이터 문제(빈 프로필, 잘못된 필드명) → 400
      그 외          → 모델 호출/내부 오류                        → 500
────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

from cover_letter_ai import (
    GeminiClient,
    UserProfile,
    ReferenceExample,
    ReferenceStore,
    generate_application,
    format_application,
    result_to_json,
)


# ==========================================================================
#  (B) 모범 자소서(레퍼런스) DB 연결
# --------------------------------------------------------------------------
#  실제 모범 자소서(한국형 750 + 미국형 250)는 별도 코드/DB 에서 불러온다면
#  loader 함수를 만들어 주입하세요. 없어도(공란) 자소서 생성은 동작합니다.
#
#      def load_examples_from_db() -> list[ReferenceExample]:
#          rows = your_db.query("SELECT region, job_key, text, source FROM refs")
#          return [ReferenceExample(region=r.region, job_key=r.job_key,
#                                   text=r.text, source=r.source) for r in rows]
#      store = ReferenceStore(loader=load_examples_from_db)
# ==========================================================================
def build_reference_store() -> ReferenceStore:
    store = ReferenceStore()

    # ↓↓↓ 여기에 DB에서 불러온 모범 자소서를 넣으세요 (지금은 공란) ↓↓↓
    # store.add(ReferenceExample(region="KR", job_key="backend", text="", source=""))
    # store.add(ReferenceExample(region="US", job_key="data",    text="", source=""))
    # ↑↑↑ 공란 ↑↑↑

    return store


# ==========================================================================
#  (C) ★★★ 사용자 데이터 입력 구역 (CLI 기본값) ★★★
# --------------------------------------------------------------------------
#  CLI 로 직접 실행할 때 쓰이는 기본 프로필입니다.
#  백엔드에서 main(user=...) 로 넘기면 이 값은 사용되지 않습니다.
#  ─ 제1원칙(환각 방지): 여기에 없는 내용은 자소서에 절대 등장하지 않습니다.
#  ─ 비워 둔 항목은 자소서에서 다루지 않습니다.
#  ─ 리스트 항목은 "문자열" 또는 {"키": "값"} 형태 모두 가능합니다.
# ==========================================================================
def build_user_profile() -> UserProfile:
    user = UserProfile(
        name="",                 # 예: "홍길동"
        target_company="",       # 예: "OO전자"  ← Google 검색 회사 리서치에 사용됨
        target_job="",           # 예: "백엔드 개발자"

        education=[
            # 예: {"school": "OO대학교", "major": "컴퓨터공학", "period": "2019-2025"},
        ],
        experiences=[
            # 예: {"company": "OO스타트업", "role": "백엔드 인턴",
            #      "period": "2024.01-2024.06", "detail": "결제 API 개발"},
        ],
        projects=[
            # 예: {"name": "커머스 서버", "detail": "일 10만 요청 처리, 응답속도 40% 개선"},
        ],
        skills=[
            # 예: "Python", "Django", "PostgreSQL", "AWS"
        ],
        certifications=[
            # 예: "정보처리기사"
        ],
        awards=[
            # 예: {"name": "교내 해커톤 대상", "year": "2024"}
        ],
        activities=[
            # 예: "개발 동아리 3년 운영"
        ],
        achievements=[
            # 예: "응답속도 40% 단축", "월 매출 20% 성장"  (숫자는 반드시 사실만!)
        ],
        strengths=[
            # 예: "끈질긴 문제해결", "협업 커뮤니케이션"
        ],
        motivation="",           # 지원동기 메모(사실 기반)  예: "..."
        career_goal="",          # 입사 후 포부         예: "..."
        extra_notes="",          # 기타 사실 메모       예: "..."
    )
    return user
# ==========================================================================
#  ★★★ 사용자 데이터 입력 구역 끝 ★★★
# ==========================================================================


# ==========================================================================
#  (D) 자소서 문항 입력 (CLI 기본값)
# --------------------------------------------------------------------------
#  CLI 로 직접 실행할 때 쓰이는 기본 문항입니다.
#  백엔드에서 main(questions=[...]) 으로 넘기면 이 값은 사용되지 않습니다.
#  비워 두면([]) 자유 형식 1건이 생성됩니다.
#  ─ 문항은 "문자열" 그대로 넣거나, {"question": "...", "max_chars": N}
#    딕셔너리로 넣거나 둘 다 가능합니다. (문자열이면 max_chars=1000 기본 적용)
# ==========================================================================
QUESTIONS: list[Any] = [
    # 방법 1) 문자열만 넣기 (간단, 글자수 제한은 기본 1000자)
    # "지원동기와 입사 후 포부를 기술하시오.",

    # 방법 2) 딕셔너리로 글자수까지 지정 (권장 — 실제 문항의 글자수 제한을 맞출 수 있음)
    # {"question": "지원동기와 입사 후 포부를 기술하시오.", "max_chars": 1000},
    # {"question": "가장 도전적이었던 경험과 배운 점을 기술하시오.", "max_chars": 1500},
]


# ==========================================================================
#  입력 정규화 — 백엔드는 JSON(dict)을 받으므로 dataclass 로 변환해 준다
# ==========================================================================
def coerce_user_profile(user: Any, strict_fields: bool = True) -> UserProfile:
    """user 를 UserProfile 로 변환한다.

    백엔드는 HTTP 로 받은 dict 를 그대로 넘기는 경우가 많아, dict / UserProfile
    / None 을 모두 받아 준다.

    strict_fields=True (기본): UserProfile 에 없는 키가 들어오면 ValueError.
      필드명 오타(예: "experience" ← 's' 누락)를 조용히 흘려보내면 해당 이력이
      통째로 누락된 채 자소서가 생성되므로, 연동 단계에서 즉시 잡는 편이 안전하다.
    strict_fields=False: 모르는 키는 무시(백엔드가 id/created_at 등을 함께
      넘기는 경우에 사용).
    """
    if user is None:
        return build_user_profile()
    if isinstance(user, UserProfile):
        return user
    if not isinstance(user, dict):
        raise TypeError(
            f"user 는 UserProfile 또는 dict 여야 합니다 (받은 타입: {type(user).__name__})."
        )

    valid = {f.name for f in dataclass_fields(UserProfile)}
    unknown = [k for k in user if k not in valid]
    if unknown and strict_fields:
        raise ValueError(
            f"UserProfile 에 없는 필드입니다: {sorted(unknown)}\n"
            f"사용 가능한 필드: {sorted(valid)}\n"
            f"(백엔드가 id 등 부가 키를 함께 넘긴다면 strict_fields=False 로 호출하세요)"
        )
    return UserProfile(**{k: v for k, v in user.items() if k in valid})


def _error(message: str, error_type: str) -> dict[str, Any]:
    return {"status": "error", "message": message, "error_type": error_type}


# ==========================================================================
#  (E) ★ 엔트리포인트 — CLI 실행과 백엔드 호출을 겸한다
# ==========================================================================
def main(
    client: GeminiClient | None = None,
    user: UserProfile | dict | None = None,
    job_key: str = "",
    region: str = "KR",
    questions: list[Any] | None = None,
    tone: str = "",
    store: ReferenceStore | None = None,
    num_style_examples: int = 3,
    reference_max_chars_each: int = 1400,
    use_company_research: bool = True,
    include_writing_guide: bool = True,
    include_action_plan: bool = True,
    max_grounding_iterations: int = 2,
    polish: bool = True,
    industry: str = "",
    rank_experiences: bool = True,
    max_core_experiences: int | None = None,
    max_supporting_experiences: int | None = None,
    # ---- main() 전용(파이프라인에 전달되지 않는) 옵션 ----
    api_key: str | None = None,
    model_name: str | None = None,
    verbose: bool = True,
    strict_fields: bool = True,
) -> dict[str, Any]:
    """문항별 완성형 자소서를 생성해 envelope dict 로 반환한다.

    반환
        성공: {"status": "success", "result": {...}}
        실패: {"status": "error", "message": "...", "error_type": "..."}

    파라미터 (앞 18개는 generate_application() 과 1:1 대응)
        client        : GeminiClient. None 이면 api_key/model_name 으로 새로 만든다.
        user          : UserProfile 또는 dict. None 이면 (C) 구역의 기본 프로필.
        job_key       : "backend"/"frontend"/"data"/"pm"/"marketing"/"sales"/"hr"/
                        "finance"/"design"/"research"/"operations"/"general".
                        한글·약어 별칭 자동 인식("백엔드"→backend). 공란이면 general.
        region        : "KR"(한국형 문항형) 또는 "US"(비즈니스 레터형).
        questions     : 문항 목록. "문자열" 또는 {"question": str, "max_chars": int}.
                        None 이면 (D) 구역의 QUESTIONS. 빈 리스트면 자유 형식 1건.
        tone          : 추가 톤 요청. 비우면 직무 기본 톤.
        store         : ReferenceStore(모범 자소서 DB). None 이면 (B) 구역 기본값.
        num_style_examples       : 프롬프트에 넣을 few-shot 문체 예시 개수.
        reference_max_chars_each : 예시 1건당 최대 글자수(토큰 절약용 컷).
        use_company_research     : True 면 target_company 를 Google 검색으로 조사해
                                   회사 가치를 글의 방향에 은은하게 반영.
        include_writing_guide    : 문항별 '내 것으로 만드는 가이드' 생성 여부.
        include_action_plan      : (부가) HR 관점 커리어 액션플랜 생성 여부.
        max_grounding_iterations : 환각 검증→교정 반복 최대 횟수.
        polish                   : 어미·반복·맞춤법 최종 다듬기 패스 수행 여부.
        industry      : "finance"/"it"/"manufacturing"/"public"/"consulting"/
                        "commerce"/"bio". 비우면 회사명·직무명에서 자동 추정.
        rank_experiences         : True 면 이력 전체를 지원 회사 기준으로 채점해
                                   주목할 경험을 우선 선별하고 시간 순으로 배치.
                                   False 면 모델이 알아서 고르는 이전 동작.
        max_core_experiences     : 깊게 쓸 핵심 경험 수. None 이면 문항 글자수에서
                                   자동 산정(1000자 → 핵심 1 + 보조 2).
        max_supporting_experiences : 핵심을 잇는 보조 경험 수. None 이면 자동 산정.
                                   분량이 넘칠 때 이 값을 줄이는 것이 첫 대응책.

    main() 전용 옵션
        api_key       : Gemini API 키. None 이면 환경변수/config.py 값 사용.
                        (client 를 직접 넘기면 무시된다)
        model_name    : 모델명. None 이면 config.GEMINI_MODEL_NAME("gemini-2.5-flash").
        verbose       : True 면 사람이 읽는 결과를 표준출력에 print 한다(CLI용).
                        서버에서는 False 를 권장.
        strict_fields : user 를 dict 로 넘겼을 때 모르는 키를 오류로 볼지 여부.
    """
    # ---- 입력 정규화 (여기서 난 오류도 envelope 로 감싸 돌려준다) ----
    try:
        resolved_user = coerce_user_profile(user, strict_fields=strict_fields)
        resolved_questions = QUESTIONS if questions is None else questions
        resolved_store = build_reference_store() if store is None else store

        if client is None:
            client = GeminiClient(api_key=api_key, model_name=model_name)
    except Exception as exc:
        if verbose:
            print(f"[입력 오류] {type(exc).__name__}: {exc}")
        return _error(str(exc), type(exc).__name__)

    if verbose:
        # 750:250 균형 점검(레퍼런스 데이터가 없으면 0건으로 표시됨)
        print(resolved_store.balance_report())

    # ---- 파이프라인 실행 ----
    try:
        result = generate_application(
            client=client,
            user=resolved_user,
            job_key=job_key,
            region=region,
            questions=resolved_questions,
            tone=tone,
            store=resolved_store,
            num_style_examples=num_style_examples,
            reference_max_chars_each=reference_max_chars_each,
            use_company_research=use_company_research,
            include_writing_guide=include_writing_guide,
            include_action_plan=include_action_plan,
            max_grounding_iterations=max_grounding_iterations,
            polish=polish,
            industry=industry,
            rank_experiences=rank_experiences,
            max_core_experiences=max_core_experiences,
            max_supporting_experiences=max_supporting_experiences,
        )
    except Exception as exc:
        message = str(exc)
        if verbose:
            print(f"[생성 실패] {type(exc).__name__}: {message}")
        return _error(message, type(exc).__name__)

    # 사람이 읽는 CLI 출력 (서버에서는 verbose=False 로 끈다)
    if verbose:
        print(format_application(result))

    # 프론트엔드/ API 용 구조화 payload
    #   result_to_json() 은 char_count / sentences / experience_selection 등
    #   화면 구현에 필요한 파생 필드까지 포함한다(asdict 보다 상위집합).
    return {"status": "success", "result": result_to_json(result)}


if __name__ == "__main__":
    main()
