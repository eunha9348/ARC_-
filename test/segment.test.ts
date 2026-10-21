/**
 * 경험 분리 검증 — API 키 없이 돈다.
 *   npx tsx test/segment.test.ts
 *
 * 1) 분리 계획: 분류기의 분리 목록(anchor)으로 원문을 경험별 구간으로 정확히 자르는가.
 *    줄바꿈이 없는 PDF 텍스트, 표기가 조금 다른 anchor, 위치를 못 찾는 후보, 중복·초과 후보.
 * 2) 전체 파이프라인: 가짜 LLM으로 끝까지 돌려, 경험마다 따로 정리되고
 *    각 추출 호출이 **자기 구간만** 받는가 (다른 경험 내용이 섞이지 않는가).
 */
import assert from "node:assert/strict";
import { focusHint, planSegments, segmentDocs, shiftProvenance } from "../src/agents/segment.js";
import { organizeExperience, organizeExperiences } from "../src/pipeline.js";
import { PIPELINE } from "../src/config.js";
import type { LlmSession, StructuredRequest } from "../src/llm/index.js";
import type { ClassificationResult, ExtractedDoc } from "../src/types.js";

let passed = 0;
async function test(name: string, fn: () => void | Promise<void>) {
  try {
    await fn();
    passed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    console.error(`  ✗ ${name}\n    ${(e as Error).message}`);
    process.exitCode = 1;
  }
}

/* ── 이력서 예시 (실제 사용자 이력서와 같은 구조) ─────────────────── */

const RESUME = [
  "YUN JIHO",
  "jiho@example.com · Seoul",
  "EDUCATION",
  "Korea University Mar 2021 - Present",
  "B.S. in Business Administration, GPA 3.9/4.5",
  "PROJECTS & AWARDS",
  "Pension AI Agent Jul 2026 - Present",
  "Team Lead & PM · AI Developer",
  "• Led end-to-end product and AI development, designing a hierarchical multi-agent retirement planner",
  "AI-Based Youth Experience Archiving & Analysis Service ‘ARC’ Mar 2026 - Present",
  "Air Force Startup Competition · PM & AI Developer",
  "• Defined ARC's product concept to address youth job seekers' lack of self-understanding",
  "• Completed the web prototype (story-arc.org) and tested it with 20 domestic and international university students",
  "• Advanced to the Air Force Startup Competition finals, earned the Creativity Award; 30 of 337 teams (8.9%) received awards",
  "ACTIVITIES",
  "KUBS Finance Club Sep 2022 - Feb 2024",
  "• Ran weekly equity research sessions for 40 members",
  "SKILLS",
  "Python, TypeScript, Figma",
].join("\n");

function doc(text: string, sourceId = "src1", name = "Yun_Jiho_Resume.pdf"): ExtractedDoc {
  return {
    sourceId, name, kind: "pdf", mimeType: "application/pdf", bytesLength: text.length,
    text, pages: [], metadata: {}, warnings: [], confidence: 1,
  } as unknown as ExtractedDoc;
}

const SUGGESTIONS: ClassificationResult["splitSuggestions"] = [
  { title: "고려대학교 경영학과", typeId: "academic.major_course", hint: "EDUCATION", anchor: "Korea University Mar 2021 - Present", confidence: 0.9 },
  { title: "Pension AI Agent", typeId: "project.team", hint: "PROJECTS 첫 항목", anchor: "Pension AI Agent Jul 2026 - Present", confidence: 0.8 },
  { title: "ARC", typeId: "project.team", hint: "공군 창업경진대회", anchor: "AI-Based Youth Experience Archiving & Analysis Service ‘ARC’ Mar 2026 - Present", confidence: 0.7 },
  { title: "KUBS Finance Club", typeId: "academic.club", hint: "ACTIVITIES", anchor: "KUBS Finance Club Sep 2022 - Feb 2024", confidence: 0.85 },
];

