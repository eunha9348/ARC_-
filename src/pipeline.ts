import { PIPELINE } from "./config.js";
import { classify } from "./agents/classifier.js";
import { evidenceSpans } from "./agents/evidence.js";
import { extract } from "./agents/extractor.js";
import { buildFactsheet, factsheetText, type Factsheet } from "./agents/factsheet.js";
import { buildFallbackGuide } from "./agents/guide.js";
import { arbitrate, mergeDrafts } from "./agents/merge.js";
import { supervise } from "./agents/supervisor.js";
import { auditFields } from "./agents/auditor.js";
import {
  focusHint, planSegments, segmentDocs, shiftProvenance,
  type ExperienceSegment, type SegmentPlan,
} from "./agents/segment.js";
import { SourceIndex, loadKiwi } from "./ragkor/index.js";
import { ingestFiles } from "./ingest/index.js";
import { createSession, type LlmSession } from "./llm/index.js";
import { CATEGORIES, EXPERIENCE_TYPES, TYPE_BY_ID, resolveLayout } from "./schema/index.js";
import type {
  ClassificationResult, ExperienceTypeSpec, ExtractedDoc, ExtractionResult, InputFile,
  OrganizeResult, ProgressHandler, ReviewIssue, ReviewResult, UsageStat,
} from "./types.js";
import { checkGrounding } from "./validate/grounding.js";
import { validateStructure } from "./validate/structural.js";
import { locateQuotes } from "./validate/locate.js";
import { checkContext } from "./validate/context.js";
import { defaultEmbedder } from "./llm/embed.js";
import { setByPath } from "./util/path.js";

export interface OrganizeOptions {
  /** 사용자가 덧붙인 설명 ("작년 여름 인턴 때 만든 자료입니다" 등) */
  userHint?: string;
  /** 유형을 사용자가 직접 지정한 경우 — 분류 단계를 건너뛴다 (경험 분리도 하지 않는다) */
  forceTypeId?: string;
  onProgress?: ProgressHandler;
  session?: LlmSession;
  /** 속도/정확도 프리셋 — {@link QUALITY_PRESETS}. 기본은 PIPELINE.defaultQuality ("fast") */
  quality?: Quality;
}

export type Quality = "fast" | "balanced" | "best";

/**
 * 속도/정확도 프리셋. 사용자가 결과를 직접 손본다는 전제라 기본(fast)은 속도를 우선한다.
 *
 *   fast     — 값싼 모델 배분 1회 + 기계 검증(근거·수치·형식) + 빈 칸 안내. 상위 모델 호출 없음.
 *   balanced — fast + 사실 시트 + 상위 모델 필드 감사 1회.
 *   best     — 예전 전체 경로: 상위 모델 배분 앙상블 + 감독 루프 + 필드 감사.
 *
 * 실측(이력서 1장, 경험 8개): 예전 balanced는 경험당 LLM 6~8회를 순서대로 돌려 약 30분 걸렸고,
 * 감독·감사관이 실제로 고친 칸은 8개 경험을 통틀어 1칸이었다. 경험은 이제 병렬로 정리한다.
 */
export const QUALITY_PRESETS: Record<Quality, {
  factsheet: boolean; ensemble: number; supervise: boolean; auditLlm: boolean; heavyExtract: boolean;
}> = {
  fast: { factsheet: false, ensemble: 1, supervise: false, auditLlm: false, heavyExtract: false },
  balanced: { factsheet: true, ensemble: 1, supervise: false, auditLlm: true, heavyExtract: false },
  best: { factsheet: true, ensemble: PIPELINE.ensemble, supervise: true, auditLlm: true, heavyExtract: true },
};

/** 여러 경험을 나눠 정리한 결과 */
export interface OrganizeManyResult {
  /** 문서 전체에 대한 분류 결과 (분리 목록 포함) */
  classification: ClassificationResult;
  /** 경험 분리 계획 — 나눴는지, 왜, 어디서 잘랐는지 */
  split: SegmentPlan;
  /** 경험별 정리 결과. 분리하지 않았으면 1개 */
  items: (OrganizeResult & { segment?: ExperienceSegment })[];
  /** 정리하다 실패한 경험 — 나머지 경험은 계속 정리한다 */
  failed: { title: string; typeId: string; error: string }[];
  /** 전체 사용량 (분류·사실 시트 포함) */
  usage: UsageStat;
}

