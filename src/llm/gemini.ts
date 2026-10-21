import { MODELS, PRICING, THINKING, googleKey } from "../config.js";
import type { UsageStat } from "../types.js";
import { coerceToSchema, toGeminiSchema } from "./gemini-schema.js";
import { newUsage, type LlmContent, type LlmSession, type Stage, type StructuredRequest } from "./provider.js";

const BASE = "https://generativelanguage.googleapis.com/v1beta";

interface GeminiModelInfo {
  name: string;
  displayName?: string;
  supportedGenerationMethods?: string[];
  inputTokenLimit?: number;
}

/**
 * Gemini 엔진.
 *
 * 모델 ID를 하드코딩하지 않는다. 첫 호출 때 ListModels로 실제 계정에서 쓸 수 있는
 * 모델 목록을 받아, config.MODELS.gemini.prefer 우선순위에 따라 **가장 최신 세대**를
 * 자동으로 고른다. config.MODELS.gemini.pin(기본 gemini-3.5-pro)이 목록에 있으면 그 모델을 쓴다.
 */
export class GeminiSession implements LlmSession {
  readonly providerName = "gemini";
  readonly usage: UsageStat = newUsage();
  private modelPromise: Promise<{ main: string; light: string }> | null = null;
  private noThinking = new Set<string>();
  /** 호출이 404로 막힌 자동 선택 모델 → 대신 쓸 모델 */
  private replaced = new Map<string, string>();

  constructor(private readonly apiKey: string = googleKey()) {}

  /* ───────────────── 모델 자동 선택 ───────────────── */

  async listModels(): Promise<GeminiModelInfo[]> {
    const res = await fetch(`${BASE}/models?pageSize=200`, { headers: { "x-goog-api-key": this.apiKey } });
    const body = await readBody(res);
    if (!res.ok || !body.json) throw new Error(describeError(res.status, body, "모델 목록 조회"));
    return (body.json as { models?: GeminiModelInfo[] }).models ?? [];
  }

  /** 지정 모델을 목록에서 찾지 못해 다른 모델로 바꿨을 때의 안내 */
  modelNotice = "";

