/**
 * career_individual.py — 단일 경력 분석 응답 타입 (v1.2)
 * ===========================================================================
 * 프론트엔드가 참조할 응답 계약. 백엔드 구현(career_individual.py)의 실제
 * 출력에서 도출했으며, schema/export_schema.py 가 코드와의 일치를 검사한다.
 *
 * 계약 규칙 3가지
 * ---------------------------------------------------------------------------
 * 1. status 는 envelope 최상위에만 있다. result 안에는 없다.
 * 2. vector 는 값이 없으면 키 자체가 사라진다 (exclude_none=True 가 최상위에만
 *    적용되기 때문). 반면 result 안의 빈 값은 키가 남고 값이 null 이다.
 *    → result.* 는 항상 존재한다고 가정하고, null 체크만 하면 된다.
 * 3. 한글 키를 쓰는 곳이 두 군데 있다: action_plan, time_context.
 *    (백엔드 로그·프롬프트와 표기를 맞추기 위한 의도적 선택)
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

/** 좁히기 헬퍼 */
export const isSuccess = (r: AnalysisResponse): r is AnalysisSuccess =>
  r.status === "success";

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
