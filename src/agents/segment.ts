import { PIPELINE } from "../config.js";
import { alignQuote, fold, foldWithMap, type FoldedText } from "../ragkor/index.js";
import { TYPE_BY_ID } from "../schema/index.js";
import type { ClassificationResult, ExtractedDoc, FieldValue } from "../types.js";

/**
 * 경험 분리 — 이력서·포트폴리오처럼 한 파일에 여러 경험이 섞여 있을 때
 * 원문을 경험별 구간으로 잘라, 구간마다 따로 정리하게 한다.
 *
 * 분류기가 경험 목록(splitSuggestions)과 각 경험이 시작되는 원문 문구(anchor)를 준다.
 * 여기서는 LLM을 부르지 않는다. anchor를 원문에 정렬해 시작 위치를 찾고,
 * 다음 경험이 시작되는 곳까지를 그 경험의 구간으로 삼는다.
 *
 * 구간으로 자르면 좋은 점
 *   · 추출기가 '어느 경험을 쓸지' 고를 필요가 없다 → 다른 경험 내용이 섞이지 않는다
 *   · 근거 인용이 다른 경험의 같은 문구에 붙지 않는다 (정렬 범위가 그 구간뿐)
 *   · 감독·감사관이 구간 전체를 본다 (짧아서 압축으로 잘려 나가지 않는다)
 * 위치를 못 찾은 경험은 원문 전체를 주되 "이 경험만" 정리하라고 지시한다.
 */

export interface ExperienceSegment {
  /** 문서 순서 (0부터) */
  index: number;
  title: string;
  typeId: string;
  hint: string;
  confidence: number;
  /** 구간이 있는 파일. 위치를 못 찾았으면 null (원문 전체 사용) */
  sourceId: string | null;
  /** 원문 좌표 [start, end). 위치를 못 찾았으면 0, 0 */
  start: number;
  end: number;
  located: boolean;
  /** anchor 정렬 일치도 (0~1) */
  anchorScore: number;
}

export interface SegmentPlan {
  /** 실제로 나눠서 정리하는가 */
  applied: boolean;
  /** 나누거나 나누지 않은 이유 (진행 로그·보고서용) */
  reason: string;
  segments: ExperienceSegment[];
  /** 목록에서 뺀 후보와 이유 */
  dropped: { title: string; why: string }[];
}

type Suggestion = ClassificationResult["splitSuggestions"][number];

/** 시작 위치를 줄 머리로 당긴다 — 글머리표·번호 없이 제목 줄 전체가 구간에 들어가게 */
function snapToLineStart(text: string, pos: number, maxBack = 120): number {
  const from = Math.max(0, pos - maxBack);
  const nl = text.lastIndexOf("\n", pos - 1);
  return nl >= from ? nl + 1 : pos;
}

/** anchor → title 순서로 원문 위치를 찾는다 */
function locate(
  s: Suggestion,
  docs: ExtractedDoc[],
  folded: Map<string, FoldedText>,
): { sourceId: string; start: number; score: number } | null {
  const needles = [s.anchor, s.title].filter((x): x is string => !!x && fold(x).length >= 4);
  let best: { sourceId: string; start: number; score: number } | null = null;
  for (const needle of needles) {
    for (const d of docs) {
      let f = folded.get(d.sourceId);
      if (!f) folded.set(d.sourceId, (f = foldWithMap(d.text)));
      const r = alignQuote(needle, f);
      if (r && r.score > (best?.score ?? -1)) best = { sourceId: d.sourceId, start: r.start, score: r.score };
    }
    // anchor로 확실히 찾았으면 title은 볼 필요가 없다
    if (best && best.score >= PIPELINE.segmentAnchorFloor) break;
  }
  return best && best.score >= PIPELINE.segmentAnchorFloor ? best : null;
}

/**
 * 분류 결과로 분리 계획을 세운다 (LLM 호출 없음).
 * 경험이 2개 이상일 때만 applied=true.
 */
