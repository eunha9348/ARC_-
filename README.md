# Cover Letter AI — 자기소개서를 '대신 써 주는' AI 생성 서비스

Google AI Studio의 **Gemini(`gemini-2.5-flash`)** 를 사용해, **사용자 본인의 사실 데이터**를
재료로 **그대로 제출 가능한 수준의 완성형 자기소개서를 문항별로 생성**하는 서비스입니다.

> 첨삭 도구가 아닙니다. AI가 자소서를 **직접 써 주고**, 그 글을 사용자가 자기 것으로
> 소화해 최종 제출본을 완성하도록 **작성 가이드**까지 함께 제공합니다.

## 사용 방법 (Colab / 아이패드)

1. 이 저장소의 **`cover_letter_ai_all_in_one.py`** 파일을 열고 전체 내용을 복사
2. Google Colab 새 노트북의 **코드 셀 1개**에 그대로 붙여넣기
3. 파일 안의 표시된 구역만 채우기:
   - `[1. API 키 설정]` — Google AI Studio 키 입력
   - `[9. 사용자 데이터 입력]` — 본인의 사실(경력/프로젝트/스킬 + **지원 회사명**)
   - `[10. 자소서 문항 입력]` — 지원할 회사의 실제 문항들
4. 셀 실행(▶️)

## 무엇이 나오나 (출력물)

1. **★ 문항별 완성형 자소서** — 주 결과물. 핵심 경험 1~2개를
   What/When/Where/How + 결과·성과가 이어지는 완결된 이야기로 깊게 서술
2. **근거 검증 결과** — 사용자 데이터에 없는 내용(환각)이 없는지 자동 확인
3. **이 자소서를 내 것으로 만드는 가이드** — 글의 전략/문단별 해설, 본인만 아는
   디테일을 더할 위치, 제출 전 체크리스트, 예상 면접 질문
4. **(참고) 지원 회사 리서치 요약** — Google 검색으로 조사한 회사 가치/인재상
5. **(부가) HR 관점 커리어 액션플랜** — 다음 지원까지 이력을 보강하는 제안

## 핵심 기능

### 🔍 회사 맞춤 (Google 검색 그라운딩)
`target_company` 에 회사명을 넣으면 **Gemini의 Google 검색 그라운딩**으로 회사의
미션/핵심가치/인재상/최근 사업 방향을 자동 조사합니다. 조사 결과는 **노골적으로
인용되지 않고**, 경험 선택·강조점·포부의 방향에만 은은하게 스며들도록(penetrate)
프롬프트로 제어됩니다.

### ✍️ 서술 품질 규칙
- **나열 금지**: 여러 경험을 얕게 훑지 않고, 문항·회사에 가장 맞는 경험 1~2개를
  6하원칙(What/When/Where/How)과 결과·성과 중심으로 깊게 서술
- **돌림노래 금지**: 같은 강점·성과를 표현만 바꿔 반복하지 않음
- **어미·시점**: '~했습니다'체로 통일하되 단조롭지 않게 문장 구조를 변주,
  "~전문가이다" 같은 3인칭 관찰자식 표현 금지 (1인칭 유지)
- 생성 후 **최종 다듬기(polish) 패스**가 어미/반복/맞춤법을 한 번 더 정리

### 🛡️ 환각 방지 (제1원칙)
- 지원자의 사실은 오직 **사용자 데이터(UserProfile)** 에서만 나옵니다
- 모범 자소서(한국형 750 + 미국형 250 목표)는 **문체 참조로만** 사용, 내용 복사 금지
- 생성 후 **근거 검증(grounding) 패스**가 사용자 데이터에 없는 주장을 자동 탐지·교정
- 회사 관련 서술은 검색 리서치 결과 범위 안에서만 허용

### 🗂️ 직무별 구분
12개 직무(백엔드/데이터/마케팅/HR 등)별 스타일·양식·HR 평가 포인트로 분기.
한글/약어 별칭 자동 인식(`"백엔드"→backend`), 한국형(KR)/미국형(US) 문화 차이 반영.

## 파이프라인

```
회사 리서치(Google 검색) → 완성형 집필 → 근거 검증(환각 탐지) → 교정(반복)
→ 최종 다듬기(어미·반복·맞춤법) → 작성 가이드 → (부가) 액션플랜
```

## 브랜치 안내

- **`main`**: Colab 복붙용 단일 파일 (`cover_letter_ai_all_in_one.py`) ← 이 파일을 쓰세요
- **`claude/cover-letter-ai-generator-7uvjuj`**: 동일 로직의 모듈형 패키지 (로컬/서버·DB 연동용)

---

# Career Analysis AI — COMPREHENSIVE Edition v3.0

