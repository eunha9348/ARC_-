# Cover Letter AI — 자기소개서를 '대신 써 주는' AI 생성 서비스

Google AI Studio의 **Gemini(`gemini-2.5-flash`)** 를 사용해, **사용자 본인의 사실 데이터**를
재료로 **그대로 제출 가능한 수준의 완성형 자기소개서를 문항별로 생성**하는 서비스입니다.

> 첨삭 도구가 아닙니다. AI가 자소서를 **직접 써 주고**, 그 글을 사용자가 자기 것으로
> 소화해 최종 제출본을 완성하도록 **작성 가이드**까지 함께 제공합니다.

## 무엇이 나오나 (출력물)

1. **★ 문항별 완성형 자소서** — 주 결과물. 핵심 경험 1~2개를
   What/When/Where/How + 결과·성과가 이어지는 완결된 이야기로 깊게 서술
2. **근거 검증 결과** — 사용자 데이터에 없는 내용(환각)이 없는지 자동 확인한 리포트
3. **이 자소서를 내 것으로 만드는 가이드** — 글의 전략/문단별 해설, 본인만 아는 디테일을
   더할 위치, 제출 전 체크리스트, 예상 면접 질문
4. **(참고) 지원 회사 리서치 요약** — Google 검색으로 조사한 회사 가치/인재상
5. **(부가) HR 관점 커리어 액션플랜** — 다음 지원까지 이력을 보강하는 제안

## 회사 맞춤 (Google 검색 그라운딩)

`target_company` 에 회사명을 넣으면 **Gemini의 Google 검색 그라운딩**으로 회사의
미션/핵심가치/인재상/최근 사업 방향을 자동 조사합니다. 조사 결과는 **노골적으로
인용되지 않고**, 경험 선택·강조점·포부의 방향에만 은은하게 스며들도록(penetrate)
프롬프트로 제어됩니다.

## 서술 품질 규칙

- **나열 금지**: 여러 경험을 얕게 훑지 않고, 문항·회사에 가장 맞는 경험 1~2개를
  6하원칙(What/When/Where/How)과 결과·성과 중심으로 깊게 서술
- **돌림노래 금지**: 같은 강점·성과를 표현만 바꿔 반복하지 않음
- **어미·시점**: '~했습니다'체로 통일하되 단조롭지 않게 문장 구조를 변주,
  "~전문가이다" 같은 3인칭 관찰자식 표현 금지 (1인칭 유지)
- 생성 후 **최종 다듬기(polish) 패스**가 어미/반복/맞춤법을 한 번 더 정리

## 실행 방법 2가지

| 방법 | 파일 | 이럴 때 사용 |
|---|---|---|
| **Colab / 아이패드** | `main` 브랜치의 `cover_letter_ai_all_in_one.py` | 파일 내용을 통째로 복사해 Colab 코드 셀 1개에 붙여넣고 실행 |
| **로컬/서버 (모듈형)** | `main.py` + `cover_letter_ai/` 패키지 | PC에서 파일 여러 개로 관리하며 DB 연동 |

두 버전은 로직이 완전히 동일합니다.

## 핵심 설계 원칙

1. **제1원칙 — 환각(Hallucination) 방지**
   자소서 *내용의 사실*은 오직 **사용자 데이터(UserProfile)** 에서만 나옵니다.
   - 모범 자소서 1000개(한국형 750 + 미국형 250)는 **문체·구조 참조(스타일)** 로만 사용하고,
     그 내용을 복사하지 않습니다. (few-shot 스타일 예시 방식)
   - 생성 후 **근거 검증(grounding) 패스**로 사용자 데이터에 없는 주장을 자동 탐지하고,
     발견되면 **자동 교정**으로 제거/수정합니다.
2. **제2원칙 — 맞춤법/문맥/문체**
   자소서 특유의 담백한 문어체를 프롬프트로 강제하고, 생성 후 **최종 다듬기(polish) 패스**로
   제출 직전 수준까지 완성도를 끌어올립니다.