function cls(over: Partial<ClassificationResult> = {}): ClassificationResult {
  return {
    categoryId: "project", typeId: "project.team", confidence: 0.55, rationale: "종합 이력서",
    alternatives: [], multipleExperiences: true, splitSuggestions: SUGGESTIONS, ...over,
  };
}

const textOf = (d: ExtractedDoc, s: { start: number; end: number }) => d.text.slice(s.start, s.end);

/* ── 1) 분리 계획 ─────────────────────────────────────────── */

await test("이력서를 경험 4개 구간으로 자르고, 구간마다 자기 내용만 담는다", () => {
  const d = doc(RESUME);
  const plan = planSegments([d], cls());
  assert.equal(plan.applied, true, plan.reason);
  assert.equal(plan.segments.length, 4);
  assert.deepEqual(plan.segments.map((s) => s.title), ["고려대학교 경영학과", "Pension AI Agent", "ARC", "KUBS Finance Club"]);
  assert.ok(plan.segments.every((s) => s.located), "모든 경험의 위치를 찾아야 한다");

  const [edu, pension, arc, club] = plan.segments.map((s) => textOf(d, s));
  assert.ok(edu!.startsWith("Korea University") && edu!.includes("GPA 3.9"));
  assert.ok(pension!.startsWith("Pension AI Agent") && pension!.includes("hierarchical"));
  assert.ok(!pension!.includes("story-arc"), "Pension 구간에 ARC 내용이 섞였다");
  assert.ok(arc!.startsWith("AI-Based Youth") && arc!.includes("30 of 337 teams (8.9%)"));
  assert.ok(!arc!.includes("hierarchical"), "ARC 구간에 Pension 내용이 섞였다");
  assert.ok(club!.includes("40 members") && !club!.includes("Creativity Award"));
  // 같은 'PM · AI Developer' 문구가 두 프로젝트에 있어도 각자 자기 구간에만 있다
  assert.ok(pension!.includes("PM · AI Developer") && arc!.includes("PM & AI Developer"));
});

await test("줄바꿈이 없는 PDF 텍스트도 같은 위치에서 자른다", () => {
  const flat = doc(RESUME.replace(/\n/g, " "));
  const plan = planSegments([flat], cls());
  assert.equal(plan.segments.filter((s) => s.located).length, 4);
  const arc = textOf(flat, plan.segments[2]!);
  assert.ok(arc.startsWith("AI-Based Youth"), arc.slice(0, 40));
  assert.ok(!arc.includes("KUBS"), "다음 경험 앞에서 끊겨야 한다");
});

await test("anchor 표기가 조금 달라도(대시·따옴표·공백) 위치를 찾는다", () => {
  const sugg = SUGGESTIONS.map((s) => (s.title === "ARC"
    ? { ...s, anchor: "AI-Based Youth Experience Archiving & Analysis Service 'ARC'  Mar 2026 – Present" }
    : s));
  const plan = planSegments([doc(RESUME)], cls({ splitSuggestions: sugg }));
  const arc = plan.segments.find((s) => s.title === "ARC")!;
  assert.ok(arc.located, `일치도 ${arc.anchorScore}`);
  assert.ok(arc.anchorScore >= PIPELINE.segmentAnchorFloor);
});

await test("위치를 못 찾은 경험은 원문 전체 + '이 경험만' 지시로 넘기고, 뒤로 보낸다", () => {
  const sugg = [...SUGGESTIONS, { title: "토익 900점", typeId: "career.language", hint: "어학", anchor: "TOEIC 900 (2025)", confidence: 0.6 }];
  const d = doc(RESUME);
  const plan = planSegments([d], cls({ splitSuggestions: sugg }));
  const last = plan.segments.at(-1)!;
  assert.equal(last.title, "토익 900점");
  assert.equal(last.located, false);
  assert.deepEqual(segmentDocs([d], last), [d], "원문 전체를 줘야 한다");
  assert.match(focusHint(last), /다른 경험의 내용은 어느 칸에도 넣지 않는다/);
  assert.match(plan.reason, /위치 미확인 1개/);
});

