# 응답 스키마 — 프론트엔드 전달용

`career_individual.py` 의 응답 계약입니다. **프론트에는 이 폴더만 주면 됩니다.**

| 파일 | 용도 |
|---|---|
| `analysis_result.d.ts` | **TypeScript 프론트라면 이것.** 타입 정의 + 주석 |
| `analysis_result.schema.json` | JSON Schema. 런타임 검증·타입 자동생성·타 언어용 |
| `example_success.json` | 성공 응답 실제 예시 (후처리 파이프라인 통과본) |
| `example_error.json` | 실패 응답 예시 |
| `export_schema.py` | 스키마 ↔ 실제 코드 출력 일치 검사 |

## 계약 규칙 3가지

1. **`status` 는 envelope 최상위에만 있다.** `result` 안에는 없습니다.
2. **`vector` 는 값이 없으면 키 자체가 사라집니다.** 반면 `result` 안의 빈 값은
   키가 남고 값이 `null` 입니다. → `result.*` 는 항상 존재한다고 보고 null 체크만 하면 됩니다.
3. **한글 키를 쓰는 곳이 두 군데 있습니다** — `action_plan` (단기/중기/장기),
   `time_context` (기준일 등). 백엔드 로그·프롬프트와 표기를 맞추기 위한 의도적 선택입니다.

```ts
import type { AnalysisResponse } from "./analysis_result";
import { isSuccess } from "./analysis_result";

const res: AnalysisResponse = await fetch(...).then(r => r.json());
if (!isSuccess(res)) return showError(res.message);

res.result.action_plan.단기.마감일;        // "2026-11-30"
res.result.item_diagnosis.weaknesses[0].severity;   // "critical" | "major" | "minor"
```

## 주의: `career_individual.py` 를 그대로 넘기지 마세요

스키마가 파일 안 두 곳에 나뉘어 있고, 한쪽이 실제 응답과 다릅니다.

- `build_system_prompt_individual()` 의 JSON 예시 — LLM 에게 주는 **지시문**입니다.
  여기서 `action_plan` 은 문자열이지만, 실제 응답은 객체입니다.
- `postprocess_result()` — 프롬프트에 없는 필드 **8개를 추가**합니다
  (`time_context`, `validation`, `removed_recommendations`, `input_time_resolution`,
  `input_time_facts`, `time_warnings`, `analysis_date`, `embedding_dim`).

두 곳을 머리로 합쳐야 실제 형태가 나오므로, 이 폴더의 스키마를 쓰는 편이 정확합니다.

## 스키마가 코드와 어긋나지 않게 유지하기

응답 형태를 바꾼 뒤에는 반드시 실행하세요. 어긋나면 **exit code 1** 로 실패합니다.

```bash
python schema/export_schema.py            # 검사만
python schema/export_schema.py --write    # 검사 + 예시 파일 갱신
```

실제 후처리 파이프라인을 통과시킨 결과를 스키마의 `required` 목록과 **양방향**으로
대조합니다 (스키마에만 있는 필드 / 응답에만 있는 필드 둘 다 검출). `action_plan` 이
객체로 변환됐는지도 확인합니다.

> v1.1 → v1.2 에서 후처리가 필드 8개를 추가하고 `action_plan` 구조를 바꿨지만
> 프롬프트 템플릿의 JSON 예시는 그대로여서, 한 파일 안에서 두 곳이 서로 다른
> 형태를 말하고 있었습니다. 이 검사는 그 상황이 다시 생기는 것을 막습니다.
