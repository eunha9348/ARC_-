# ARC 경험 자동 추출 엔진 — `extracter` 브랜치

활동 산출물 파일(보고서·상장·이력서·포트폴리오·사진·녹음 등)을 올리면, 그것이 ARC의 어떤 경험인지
판별하고 **그 경험 유형의 입력 칸에 맞춰 자동으로 채운 뒤, 칸마다 원문 근거와 대조한 결과**를 돌려주는
엔진입니다. 이력서처럼 한 파일에 경험이 여러 개 섞여 있으면 **경험별로 나눠 각각** 정리합니다.

- 엔진: Google Gemini — **Google API 키 하나**면 됩니다
- 언어: TypeScript (Node 20+). 한국어 근거 검증기 RAGKOR는 TypeScript·Python 두 구현이 같은 결과를 냅니다
- 이 브랜치는 ARC 저장소의 **추출 엔진 브랜치**입니다. `main`의 자기소개서 AI 파일은 그대로 두었습니다
  ([브랜치 안내](#브랜치-안내))

---

## 바로 써 보기 — Colab (PC 없이, 아이패드·휴대폰 브라우저로)

**[▶ Colab에서 열기](https://colab.research.google.com/github/eunha9348/ARC_-/blob/extracter/colab/ARC_engine.ipynb)**

1. https://aistudio.google.com/apikey 에서 키를 발급받습니다 (`AIza…`로 시작).
2. Colab 왼쪽 막대 **🔑 보안 비밀**에 이름 `GOOGLE_API_KEY`로 키를 등록하고 **노트북 액세스**를 켭니다.
   (등록하지 않으면 실행할 때 키를 물어봅니다.)
3. 첫 셀의 ▶ 를 누르고, 업로드 창이 뜨면 파일을 고릅니다.
4. 칸별 감사 결과와 원문 하이라이트가 담긴 보고서가 출력창에 나옵니다.

노트북은 이 브랜치의 엔진(`src/`)을 **그대로** 설치해서 돌립니다. 따로 옮겨 적은 판이 아니라서
여기서 보는 결과가 곧 실제 엔진의 결과입니다. 처음 실행은 설치 때문에 2~3분 걸립니다.

> 다른 브랜치나 포크에서 돌리려면 노트북의 `BRANCH`와, 실행 전 환경 변수 `ARC_REPO`·`ARC_BRANCH`를 바꾸세요.
> 같은 Colab 세션에 다른 저장소의 예전 설치본이 있으면 실행기가 알아서 새로 받습니다.

## 무엇이 나오나

| 결과물 | 내용 |
|---|---|
| **HTML 보고서** (`report.html`) | 경험별로 칸마다 [값 · 감사 상태 · 원문 근거 하이라이트]. 여러 경험이면 맨 위에 경험 목록 |
| **결과 JSON** (`result.json`) | 폼에 그대로 바인딩할 값, 화면 배치, 값별 근거 위치, 감독·감사 결과, 빈 칸 안내 |
| **빈 칸 안내** | 못 채운 칸은 비우고 "무엇을 알려 주면 채워지는지" 질문과 추가로 올리면 좋은 자료 |

보고서의 칸 색: 초록 = 확인됨 · 파랑 = 감사관이 고치거나 옮김 · 주황 = 사람이 확인 필요 ·
노란 형광펜 = 그 값의 근거가 원문 어디에 있는지.

## 처리 흐름

```
파일 업로드
   │
   ├─ ⓪ 수집 / OCR ───── 어떤 형식이든 텍스트로 (PDF·이미지·오피스·한글·음성·영상·압축)
   │
   ├─ ① 분류 ─────────── 대분류 4종 → 세부 유형 18종. 경험이 여러 개면 경험 목록 +
   │                     각 경험이 시작되는 원문 줄(anchor)
   │
   ├─ ①' 경험 분리 ───── anchor를 원문에 정렬해 경험별 구간으로 자름            LLM 0회
   │                     (경험 하나짜리 자료면 건너뜀)
   │
   └─ 경험마다 ─────────────────────────────────────────────────────────────────
        ├─ 사실 시트 ────── 값싼 모델 1회로 수치·고유명사·날짜를 먼저 추출 (누락 방지)
        ├─ ② 배분 ───────── 값싼 모델 N회 병렬 → 필드별 우수안 병합(LLM 0회) → 충돌만 중재
        ├─ ②' 기계 검증 ─── 근거 인용 → 원문 위치 정렬 · 수치 3단 판정 · 맥락 검사   LLM 0회
        ├─ ③ 감독 ───────── 원문과 대조 검수 → 환각·오배치·왜곡 적발 → 수정 패치 (재작업 기본 1회)
        ├─ ③' 필드 감사관 ─ 칸 하나씩 "이 칸에 이 칸의 정보가 들어갔나" 최종 판정    LLM 1회
        └─ ④ 빈 칸 안내 ── 못 채운 칸마다 무엇을 주면 채워지는지 질문 생성
```

### 경험 분리 (이력서·포트폴리오)

이전에는 이력서를 넣어도 대표 경험 **하나만** 정리됐습니다. 분류기가 경험 목록을 만들고도
파이프라인이 그 목록을 쓰지 않았기 때문입니다. 이제는:

1. 분류기가 경험마다 **시작 원문 줄을 글자 그대로** 냅니다 (예: `Pension AI Agent Jul 2026 - Present`).
2. 엔진이 그 줄을 원문에 정렬해 다음 경험이 시작되기 전까지를 그 경험의 구간으로 자릅니다.
   대시·따옴표 표기 차이, 줄바꿈 없는 PDF 텍스트도 처리합니다.
3. 구간마다 사실 시트부터 빈 칸 안내까지 **따로** 돌립니다. 다른 경험의 내용·수치·근거가 섞이지 않습니다.
4. 위치를 못 찾은 경험은 원문 전체를 주되 "이 경험만 정리하라"고 지시합니다.
   한 경험이 실패해도 나머지는 계속 정리하고, 실패 목록에 남깁니다.

경험은 순서대로 하나씩 정리합니다(호출 한도 회피, 경험별 비용을 정확히 나누기 위해서).
그래서 **시간과 비용은 경험 수에 비례**합니다. 나누지 않으려면 CLI에 `--single`을 붙이세요.

## 로컬에서 실행

```bash
npm install
cp .env.example .env      # GOOGLE_API_KEY=AIza... 붙여넣기
npm run check             # 키 확인 + 선택된 모델 표시
npm run kiwi:model        # (선택) Kiwi 형태소 모델 받기 — 없으면 규칙 기반으로 자동 전환

npm run serve             # → http://localhost:5174  파일을 끌어다 놓으면 폼이 채워집니다
npm run organize -- ./인턴_최종보고서.pdf --hint "작년 여름 인턴"
npm run organize -- ./이력서.pdf --html report.html --out result.json
npm test                  # API 키 없이 도는 오프라인 테스트 80건
```

| CLI 옵션 | 설명 |
|---|---|
| `--html <경로>` | 칸별 감사 결과·원문 하이라이트 HTML 보고서 저장 |
| `--out <경로>` | 결과 JSON 저장 |
| `--hint "<설명>"` | 활동에 대한 한 줄 설명 (분류·추출 참고) |
| `--type <유형id>` | 유형을 직접 지정 (분류·경험 분리 생략). 목록은 `--list-types` |
| `--quality fast\|balanced\|best` | fast = 앙상블 1회·LLM 감사 생략 / balanced(기본) / best = 배분도 상위 모델 |
| `--single` | 여러 경험이 섞인 자료도 나누지 않고 대표 경험 하나만 |
| `--json` · `--form` | 전체 JSON / 프론트 바인딩용 FormState만 출력 |

> `npm run serve`(웹 데모 서버)는 아직 경험 하나 단위로 정리합니다. 경험 분리는 CLI·Colab·라이브러리에서 됩니다.

## 라이브러리로 쓰기

```ts
import {
  organizeExperience, organizeExperiences, renderManyReport, toFormState, readInputFiles,
} from "arc-auto-organize";

// 경험 하나짜리 자료 (보고서·상장 등)
const result = await organizeExperience(await readInputFiles(["./보고서.pdf"]), {
  userHint: "동아리에서 한 프로젝트입니다",
  onProgress: (e) => console.log(e.stage, e.message),
});
result.typeLabel;              // "팀 프로젝트"
result.form.values;            // 폼에 그대로 바인딩할 값
result.provenance;             // 값마다 원문 근거 (위치 포함)
result.audit;                  // 칸별 감사 상태
result.fallback.nextQuestions; // 사용자에게 되물을 질문

// 여러 경험이 섞인 자료 (이력서·포트폴리오) — 경험 하나짜리여도 그대로 동작
const many = await organizeExperiences(await readInputFiles(["./이력서.pdf"]));
many.split.reason;             // "경험 4개로 나눠 정리합니다 (원문 위치 확인 4개)."
many.items.map((r) => toFormState(r));   // 경험마다 폼 하나
many.items[0].segment;         // 원문 어디를 잘라 썼는지
many.failed;                   // 정리하지 못한 경험
renderManyReport(many);        // 한 장짜리 HTML 보고서
```

프론트엔드 연동(Next.js 예제, `FormState` 전체 레퍼런스)은 **[USAGE.md](./USAGE.md)** 를 보세요.

## API 키

`src/config.ts` **한 곳**에만 있습니다. `.env`의 `GOOGLE_API_KEY`를 쓰면 코드는 그대로 두면 됩니다.

| 키 | 필요성 | 용도 |
|---|---|---|
| `API_KEYS.google` | **필수** | Gemini — 분류·배분·감독·안내 + 이미지 OCR + 음성 인식 |
| `API_KEYS.googleVision` | 선택 | OCR 보조. 비우면 위 키를 그대로 씀 (Cloud Vision API를 켠 경우만 동작) |
| `API_KEYS.clova` | 선택 | 한국어 증명서 특화 OCR 보조 엔진 |
| `API_KEYS.anthropic` | 선택 | 엔진을 Anthropic으로 바꿀 때만 (`ARC_LLM_PROVIDER=anthropic`) |

선택 키가 없으면 자동으로 건너뛰고 나머지 엔진으로 계속 돕니다. **모델 ID는 하드코딩하지 않습니다** —
시작할 때 사용 가능한 모델 목록을 받아 최신 세대를 고릅니다. 고정하려면 `.env`에 `GEMINI_MODEL=...`.

## 핵심 설계

### 필드 감사관 — 칸마다 맞는 정보가 들어갔는가

추출 실패의 대부분은 없는 말을 지어내는 것보다 **맞는 말을 틀린 칸에 넣는 것**입니다
(한계 문장을 '핵심 성과'에, 팀이 한 일을 '내 역할'에).

1. **필드 계약** (`src/schema/contracts.ts`) — 모든 칸에 역할(명칭·날짜·내가 한 일·성과·회고·배경·팀…)과
   "넣을 것 / 넣지 말 것"을 정의. 배분·감독·감사관이 같은 기준을 씁니다.
2. **기계 사전 감사** — 근거 위치·일치도, 수치, 맥락(섹션·문장 성격), 같은 문장의 중복 배치를 칸별로 점검.
3. **LLM 감사 1회** — 칸마다 `correct / wrong_field / distorted / incomplete / unsupported / fill` 판정.
4. **관문** — 감사관 수정은 근거 인용이 원문과 정렬되고(일치도 ≥ 0.85) 수치가 원문값·파생값일 때만 적용.
   적용 후 기계 검증에서 새 문제가 생기면 그 수정만 되돌립니다. 재작업 루프는 없습니다.

### RAGKOR — 한국어 근거 검증

감독이 멀쩡한 인용을 '환각'으로 찍던 원인은 의미가 아니라 **표기**(말줄임표·조사·오타)였습니다.
RAGKOR(`src/ragkor/`, `ragkor/`)는 이를 대체하는 규칙 기반 한국어 어휘 자원 + 자모 유사도 매처입니다.

| | 기존 | RAGKOR |
|---|---:|---:|
| 근거 검증 F1 | 0.918 | **1.000** |
| 정상 인용을 환각으로 오탐 | 21건 / 180 | **0건** |
| 말줄임표 붙은 인용 | 2/23 | **23/23** |
| 오타 복원 (사전 미수록) | — | **98.0%** |
| 근거 인용의 원문 위치 찾기 | — | **138/138** |

Kiwi 형태소 분석이 조사·어미를 떼고, 인용 위치는 RapidFuzz `partial_ratio_alignment`와 같은 방식으로
찾습니다. 자세한 분석은 [docs/RAGKOR-report.md](./docs/RAGKOR-report.md).

### OCR — 4단 설계

전처리(회전·대비·300DPI 업스케일) → **다중 엔진 병렬**(Gemini Vision 주 엔진, Cloud Vision·CLOVA·
tesseract.js 보조) → 엔진 간 합의율이 82% 미만이거나 긴 이미지는 **타일로 잘라 재판독** → 신뢰도 산출.
낮은 신뢰도 문서에서만 나온 값은 배분 단계에서 신뢰도를 낮춰 자동으로 비웁니다.

### 받는 파일 형식

| 계열 | 확장자 | 처리 |
|---|---|---|
| 문서 | pdf | 텍스트 레이어 우선 → 없는 페이지만 렌더 후 OCR |
| | docx · doc · odt · pptx · ppt · odp | 본문 + 발표자 노트까지 |
| | xlsx · xls · csv · tsv | 시트를 표 텍스트로 (열 이름 유지) |
| | hwp · hwpx | HWPX는 ZIP+XML 직접 파싱, HWP는 hwp.js / hwp5txt |
| 이미지 | png jpg webp gif bmp tiff heic avif | 전처리 + 다중 엔진 OCR, EXIF 촬영일 |
| 미디어 | mp3 m4a wav · mp4 mov mkv | Gemini 받아쓰기 (+ 영상은 장면 전환 프레임 OCR) |
| 웹/메일/코드 | html eml · ts py ipynb … | 본문 추출, 노트북은 셀 단위 분해 |
| 압축 | zip | 내부 파일 재귀 처리 (최대 40개, 깊이 2) |

확장자와 내용이 다르면 매직 넘버를 믿고, EUC-KR/CP949 한글 텍스트는 자동 감지합니다. 선택 의존성이
없어도 크래시 없이 동작하고, 무엇을 못 읽었는지 `warnings`로 알려줍니다.

### 지원 경험 유형 (18종)

| 대분류 | 유형 |
|---|---|
| 🎓 학업 | 전공 및 수강 수업 · 학회 · 동아리/교내 단체 · 연구 경험/논문 |
| 💼 커리어 | 인턴 및 업무 경력 · 대외활동 · 수상 경력 · 보유 자격증 · 어학 능력 |
| 🚀 프로젝트 | 개인 프로젝트 · 팀 프로젝트 · 창작물/작업물 |
| 🌱 개인성장 | 봉사활동 · 해외 경험 · 운동 및 신체 역량 · 독서 · 기록(일지/회고) · 목표/계획 |

전체 입력 칸 명세는 `src/schema/templates-v2.ts`. ARC 본체의 `lib/constants/templates-v2.ts`가 있으면
그 상수를 `ExperienceTypeSpec[]`로 바꾸는 어댑터만 끼우면 나머지는 그대로 돕니다.

## 튜닝 (`src/config.ts`의 `PIPELINE`)

| 값 | 기본 | 의미 |
|---|---|---|
| `splitExperiences` | `true` | 여러 경험이 섞인 자료를 경험별로 나눠 정리 |
| `maxExperiences` | 8 | 한 파일에서 나눠 정리할 최대 경험 수 (넘치면 문서 앞쪽부터) |
| `segmentAnchorFloor` | 0.8 | 경험 시작 줄이 원문과 이 일치도 이상일 때만 그 위치에서 자름 |
| `classifierDigestChars` | 16000 | 분류기에 보여 주는 문서 앞부분 길이 (뒤쪽 경험 누락 방지) |
| `ensemble` | 2 | 배분 시도 횟수. 값싼 모델 N회 → 필드별 우수안 병합 |
| `maxSupervisorRounds` | 1 | 감독 재검수 최대 횟수 |
| `supervisorEvidenceChars` | 9000 | 감독에게 넘기는 근거 구간 상한 |
| `fieldConfidenceFloor` | 0.4 | 미만인 값은 자동으로 비움 |
| `classificationConfidenceFloor` | 0.55 | 미만이면 사용자에게 유형 확인 요청 |
| `auditor` · `auditorPatchFloor` | `true` · 0.85 | 필드 감사관 사용 · 감사관 수정 적용 기준 |

## 알려진 한계와 다음 작업

실제 이력서 실행 결과를 분석해 찾은 문제 가운데 **경험 분리만 이번 버전에 반영**했고, 나머지는 남아 있습니다.

- **경험 분리는 가짜 LLM 테스트로만 검증했습니다.** 실제 Gemini가 경험 시작 줄을 원문 그대로 잘 내주는지는
  실제 문서로 확인이 필요합니다. 못 찾은 경험은 "원문 전체 + 이 경험만" 방식으로 처리됩니다.
- **감사관이 원문에 있는 정보를 지울 수 있습니다.** 감사관 수정 관문은 *새로 넣는* 수치·문장만 검사하고,
  *지우는* 수정은 막지 않습니다. 감사관이 근거 문장을 잘린 채로 보면 실제 있는 사실을 지웁니다.
- **근거 문장 경계가 잘못 잡힐 수 있습니다.** `8.9%`, `story-arc.org`의 마침표를 문장 끝으로 보고,
  짧은 문서도 감독용 근거를 압축합니다. (경험 분리 후에는 구간이 짧아 영향이 줄 것으로 예상)
- **'칸 정확도'는 실제 정확도가 아니라 '근거 확인율'에 가깝습니다.** 근거 인용이 없는 칸은 감사관이
  맞다고 판정해도 '확인 필요'로 셉니다. 추출기가 값마다 인용을 강제받지 않아 인용이 자주 빠집니다.
- 두 초안을 합칠 때 표현만 다른 같은 반복 입력 행(작업 기록 등)이 중복될 수 있고,
  수정 전에 나온 감독 이슈가 수정 후 다시 확인되지 않아 이미 해결된 이슈가 '남은 문제'로 보일 수 있습니다.
- 영어 원문을 한국어 값으로 정리하면 값과 원문의 글자 대조가 어려워 근거 위치를 못 찾는 칸이 생깁니다.
- 웹 데모 서버(`npm run serve`)는 아직 경험 분리를 하지 않습니다.

## 프로젝트 구조

```
src/
  pipeline.ts        organizeExperience(단일) · organizeExperiences(경험별)
  agents/            classifier · segment(경험 분리) · factsheet · extractor · merge
                     supervisor · auditor · guide · evidence
  ragkor/            한국어 근거 검증 (TypeScript)
  validate/          형식·근거·맥락 기계 검증, 인용 위치 찾기
  ingest/ ocr/       파일 수집·OCR
  schema/            18종 유형·입력 칸·필드 계약
  report/html.ts     칸별 HTML 보고서 (renderReport · renderManyReport)
  cli.ts  form.ts    CLI · 프론트 바인딩(toFormState)
ragkor/              RAGKOR Python 구현 + 벤치마크
colab/               ARC_engine.ipynb · run_engine.py (Colab 실행기)
server/ public/      웹 데모 서버
test/                오프라인 테스트 (API 키 불필요)
tools/ docs/         모델 받기·시드 생성 도구, RAGKOR 보고서
```

## 브랜치 안내

| 브랜치 | 내용 |
|---|---|
| **`extracter`** | ← 이 브랜치. 경험 자동 추출 엔진 |
| `main` | 자기소개서 AI — Colab 복붙용 단일 파일 (`cover_letter_ai_all_in_one.py`) |
| `claude/cover-letter-ai-generator-7uvjuj` | 자기소개서 AI 모듈형 패키지 (로컬/서버·DB 연동용) |
| `claude/dazzling-cray-bm7fzu` | 자기소개서 AI — 경험 선택기·백엔드 연동 envelope |
| `claude/career-analysis-individual-dl20u5` | 커리어 개별 분석 |
| `claude/comprehensive-analysis-hallucination-fix-o67sc5` | 커리어 종합 분석 + 환각 방지 |

이 엔진은 `New-Function-Test-Lab` 저장소의 `claude/arc-service-awareness-z00hjs`(`b1dd4e3`)에서
옮겨 와, 경험 분리 기능을 더한 것입니다.
