# Cover Letter AI (자기소개서 AI 생성기)

Google AI Studio의 **Gemini(`gemini-2.5-flash`)** 를 사용해, **사용자 본인의 데이터**를
근거로 직무 맞춤 자기소개서를 생성·검증·첨삭하고, HR 관점의 액션플랜까지 제안하는 도구입니다.

## 실행 방법 2가지

| 방법 | 파일 | 이럴 때 사용 |
|---|---|---|
| **Colab / 아이패드** | [`cover_letter_ai_colab.ipynb`](./cover_letter_ai_colab.ipynb) | 태블릿, Google Colab에서 셀 단위로 실행 |
| **로컬/서버 (모듈형)** | `main.py` + `cover_letter_ai/` 패키지 | PC에서 파일 여러 개로 관리하며 DB 연동 |

두 버전은 로직이 완전히 동일합니다. Colab 노트북은 모든 모듈을 한 파일에 셀 단위로 통합한 버전입니다.

### Colab에서 열기
1. GitHub에서 `cover_letter_ai_colab.ipynb` 파일 페이지로 이동 → **Raw** 또는 파일 자체를 열고,
   주소창의 `github.com` 을 `colab.research.google.com/github` 으로 바꿔 접속하면 바로 Colab으로 열립니다.
   예: `https://colab.research.google.com/github/eunha9348/ARC_-/blob/claude/cover-letter-ai-generator-7uvjuj/cover_letter_ai_colab.ipynb`
2. 위에서부터 셀을 순서대로 실행(▶️ 또는 `Runtime → Run all`).
3. **[API 키 설정]** 셀에 키 입력, **[사용자 데이터 입력]** 셀에 본인 사실 입력 후 **[실행]** 셀 실행.
4. 키를 코드에 남기고 싶지 않으면 Colab 왼쪽 🔑(Secrets)에 `GOOGLE_AI_STUDIO_API_KEY` 이름으로 등록하면 자동 인식됩니다.

## 핵심 설계 원칙

1. **제1원칙 — 환각(Hallucination) 방지**
   자소서 *내용의 사실*은 오직 **사용자 데이터(UserProfile)** 에서만 나옵니다.
   - 모범 자소서 1000개(한국형 750 + 미국형 250)는 **문체·구조 참조(스타일)** 로만 사용하고,
     그 내용을 복사하지 않습니다. (few-shot 스타일 예시 방식)
   - 생성 후 **근거 검증(grounding) 패스**로 사용자 데이터에 없는 주장을 자동 탐지하고,
     발견되면 **자동 교정**으로 제거/수정합니다. (`temperature=0.25`, 검증은 `0.0`)
2. **제2원칙 — 맞춤법/문맥/문체**
   자소서 특유의 담백한 문어체, 맞춤법·띄어쓰기·문맥 자연스러움을 프롬프트로 강제합니다.
3. **직무별 구분**
   `job_profiles.py` 의 직무 프로필(스타일/양식/HR 평가 포인트)로 생성·첨삭·액션플랜을 분기합니다.
   한국형(KR)/미국형(US) 문화 차이도 반영합니다.

## 설치

```bash
pip install -r requirements.txt
```

## 실행 준비 (2가지만 채우면 됩니다)

1. **API 키 / 모델** — `cover_letter_ai/config.py`
   - `GOOGLE_AI_STUDIO_API_KEY = ""` 에 키 입력 (또는 환경변수 `GOOGLE_AI_STUDIO_API_KEY`)
   - 모델은 `GEMINI_MODEL_NAME = "gemini-2.5-flash"` 로 고정되어 있습니다.
2. **사용자 데이터** — `main.py` 의 `build_user_profile()` (현재 전부 공란)
   - 본인의 *사실*만 채워 넣으세요. 여기 없는 내용은 자소서에 등장하지 않습니다.

그런 다음:

```bash
python main.py
```

## 구조

```
main.py                      # 실행 진입점 (API 키/데이터는 여기·config에서 주입)
requirements.txt
cover_letter_ai/
  config.py                  # ★ API 키 입력 + 모델(gemini-2.5-flash) 선택 구역
  core/
    data_models.py           # UserProfile / ReferenceExample / 결과 구조
    job_profiles.py          # 직무별 스타일·양식·HR 평가 포인트 사전
    reference_store.py       # 모범 자소서 DB 연결 + few-shot 예시 선별(KR750:US250)
    prompt_builder.py        # 환각방지·문체·직무 규칙을 담은 프롬프트 조립
    gemini_client.py         # Gemini 호출 래퍼(신형/구형 SDK 자동 폴백)
    generator.py             # 생성 → 근거검증(환각탐지) → 자동교정
    reviewer.py              # 직무 맞춤 '수정 제안'
    action_plan.py           # HR 관점 '액션플랜' 제안
    pipeline.py              # 전 과정 오케스트레이션 + 결과 포매팅
```

## 함수 위주 사용 예 (DB/데이터는 직접 주입)

```python
from cover_letter_ai import (
    GeminiClient, UserProfile, GenerationRequest,
    ReferenceStore, generate_cover_letter_package, format_result,
)

client = GeminiClient()                 # config.py 의 키/모델 사용

user = UserProfile(                      # ← 사용자 사실만 입력
    target_company="", target_job="", projects=[], skills=[],  # ...
)

req = GenerationRequest(
    user=user, job_key="backend", region="KR",
    question="지원동기와 입사 후 포부를 기술하시오.", max_chars=1000,
)

store = ReferenceStore()                 # DB 로더 주입 가능(없어도 동작)

result = generate_cover_letter_package(client, req, store=store)
print(format_result(result))
```

## 지원 직무 key

`backend, frontend, data, pm, marketing, sales, hr, finance, design, research, operations, general`
(한글/약어 별칭 자동 인식: 예 `"백엔드"→backend`, `"그로스"→marketing`)

## 주의

- 모범 자소서 원문은 저작권/개인정보에 유의해 적법하게 수집·보관하세요.
  본 도구는 그 내용을 복제하지 않고 문체 참조로만 사용하도록 설계했습니다.
- 액션플랜은 *미래 제안*이며, "이미 했다"는 사실로 자소서에 반영되지 않습니다.
