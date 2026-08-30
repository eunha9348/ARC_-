/**
 * Career Analysis AI — 단일 경력 분석 응답 계약 (v1.2)
 * ===========================================================================
 * 프론트엔드는 이 파일 하나만 import 하면 된다.
 * 타입 정의 · 타입 가드 · 예시 응답 · 런타임 검증이 모두 들어 있다.
 *
 *   import type { AnalysisResponse } from "./analysis_result";
 *   import { isSuccess, EXAMPLE_SUCCESS } from "./analysis_result";
 *
 *   const res: AnalysisResponse = await fetch(...).then(r => r.json());
 *   if (!isSuccess(res)) return showError(res.message);
 *   res.result.action_plan.단기.마감일;                  // "2026-11-30"
 *   res.result.item_diagnosis.weaknesses[0].severity;    // "critical" | "major" | "minor"
 *
 * ---------------------------------------------------------------------------
 * 계약 규칙 3가지
 * ---------------------------------------------------------------------------
 * 1. status 는 envelope 최상위에만 있다. result 안에는 없다.
 *
 * 2. vector 는 값이 없으면 키 자체가 사라진다. 반면 result 안의 빈 값은
 *    키가 남고 값이 null 이다. (백엔드의 exclude_none 이 최상위에만 적용되며,
 *    Pydantic 과 내장 폴백 양쪽에서 동일하게 동작하는 것을 확인했다.)
 *    → result.* 는 항상 존재한다고 가정하고 null 체크만 하면 된다.
 *
 * 3. 한글 키를 쓰는 곳이 두 군데 있다: action_plan, time_context.
 *    백엔드 로그·프롬프트와 표기를 맞추기 위한 의도적 선택이다.
 *
 * ---------------------------------------------------------------------------
 * 백엔드 소스를 직접 읽지 말 것
 * ---------------------------------------------------------------------------
 * career_individual.py 안에는 응답 형태가 두 곳에 나뉘어 있고 서로 다르다.
 *   - build_system_prompt_individual() 의 JSON 예시는 LLM 에게 주는 지시문이다.
 *     거기서 action_plan 은 문자열이지만 실제 응답은 객체다.
 *   - postprocess_result() 가 프롬프트에 없는 필드 8개를 추가한다.
 * 이 파일이 실제 응답의 단일 출처이며, schema/export_schema.py 가 실제 코드
 * 출력과의 일치를 검사한다. (어긋나면 exit 1)
 * ===========================================================================
 */

// ═══════════════════════════════════════════════════════════
// Envelope
// ═══════════════════════════════════════════════════════════
export type AnalysisResponse = AnalysisSuccess | AnalysisError;

export interface AnalysisSuccess {
  status: "success";
  /** 임베딩 벡터. 생성 실패 시 이 키 자체가 응답에서 빠진다. */
  vector?: number[];
  result: AnalysisResult;
}

export interface AnalysisError {
  status: "error";
  /** 사용자에게 그대로 노출 가능한 한국어 메시지 */
  message: string;
}

// ═══════════════════════════════════════════════════════════
// result — 최상위 19개 필드
// ═══════════════════════════════════════════════════════════
export interface AnalysisResult {
  // ── 항목 메타 ──
  item_name: string;
  item_type: ItemType;
  brief_summary: string;

  // ── STAR 이력서 초안 ──
  /** 데이터 부족 시 각 필드가 null 일 수 있다. 그때 star_note 를 대신 노출할 것. */
  star_format: StarFormat | null;
  /** STAR 작성 불가 사유 + 어떻게 기록하면 되는지 안내. 충분하면 null. */
  star_note: string | null;

  // ── 심층 분석 ──
  deep_analysis: DeepAnalysis;

  // ── 강점 / 약점 ──
  item_strengths: ItemStrengths;
  item_diagnosis: ItemDiagnosis;

  // ── 추천 / 계획 ──
  /** 자격증 검증을 통과한 것만 남는다. priority 는 1부터 빈 번호 없이 재부여됨. */
  synergy_recommendations: SynergyRecommendation[];
  action_plan: ActionPlan;