종합 커리어 분석 모듈. v2.0 에서 발생한 **환각(Hallucination) 장애**를 구조적으로
재설계한 버전입니다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `career_analysis_comprehensive.py` | 분석 파이프라인 (크롤링 → 분석 → 검증 → 출력) |
| `hallucination_guard.py` | 환각 차단 가드 (URL 프로브·그라운딩 대조·자격증 레지스트리·STAR 근거 결속) |
| `star_quality.py` | STAR 작성 품질 채점 (10개 루브릭 + 개선 지시) |
| `analysis_response.py` | 응답 envelope 모델 (pydantic 선택 의존) |
| `tests/test_hallucination_guard.py` | 환각 가드 회귀 테스트 25건 |
| `tests/test_star_quality.py` | STAR 품질 회귀 테스트 18건 |
| `docs/field_report_hallucination_v3.html` | 장애 원인 분석 필드 리포트 |

## 실행

```bash
export GEMINI_API_KEY="..."          # 소스 하드코딩 금지 (v3.0에서 제거)
export USER_SCHOOL="서울대학교"        # 선택
export USER_DEPARTMENT="경영학과"      # 선택

cat my_career.txt | python3 career_analysis_comprehensive.py

python3 tests/test_hallucination_guard.py   # 회귀 테스트
```

## v2.0 에서 무엇이 문제였나

프롬프트에 9개의 환각 방지 규칙이 있었지만, **코드가 규칙과 반대 방향으로 강제**하고
있었습니다.

| 증상 | 구조적 원인 |
|---|---|
| 동아리·학회 추천에 접속 불가 URL | "최소 3개 추천" 쿼터가 "확실하지 않으면 제외"를 무력화. URL 은 HTTP 확인 없이 모델 주장을 그대로 부착 |
| STAR 가 입력 문장 재구조화 / 없는 내용 창작 | 규칙은 "부족하면 만들지 말라"였지만 스키마에 `resume_star_format` 이 예시와 함께 항상 존재. STAR 만 근거 인용 의무에서 제외 |
| 존재하지 않는 자격증 추천 | 생성자와 검증자가 같은 모델. `use_google_search=True` 만 넘기고 실제 검색 여부(`grounding_metadata`)는 미확인 |

전체 13개 결함의 코드 근거는 필드 리포트를 참고하십시오.

## v3.0 의 환각 차단 구조

신뢰 원천을 셋으로 한정하고, 그 밖의 값은 코드가 기계적으로 제거합니다 —
**사용자 입력 원문 / 검색 그라운딩 메타데이터 / 실제 HTTP 응답**.

- **F-1 쿼터 폐지** — 최소 개수 요구와 재추천 루프 삭제. 0개도 정상 결과이며 사유를 함께 반환
- **F-2 URL 무생성** — 스키마에서 `url` 필드 제거. 검색 근거 URI 만 후보가 되며
  `probe_url()` 의 200 + soft-404 탐지 + 본문 토큰 대조를 통과해야 부착
- **F-3 그라운딩 강제** — `grounding_chunks` 파싱으로 실제 검색 여부 확인, 항목명이
  검색 근거에 등장하는지 코드가 직접 대조. 모델의 `"verified": true` 는 무효
- **F-4 반증형 이중 검증** — "존재하지 않는다는 증거를 찾아라"로 프롬프트를 뒤집고,
  온도가 다른 2회 호출이 모두 통과해야 인정
- **F-5 자격증 레지스트리** — 자격증별 유효 등급 집합을 코드가 보유해
  `빅데이터분석기사 2급` 류 등급 환각을 네트워크 호출 없이 차단
- **F-6 STAR 근거 결속** — 생성 전 입력 적합성 판정(미달 시 요청 자체를 생략),
  생성 후 슬롯별 원문 인용 대조 · 수치 환각 삭제 · 슬롯 간 중복 시 '재구조화' 강등
- **F-7 fail-closed 일관화** — 누락 필드 기본값을 전부 불합격으로 통일
- **F-8 감사 추적** — `verification_audit` / `rejected_by_guard` 로 제거 사유 전량 노출

### 트레이드오프

검증을 통과한 항목만 남으므로 **추천 개수가 줄고 빈 결과가 늘어납니다.** 의도된
교환이며, 빈 결과에는 항상 사유와 사용자가 직접 확인할 검색어가 따라붙습니다.

## v3.1 — STAR 품질 채점

v3.0 은 STAR 의 *환각*을 잡았습니다. 그러나 환각이 없다고 좋은 STAR 가 되지는
않습니다 — 근거만 지키면 STAR 는 쉽게 "사용자 문장을 네 칸에 나눠 담은 것"에
머뭅니다. v3.1 은 그 다음 관문인 **작성 품질**을 채점합니다.

### 전문성은 사실을 늘려서 만들지 않는다

"전문적인 STAR"를 만드는 흔한 방법은 그럴듯한 배경과 성과를 덧붙이는 것이고,
그것이 정확히 v2.0 이 실패한 방식입니다. v3.1 은 반대 경로를 씁니다.