/** 경험 하나를 정리하는 데 필요한 것들 */
interface RunContext {
  session: LlmSession;
  docs: ExtractedDoc[];
  index: SourceIndex;
  quality: Quality;
  userHint?: string;
  embedder: ReturnType<typeof defaultEmbedder>;
  onProgress?: ProgressHandler;
}

/** 수집 + 형태소 분석기 준비 + 원문 색인 — 단일/다중 정리가 함께 쓴다 */
async function prepare(files: InputFile[], options: OrganizeOptions) {
  const onProgress = options.onProgress;
  const session = options.session ?? (await createSession());

  // Kiwi(WASM) 빌드는 수 초 걸린다 — 수집/OCR과 겹쳐서 시작해 둔다
  const kiwiReady = PIPELINE.useKiwi ? loadKiwi({ quiet: true }).catch(() => null) : null;

  /* ── 0. 수집 / OCR ─────────────────────────────── */
  const docs = await ingestFiles(session, files, onProgress);
  if (docs.every((d) => !d.text.trim())) {
    throw new Error(
      "업로드한 파일에서 텍스트를 하나도 얻지 못했습니다. " +
        "이미지라면 더 선명한 사진을, 문서라면 PDF로 변환해 다시 올려주세요.",
    );
  }

  // 맥락 검사용 임베딩 (Google 키가 없으면 단서어 규칙만으로 돈다)
  const embedder = defaultEmbedder(session.usage);
  const morph = await kiwiReady;
  onProgress?.({ stage: "validate", message: morph ? "형태소 분석: Kiwi" : "형태소 분석: 규칙 기반 (Kiwi 모델 없음)" });
  const index = new SourceIndex(docs.map((d) => d.text));
  return { session, docs, index, embedder };
}

function forcedClassification(typeId: string): ClassificationResult {
  const t = TYPE_BY_ID.get(typeId)!;
  return {
    categoryId: t.category,
    typeId: t.id,
    confidence: 1,
    rationale: "사용자가 유형을 직접 지정했습니다.",
    alternatives: [],
    multipleExperiences: false,
    splitSuggestions: [],
  };
}

function reportClassification(onProgress: ProgressHandler | undefined, c: ClassificationResult) {
  onProgress?.({
    stage: "classify",
    message: `유형 판별: ${TYPE_BY_ID.get(c.typeId)?.label ?? c.typeId} (신뢰도 ${(c.confidence * 100).toFixed(0)}%)`,
    detail: c,
  });
}

function reportFactsheet(onProgress: ProgressHandler | undefined, factsheet: Factsheet | null) {
  if (!factsheet) return;
  onProgress?.({
    stage: "extract",
    message: `사실 시트: ${factsheet.docType}·${factsheet.register} / `
      + `수치 ${factsheet.numbers?.length ?? 0}건 · 성과 ${factsheet.achievements?.length ?? 0}건 `
      + `· 표기 정규화 ${factsheet.normalized?.length ?? 0}건`,
  });
}

/**
 * 산출물 파일 → 정리된 ARC 경험 항목 (대표 경험 1개).
 *
 * ┌ 수집/OCR ─ 사실 시트 ─ 분류 ─┬ 배분 A ┐
 * │                             └ 배분 B ┘→ 결정론적 병합 → (충돌만) 중재
 * └───────────────────────────────────────→ 감독(근거 구간만) → 안내
 *
 * 비용 설계
 *   · 무거운 단계(배분)는 **값싼 모델로 병렬 N회**, 필드별로 좋은 쪽만 골라 합친다.
 *   · 감독만 상위 모델을 쓰되, 원문 전체가 아니라 **관련 근거 구간**만 본다.
 *   · RAGKOR로 검증기 오탐이 사라져 재작업 루프가 3회 → 1회로 줄었다.
 *
 * 이력서·포트폴리오처럼 여러 경험이 섞인 자료는 {@link organizeExperiences}를 쓴다.
 */
