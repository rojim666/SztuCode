import { OpenAiCompatibleProvider, type OpenAiProviderOptions, type ProviderCompat } from "./openai.js";

export const ORCAROUTER_BASE_URL = "https://api.orcarouter.ai/v1";
export const ORCAROUTER_VENDOR = "orcarouter";

/** 内置档案覆盖 OrcaRouter 上适合 Agent 编码的主流模型；context_window 取自 /v1/models 实测值。 */
export const ORCAROUTER_MODELS: Array<{ id: string; context_window: number }> = [
  { id: "orcarouter/auto", context_window: 128_000 },
  { id: "deepseek/deepseek-v4-flash", context_window: 1_048_576 },
  { id: "deepseek/deepseek-v4-pro", context_window: 1_048_576 },
  { id: "anthropic/claude-sonnet-4.6", context_window: 1_000_000 },
  { id: "anthropic/claude-opus-4.7", context_window: 1_000_000 },
  { id: "openai/gpt-5.2-codex", context_window: 400_000 },
  { id: "openai/gpt-5.6-terra", context_window: 1_050_000 },
  { id: "openai/gpt-5.6-luna", context_window: 1_050_000 },
  { id: "google/gemini-3.6-flash", context_window: 1_048_576 },
  { id: "kimi/kimi-k2.7-code", context_window: 262_144 },
  { id: "minimax/minimax-m3", context_window: 1_048_576 },
];

/** 这些模型族直接拒绝 temperature，传入会报 400；top_p 仅 Kimi K3 一并拒绝。 */
const TEMPERATURELESS = [/^gpt-5/i, /^o\d/i, /^claude-(opus-(4\.([5-9]|\d{2,})|[5-9])|fable)/i, /^deepseek-(reasoner|r1)/i, /^kimi-k3/i];
const SAMPLELESS = [/^kimi-k3/i];

export type OrcaRouterProviderOptions = Omit<OpenAiProviderOptions, "compat" | "baseUrl"> & { baseUrl?: string; fallbacks?: string[]; appReferer?: string; appTitle?: string };

/** OrcaRouter 的模型 ID 带 provider 前缀（openai/gpt-5.4），能力判定要基于去掉前缀的部分。 */
export function bareModelId(model: string): string { const slash = model.indexOf("/"); return slash === -1 ? model : model.slice(slash + 1); }
export function rejectsTemperature(model: string): boolean { const id = bareModelId(model); return TEMPERATURELESS.some((pattern) => pattern.test(id)); }
export function rejectsTopP(model: string): boolean { const id = bareModelId(model); return SAMPLELESS.some((pattern) => pattern.test(id)); }
export function isOrcaRouterUrl(baseUrl?: string): boolean { return typeof baseUrl === "string" && /orcarouter\.ai/i.test(baseUrl); }

export function orcaRouterCompat(model: string, options: { fallbacks?: string[]; appReferer?: string; appTitle?: string } = {}): ProviderCompat {
  return {
    headers: { "HTTP-Referer": options.appReferer ?? "https://github.com/rojim666/SztuCode", "X-Title": options.appTitle ?? "SztuCode" },
    ...(options.fallbacks?.length ? { extraBody: { models: [model, ...options.fallbacks], route: "fallback" } } : {}),
    dropTemperature: rejectsTemperature(model),
    dropTopP: rejectsTopP(model),
    // cache_control 是 Anthropic 专有字段，经网关转发到 OpenAI/Google 上游会被拒绝。
    disableCacheControl: !/^anthropic\//i.test(model),
  };
}

/** OrcaRouter 走 OpenAI chat-completions 协议，差异全部收敛在 compat 里。 */
export class OrcaRouterProvider extends OpenAiCompatibleProvider {
  constructor(options: OrcaRouterProviderOptions) {
    const { fallbacks, appReferer, appTitle, ...rest } = options;
    super({ ...rest, baseUrl: options.baseUrl || ORCAROUTER_BASE_URL, compat: orcaRouterCompat(options.model, { fallbacks, appReferer, appTitle }) });
  }
}