  // ── 검증·시간 메타 (v1.2 신규) ──
  /** 검증에서 제거된 추천과 사유. 제거된 것이 없으면 null. */
  removed_recommendations: RemovedRecommendation[] | null;
  validation: ValidationMeta;
  time_context: TimeContext;
  /** 입력에서 확정된 시간 사실 문장. 예: "활동 기간: 2021년 3월 ~ 2021년 8월 = 5개월" */
  input_time_facts: string[];
  input_time_resolution: TimeResolution;
  /** 미래 연도 언급 등 시간 이상 경고. 없으면 null. */
  time_warnings: string[] | null;

  // ── 기타 ──
  /** 기준일 (YYYY-MM-DD, KST). time_context.기준일 과 동일값 — 하위 호환용. */
  analysis_date: string;
  /** 임베딩 차원. 생성 실패 시 null. */
  embedding_dim: number | null;
  /** 입력 정보 부족 안내. 없으면 null. */
  missing_info_warning: string | null;
}

export type ItemType =
  | "자격증" | "직무경력" | "인턴십" | "프로젝트"
  | "교육" | "봉사" | "대외활동" | "수상" | "기타";

// ═══════════════════════════════════════════════════════════
// STAR
// ═══════════════════════════════════════════════════════════
export interface StarFormat {
  title: string | null;
  /** Situation */ S: string | null;
  /** Task */      T: string | null;
  /** Action */    A: string | null;
  /** Result */    R: string | null;
}

// ═══════════════════════════════════════════════════════════
// 심층 분석
// ═══════════════════════════════════════════════════════════
export interface DeepAnalysis {
  career_value: string;
  /** analysis_date 기준의 시장 평가 */
  market_value: string;
  applicable_roles: string[];
}

// ═══════════════════════════════════════════════════════════
// 강점
// ═══════════════════════════════════════════════════════════
export interface ItemStrengths {
  /** false 면 strengths 는 빈 배열이고 아래 요약 필드들이 전부 null 이다. */
  has_genuine_strengths: boolean;
  one_line_strength_verdict: string | null;
  /** 강점이 없다고 판단한 사유. 강점이 있으면 null. */
  no_strength_reason: string | null;
  summarized_strengths: string[];
  strengths: Strength[];
  strongest_asset: string | null;
  positioning_tip: string | null;
}

export interface Strength {
  id: number;
  category: StrengthCategory;
  strength_level: StrengthLevel;
  /** 10자 이내 */
  title: string;
  analysis: string;
  /** 입력 텍스트에서 직접 확인 가능한 근거 */
  evidence: string;
  career_impact: string;
  /** 동사로 시작하는 실행 항목 */
  leverage_action: string;
  /** "Before: ... → After: ..." 형식. 없으면 null. */
  showcase_example: string | null;
}

export type StrengthCategory =
  | "전문성_희소성" | "성과_입증" | "역량_다양성"
  | "경험_깊이" | "도메인_전문성" | "차별화_포인트";

export type StrengthLevel = "outstanding" | "notable" | "moderate";

// ═══════════════════════════════════════════════════════════
// 약점 진단
// ═══════════════════════════════════════════════════════════
export interface ItemDiagnosis {
  one_line_verdict: string;
  limitations: string[];
  weaknesses: Weakness[];
  /** 서술에 반드시 추가해야 할 누락 요소 (수치, 기간, 팀 규모 등) */
  missing_elements: string[];
  rewrite_suggestion: string;
}

export interface Weakness {
  id: number;
  category: WeaknessCategory;
  severity: Severity;
  /** 10자 이내 */
  title: string;
  diagnosis: string;
  evidence: string;
  impact: string;
  /** 동사로 시작하는 실행 항목 */
  priority_action: string;
  /** "Before: ... → After: ..." 형식. 없으면 null. */
  improvement_example: string | null;
}

export type WeaknessCategory =
  | "서술_완성도" | "차별성_부족" | "직무_연결_약함"
  | "성과_불명확" | "기간_문제" | "단독_활용_한계";