  private async resolveModels(): Promise<{ main: string; light: string }> {
    if (!this.modelPromise) {
      this.modelPromise = (async () => {
        const cfg = MODELS.gemini;
        let usable: string[];
        try {
          usable = (await this.listModels())
            .filter((m) => (m.supportedGenerationMethods ?? []).includes("generateContent"))
            .map((m) => m.name.replace(/^models\//, ""));
        } catch {
          // 목록 조회가 막혀 있어도 파이프라인은 계속 돌아야 한다
          const main = cfg.pin || cfg.fallback;
          return { main, light: cfg.lightPin || main };
        }
        let main = cfg.pin ? resolvePinned(usable, cfg.pin) : null;
        if (cfg.pin && !main) {
          main = pickModel(usable) ?? cfg.fallback;
          this.modelNotice = `지정 모델 "${cfg.pin}" 이 이 키의 모델 목록에 없어 "${main}" 으로 대신합니다.`;
        }
        main ??= pickModel(usable) ?? cfg.fallback;
        const light = cfg.lightPin || pickTier(usable, "flash") || main;
        return { main, light };
      })();
    }
    return this.modelPromise;
  }

  /** 키가 실제로 유효한지, 어떤 모델을 쓸 수 있는지 실제 호출로 확인한다 */
  async verify(): Promise<{ ok: boolean; detail: string }> {
    try {
      const models = await this.listModels();
      const usable = models
        .filter((m) => (m.supportedGenerationMethods ?? []).includes("generateContent"))
        .map((m) => m.name.replace(/^models\//, ""));
      if (!usable.length) {
        return { ok: false, detail: "generateContent를 지원하는 모델이 없습니다. API 키의 권한을 확인해 주세요." };
      }
      const chosen = await this.resolveModel("extract");
      const notice = this.modelNotice ? ` — ${this.modelNotice}` : "";
      return { ok: true, detail: `사용 가능한 모델 ${usable.length}개 중 "${chosen}" 선택${notice}` };
    } catch (e) {
      return { ok: false, detail: (e as Error).message };
    }
  }

  async resolveModel(stage: Stage): Promise<string> {
    const { main, light } = await this.resolveModels();
    return stage === "guide" || stage === "ocr" ? light : main;
  }

  /* ───────────────── 호출 ───────────────── */

  async structured<T>(req: StructuredRequest): Promise<T> {
    const model = req.light ? await this.resolveModel("guide") : await this.resolveModel(req.stage);
    const schema = toGeminiSchema(req.schema);
    const system = [req.systemStable, req.systemVolatile].filter(Boolean).join("\n\n");

    const raw = await this.generate(req.stage, model, system, req.content, {
      responseMimeType: "application/json",
      responseSchema: schema,
      maxOutputTokens: req.maxTokens ?? 32_768,
      temperature: req.temperature ?? 0.1,
    });

    let parsed: unknown;
    try {
      parsed = JSON.parse(stripCodeFence(raw));
    } catch {
      throw new Error(
        `[${req.stage}] 모델이 JSON을 반환하지 않았습니다. 앞부분: ${raw.slice(0, 200)}`,
      );
    }
    return coerceToSchema(parsed, req.schema) as T;
  }

  async text(
    stage: Stage,
    systemStable: string,
    content: LlmContent[],
    maxTokens = 32_768,
  ): Promise<string> {
    const model = await this.resolveModel(stage);
    return this.generate(stage, model, systemStable, content, {
      maxOutputTokens: maxTokens,
      temperature: 0,
    });
  }

  private async generate(
    stage: Stage,
    model: string,
    system: string,
    content: LlmContent[],
    generationConfig: Record<string, unknown>,
  ): Promise<string> {
    const started = Date.now();
    const budget = THINKING[stageToThinkingKey(stage)];
    const withThinking =
      budget !== undefined && !this.noThinking.has(model)
        ? { ...generationConfig, thinkingConfig: { thinkingBudget: budget } }
        : generationConfig;

    model = this.replaced.get(model) ?? model;
    let json = await this.post(model, system, content, withThinking).catch((e) => ({ thrown: e }));

    // 고른 모델이 이 키로 호출되지 않으면(404) 기본 모델로 한 번 바꿔 다시 부른다
    const fallback = MODELS.gemini.fallback;
    if (isNotFound(json) && model !== fallback) {
      this.replaced.set(model, fallback);
      model = fallback;
      json = await this.post(model, system, content, withThinking).catch((e) => ({ thrown: e }));
    }
    if (json.thrown) throw new Error(`[${stage}] ${(json.thrown as Error).message}`);

    // thinkingConfig를 모르는 모델이면 한 번만 빼고 재시도
    if (json.error && /thinking/i.test(JSON.stringify(json.error))) {
      this.noThinking.add(model);
      json = await this.post(model, system, content, generationConfig);
    }
    if (json.error) {
      throw new Error(`[${stage}] Gemini 오류 (모델 ${model}): ${json.error.message ?? JSON.stringify(json.error)}`);
    }

    const candidate = json.candidates?.[0];
    const finish = candidate?.finishReason;
    if (finish === "SAFETY" || finish === "PROHIBITED_CONTENT" || finish === "BLOCKLIST") {
      throw new Error(
        `[${stage}] 안전 필터에 걸려 응답이 차단됐습니다 (${finish}). ` +
          "개인정보가 많이 담긴 파일이면 해당 부분을 가리고 다시 시도해 주세요.",
      );
    }
    if (finish === "MAX_TOKENS") {
      throw new Error(`[${stage}] 응답이 최대 길이를 넘었습니다. 파일을 나눠 올려 주세요.`);
    }

    const text = (candidate?.content?.parts ?? [])
      .map((p: any) => p.text ?? "")
      .join("")
      .trim();

    const usage = json.usageMetadata ?? {};
    this.track(stage, Date.now() - started, usage, model);

    if (!text) throw new Error(`[${stage}] 빈 응답을 받았습니다 (finishReason=${finish ?? "없음"}).`);
    return text;
  }

  private async post(
    model: string,
    system: string,
    content: LlmContent[],
    generationConfig: Record<string, unknown>,
  ): Promise<any> {
    const body = {
      systemInstruction: system ? { parts: [{ text: system }] } : undefined,
      contents: [{ role: "user", parts: content.map(toPart) }],
      generationConfig,
      safetySettings: [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
      ].map((category) => ({ category, threshold: "BLOCK_ONLY_HIGH" })),
    };

    return withRetry(async () => {
      const res = await fetch(`${BASE}/models/${model}:generateContent`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-goog-api-key": this.apiKey },
        body: JSON.stringify(body),
      });
      const got = await readBody(res);
      if (res.status === 429 || res.status >= 500) {
        throw Object.assign(new Error(describeError(res.status, got, "생성", model)), { retryable: true });
      }
      // 정상 응답이거나 JSON 오류 본문이면 그대로 넘긴다 (thinking 재시도·404 대체가 json.error를 본다)
      if (got.json && (res.ok || got.json.error)) return got.json;
      // HTML 오류 페이지 등 — 예전에는 여기서 res.json()이 터져 실제 상태 코드가 가려졌다
      throw Object.assign(new Error(describeError(res.status, got, "생성", model)), { status: res.status });
    });
  }

  readonly usageByTier = { pro: 0, light: 0 };

  private track(stage: Stage, ms: number, usage: any, model = "") {
    const inp = usage.promptTokenCount ?? 0;
    const out = (usage.candidatesTokenCount ?? 0) + (usage.thoughtsTokenCount ?? 0);
    const cached = usage.cachedContentTokenCount ?? 0;
    this.usage.inputTokens += inp;
    this.usage.outputTokens += out;
    this.usage.cacheReadTokens += cached;
    // flash 계열은 단가가 크게 낮다 — tier를 구분해야 절감 효과가 숫자로 보인다
    const rate = /flash/i.test(model) ? PRICING.geminiFlash : PRICING.gemini;
    this.usage.estimatedCostUsd +=
      (inp / 1e6) * rate.inputPerMTok + (out / 1e6) * rate.outputPerMTok;
    if (/flash/i.test(model)) this.usageByTier.light += inp;
    else this.usageByTier.pro += inp;
    this.usage.calls.push({ stage, ms });
  }
}

/* ───────────────── 헬퍼 ───────────────── */

function toPart(c: LlmContent) {
  // 이미지든 오디오든 Gemini는 같은 inline_data로 받는다
  return c.type === "text"
    ? { text: c.text }
    : { inline_data: { mime_type: c.mediaType, data: c.dataBase64 } };
}

function stageToThinkingKey(stage: Stage): keyof typeof THINKING {
  switch (stage) {
    case "classify": return "classifier";
    case "extract": return "extractor";
    case "supervise": return "supervisor";
    case "guide": return "guide";
    case "ocr": return "visionOcr";
  }
}

/**
 * 세대를 먼저 보고, 같은 세대 안에서 tier를 본다.
 *
 * 예전에는 'pro 패턴'을 먼저 훑어서 gemini-3.8-flash 가 있는데도
 * gemini-2.5-pro 를 골랐다. 세대 차가 tier 차보다 크므로 순서를 뒤집는다.
 */
export function pickModel(models: string[]): string | null {
  const scored: [number, number, number, number, string][] = [];
  for (const m of models) {
    const g = MODELS.gemini.pattern.exec(m);
    if (!g) continue;
    const gen = Number(g[1]);
    if (!Number.isFinite(gen)) continue;
    scored.push([-gen, g[2] === "pro" ? 0 : 1, g[3] ? 1 : 0, m.length, m]);
  }
  if (!scored.length) return null;
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
  return scored[0]![4];
}

/**
 * 지정 모델을 목록에서 찾는다. 정확히 같은 이름이 없으면 그 이름으로 시작하는
 * preview·exp 판 중 가장 짧은(=기본) 것을 쓴다. 없으면 null.
 */
export function resolvePinned(models: string[], pin: string): string | null {
  if (models.includes(pin)) return pin;
  const variants = models.filter((m) => m.startsWith(`${pin}-`) && /-(preview|exp)/.test(m.slice(pin.length)));
  variants.sort((a, b) => a.length - b.length || a.localeCompare(b));
  return variants[0] ?? null;
}

/** 특정 tier에서 가장 최신 세대 */
export function pickTier(models: string[], tier: "pro" | "flash"): string | null {
  const scored: [number, number, number, string][] = [];
  for (const m of models) {
    const g = MODELS.gemini.pattern.exec(m);
    if (!g || g[2] !== tier) continue;
    const gen = Number(g[1]);
    if (!Number.isFinite(gen)) continue;
    scored.push([-gen, g[3] ? 1 : 0, m.length, m]);
  }
  if (!scored.length) return null;
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return scored[0]![3];
}

function stripCodeFence(s: string): string {
  const m = /^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$/.exec(s);
  return m ? m[1]! : s;
}

interface Body {
  json: any;
  /** JSON이 아닐 때 본문 요약 (HTML이면 <title> 또는 태그를 걷어 낸 앞부분) */
  snippet: string;
}

/** 본문을 한 번만 읽는다. Google 프런트엔드는 경로가 틀리거나 요청이 너무 크면 HTML을 돌려준다. */
async function readBody(res: Response): Promise<Body> {
  const raw = await res.text().catch(() => "");
  try {
    return { json: JSON.parse(raw), snippet: "" };
  } catch {
    const title = /<title>([\s\S]*?)<\/title>/i.exec(raw)?.[1];
    const plain = (title ?? raw.replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>|<[^>]+>/gi, " "))
      .replace(/\s+/g, " ")
      .trim();
    return { json: null, snippet: plain.slice(0, 160) };
  }
}

function isNotFound(r: any): boolean {
  return r?.thrown?.status === 404 || r?.error?.code === 404 || r?.error?.status === "NOT_FOUND";
}

export function describeError(status: number, body: Body, what: string, model?: string): string {
  const detail = body.json?.error?.message ?? (body.snippet ? `서버가 JSON 대신 HTML 페이지를 돌려줌: "${body.snippet}"` : "");
  const on = model ? `, 모델 ${model}` : "";
  if (status === 400 && /API key not valid/i.test(detail)) {
    return "Google API 키가 올바르지 않습니다. https://aistudio.google.com/apikey 에서 키를 확인해 주세요.";
  }
  if (status === 403) {
    return `권한이 없습니다(403). Generative Language API가 켜져 있는지 확인해 주세요. ${detail}`;
  }
  if (status === 429) return `요청 한도를 초과했습니다(429). 잠시 후 다시 시도합니다. ${detail}`;
  if (status === 404) {
    return `${what} 실패 (HTTP 404${on}) — 이 키로 호출할 수 없는 모델이거나 주소가 잘못됐습니다. `
      + `GEMINI_MODEL=gemini-3.5-flash 처럼 다른 모델을 지정해 보세요. ${detail}`;
  }
  if (status === 413) return `${what} 실패 (HTTP 413${on}) — 요청이 너무 큽니다. 파일을 나눠 올려 주세요. ${detail}`;
  return `${what} 실패 (HTTP ${status}${on}) ${detail}`;
}

async function withRetry<T>(fn: () => Promise<T>, tries = 4): Promise<T> {
  let lastError: unknown;
  for (let i = 0; i < tries; i++) {
    try {
      return await fn();
    } catch (e) {
      lastError = e;
      if (!(e as any)?.retryable && i > 0) break;
      await new Promise((r) => setTimeout(r, 1000 * 2 ** i));
    }
  }
  throw lastError;
}