export async function organizeExperience(
  files: InputFile[],
  options: OrganizeOptions = {},
): Promise<OrganizeResult> {
  const onProgress = options.onProgress;
  const { session, docs, index, embedder } = await prepare(files, options);

  const quality = options.quality ?? PIPELINE.defaultQuality;
  const wantFactsheet = QUALITY_PRESETS[quality].factsheet;

  /* ── 1. 사실 시트 + 분류를 병렬로 ────────────────── */
  onProgress?.({ stage: "extract", message: wantFactsheet ? "사실 시트 작성 + 유형 판별 (병렬)" : "유형 판별" });
  let factsheet: Factsheet | null = null;
  let classification: ClassificationResult;
  if (options.forceTypeId && TYPE_BY_ID.has(options.forceTypeId)) {
    classification = forcedClassification(options.forceTypeId);
    factsheet = wantFactsheet ? await buildFactsheet(session, docs).catch(() => null) : null;
  } else {
    const [fsResult, clsResult] = await Promise.allSettled([
      wantFactsheet ? buildFactsheet(session, docs) : Promise.resolve(null),
      classify(session, docs, options.userHint),
    ]);
    if (fsResult.status === "fulfilled") factsheet = fsResult.value;
    else onProgress?.({ stage: "extract", message: `사실 시트 실패 — 원문만으로 진행합니다` });
    if (clsResult.status === "rejected") throw clsResult.reason;
    classification = clsResult.value;
    reportClassification(onProgress, classification);
  }
  reportFactsheet(onProgress, factsheet);

  return runExperience(
    { session, docs, index, quality, userHint: options.userHint, embedder, onProgress },
    classification,
    factsheet,
  );
}

/**
 * 산출물 파일 → 경험별로 정리된 ARC 경험 항목들.
 *
 * 분류기가 "여러 경험이 섞인 자료"(이력서·포트폴리오 등)라고 판단하면, 분리 목록의
 * 시작 문구로 원문을 경험별 구간으로 잘라 **구간마다** 사실 시트 → 배분 → 감독 → 감사 → 안내를
 * 따로 돌린다. 경험 하나짜리 자료면 {@link organizeExperience}와 같은 결과 1개를 돌려준다.
 *
 * 경험은 PIPELINE.experienceConcurrency개씩 동시에 정리한다. 경험마다 세션을 갈라(fork)
 * 사용량을 따로 세므로 경험별 비용이 섞이지 않는다. 429는 세션의 재시도가 처리한다.
 * 한 경험이 실패해도 나머지는 계속 정리하고 failed에 남긴다.
 */