3. **직무별 구분**
   `job_profiles.py` 의 직무 프로필(스타일/양식/HR 평가 포인트)로 생성·가이드·액션플랜을
   분기합니다. 한국형(KR)/미국형(US) 문화 차이도 반영합니다.

## 설치

```bash
pip install -r requirements.txt
```

## 실행 준비 (3가지만 채우면 됩니다)

1. **API 키 / 모델** — `cover_letter_ai/config.py`
   - `GOOGLE_AI_STUDIO_API_KEY = ""` 에 키 입력 (또는 환경변수 `GOOGLE_AI_STUDIO_API_KEY`)
   - 모델은 `GEMINI_MODEL_NAME = "gemini-2.5-flash"` 로 고정되어 있습니다.
2. **사용자 데이터** — `main.py` 의 `build_user_profile()` (현재 전부 공란)
   - 본인의 *사실*만 채워 넣으세요. 여기 없는 내용은 자소서에 등장하지 않습니다.
3. **자소서 문항** — `main.py` 의 `QUESTIONS` 리스트
   - 지원할 회사의 실제 문항들을 넣으면 문항별로 각각 생성됩니다. 비우면 자유 형식 1건.

그런 다음:

```bash
python main.py
```

## 구조

```
main.py                      # 실행 진입점 (API 키/데이터/문항은 여기·config에서 주입)
requirements.txt
cover_letter_ai/
  config.py                  # ★ API 키 입력 + 모델(gemini-2.5-flash) 선택 구역
  core/
    data_models.py           # UserProfile / AnswerResult / ApplicationResult 등
    job_profiles.py          # 직무별 스타일·양식·HR 평가 포인트 사전
    reference_store.py       # 모범 자소서 DB 연결 + few-shot 예시 선별(KR750:US250)
    prompt_builder.py        # 완성형 집필·환각방지·최종 다듬기 프롬프트 조립
    gemini_client.py         # Gemini 호출 래퍼(신형/구형 SDK 자동 폴백)
    generator.py             # 집필 → 근거검증(환각탐지) → 교정 → 최종 다듬기
    writing_guide.py         # '이 자소서를 내 것으로 만드는 가이드' 생성
    action_plan.py           # (부가) HR 관점 액션플랜 제안
    pipeline.py              # 문항별 생성 오케스트레이션 + 결과 포매팅
```

## 함수 위주 사용 예 (DB/데이터는 직접 주입)

```python
from cover_letter_ai import (
    GeminiClient, UserProfile, ReferenceStore,
    generate_application, format_application,
)

client = GeminiClient()                 # config.py 의 키/모델 사용

user = UserProfile(                      # ← 사용자 사실만 입력
    target_company="", target_job="", projects=[], skills=[],  # ...
)

result = generate_application(
    client=client,
    user=user,
    job_key="backend",
    region="KR",
    questions=[
        {"question": "지원동기와 입사 후 포부를 기술하시오.", "max_chars": 1000},
        {"question": "가장 도전적이었던 경험을 기술하시오.", "max_chars": 1500},
    ],
    store=ReferenceStore(),              # DB 로더 주입 가능(없어도 동작)
)
print(format_application(result))
```

## 지원 직무 key

`backend, frontend, data, pm, marketing, sales, hr, finance, design, research, operations, general`
(한글/약어 별칭 자동 인식: 예 `"백엔드"→backend`, `"그로스"→marketing`)

## 주의

- 모범 자소서 원문은 저작권/개인정보에 유의해 적법하게 수집·보관하세요.
  본 도구는 그 내용을 복제하지 않고 문체 참조로만 사용하도록 설계했습니다.
- 액션플랜은 *미래 제안*이며, "이미 했다"는 사실로 자소서에 반영되지 않습니다.
- 생성된 자소서는 제출 전 반드시 본인이 읽고 사실관계를 최종 확인하세요.