await test("나누지 않는 경우: 단일 경험 판단 · 후보 1개 · 중복 제목", () => {
  assert.equal(planSegments([doc(RESUME)], cls({ multipleExperiences: false })).applied, false);
  assert.equal(planSegments([doc(RESUME)], cls({ splitSuggestions: SUGGESTIONS.slice(0, 1) })).applied, false);
  const dup = planSegments([doc(RESUME)], cls({ splitSuggestions: [SUGGESTIONS[0]!, { ...SUGGESTIONS[0]! }] }));
  assert.equal(dup.applied, false);
  assert.equal(dup.dropped.length, 1);
});

await test("모르는 유형은 대표 유형으로 바꾸고, 최대 개수를 넘는 후보는 뺀다", () => {
  const lines: string[] = [];
  const sugg: ClassificationResult["splitSuggestions"] = [];
  for (let i = 1; i <= PIPELINE.maxExperiences + 2; i++) {
    lines.push(`Volunteer Program Number ${i} Jan 20${10 + i} - Dec 20${10 + i}`, `• Helped community center ${i} with weekly tutoring`);
    sugg.push({ title: `Program ${i}`, typeId: i === 1 ? "nope.unknown" : "growth.volunteer", hint: "", anchor: `Volunteer Program Number ${i} Jan 20${10 + i}`, confidence: 0.8 });
  }
  const plan = planSegments([doc(lines.join("\n"))], cls({ splitSuggestions: sugg }));
  assert.equal(plan.segments.length, PIPELINE.maxExperiences);
  assert.equal(plan.dropped.length, 2);
  assert.equal(plan.segments[0]!.typeId, "project.team", "모르는 유형은 대표 유형으로");
});

await test("구간 기준 근거 위치를 원문 전체 좌표로 옮긴다", () => {
  const d = doc(RESUME);
  const arc = planSegments([d], cls()).segments[2]!;
  const local = textOf(d, arc).indexOf("30 of 337");
  const [moved] = shiftProvenance([{ path: "title", value: undefined, confidence: 0.9,
    quotes: [{ sourceId: "src1", text: "30 of 337", start: local, end: local + 9 }] }], arc);
  const q = moved!.quotes[0]!;
  assert.equal(d.text.slice(q.start!, q.end!), "30 of 337");
});

/* ── 2) 전체 파이프라인 (가짜 LLM) ─────────────────────────── */

/** 호출마다 사용량을 올리는 가짜 세션 — 경험별 사용량 나누기를 검증하려고 */
function stubSession(handler: (req: StructuredRequest) => unknown) {
  const calls: { tool: string; text: string; hint: string }[] = [];
  const flight = { now: 0, max: 0 };
  const make = (): LlmSession => {
    const usage = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, estimatedCostUsd: 0, calls: [] as { stage: string; ms: number }[] };
    return {
      providerName: "stub",
      usage,
      async resolveModel() { return "stub"; },
      async structured<T>(req: StructuredRequest) {
        calls.push({
          tool: req.toolName,
          text: req.content.map((c) => (c.type === "text" ? c.text : "")).join("\n"),
          hint: req.systemVolatile ?? "",
        });
        flight.max = Math.max(flight.max, ++flight.now);
        await new Promise((r) => setTimeout(r, 5));
        flight.now--;
        usage.inputTokens += 100; usage.outputTokens += 10; usage.estimatedCostUsd += 0.001;
        usage.calls.push({ stage: req.stage, ms: 1 });
        return handler(req) as T;
      },
      async text() { return ""; },
      async verify() { return { ok: true, detail: "stub" }; },
      fork: () => make(),
    };
  };
  return { session: make(), calls, flight };
}

const FACTSHEET = { docType: "이력서", register: "격식체", title: null, outline: [],
  entities: { people: [], orgs: [], products: [], tools: [] }, numbers: [], dates: [], myActions: [],
  teamActions: [], unclear: [], achievements: [], problems: [], learnings: [], links: [], normalized: [] };
