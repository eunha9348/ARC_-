
import { PIPELINE } from "../config.js";
import { CATEGORIES, EXPERIENCE_TYPES } from "../schema/index.js";
import type { ClassificationResult, ExtractedDoc } from "../types.js";
import type { LlmSession } from "../llm/index.js";
import { buildClassificationDigest } from "./evidence.js";

/** 캐시되는 안정 프리픽스 — 18종 카탈로그. 요청마다 동일해야 캐시가 산다. */
const TYPE_CATALOG = (() => {
  const byCat = CATEGORIES.map((c) => {
    const types = EXPERIENCE_TYPES.filter((t) => t.category === c.id)
      .map(
        (t) =>
          `  · ${t.id} — ${t.label}\n      동의어: ${t.aliases.join(", ")}\n      신호: ${t.signals.join(", ")}\n      전용 항목: ${t.fields.map((f) => f.label).join(", ")}`,
      )
      .join("\n");
    return `[${c.id}] ${c.emoji} ${c.label}\n  대분류 신호: ${c.signals.join(", ")}\n${types}`;
  }).join("\n\n");
  return byCat;
})();

const SYSTEM = `당신은 ARC 경험 기록 서비스의 **1단계 분류 에이전트**다.
사용자가 올린 산출물(파일)을 읽고, 그것이 어떤 경험인지 판별한다.

작업 순서는 반드시 이 순서다.
  1) 먼저 **대분류**(학업 / 커리어 / 프로젝트 / 개인성장) 4개 중 하나를 고른다.
  2) 그 대분류 안의 **세부 유형**을 고른다.

── 판별 원칙 ──
1. **산출물의 형식이 아니라 활동의 성격**으로 판단한다.
   PDF라서 논문이 아니고, 코드라서 개인 프로젝트가 아니다. 누가·어디서·왜 한 일인지를 본다.
2. 헷갈리는 경계는 다음 기준으로 자른다.
   · 회사에서 급여를 받고 한 일 → career.work (팀 프로젝트처럼 보여도)
   · 학교 수업의 일부로 한 팀 과제 → academic.major_course (수업 기록 안에 담는다)
   · 수업/회사와 무관하게 스스로 만든 것 → project.personal / project.team
   · 대회에서 상을 받은 게 핵심이면 → career.award (만든 결과물이 있어도)
   · 상을 못 받았거나 참가가 핵심이면 → career.external 또는 project.*
   · 학회·동아리는 소속 단체가 주체, 대외활동은 외부 기관이 주최
   · 결과물의 '완성도·작품성'이 핵심이면 project.creative
   · 배운 것/느낀 것이 핵심이고 산출물이 부차적이면 growth.*
3. 근거가 약하면 confidence를 정직하게 낮춘다. 억지로 확신하지 않는다.
4. 한 파일에 서로 다른 경험이 여러 개 섞여 있으면(예: 이력서, 포트폴리오 전체, 활동 모음)
   multipleExperiences=true 로 두고 splitSuggestions에 **경험마다 하나씩** 담는다.
   시스템은 이 목록대로 원문을 잘라 경험별로 따로 정리한다. 빠진 경험은 정리되지 않는다.
   · 나누는 단위: 학교 1곳, 회사·인턴 1곳, 프로젝트 1개, 대외활동·동아리·학회 1개,
     자격증 1개, 어학 시험 1개, 독립된 수상 1건.
   · 같은 활동에서 받은 상·성과는 그 활동에 포함한다. 별도 경험으로 쪼개지 않는다.
     (상이 어떤 활동에도 속하지 않고 따로 적혀 있을 때만 career.award)
   · 연락처·자기소개·기술 스택 목록·관심사처럼 '경험'이 아닌 부분은 넣지 않는다.
   · anchor: 그 경험이 시작되는 원문 줄(보통 활동명·회사명·학교명이 적힌 제목 줄)을
     **원문 글자 그대로** 20~80자 복사한다. 번역·요약·고쳐 쓰기 금지 — 시스템이 이 문구로
     원문 위치를 찾아 자른다. 같은 문구가 여러 번 나오면 그 경험을 특정할 수 있게 길게 잡는다.
   · confidence: 그 경험의 유형 판별 신뢰도(0~1).
   · 문서에 나온 순서대로 적는다.
   · 이때 최상위 typeId/categoryId는 가장 비중이 큰 경험의 유형으로 둔다.
   한 파일이 경험 하나뿐이면 multipleExperiences=false, splitSuggestions=[].
5. rationale은 한국어 2~3문장. "무엇을 보고" 그렇게 판단했는지 원문 표현을 인용한다.

── 경험 유형 카탈로그 (18종) ──
${TYPE_CATALOG}`;

const SCHEMA = {
  type: "object",
  properties: {
    categoryId: { type: "string", enum: CATEGORIES.map((c) => c.id) },
    typeId: { type: "string", enum: EXPERIENCE_TYPES.map((t) => t.id) },
    confidence: { type: "number", description: "0~1. 근거가 약하면 정직하게 낮출 것." },
    rationale: { type: "string", description: "한국어 2~3문장. 원문 표현을 인용." },
    alternatives: {
      type: "array",
      description: "차점 후보 최대 2개. 없으면 빈 배열.",
      items: {
        type: "object",
        properties: {
          typeId: { type: "string", enum: EXPERIENCE_TYPES.map((t) => t.id) },
          confidence: { type: "number" },
          reason: { type: "string" },
        },
        required: ["typeId", "confidence", "reason"],
        additionalProperties: false,
      },
    },
    multipleExperiences: { type: "boolean" },
    splitSuggestions: {
      type: "array",
      description: "여러 경험이 섞여 있을 때만 채운다. 아니면 빈 배열.",
      items: {
        type: "object",
        properties: {
          title: { type: "string" },
          typeId: { type: "string", enum: EXPERIENCE_TYPES.map((t) => t.id) },
          hint: { type: "string", description: "원문 어느 부분이 이 경험인지" },
          anchor: { type: "string", description: "이 경험이 시작되는 원문 줄을 글자 그대로 20~80자. 번역·수정 금지." },
          confidence: { type: "number", description: "이 경험의 유형 판별 신뢰도 0~1" },
        },
        required: ["title", "typeId", "hint", "anchor", "confidence"],
        additionalProperties: false,
      },
    },
  },
  required: ["categoryId", "typeId", "confidence", "rationale", "alternatives", "multipleExperiences", "splitSuggestions"],
  additionalProperties: false,
} as const;

export async function classify(
  session: LlmSession,
  docs: ExtractedDoc[],
  userHint?: string,
): Promise<ClassificationResult> {
  const digest = buildClassificationDigest(docs, PIPELINE.classifierDigestChars);
  const result = await session.structured<ClassificationResult>({
    stage: "classify",
    systemStable: SYSTEM,
    systemVolatile: userHint ? `사용자가 준 추가 맥락: ${userHint}` : undefined,
    toolName: "submit_classification",
    toolDescription: "판별한 대분류와 세부 유형을 제출한다.",
    schema: SCHEMA as unknown as Record<string, unknown>,
    content: [{ type: "text", text: digest }],
    maxTokens: 8000,
  });

  // 유형과 대분류가 어긋나면 유형 쪽을 신뢰한다
  const spec = EXPERIENCE_TYPES.find((t) => t.id === result.typeId);
  if (spec && spec.category !== result.categoryId) result.categoryId = spec.category;
  return result;
}
