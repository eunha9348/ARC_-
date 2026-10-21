/**
 * ARC 자동 정리 엔진 — 설정 / API 키
 *
 * ┌──────────────────────────────────────────────────────────────┐
 * │  ★ API 키는 여기 한 곳에만 넣으면 됩니다.                     │
 * │    Google API 키 하나로 LLM(Gemini)과 OCR이 전부 돕니다.      │
 * └──────────────────────────────────────────────────────────────┘
 */
import { loadEnv } from "./load-env.js";

loadEnv();

export const API_KEYS = {
  /**
   * ★★ 필수 — Google API 키 (Google AI Studio에서 발급) ★★
   * 이 키 하나가 다음 모두를 담당합니다.
   *   · Gemini  … 분류 / 배분 / 감독 / 안내 + 이미지 OCR(Vision)
   *   · Cloud Vision … OCR 보조 엔진 (같은 GCP 프로젝트에서 API를 켠 경우에만)
   *
   * 발급: https://aistudio.google.com/apikey
   */
  google: process.env.GOOGLE_API_KEY ?? "", // <<<<<< 여기에 Google API 키를 넣으세요

  /**
   * 선택 — Cloud Vision을 다른 키로 쓰고 싶을 때만.
   * 비워 두면 위 google 키를 그대로 씁니다.
   */
  googleVision: process.env.GOOGLE_VISION_API_KEY ?? "",

  /** 선택 — 한국어 증명서 특화 OCR 보조 엔진. 없으면 자동 skip. */
  clova: {
    invokeUrl: process.env.CLOVA_OCR_INVOKE_URL ?? "",
    secret: process.env.CLOVA_OCR_SECRET ?? "",
  },

  /** 선택 — Anthropic 엔진으로 바꿔 쓸 때만 (PROVIDER를 "anthropic"으로 둔 경우). */
  anthropic: process.env.ANTHROPIC_API_KEY ?? "",
} as const;

/** 사용할 LLM 엔진. Google 키를 쓰므로 기본은 gemini. */
export const PROVIDER: "gemini" | "anthropic" =
  (process.env.ARC_LLM_PROVIDER as "gemini" | "anthropic") ?? "gemini";

/**
 * 모델 선택.
 *
 * Gemini 모델 ID는 자주 바뀌고 구버전은 종료됩니다(2.5 계열은 2026-10-16 종료 예정).
 * 그래서 **하드코딩하지 않고**, 시작할 때 ListModels API로 실제 사용 가능한 모델을
 * 받아와 아래 우선순위 규칙에 맞는 최신 모델을 자동으로 고릅니다.
 *
 * 기본 모델은 `pin`(gemini-3.5-pro)입니다. 계정 목록에 정확히 그 이름이 없으면
 * 같은 이름의 preview 판(예: gemini-3.5-pro-preview-…)을 쓰고, 그것도 없으면 아래 규칙으로
 * 최신 모델을 자동으로 고른 뒤 바꿨다는 사실을 알립니다. 환경 변수 GEMINI_MODEL로 바꿀 수 있고,
 * 빈 문자열("")이면 처음부터 자동 선택입니다.
 */
export const MODELS = {
  gemini: {
    /** 주 모델. 목록에 없으면 자동 선택으로 대체된다. */
    pin: process.env.GEMINI_MODEL ?? "gemini-3.5-pro", // <<<<<< 주 모델

    /**
     * 자동 선택은 **세대를 tier보다 먼저** 봅니다.
     * 예전에는 'pro 패턴'을 먼저 훑어서 gemini-3.8-flash 가 있는데도
     * gemini-2.5-pro 를 골랐습니다. 세대 차가 tier 차보다 크므로 순서를 뒤집었습니다.
     */
    pattern: /^gemini-(\d+(?:\.\d+)?)-(pro|flash)(?:-(preview|exp).*)?$/,
    /** 자동 선택이 실패했을 때 마지막으로 시도할 모델 */
    fallback: "gemini-3.5-flash",
    /** 가벼운 단계(앙상블 배분·안내 생성 등)에 쓸 모델. 비우면 최신 flash를 자동 선택 */
    lightPin: process.env.GEMINI_LIGHT_MODEL ?? "",
  },
  anthropic: {
    main: "claude-opus-5",
  },
} as const;

/**
 * 단계별 사고 예산(thinking budget).
 * -1 = 모델이 알아서(dynamic), 0 = 사고 끄기.
 * 감독 단계만 크게 잡아 정확도를 끌어올립니다.
 */
export const THINKING = {
  classifier: -1,
  extractor: -1,
  supervisor: -1,
  guide: 0,
  visionOcr: 0,
} as const;