const REVIEW = { verdict: "approve", scores: { classification: 95, coverage: 80, faithfulness: 90, formatting: 100 },
  issues: [], reclassifyTo: null, patch: [], comment: "" };
const GUIDE = { missing: [], recommendedUploads: [], nextQuestions: [] };

/** 추출기: 받은 원문 구간에서 첫 줄을 경험명으로 쓴다 (근거 = 그 줄 그대로) */
function extractFrom(req: StructuredRequest) {
  const text = req.content.map((c) => (c.type === "text" ? c.text : "")).join("\n");
  const body = text.split("## 원문\n")[1] ?? "";
  const first = body.split("\n").find((l) => l.trim() && !l.startsWith("<<<") && !l.startsWith("[")) ?? "";
  return {
    values: { title: first.trim() },
    evidence: [{ path: "title", sourceId: "src1", quote: first.trim(), confidence: 0.9 }],
    unfilled: [],
  };
}

await test("이력서 → 경험 2개를 따로 정리하고, 추출기는 자기 구간만 받는다", async () => {
  const two = [SUGGESTIONS[1]!, SUGGESTIONS[2]!];
  const { session, calls, flight } = stubSession((req) => {
    switch (req.toolName) {
      case "submit_classification": return cls({ splitSuggestions: two });
      case "submit_factsheet": return FACTSHEET;
      case "submit_experience": return extractFrom(req);
      case "submit_arbitration": return { decisions: [] };
      case "submit_review": return REVIEW;
      case "submit_field_audit": return { fields: [], comment: "" };
      case "submit_guide": return GUIDE;
      default: throw new Error(`예상하지 못한 호출: ${req.toolName}`);
    }
  });
  const progress: string[] = [];
  const r = await organizeExperiences([{ name: "Yun_Jiho_Resume.pdf", text: RESUME }],
    { session, quality: "balanced", onProgress: (e) => progress.push(e.message) });

  assert.equal(r.split.applied, true);
  assert.equal(r.items.length, 2);
  assert.equal(r.failed.length, 0);
  assert.deepEqual(r.items.map((i) => i.segment?.title), ["Pension AI Agent", "ARC"]);
  assert.ok(String(r.items[0]!.form.values.title).startsWith("Pension AI Agent"));
  assert.ok(String(r.items[1]!.form.values.title).startsWith("AI-Based Youth"));

  // 추출 호출 2번(경험 2개 × 1회) — Pension 쪽 원문에 ARC 내용이 없고, 그 반대도 마찬가지
  const ex = calls.filter((c) => c.tool === "submit_experience");
  assert.equal(ex.length, 2);
  const pensionCalls = ex.filter((c) => c.text.includes("hierarchical"));
  const arcCalls = ex.filter((c) => c.text.includes("story-arc.org"));
  assert.equal(pensionCalls.length, 1);
  assert.equal(arcCalls.length, 1);
  assert.ok(pensionCalls.every((c) => !c.text.includes("story-arc.org")), "Pension 추출에 ARC 원문이 섞였다");
  assert.ok(arcCalls.every((c) => !c.text.includes("hierarchical")), "ARC 추출에 Pension 원문이 섞였다");
  assert.ok(ex.every((c) => /경험 부분만 잘라 낸 것이다/.test(c.hint)), "집중 지시가 빠졌다");

  // 경험은 동시에 정리하고, 경험별 사용량은 섞이지 않는다 (분류 1회는 전체에만)
  assert.ok(flight.max >= 2, `경험이 순서대로만 돌았다 (동시 호출 최대 ${flight.max})`);
  const perItem = r.items.map((i) => i.usage.calls.length);
  assert.equal(perItem[0], perItem[1]);
  assert.equal(r.usage.calls.length, 1 + perItem[0]! + perItem[1]!);

  // 사실 시트도 경험마다 따로 (분류 1 + 사실 시트 2)
  assert.equal(calls.filter((c) => c.tool === "submit_factsheet").length, 2);
  assert.equal(calls.filter((c) => c.tool === "submit_classification").length, 1);

  // 근거 위치는 원문 전체 좌표 — 보고서가 원문 전체 위에 하이라이트한다
  const q = r.items[1]!.provenance.find((p) => p.path === "title")!.quotes[0]!;
  assert.ok(RESUME.slice(q.start!, q.end!).startsWith("AI-Based Youth"), RESUME.slice(q.start!, q.end!));
  assert.equal(r.items[1]!.sources![0]!.text, RESUME);

  // 경험별 사용량 = 그 경험에 든 호출만, 합은 전체 이하 (분류 호출은 공통 비용)
  const per = r.items.map((i) => i.usage.calls.length);
  assert.ok(per.every((n) => n > 0));
  assert.equal(per[0]! + per[1]! + 1, r.usage.calls.length);
  assert.ok(progress.some((m) => m.startsWith("[2/2 ARC]")), "진행 로그에 경험 표시가 없다");
});

