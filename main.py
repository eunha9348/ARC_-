"""
main.py
============================================================================
AI 자기소개서 '생성' 서비스 — 실행 진입점.

★ 이 프로그램은 자소서를 '대신 써 주는' 서비스입니다.
  사용자의 사실 데이터만을 재료로, 문항별로 그대로 제출 가능한 수준의
  완성형 자소서를 생성하고, 그 글을 사용자가 자기 것으로 소화하도록
  돕는 '작성 가이드'를 함께 제공합니다.

여기서 하는 일:
  (A) API 키/모델 확인  (실제 키는 cover_letter_ai/config.py 에 입력)
  (B) 모범 자소서(레퍼런스) DB 연결  ← 다른 코드/DB에서 주입(여기선 공란)
  (C) ★ 사용자 데이터 입력 ★         ← 실행 시 '직접' 채워 넣는 부분(공란)
  (D) 자소서 문항 입력               ← 지원할 회사의 실제 문항들
  (E) 파이프라인 실행 → 문항별 완성형 자소서 + 가이드 + (부가) 액션플랜

────────────────────────────────────────────────────────────────────────
사용 방법
  1) cover_letter_ai/config.py 의 GOOGLE_AI_STUDIO_API_KEY 에 키 입력
     (또는 환경변수 GOOGLE_AI_STUDIO_API_KEY 설정)
  2) 아래 (C) 구역의 UserProfile(...) 에 본인 사실 데이터 입력
  3) 아래 (D) 구역의 QUESTIONS 에 지원할 회사의 자소서 문항 입력
  4) python main.py 실행
────────────────────────────────────────────────────────────────────────
"""

from cover_letter_ai import (
    GeminiClient,
    UserProfile,
    ReferenceExample,
    ReferenceStore,
    generate_application,
    format_application,
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
#  (C) ★★★ 사용자 데이터 입력 구역 ★★★
# --------------------------------------------------------------------------
#  실행 시 본인의 '사실'만 채워 넣으세요. (현재는 모두 공란)
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
#  (D) 자소서 문항 입력 — 지원할 회사의 실제 문항을 그대로 넣으세요
# --------------------------------------------------------------------------
#  여러 문항을 넣으면 문항별 완성형 자소서가 각각 생성됩니다.
#  비워 두면([]) 자유 형식 1건이 생성됩니다.
# ==========================================================================
QUESTIONS = [
    # 예:
    # {"question": "지원동기와 입사 후 포부를 기술하시오.", "max_chars": 1000},
    # {"question": "가장 도전적이었던 경험과 그 과정에서 배운 점을 기술하시오.", "max_chars": 1500},
    # {"question": "본인의 강점과 이를 직무에 어떻게 활용할지 기술하시오.", "max_chars": 800},
]


def main():
    # ---- (A) 클라이언트 준비 (API 키/모델은 config.py 에서) ----
    client = GeminiClient()   # config.py 의 키/모델(gemini-2.5-flash) 사용

    # ---- (B) 레퍼런스 스토어 ----
    store = build_reference_store()
    print(store.balance_report())   # 750:250 균형 점검(데이터 없으면 0건)

    # ---- (C) 사용자 데이터 ----
    user = build_user_profile()

    # ---- (E) 파이프라인 실행: 문항별 완성형 자소서 생성 ----
    result = generate_application(
        client=client,
        user=user,
        job_key="",                  # 예: "backend" / "data" / "marketing" (공란 시 general)
        region="KR",                 # "KR"(한국형) 또는 "US"(미국형)
        questions=QUESTIONS,         # (D) 에서 입력한 문항들
        tone="",                     # 추가 톤 요청(비우면 직무 기본 톤)
        store=store,
        num_style_examples=3,        # few-shot 문체 예시 개수
        use_company_research=True,   # ★ 지원 회사 가치를 검색해 은은하게 반영
        include_writing_guide=True,  # '내 것으로 만드는 가이드' 포함
        include_action_plan=True,    # (부가) HR 관점 액션플랜 포함
        max_grounding_iterations=2,  # 환각 검증→교정 반복 횟수
        polish=True,                 # 최종 문체 다듬기 패스(어미·반복 정리)
    )

    print(format_application(result))


if __name__ == "__main__":
    main()