/**
 * critical — 이 상태로 이력서에 넣으면 역효과 가능 (빨강)
 * major    — 설득력을 크게 낮추는 문제 (주황)
 * minor    — 있으면 좋지만 치명적이지 않음 (회색)
 */
export type Severity = "critical" | "major" | "minor";

// ═══════════════════════════════════════════════════════════
// 시너지 추천
// ═══════════════════════════════════════════════════════════
export interface SynergyRecommendation {
  /** 1부터 시작. 검증 제거 후 빈 번호 없이 재부여된다. */
  priority: number;
  category: RecommendationCategory;
  /** 자격증인 경우 검증된 레지스트리의 정본 표기 */
  name: string;
  reason: string;
  expected_effect: string;
  /** 예: "2개월". 모르면 null. */
  estimated_duration: string | null;
  /**
   * 공식 URL. 기관 실재성이 확인되지 않으면 null 로 치환된다.
   * 키 이름에 url/link/링크/주소 가 들어가면 모두 같은 검증을 받는다.
   */
  official_url?: string | null;
}

export type RecommendationCategory =
  | "자격증" | "교육강의" | "프로젝트" | "대외활동" | "경험";

/** 실재성 검증에서 제거된 추천. 사용자에게 "왜 빠졌는지" 안내할 때 사용. */
export interface RemovedRecommendation {
  name: string;
  category: string;
  /** 예: "실재하지 않는 자격증으로 확인됨 (실재 유사 자격: 사회조사분석사)" */
  removed_reason: string;
}

// ═══════════════════════════════════════════════════════════
// 액션 플랜 — ★ 한글 키
// ═══════════════════════════════════════════════════════════
/**
 * 주의: 프롬프트 템플릿에는 문자열로 적혀 있지만, 백엔드 후처리가 반드시
 * 아래 객체 형태로 변환한다. 프론트는 객체로만 받으면 된다.
 */
export interface ActionPlan {
  단기: ActionPlanWindow;
  중기: ActionPlanWindow;
  장기: ActionPlanWindow;
}

export interface ActionPlanWindow {
  /** "2026-08-30 ~ 2026-11-30" — 기준일에서 계산된 절대 기간 */
  기간: string;
  /** "2026-11-30" (YYYY-MM-DD) */
  마감일: string;
  /** 실행 내용. 모델이 비워두면 null. */
  내용: string | null;
}

// ═══════════════════════════════════════════════════════════
// 시간 메타 — ★ 한글 키
// ═══════════════════════════════════════════════════════════
export interface TimeContext {
  /** ISO8601 with offset. 예: "2026-08-30T17:42:14+09:00" */
  기준시각_KST: string;
  /** "2026-08-30" */
  기준일: string;
  기준연도: number;
  /** "2026년 3분기" */
  기준분기: string;
  /** "2026-08-30 ~ 2026-11-30" */
  단기_구간: string;
  중기_구간: string;
  장기_구간: string;
  /** 항상 "Asia/Seoul (UTC+09:00)" */
  타임존: string;
}

export interface TimeResolution {
  /**
   * absolute      — 연·월이 확인됨
   * relative      — "작년", "3년 전" 등에서 역산
   * duration_only — 기간만 확인되고 시점은 모름 ("재직 3년차")
   * none          — 시간 정보 없음. 기간 관련 UI 는 숨기는 편이 낫다.
   */
  resolution: "absolute" | "relative" | "duration_only" | "none";
  facts: string[];
  warnings: string[] | null;
  /** 현재 진행/재직 중이면 true */
  ongoing: boolean;
  /** "2021년 3월" 형태. 없으면 null. */
  earliest: string | null;
  latest: string | null;
  /** 최근 시점부터 기준일까지 경과 개월. 진행 중이면 0. */
  months_since_latest: number | null;
  total_duration_months: number | null;
  /** "1년 6개월" 형태 */
  total_duration_label: string | null;
}