export async function organizeExperiences(
  files: InputFile[],
  options: OrganizeOptions = {},
): Promise<OrganizeManyResult> {
  const onProgress = options.onProgress;
  const { session, docs, index, embedder } = await prepare(files, options);
  const quality = options.quality ?? PIPELINE.defaultQuality;
  const preset = QUALITY_PRESETS[quality];
  const base: RunContext = {
    session, docs, index, quality,
    userHint: options.userHint, embedder, onProgress,
  };

  /* ── 1. 분류 (분리 목록 포함) ─────────────────────── */
  let classification: ClassificationResult;
  if (options.forceTypeId && TYPE_BY_ID.has(options.forceTypeId)) {
    classification = forcedClassification(options.forceTypeId);
  } else {
    onProgress?.({ stage: "classify", message: "유형 판별 + 경험 분리 목록 작성" });
    classification = await classify(session, docs, options.userHint);
    reportClassification(onProgress, classification);
  }

  /* ── 2. 분리 계획 (LLM 없음) ──────────────────────── */
  const split = options.forceTypeId
    ? { applied: false, reason: "유형을 직접 지정해 경험 하나로 정리합니다.", segments: [], dropped: [] }
    : planSegments(docs, classification);
  if (classification.multipleExperiences || split.applied) {
    onProgress?.({ stage: "classify", message: `경험 분리: ${split.reason}`, detail: split });
    for (const s of split.segments) {
      onProgress?.({
        stage: "classify",
        message: `  ${s.index + 1}. ${s.title} — ${TYPE_BY_ID.get(s.typeId)?.label ?? s.typeId}`
          + (s.located ? ` (원문 ${s.start.toLocaleString()}~${s.end.toLocaleString()}자)` : " (위치 미확인 → 원문 전체에서 이 경험만)"),
      });
    }
    for (const d of split.dropped) onProgress?.({ stage: "classify", message: `  제외: ${d.title} — ${d.why}` });
  }

  /* ── 3a. 나누지 않음 → 예전과 같은 단일 정리 ───────── */
  if (!split.applied) {
    let factsheet: Factsheet | null = null;
    if (preset.factsheet) {
      onProgress?.({ stage: "extract", message: "사실 시트 작성" });
      factsheet = await buildFactsheet(session, docs).catch(() => {
        onProgress?.({ stage: "extract", message: "사실 시트 실패 — 원문만으로 진행합니다" });
        return null;
      });
      reportFactsheet(onProgress, factsheet);
    }
    const item = await runExperience(base, classification, factsheet);
    return { classification, split, items: [item], failed: [], usage: session.usage };
  }

  /* ── 3b. 경험별 정리 (동시에 여러 개) ─────────────── */
  const total = split.segments.length;
  const limit = Math.max(1, PIPELINE.experienceConcurrency);
  onProgress?.({ stage: "extract", message: `경험 ${total}개를 ${Math.min(limit, total)}개씩 동시에 정리합니다` });

  const outcomes = await mapLimit(split.segments, limit, async (seg) => {
    const tag = `[${seg.index + 1}/${total} ${seg.title}]`;
    const prog: ProgressHandler = (e) => onProgress?.({ ...e, message: `${tag} ${e.message}` });
    // 경험마다 세션을 갈라 사용량을 따로 센다 (모델 선택 결과는 공유)
    const own = session.fork?.() ?? session;
    const before = snapshot(own.usage);
    try {
      const segDocs = segmentDocs(docs, seg);
      const ctx: RunContext = {
        ...base,
        session: own,
        docs: segDocs,
        index: seg.located ? new SourceIndex(segDocs.map((d) => d.text)) : index,
        userHint: focusHint(seg, options.userHint),
        onProgress: prog,
      };

      // 사실 시트도 경험 구간만으로 만든다 — 다른 경험의 수치가 섞여 들어가지 않게
      let factsheet: Factsheet | null = null;
      if (preset.factsheet) {
        prog({ stage: "extract", message: "사실 시트 작성" });
        factsheet = await buildFactsheet(own, segDocs).catch(() => {
          prog({ stage: "extract", message: "사실 시트 실패 — 원문만으로 진행합니다" });
          return null;
        });
        reportFactsheet(prog, factsheet);
      }

      const spec = TYPE_BY_ID.get(seg.typeId)!;
      const segClassification: ClassificationResult = {
        categoryId: spec.category,
        typeId: spec.id,
        confidence: seg.confidence,
        rationale: `[경험 분리 ${seg.index + 1}/${total}] ${seg.title}${seg.hint ? ` — ${seg.hint}` : ""}\n`
          + `(문서 전체 판단: ${classification.rationale.split("\n")[0]})`,
        alternatives: [],
        multipleExperiences: false,
        splitSuggestions: [],
      };

      const r = await runExperience(ctx, segClassification, factsheet);
      return {
        ok: true as const,
        item: {
          ...r,
          // 근거 위치를 원문 전체 좌표로 — 보고서가 원문 전체 위에 하이라이트한다
          provenance: shiftProvenance(r.provenance, seg),
          sources: docs.map((d) => ({ sourceId: d.sourceId, name: d.name, text: d.text })),
          usage: diffUsage(own.usage, before),
          segment: seg,
        },
      };
    } catch (e) {
      const error = (e as Error).message ?? String(e);
      prog({ stage: "done", message: `실패 — ${error.slice(0, 160)} (나머지 경험은 계속 정리합니다)` });
      return { ok: false as const, failed: { title: seg.title, typeId: seg.typeId, error } };
    } finally {
      if (own !== session) addUsage(session.usage, diffUsage(own.usage, before));
    }
  });
  const items: OrganizeManyResult["items"] = outcomes.flatMap((o) => (o.ok ? [o.item] : []));
  const failed: OrganizeManyResult["failed"] = outcomes.flatMap((o) => (o.ok ? [] : [o.failed]));

  if (!items.length) {
    throw new Error(`경험 ${total}개를 모두 정리하지 못했습니다: ${failed.map((f) => `${f.title}(${f.error})`).join(" / ")}`);
  }
  onProgress?.({
    stage: "done",
    message: `경험 ${items.length}개 정리 완료${failed.length ? ` · 실패 ${failed.length}개` : ""}`,
  });
  return { classification, split, items, failed, usage: session.usage };
}