await test("한 경험이 실패해도 나머지는 정리하고 실패 목록에 남긴다", async () => {
  const two = [SUGGESTIONS[1]!, SUGGESTIONS[2]!];
  const { session } = stubSession((req) => {
    const text = req.content.map((c) => (c.type === "text" ? c.text : "")).join("\n");
    switch (req.toolName) {
      case "submit_classification": return cls({ splitSuggestions: two });
      case "submit_factsheet": return FACTSHEET;
      case "submit_experience":
        if (text.includes("hierarchical")) throw new Error("일시적 오류");
        return extractFrom(req);
      case "submit_arbitration": return { decisions: [] };
      case "submit_review": return REVIEW;
      case "submit_field_audit": return { fields: [], comment: "" };
      case "submit_guide": return GUIDE;
      default: throw new Error(`예상하지 못한 호출: ${req.toolName}`);
    }
  });
  const r = await organizeExperiences([{ name: "r.pdf", text: RESUME }], { session });
  assert.equal(r.items.length, 1);
  assert.equal(r.items[0]!.segment?.title, "ARC");
  assert.deepEqual(r.failed.map((f) => f.title), ["Pension AI Agent"]);
});

await test("경험 하나짜리 자료는 나누지 않고 예전과 같은 결과 1개", async () => {
  const one = "하계 인턴 최종 보고서\n라온테크 백엔드팀에서 재고 API를 개발했습니다.";
  const { session, calls } = stubSession((req) => {
    switch (req.toolName) {
      case "submit_classification":
        return { categoryId: "career", typeId: "career.work", confidence: 0.95, rationale: "인턴 보고서",
          alternatives: [], multipleExperiences: false, splitSuggestions: [] };
      case "submit_factsheet": return FACTSHEET;
      case "submit_experience": return extractFrom(req);
      case "submit_arbitration": return { decisions: [] };
      case "submit_review": return REVIEW;
      case "submit_field_audit": return { fields: [], comment: "" };
      case "submit_guide": return GUIDE;
      default: throw new Error(`예상하지 못한 호출: ${req.toolName}`);
    }
  });
  const r = await organizeExperiences([{ name: "report.md", text: one }], { session });
  assert.equal(r.split.applied, false);
  assert.equal(r.items.length, 1);
  assert.equal(r.items[0]!.segment, undefined);
  // 기본(fast)은 사실 시트·감독·상위 모델 감사를 부르지 않는다
  assert.equal(calls.filter((c) => c.tool === "submit_factsheet").length, 0);
  assert.equal(calls.filter((c) => c.tool === "submit_review").length, 0);
  assert.equal(calls.filter((c) => c.tool === "submit_field_audit").length, 0);
  assert.equal(r.items[0]!.review.rounds, 0);
  // 예전 진입점도 그대로 동작
  const single = await organizeExperience([{ name: "report.md", text: one }], { session });
  assert.equal(single.typeId, "career.work");
});

console.log(`\n경험 분리 ${passed}건 통과`);