// ═══════════════════════════════════════════════════════════
// 검증 메타
// ═══════════════════════════════════════════════════════════
export interface ValidationMeta {
  /** strict — 화이트리스트 밖 자격증 전부 제거 / blocklist_only — 알려진 환각만 제거 */
  cert_whitelist_mode: "strict" | "blocklist_only";
  /**
   * live  — 공식 출처에서 방금 수집한 목록
   * cache — 캐시된 수집 결과
   * seed  — 내장 기본 목록 (공식 출처 수집이 아직 없거나 실패)
   */
  cert_registry_origin: "live" | "cache" | "seed";
  /** 공식 출처 마지막 수집 시각(ISO8601). seed 면 null. */
  cert_registry_fetched_at: string | null;
  verified_cert_count: number;
  removed_recommendation_count: number;
  time_resolution: TimeResolution["resolution"];
  /** "2026-08-30T17:42:14+09:00 (Asia/Seoul)" */
  time_basis: string;
}

// ═══════════════════════════════════════════════════════════
// 타입 가드
// ═══════════════════════════════════════════════════════════

/** 성공 응답으로 좁힌다. */
export function isSuccess(r: AnalysisResponse): r is AnalysisSuccess {
  return r.status === "success";
}

/** 실패 응답으로 좁힌다. */
export function isError(r: AnalysisResponse): r is AnalysisError {
  return r.status === "error";
}

/** 강점 섹션을 렌더링할 값이 있는지. */
export function hasStrengths(result: AnalysisResult): boolean {
  return result.item_strengths.has_genuine_strengths &&
         result.item_strengths.strengths.length > 0;
}

/**
 * STAR 초안을 그대로 노출해도 되는지.
 * false 면 star_note 에 담긴 안내(어떻게 기록하면 되는지)를 대신 보여줄 것.
 */
export function hasStarDraft(result: AnalysisResult): boolean {
  const s = result.star_format;
  return !!s && [s.S, s.T, s.A, s.R].every((v) => !!v && v.trim().length > 0);
}

/**
 * 기간 관련 UI(신선도 배지, 활동 기간 등)를 보여줘도 되는지.
 * resolution 이 "none" 이면 입력에 시간 정보가 전혀 없다는 뜻이므로 숨기는 편이 낫다.
 */
export function hasTimeInfo(result: AnalysisResult): boolean {
  return result.input_time_resolution.resolution !== "none";
}

/** severity 를 UI 우선순위(숫자가 클수록 심각)로. 정렬에 사용. */
export const SEVERITY_RANK: Record<Severity, number> = {
  critical: 3,
  major: 2,
  minor: 1,
};

/** strength_level 을 UI 우선순위(숫자가 클수록 강함)로. */
export const STRENGTH_RANK: Record<StrengthLevel, number> = {
  outstanding: 3,
  notable: 2,
  moderate: 1,
};


// ═══════════════════════════════════════════════════════════
// 런타임 검증
// ═══════════════════════════════════════════════════════════
//  타입은 컴파일 타임에만 존재하므로, 백엔드가 계약을 어긴 응답을 보내도
//  런타임에는 조용히 통과한다. 개발/스테이징에서 이 함수를 통과시키면
//  "필드가 없어서 화면이 빈다" 류의 버그를 응답 단계에서 잡을 수 있다.

/** result 최상위 필수 키 (19개) */
const REQUIRED_RESULT_KEYS = [
  "item_name", "item_type", "brief_summary", "star_format", "star_note",
  "deep_analysis", "item_strengths", "item_diagnosis", "synergy_recommendations",
  "action_plan", "removed_recommendations", "validation", "time_context",
  "input_time_facts", "input_time_resolution", "time_warnings",
  "analysis_date", "embedding_dim", "missing_info_warning",
] as const;

const ACTION_PLAN_WINDOWS = ["단기", "중기", "장기"] as const;
const ACTION_PLAN_FIELDS = ["기간", "마감일", "내용"] as const;
const SEVERITIES: readonly string[] = ["critical", "major", "minor"];
const STRENGTH_LEVELS: readonly string[] = ["outstanding", "notable", "moderate"];
const TIME_RESOLUTIONS: readonly string[] =
  ["absolute", "relative", "duration_only", "none"];

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * 응답이 계약을 지키는지 검사한다.
 * @returns 문제 목록. 빈 배열이면 통과.
 */