export const PIPELINE = {
  /**
   * 감독 sub-Agent 재검수 최대 횟수.
   * RAGKOR로 검증기 오탐이 사라져 1회로 충분해졌습니다 (예전 기본 2).
   */
  maxSupervisorRounds: 1,
  /**
   * 배분 앙상블 시도 횟수.
   * 값싼 모델로 N번 시도해 필드별로 좋은 쪽만 합치는 편이,
   * 비싼 모델로 한 번 시도하고 틀려서 재작업하는 것보다 쌉니다.
   */
  ensemble: 2,
  /** 감독에게 넘기는 근거 구간 최대 길이(문자). 원문 전체를 보내지 않습니다. */
  supervisorEvidenceChars: 9000,
  /** 분류 신뢰도가 이 값 미만이면 사용자에게 유형 확인을 요청 */
  classificationConfidenceFloor: 0.55,
  /** 필드 신뢰도가 이 값 미만이면 값을 비우고 Fallback 안내로 넘김 */
  fieldConfidenceFloor: 0.4,
  /** LLM에 넘기는 근거 텍스트 최대 길이(문자) */
  maxEvidenceChars: 180_000,
  /** OCR 앙상블에서 주 엔진과 보조 엔진 일치율이 이 값 미만이면 재판독 */
  ocrAgreementFloor: 0.82,
  /** 이미지 OCR 타일 분할 임계 높이(px) */
  ocrTileThresholdPx: 2200,
  /** 타일 겹침(px) */
  ocrTileOverlapPx: 160,
  /**
   * Kiwi 형태소 분석으로 조사·어미를 떼어 낸다 (모델: tools/fetch_kiwi_model.sh).
   * 모델이 없으면 자동으로 기존 규칙을 쓴다.
   */
  useKiwi: true,
  /**
   * 최종 필드 감사관(sub-agent)을 돌린다. 결정론적 사전 감사 + LLM 1회.
   * false면 결정론적 감사만 하고 LLM은 부르지 않는다.
   */
  auditor: true,
  /** 감사관 패치는 이 정렬 일치도 이상인 근거가 있을 때만 적용한다 */
  auditorPatchFloor: 0.85,
  /**
   * 한 파일에 여러 경험이 섞여 있으면(이력서·포트폴리오 등) 경험별로 잘라 따로 정리한다.
   * false면 예전처럼 대표 경험 하나만 정리한다.
   */
  splitExperiences: true,
  /** 한 파일에서 나눠 정리할 최대 경험 수 — 넘치면 문서 앞쪽 경험부터 */
  maxExperiences: 8,
  /** 경험 시작 문구(anchor)가 원문과 이 정렬 일치도 이상일 때만 그 위치에서 자른다 */
  segmentAnchorFloor: 0.8,
  /** 분류기에 보여 주는 문서 앞부분 길이(문자) — 문서 뒤쪽 경험도 분리 목록에 들어가게 */
  classifierDigestChars: 16_000,
  /** 업로드 허용 최대 용량 (서버) */
  maxUploadBytes: 40 * 1024 * 1024,
} as const;

/** 비용 추정용 단가 (USD / 1M tokens). 모델·요금제에 맞게 조정하세요. */
export const PRICING = {
  gemini: { inputPerMTok: 1.25, outputPerMTok: 10.0 },
  /** flash 계열은 훨씬 쌉니다 — 무거운 단계를 여기로 옮겨 비용을 줄입니다. */
  geminiFlash: { inputPerMTok: 0.3, outputPerMTok: 2.5 },
  anthropic: { inputPerMTok: 5.0, outputPerMTok: 25.0 },
} as const;

export function googleKey(): string {
  if (!API_KEYS.google) {
    throw new Error(
      "Google API 키가 없습니다.\n" +
        "  1) https://aistudio.google.com/apikey 에서 키를 발급받고\n" +
        "  2) src/config.ts 의 API_KEYS.google 에 붙여넣거나 .env 에 GOOGLE_API_KEY=... 로 넣으세요.",
    );
  }
  const key = API_KEYS.google.trim().replace(/^["']|["']$/g, "");
  const problem = googleKeyProblem(key);
  if (problem) {
    throw new Error(
      `GOOGLE_API_KEY 값이 API 키가 아닙니다 — ${problem}\n` +
        "  https://aistudio.google.com/apikey 에서 키(AIza…로 시작하는 39자)를 복사해 다시 넣어 주세요.",
    );
  }
  return key;
}

/**
 * 키 모양 검사. 형식이 바뀔 수 있으니 AIza 접두사는 강제하지 않고, 확실히 키가 아닌 값만 거른다.
 * 키가 너무 길면 URL이 Google 프런트엔드 한도(약 16KB)를 넘어 "Error 400 (Bad Request)" HTML이 돌아온다.
 */
export function googleKeyProblem(key: string): string | null {
  if (key.length > 200) return `길이가 ${key.length.toLocaleString()}자입니다 (실제 키는 39자 안팎). 키가 아닌 다른 내용이 들어 있습니다.`;
  if (/\s/.test(key)) return "공백이나 줄바꿈이 섞여 있습니다.";
  if (!/^[\x21-\x7e]+$/.test(key)) return "한글 등 키에 쓸 수 없는 글자가 들어 있습니다.";
  return null;
}

export function visionKey(): string {
  return API_KEYS.googleVision || API_KEYS.google;
}
