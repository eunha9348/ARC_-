/**
 * ARC 경험 자동 정리 엔진 — 공개 API
 *
 *   import { organizeExperience, readInputFiles } from "arc-auto-organize";
 *   const result = await organizeExperience(await readInputFiles(["./보고서.pdf", "./상장.jpg"]));
 *
 *   // 이력서·포트폴리오처럼 여러 경험이 섞인 자료 → 경험별로 나눠 정리
 *   const { items } = await organizeExperiences(await readInputFiles(["./이력서.pdf"]));
 */
export {
  organizeExperience, organizeExperiences,
  type OrganizeOptions, type OrganizeManyResult,
} from "./pipeline.js";
export { planSegments, type ExperienceSegment, type SegmentPlan } from "./agents/segment.js";
export { createSession, GeminiSession, type LlmSession } from "./llm/index.js";
export { ingestFiles } from "./ingest/index.js";
export { ocrImage } from "./ocr/index.js";
export {
  SourceIndex, Lexicon, BM25, buildLexicon, defaultLexicon,
  decompose, similarity, typoVariants, fold, tokenize, normalizeNumber,
  type LexiconData, type QuoteCheck, type NumberKind,
} from "./ragkor/index.js";
export { buildFactsheet, factsheetText, type Factsheet } from "./agents/factsheet.js";
export { mergeDrafts, arbitrate, type FieldConflict } from "./agents/merge.js";
export * from "./schema/index.js";
export * from "./types.js";
export { readInputFiles } from "./read-files.js";
export { toFormState, type FormState, type FormFieldState } from "./form.js";
export { API_KEYS, MODELS, PIPELINE, PROVIDER } from "./config.js";
export { renderReport, renderManyReport } from "./report/html.js";