export function validateAnalysisResponse(res: unknown): string[] {
  const problems: string[] = [];
  if (!isObj(res)) return ["응답이 객체가 아닙니다"];

  if (res.status === "error") {
    if (typeof res.message !== "string" || !res.message) {
      problems.push("error 응답에 message 가 없습니다");
    }
    return problems;
  }
  if (res.status !== "success") {
    problems.push(`status 가 "success" 또는 "error" 가 아닙니다: ${String(res.status)}`);
    return problems;
  }

  // vector 는 없어도 정상 (임베딩 실패 시 키가 사라진다)
  if ("vector" in res && !Array.isArray(res.vector)) {
    problems.push("vector 가 배열이 아닙니다");
  }

  const result = res.result;
  if (!isObj(result)) return [...problems, "result 가 객체가 아닙니다"];

  if ("status" in result) problems.push("result 안에 status 가 있습니다 (envelope 최상위에만 있어야 함)");

  for (const key of REQUIRED_RESULT_KEYS) {
    if (!(key in result)) problems.push(`result.${key} 누락`);
  }

  // action_plan — 프롬프트 템플릿과 달리 반드시 객체여야 한다
  const plan = result.action_plan;
  if (!isObj(plan)) {
    problems.push("result.action_plan 이 객체가 아닙니다");
  } else {
    for (const w of ACTION_PLAN_WINDOWS) {
      const win = plan[w];
      if (!isObj(win)) {
        problems.push(`action_plan.${w} 가 객체가 아닙니다 (백엔드 후처리 미적용)`);
        continue;
      }
      for (const f of ACTION_PLAN_FIELDS) {
        if (!(f in win)) problems.push(`action_plan.${w}.${f} 누락`);
      }
    }
  }

  // 배열이어야 하는 필드
  for (const key of ["synergy_recommendations", "input_time_facts"] as const) {
    if (!Array.isArray(result[key])) problems.push(`result.${key} 가 배열이 아닙니다`);
  }
  // 배열 또는 null 이어야 하는 필드
  for (const key of ["removed_recommendations", "time_warnings"] as const) {
    const v = result[key];
    if (v !== null && !Array.isArray(v)) {
      problems.push(`result.${key} 가 배열도 null 도 아닙니다`);
    }
  }

  // enum 값
  const diagnosis = result.item_diagnosis;
  if (isObj(diagnosis) && Array.isArray(diagnosis.weaknesses)) {
    diagnosis.weaknesses.forEach((w, i) => {
      if (isObj(w) && !SEVERITIES.includes(String(w.severity))) {
        problems.push(`weaknesses[${i}].severity 값이 올바르지 않습니다: ${String(w.severity)}`);
      }
    });
  }
  const strengths = result.item_strengths;
  if (isObj(strengths) && Array.isArray(strengths.strengths)) {
    strengths.strengths.forEach((s, i) => {
      if (isObj(s) && !STRENGTH_LEVELS.includes(String(s.strength_level))) {
        problems.push(`strengths[${i}].strength_level 값이 올바르지 않습니다: ${String(s.strength_level)}`);
      }
    });
  }
  const timeRes = result.input_time_resolution;
  if (isObj(timeRes) && !TIME_RESOLUTIONS.includes(String(timeRes.resolution))) {
    problems.push(`input_time_resolution.resolution 값이 올바르지 않습니다: ${String(timeRes.resolution)}`);
  }

  return problems;
}

/** 검증 실패 시 예외를 던지는 버전. 개발 환경에서 사용. */
export function assertAnalysisResponse(res: unknown): asserts res is AnalysisResponse {
  const problems = validateAnalysisResponse(res);
  if (problems.length > 0) {
    throw new Error("응답이 계약을 위반했습니다:\n" + problems.map((p) => `  - ${p}`).join("\n"));
  }
}