/**
 * 경험 하나 정리 — 배분 ↔ 감독 루프 → 최종 필드 감사 → 빈 칸 안내.
 * ctx.docs는 원문 전체일 수도, 경험 하나의 구간일 수도 있다.
 */
async function runExperience(
  ctx: RunContext,
  initialClassification: ClassificationResult,
  factsheet: Factsheet | null,
): Promise<OrganizeResult> {
  const { session, docs, index, embedder, onProgress } = ctx;
  let classification = initialClassification;
  const quality = ctx.quality;
  const preset = QUALITY_PRESETS[quality];
  const heavyExtract = preset.heavyExtract;
  const ensemble = preset.ensemble;
  const fsText = factsheetText(factsheet);

  const initialType = TYPE_BY_ID.get(classification.typeId);
  if (!initialType) throw new Error(`알 수 없는 경험 유형: ${classification.typeId}`);
  let type: ExperienceTypeSpec = initialType;

  /* ── 2~3. 배분 ↔ 감독 루프 ──────────────────────── */
  let draft: ExtractionResult | null = null;
  let feedback: string | undefined;
  const history: ReviewResult[] = [];
  let final: ReviewResult | null = null;
  let rounds = 0;

  for (let round = 0; round <= PIPELINE.maxSupervisorRounds; round++) {
    rounds = round + 1;

    if (!draft || feedback) {
      if (ensemble > 1 && !feedback) {
        onProgress?.({ stage: "extract", message: `값싼 모델 ${ensemble}회 병렬 배분` });
        const temps = [0.05, 0.35, 0.6].slice(0, ensemble);
        const settled = await Promise.allSettled(temps.map((temperature) =>
          extract(session, type!, docs, {
            userHint: ctx.userHint, factsheet: fsText,
            temperature, light: !heavyExtract,
          })));
        const drafts = settled
          .filter((r): r is PromiseFulfilledResult<ExtractionResult> => r.status === "fulfilled")
          .map((r) => r.value);
        if (!drafts.length) throw (settled[0] as PromiseRejectedResult).reason;

        if (drafts.length === 1) {
          draft = drafts[0]!;
        } else {
          const { result, conflicts } = mergeDrafts(type, drafts, index);
          draft = result;
          onProgress?.({
            stage: "extract",
            message: `필드별 우수안 선택 · 충돌 ${conflicts.length}건`,
          });
          if (conflicts.length) {
            const fixed = await arbitrate(session, conflicts, fsText).catch(() => ({}));
            for (const [k, v] of Object.entries(fixed)) draft.values[k] = v;
            onProgress?.({ stage: "extract", message: `충돌 중재 ${Object.keys(fixed).length}건 확정` });
          }
        }
      } else {
        onProgress?.({
          stage: "extract",
          message: feedback ? `재작업 중 (${round + 1}회차)` : `항목별 배분 중${heavyExtract ? "" : " (값싼 모델)"}`,
        });
        draft = await extract(session, type, docs, {
          userHint: ctx.userHint, feedback, factsheet: fsText, light: !heavyExtract,
        });
      }
      feedback = undefined;
    }

    // 근거 인용마다 원문 위치를 붙인다 (LLM 호출 없음) — 감독 근거 구간·하이라이트·감사관이 쓴다
    draft = { ...draft, provenance: locateQuotes(draft.provenance, docs) };

    onProgress?.({ stage: "validate", message: "형식·근거·맥락 기계 검증 (RAGKOR)" });
    const validatorIssues = [
      ...runValidators(type, draft, docs, index),
      ...(await checkContext(type, draft.values, draft.provenance, docs, { embedder })),
    ];

    // 빠른 경로: 감독 LLM 없이 기계 검증 결과만 넘긴다 — 판정은 필드 감사와 사용자 확인이 맡는다
    if (!preset.supervise) {
      rounds = 0;
      final = {
        verdict: "approve",
        scores: { classification: 0, coverage: 0, faithfulness: 0, formatting: 0 },
        issues: validatorIssues,
        patch: {},
        comment: "감독 단계 생략 — 기계 검증(근거·수치·형식) 결과만 반영했습니다.",
      };
      break;
    }

    const spans = evidenceSpans(docs, draft.values, draft.provenance, index);
    onProgress?.({
      stage: "supervise",
      message: `감독 검수 (${round + 1}회차) · 근거 ${spans.length.toLocaleString()}자로 압축`,
    });
    const review = await supervise(session, type, draft, docs, validatorIssues,
      { evidenceText: spans, factsheet: fsText });
    history.push(review);
    final = review;
    onProgress?.({
      stage: "supervise",
      message: `검수 결과: ${review.verdict} — 충실도 ${review.scores.faithfulness}점, 이슈 ${review.issues.length}건`,
      detail: review,
    });

    /* 유형 자체가 틀렸다 → 유형 바꾸고 처음부터 다시 배분 */
    if (
      review.verdict === "reclassify" &&
      review.reclassifyTo &&
      TYPE_BY_ID.has(review.reclassifyTo) &&
      review.reclassifyTo !== type.id &&
      round < PIPELINE.maxSupervisorRounds
    ) {
      const next: ExperienceTypeSpec = TYPE_BY_ID.get(review.reclassifyTo)!;
      onProgress?.({
        stage: "classify",
        message: `감독이 유형을 정정했습니다: ${type.label} → ${next.label}`,
      });
      classification = {
        ...classification,
        typeId: next.id,
        categoryId: next.category,
        confidence: Math.min(0.85, classification.confidence + 0.1),
        rationale: `${classification.rationale}\n[감독 정정] ${review.comment}`,
        alternatives: [
          { typeId: type.id, confidence: classification.confidence, reason: "최초 분류 결과" },
          ...classification.alternatives,
        ].slice(0, 3),
      };
      type = next;
      draft = null;
      feedback = undefined;
      continue;
    }

    /* 수정 패치 적용 */
    if (Object.keys(review.patch).length) {
      draft = applyPatch(draft, review.patch);
      onProgress?.({
        stage: "supervise",
        message: `수정 ${Object.keys(review.patch).length}건 적용`,
      });
    }

    if (review.verdict === "approve") break;
    if (round >= PIPELINE.maxSupervisorRounds) break;

    /* 패치로 해결이 안 되는 blocker가 남았으면 배분 단계로 되돌린다 */
    const remaining = review.issues.filter(
      (i) => i.severity === "blocker" && !(i.path in review.patch),
    );
    if (remaining.length) {
      feedback = [
        "이전 회차 결과에서 아래 문제가 발견됐다. 원문을 다시 읽고 처음부터 정확히 다시 작성하라.",
        ...remaining.map((i) => `· [${i.type}] ${i.path} — ${i.detail}`),
        "",
        `감독 총평: ${review.comment}`,
      ].join("\n");
    } else {
      break; // major 이하만 남았고 패치로 처리됨
    }
  }

  if (!draft || !final) throw new Error("정리에 실패했습니다.");

  /* 패치 적용 후 형식 재검증 — 감독이 고치다 형식을 깨뜨렸을 수 있다 */
  draft = { ...draft, provenance: locateQuotes(draft.provenance, docs) };
  const revalidate = async (d: ExtractionResult) => [
    ...runValidators(type, d, docs, index),
    ...(await checkContext(type, d.values, d.provenance, docs, { embedder })),
  ];
  const postIssues = await revalidate(draft);
  final = {
    ...final,
    issues: mergeIssues(final.issues, postIssues),
  };

  /* ── 3.5 최종 필드 감사관 — 칸 하나씩, LLM 1회, 루프 없음 ── */
  const useAuditLlm = PIPELINE.auditor && preset.auditLlm;
  onProgress?.({
    stage: "supervise",
    message: useAuditLlm ? "최종 필드 감사 (칸별 대조)" : "최종 필드 감사 (기계 검증만)",
  });
  const audited = await auditFields(session, type, draft, docs, index, {
    issues: final.issues,
    evidenceText: evidenceSpans(docs, draft.values, draft.provenance, index, PIPELINE.supervisorEvidenceChars + 3000),
    useLlm: useAuditLlm,
    revalidate,
  });
  draft = audited.draft;
  final = { ...final, issues: mergeIssues(
    final.issues.filter((i) => i.foundBy === "supervisor"),
    audited.issues,
  ) };
  onProgress?.({
    stage: "supervise",
    message: `필드 감사: ${audited.report.summary.audited}칸 중 확인 ${audited.report.summary.ok} · `
      + `수정 ${audited.report.summary.fixed} · 확인 필요 ${audited.report.summary.flagged} `
      + `(보류 ${audited.report.rejected.length})`,
    detail: audited.report,
  });

  /* ── 4. Fallback 안내 ──────────────────────────── */
  onProgress?.({ stage: "guide", message: "빈 항목 안내 생성" });
  const fallback = await buildFallbackGuide(session, type, draft, docs, classification);

  const { layout, hiddenCommonKeys } = resolveLayout(type);
  const category = CATEGORIES.find((c) => c.id === type.category)!;

  onProgress?.({
    stage: "done",
    message: `완료 — ${type.label} / 채움률 ${fallback.completeness}% / 남은 이슈 ${final.issues.filter((i) => i.severity !== "minor").length}건`,
  });

  return {
    categoryId: type.category,
    categoryLabel: category.label,
    typeId: type.id,
    typeLabel: type.label,
    classification,
    form: { values: draft.values, layout, hiddenCommonKeys },
    provenance: draft.provenance,
    review: { rounds, final, history },
    fallback,
    audit: audited.report,
    sources: docs.map((d) => ({ sourceId: d.sourceId, name: d.name, text: d.text })),
    factsheet,
    ingest: {
      docs: docs.map((d) => ({
        sourceId: d.sourceId,
        name: d.name,
        kind: d.kind,
        chars: d.text.length,
        confidence: d.confidence,
        warnings: d.warnings,
      })),
    },
    usage: session.usage,
  };
}