| 축 | 무엇을 하는가 |
|---|---|
| 선택 | 어떤 경험을 STAR 로 쓸지 고르는 판단 |
| 배분 | Action 이 절반을 차지하도록 분량 재배치 |
| 표현 | "~를 했습니다"를 '강한 동사 + 맥락 + 결과' 성취문으로 |
| 진단 | 부족한 요소는 지어내지 않고 '무엇이 비었는지' + 채우는 법 |

새 사실은 만들지 않습니다. 이미 근거가 검증된 문장이 **어떻게 쓰였는가**만
평가하고, 미달 항목마다 구체적 개선 지시를 답니다.

### 채점 루브릭 (10개, 등급 A~D)

`분량 배분(Action 40~50%)` · `배경 간결성(S+T 30% 이하)` · `개인 기여(1인칭)` ·
`방법 구체성` · `성취 동사` · `결과 정량화` · `결과의 파급` · `모호 표현 배제` ·
`슬롯 역할 분리` · `맥락 규모`

품질 미달이라고 항목을 **버리지 않습니다.** 버리면 사용자가 무엇을 고쳐야 하는지
알 수 없기 때문입니다. 대신 등급과 우선 개선 지시를 붙입니다.

```
── 나열식 STAR: D (0/10)
   ✗ Action 비중: Action 이 전체의 12% (권장 40~50%)
   ✗ 개인 기여 명시: Action 에 공동 주어 1회, 개인 주체 표현 없음
   ✗ 결과 정량화: Result 에 수치 지표가 있는지
   ✗ 슬롯 역할 분리: Situation·Task 내용 중복도 80%
   → "Action 을 늘리십시오. 본인이 무엇을 어떤 순서로 했는지 2~3단계로 쪼개 쓰면…"

── 전문 수준 STAR: A (10/10)
   제출 가능한 수준. 구조·주체·수치가 모두 갖춰져 있습니다.
```

### 추가된 요약 계층

- **`headline`** — 이력서에 그대로 넣을 수 있는 한 줄 성취문 (강한 동사 + 맥락 + 결과).
  S/T/A/R 에 이미 있는 사실만으로 구성하며, 원문에 없는 수치는 자동 삭제됩니다.
- **`competency_evidence`** — 이 경험이 증명하는 역량과 그 판단 근거. 사실이 아니라
  해석이므로 창작이 아니지만, 근거는 반드시 S/T/A/R 안에 있어야 합니다.
- **`L` (회고)** — 표준 STAR 에 회고 한 겹을 더한 STARR/STAR-L 형태.
  **원문에 배움이 명시된 경우에만** 남고, 없으면 삭제됩니다. "무엇을 느꼈을 것이다"는
  추측이므로 금지입니다.

### STAR 품질 기준 출처

루브릭은 공개 커리어 가이드·대학 커리어센터 자료에서 반복 확인되는 규칙을 코드화한
것입니다.

- [MIT CAPD — The STAR method for behavioral interviews](https://capd.mit.edu/resources/the-star-method-for-behavioral-interviews/) — 컴포넌트별 분량 배분
- [Case Western Reserve — STAR Strategy Examples](https://case.edu/studentlife/careercenter/career-educationtips-job-seekersinterviewingbehavior-based-interviewing/star-strategy-examples)
- [UNM Career Services — The STAR Method (PDF)](https://career.unm.edu/career-tools/the-star-method-2020.pdf)
- [Yale OCS — Writing Impactful Resume Bullets](https://ocs.yale.edu/resources/writing-impactful-resume-bullets/) — 성취문 공식
- [Columbia CCE — Resumes with Impact: Creating Strong Bullet Points](https://www.careereducation.columbia.edu/resources/resumes-impact-creating-strong-bullet-points)
- [UC Davis Career Center — Accomplishment Statements](https://careercenter.ucdavis.edu/resumes-and-materials/resumes/accomplishment-statements) — 강한 동사 + 맥락 = 결과
- [The Interview Guys — The STAR Method (2026)](https://blog.theinterviewguys.com/the-star-method/) — "I" vs "we", Action 비중
- [Monster — How to Create a STAR Method Resume](https://www.monster.com/career-advice/resume/star-method-resume) — 정량화 요건
- [Toolshero — STARR method for reflection](https://www.toolshero.com/personal-development/starr-method/) — 회고 계층
- [DDI — STAR Method for Interviewing and Feedback](https://www.ddi.com/solutions/behavioral-interviewing/star-method)

## 주의

- 모범 자소서 원문은 저작권/개인정보에 유의해 적법하게 수집·보관하세요.
- 생성된 자소서는 제출 전 반드시 본인이 읽고 사실관계를 최종 확인하세요.
- 액션플랜은 *미래 제안*이며, "이미 했다"는 사실로 자소서에 반영되지 않습니다.