export function planSegments(docs: ExtractedDoc[], cls: ClassificationResult): SegmentPlan {
  const none = (reason: string): SegmentPlan => ({ applied: false, reason, segments: [], dropped: [] });
  if (!PIPELINE.splitExperiences) return none("경험 분리가 꺼져 있습니다 (PIPELINE.splitExperiences).");
  if (!cls.multipleExperiences) return none("분류기가 경험 하나짜리 자료로 판단했습니다.");

  const dropped: SegmentPlan["dropped"] = [];
  const seen = new Set<string>();
  const sugg: Suggestion[] = [];
  for (const s of cls.splitSuggestions ?? []) {
    const key = fold(s.title ?? "");
    if (!key) { dropped.push({ title: s.title ?? "", why: "제목이 비어 있습니다." }); continue; }
    if (seen.has(key)) { dropped.push({ title: s.title, why: "같은 제목이 이미 목록에 있습니다." }); continue; }
    seen.add(key);
    sugg.push(TYPE_BY_ID.has(s.typeId) ? s : { ...s, typeId: cls.typeId });
  }
  if (sugg.length < 2) {
    return { ...none(`분류기가 여러 경험이라고 했지만 나눌 후보가 ${sugg.length}개뿐입니다.`), dropped };
  }
  for (const s of sugg.slice(PIPELINE.maxExperiences)) {
    dropped.push({ title: s.title, why: `한 번에 정리하는 최대 ${PIPELINE.maxExperiences}개를 넘었습니다.` });
  }
  const kept = sugg.slice(0, PIPELINE.maxExperiences);

  // 1) 위치 찾기
  const folded = new Map<string, FoldedText>();
  const found = kept.map((s) => ({ s, at: locate(s, docs, folded) }));

  // 2) 같은 자리로 찾아진 후보는 앞의 것만 남긴다 (anchor가 같은 줄을 가리킴)
  const segs: ExperienceSegment[] = [];
  const taken: { sourceId: string; start: number }[] = [];
  for (const { s, at } of found) {
    const base = {
      title: s.title, typeId: s.typeId, hint: s.hint ?? "",
      confidence: typeof s.confidence === "number" ? s.confidence : cls.confidence,
    };
    if (!at) {
      segs.push({ ...base, index: 0, sourceId: null, start: 0, end: 0, located: false, anchorScore: 0 });
      continue;
    }
    const doc = docs.find((d) => d.sourceId === at.sourceId)!;
    const start = snapToLineStart(doc.text, at.start);
    if (taken.some((t) => t.sourceId === at.sourceId && Math.abs(t.start - start) < 12)) {
      dropped.push({ title: s.title, why: "다른 경험과 같은 위치를 가리킵니다." });
      continue;
    }
    taken.push({ sourceId: at.sourceId, start });
    segs.push({ ...base, index: 0, sourceId: at.sourceId, start, end: 0, located: true, anchorScore: at.score });
  }

  // 3) 구간 끝 = 같은 파일에서 다음 경험이 시작되는 곳 (없으면 파일 끝)
  const located = segs.filter((x) => x.located);
  for (const seg of located) {
    const doc = docs.find((d) => d.sourceId === seg.sourceId)!;
    const next = located
      .filter((o) => o.sourceId === seg.sourceId && o.start > seg.start)
      .reduce((m, o) => Math.min(m, o.start), doc.text.length);
    seg.end = next;
  }

  // 4) 문서 순서로 정렬 (파일 순서 → 위치), 위치를 못 찾은 경험은 뒤로
  const docOrder = new Map(docs.map((d, i) => [d.sourceId, i]));
  segs.sort((a, b) => {
    if (a.located !== b.located) return a.located ? -1 : 1;
    if (!a.located) return 0;
    return (docOrder.get(a.sourceId!)! - docOrder.get(b.sourceId!)!) || a.start - b.start;
  });
  // 너무 짧은 구간(제목만 걸린 경우)은 원문 전체 + 집중 지시로 돌린다
  for (const seg of segs) {
    if (seg.located && seg.end - seg.start < 20) {
      Object.assign(seg, { sourceId: null, start: 0, end: 0, located: false });
    }
  }
  segs.forEach((seg, i) => (seg.index = i));

  if (segs.length < 2) {
    return { ...none("나눌 경험이 2개 미만으로 남았습니다."), dropped };
  }
  const n = segs.filter((x) => x.located).length;
  return {
    applied: true,
    reason: `경험 ${segs.length}개로 나눠 정리합니다 (원문 위치 확인 ${n}개`
      + `${n < segs.length ? ` · 위치 미확인 ${segs.length - n}개는 원문 전체에서 해당 경험만 정리` : ""}).`,
    segments: segs,
    dropped,
  };
}

/** 이 경험에 쓸 원문. 위치를 찾았으면 그 구간만, 아니면 원문 전체 */
export function segmentDocs(docs: ExtractedDoc[], seg: ExperienceSegment): ExtractedDoc[] {
  if (!seg.located) return docs;
  const doc = docs.find((d) => d.sourceId === seg.sourceId)!;
  return [{
    ...doc,
    text: doc.text.slice(seg.start, seg.end),
    pages: [],
    metadata: { ...doc.metadata, segment: `${seg.index + 1}. ${seg.title}` },
  }];
}

/** 추출기에 줄 집중 지시 — 사용자 힌트 뒤에 붙인다 */
export function focusHint(seg: ExperienceSegment, userHint?: string): string {
  const lines = [
    seg.located
      ? `이 원문은 여러 경험이 담긴 자료에서 "${seg.title}" 경험 부분만 잘라 낸 것이다. 이 경험 하나만 정리한다.`
      : `이 원문에는 여러 경험이 섞여 있다. 그중 "${seg.title}" 경험 하나만 정리하고, 다른 경험의 내용은 어느 칸에도 넣지 않는다.`,
    seg.hint ? `이 경험의 위치 단서: ${seg.hint}` : "",
    userHint ?? "",
  ];
  return lines.filter(Boolean).join("\n");
}

/**
 * 구간 기준으로 잡힌 근거 위치를 원문 전체 좌표로 옮긴다.
 * 보고서가 원문 전체를 보여 주고 그 위에 하이라이트하기 때문이다.
 */
export function shiftProvenance(prov: FieldValue[], seg: ExperienceSegment): FieldValue[] {
  if (!seg.located || !seg.start) return prov;
  return prov.map((p) => ({
    ...p,
    quotes: p.quotes.map((q) =>
      q.sourceId === seg.sourceId && q.start !== undefined && q.end !== undefined
        ? { ...q, start: q.start + seg.start, end: q.end + seg.start }
        : q),
  }));
}