function snapshot(u: UsageStat): UsageStat {
  return { ...u, calls: [...u.calls] };
}

/** 경험 하나에 쓴 사용량 = 정리 후 누적 − 정리 전 누적 (경험마다 갈라 낸 세션 기준) */
function diffUsage(after: UsageStat, before: UsageStat): UsageStat {
  return {
    inputTokens: after.inputTokens - before.inputTokens,
    outputTokens: after.outputTokens - before.outputTokens,
    cacheReadTokens: after.cacheReadTokens - before.cacheReadTokens,
    estimatedCostUsd: after.estimatedCostUsd - before.estimatedCostUsd,
    calls: after.calls.slice(before.calls.length),
  };
}

function addUsage(into: UsageStat, add: UsageStat): void {
  into.inputTokens += add.inputTokens;
  into.outputTokens += add.outputTokens;
  into.cacheReadTokens += add.cacheReadTokens;
  into.estimatedCostUsd += add.estimatedCostUsd;
  into.calls.push(...add.calls);
}

/** 순서를 지키며 최대 limit개씩 동시에 돌린다 */
async function mapLimit<T, R>(list: T[], limit: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(list.length);
  let next = 0;
  const worker = async () => {
    while (next < list.length) {
      const i = next++;
      out[i] = await fn(list[i]!);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, list.length) }, worker));
  return out;
}