// ═══════════════════════════════════════════════════════════
// 예시 응답
// ═══════════════════════════════════════════════════════════
//  백엔드의 실제 후처리 파이프라인을 통과시켜 생성한 응답이다.
//  목 데이터·스토리북·테스트에 그대로 쓸 수 있다.
//  (schema/export_schema.py --write 로 갱신된다)

export const EXAMPLE_SUCCESS: AnalysisSuccess = {
  "status": "success",
  "vector": [
    0.0123,
    -0.0456,
    0.0789
  ],
  "result": {
    "item_name": "OO스타트업 데이터 분석 인턴",
    "item_type": "인턴십",
    "brief_summary": "5개월간 사용자 행동 로그를 분석해 리텐션 개선 지표를 도출한 인턴 경험",
    "star_format": {
      "title": "사용자 행동 로그 분석으로 리텐션 개선 지점 도출",
      "S": "월 활성 사용자가 정체된 상황에서 원인 파악이 필요했다",
      "T": "로그 데이터에서 이탈 구간을 찾아내는 과제를 맡았다",
      "A": "SQL로 퍼널 단계별 이탈률을 집계하고 코호트별로 비교했다",
      "R": "온보딩 3단계에서 이탈이 집중됨을 확인해 개선안이 채택되었다"
    },
    "star_note": null,
    "deep_analysis": {
      "career_value": "실데이터로 가설을 검증해본 경험은 신입 데이터 직군에서 변별력이 있다",
      "market_value": "SQL 기반 로그 분석 역량은 수요가 꾸준하나 지원자 수도 많아 희소성은 보통",
      "applicable_roles": [
        "데이터 분석가",
        "프로덕트 애널리스트",
        "그로스 마케터"
      ]
    },
    "item_strengths": {
      "has_genuine_strengths": true,
      "one_line_strength_verdict": "가설 수립부터 검증까지 분석 사이클을 한 번 완주한 경험",
      "no_strength_reason": null,
      "summarized_strengths": [
        "퍼널 분석 실무 경험",
        "분석 결과가 실제 의사결정에 반영됨"
      ],
      "strengths": [
        {
          "id": 1,
          "category": "성과_입증",
          "strength_level": "notable",
          "title": "개선안 채택",
          "analysis": "분석이 보고서로 끝나지 않고 실제 제품 변경으로 이어진 점이 핵심이다",
          "evidence": "온보딩 3단계 이탈 확인 후 개선안 채택",
          "career_impact": "분석의 실효성을 입증할 수 있어 면접에서 강한 근거가 된다",
          "leverage_action": "채택된 개선안의 이후 지표 변화를 수치로 확보하라",
          "showcase_example": "Before: 로그 분석 수행 → After: 퍼널 이탈 구간을 특정해 개선안 채택"
        }
      ],
      "strongest_asset": "분석 결과가 제품 의사결정으로 연결된 이력",
      "positioning_tip": "지표 정의 → 분석 → 의사결정 반영 순서로 서술하면 설득력이 올라간다"
    },
    "item_diagnosis": {
      "one_line_verdict": "경험의 흐름은 갖췄으나 성과를 뒷받침할 숫자가 전무하다",
      "limitations": [
        "개선 효과를 나타내는 수치가 없다",
        "5년 전 경험이라 최신성이 떨어진다"
      ],
      "weaknesses": [
        {
          "id": 1,
          "category": "성과_불명확",
          "severity": "major",
          "title": "수치 부재",
          "diagnosis": "'개선안이 채택되었다'로 끝나 실제 효과 크기를 알 수 없다",
          "evidence": "입력 전체에 이탈률·전환율 수치가 하나도 없음",
          "impact": "면접에서 '얼마나 개선됐나' 질문에 답하지 못하면 신뢰가 떨어진다",
          "priority_action": "당시 대시보드나 보고 자료에서 개선 전후 수치를 복원하라",
          "improvement_example": "Before: 개선안 채택 → After: 온보딩 이탈률 32%→24%로 8%p 감소"
        }
      ],
      "missing_elements": [
        "개선 전후 지표 수치",
        "분석 대상 데이터 규모",
        "팀 구성과 본인 역할 비중"
      ],
      "rewrite_suggestion": "문제 정의와 수치 결과를 앞뒤에 배치하고 분석 과정은 압축해 서술한다"
    },
    "synergy_recommendations": [
      {
        "priority": 1,
        "category": "자격증",
        "name": "SQLD",
        "reason": "실무에서 쓴 SQL 역량을 객관적으로 증명할 수 있다",
        "expected_effect": "경력 기술과 자격이 서로를 뒷받침해 신뢰도가 올라간다",
        "estimated_duration": "2개월"
      },
      {
        "priority": 2,
        "category": "프로젝트",
        "name": "공개 데이터 기반 리텐션 분석 포트폴리오",
        "reason": "5년 전 경험의 최신성 문제를 최근 산출물로 보완한다",
        "expected_effect": "현재도 분석이 가능하다는 점을 직접 보여줄 수 있다",
        "estimated_duration": "1개월"
      }
    ],
    "action_plan": {
      "단기": {
        "기간": "2026-08-30 ~ 2026-11-30",
        "마감일": "2026-11-30",
        "내용": "당시 분석 지표를 복원해 이력서 문장에 수치를 넣는다"
      },
      "중기": {
        "기간": "2026-11-30 ~ 2027-08-30",
        "마감일": "2027-08-30",
        "내용": "SQLD를 취득하고 최근 데이터로 포트폴리오를 1건 만든다"
      },
      "장기": {
        "기간": "2027-08-30 ~ 2029-08-30",
        "마감일": "2029-08-30",
        "내용": "도메인을 정해 해당 산업의 지표 체계에 대한 전문성을 쌓는다"
      }
    },
    "missing_info_warning": null,
    "time_context": {
      "기준시각_KST": "2026-08-30T22:34:56+09:00",
      "기준일": "2026-08-30",
      "기준연도": 2026,
      "기준분기": "2026년 3분기",
      "단기_구간": "2026-08-30 ~ 2026-11-30",
      "중기_구간": "2026-11-30 ~ 2027-08-30",
      "장기_구간": "2027-08-30 ~ 2029-08-30",
      "타임존": "Asia/Seoul (UTC+09:00)"
    },
    "analysis_date": "2026-08-30",
    "input_time_facts": [
      "가장 최근 시점: 2021년 8월 → 기준일(2026-08-30) 대비 5년 경과",
      "가장 이른 시점: 2021년 3월",
      "활동 기간: 2021년 3월 ~ 2021년 8월 = 5개월 (시작·종료 시점에서 계산)",
      "신선도: 5년 경과 — 오래된 경험으로 판단 가능",
      "기간 규모: 5개월 — 단기 경험 (6개월 미만)"
    ],
    "input_time_resolution": {
      "resolution": "absolute",
      "facts": [
        "가장 최근 시점: 2021년 8월 → 기준일(2026-08-30) 대비 5년 경과",
        "가장 이른 시점: 2021년 3월",
        "활동 기간: 2021년 3월 ~ 2021년 8월 = 5개월 (시작·종료 시점에서 계산)",
        "신선도: 5년 경과 — 오래된 경험으로 판단 가능",
        "기간 규모: 5개월 — 단기 경험 (6개월 미만)"
      ],
      "warnings": null,
      "ongoing": false,
      "earliest": "2021년 3월",
      "latest": "2021년 8월",
      "months_since_latest": 60,
      "total_duration_months": 5,
      "total_duration_label": "5개월"
    },
    "time_warnings": null,
    "removed_recommendations": null,
    "validation": {
      "cert_whitelist_mode": "strict",
      "cert_registry_origin": "seed",
      "cert_registry_fetched_at": null,
      "verified_cert_count": 236,
      "removed_recommendation_count": 0,
      "time_resolution": "absolute",
      "time_basis": "2026-08-30T22:34:56+09:00 (Asia/Seoul)"
    },
    "embedding_dim": 3072
  }
};

export const EXAMPLE_ERROR: AnalysisError = {
  "status": "error",
  "message": "입력 데이터가 너무 짧습니다. 분석할 경력/자격증/활동을 입력해주세요."
};