function runValidators(
  type: ExperienceTypeSpec,
  draft: ExtractionResult,
  docs: Parameters<typeof checkGrounding>[3],
  index?: SourceIndex,
): ReviewIssue[] {
  return [
    ...validateStructure(type, draft.values),
    ...checkGrounding(type, draft.values, draft.provenance, docs, index),
  ];
}

function applyPatch(draft: ExtractionResult, patch: Record<string, unknown>): ExtractionResult {
  const values = structuredClone(draft.values);
  for (const [path, value] of Object.entries(patch)) {
    try {
      setByPath(values, path, value);
    } catch {
      /* 잘못된 경로는 무시 — 감독이 만든 경로가 스키마에 없을 수 있다 */
    }
  }
  // 비워진 항목의 근거는 떼어낸다
  const cleared = new Set(
    Object.entries(patch)
      .filter(([, v]) => v === null || v === undefined || v === "")
      .map(([p]) => p),
  );
  return {
    values,
    provenance: draft.provenance.filter((p) => !cleared.has(p.path)),
    unfilled: draft.unfilled,
  };
}

function mergeIssues(a: ReviewIssue[], b: ReviewIssue[]): ReviewIssue[] {
  const seen = new Set<string>();
  return [...a, ...b].filter((i) => {
    const k = `${i.path}|${i.type}|${i.detail}`;
    return seen.has(k) ? false : (seen.add(k), true);
  });
}

export { EXPERIENCE_TYPES, CATEGORIES };
