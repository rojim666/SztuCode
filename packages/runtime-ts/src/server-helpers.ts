import { anthropicReasoningParams, openaiReasoningParams, validateReasoningEffort } from "./providers/reasoning.js";
import path from "node:path";
import net from "node:net";
import type { JsonRpcRequest, JsonRpcResponse } from "@sztucode/protocol";
import { SkillLoader } from "./skills.js";
import { SettingsStore } from "./settings.js";
export class RpcDispatchError extends Error { constructor(readonly code: number, message: string, readonly data?: unknown) { super(message); } }
const SESSION_BUSY = -32012;
const INVALID_PARAMS = -32602;
const INTERNAL_ERROR = -32603;
export const mimeType = (filePath: string): string | null => ({ ".avif": "image/avif", ".bmp": "image/bmp", ".gif": "image/gif", ".ico": "image/x-icon", ".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp" } as Record<string, string>)[path.extname(filePath).toLowerCase()] ?? null;
export function publicSkill(skill: Awaited<ReturnType<SkillLoader["list"]>>[number]): Omit<typeof skill, "system_prompt_template" | "allowed_tools"> { const { system_prompt_template: _body, allowed_tools: _tools, ...summary } = skill; return summary; }
export const ok = <T>(id: string, result: T): JsonRpcResponse<T> => ({ jsonrpc: "2.0", id, result });
export const error = (id: string | null, code: number, message: string, data?: unknown): JsonRpcResponse => ({ jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } });
export const classifyError = (cause: unknown): { code: number; message: string; data?: unknown } => {
  if (cause instanceof RpcDispatchError) return cause;
  const message = cause instanceof Error ? cause.message : String(cause);
  if (/session busy|steer unavailable/i.test(message)) return { code: SESSION_BUSY, message };
  if (/not found|unknown (session|workspace|plugin|skill|model)/i.test(message) || (cause as NodeJS.ErrnoException | null)?.code === "ENOENT") return { code: -32004, message };
  if (/required|invalid|escapes|must be|confirm=|cannot be|cannot delete|unknown model profile|archived session/i.test(message)) return { code: INVALID_PARAMS, message };
  return { code: INTERNAL_ERROR, message };
};
export const toSessionSummary = (session: import("./session-store.js").Session) => { const stats = Object.values(session.run_stats ?? {}); return { session_id: session.id, title: session.title, mode: session.mode, status: session.status, updated_at: session.updated_at, run_count: session.run_ids.length, archived: session.archived, pinned: session.pinned, workspace_id: session.workspace_id, latest_run_id: session.run_ids.at(-1) ?? null, total_input_tokens: stats.reduce((sum, item) => sum + item.input_tokens, 0), total_output_tokens: stats.reduce((sum, item) => sum + item.output_tokens, 0), total_elapsed_s: stats.reduce((sum, item) => sum + item.elapsed_s, 0) }; };
export const toProtocolSessionSnapshot = (session: import("./session-store.js").Session, attached = false) => ({ session_id: session.id, mode: session.mode, status: session.status, title: session.title, created_at: session.created_at, updated_at: session.updated_at, run_count: session.run_ids.length, archived: session.archived, pinned: session.pinned, workspace_id: session.workspace_id, latest_run_id: session.run_ids.at(-1) ?? null, attached, locked: attached });

export const topicMatches = (type: string, pattern: string): boolean => pattern === "*" || pattern === type || pattern.endsWith("*") && type.startsWith(pattern.slice(0, -1));
export const matchesSubscription = (event: import("@sztucode/protocol").RuntimeEvent, subscription: { topics: string[]; scope: string }): boolean => {
  if (!subscription.topics.some((topic) => topicMatches(event.type, topic))) return false;
  if (subscription.scope === "global") return true;
  return "run_id" in event && event.run_id === subscription.scope.slice(4);
};

export const dataRoot = (): string => process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu");
export const clientId = (socket: net.Socket): string => `${socket.remoteAddress ?? "unknown"}:${socket.remotePort ?? 0}`;
export const requestRunId = (request: JsonRpcRequest): string | null => typeof request.params?.run_id === "string" ? request.params.run_id : null;
export const responseRunId = (response: JsonRpcResponse): string | null => "result" in response && response.result && typeof response.result === "object" && typeof (response.result as { run_id?: unknown }).run_id === "string" ? (response.result as { run_id: string }).run_id : null;

type SettingsUpdateKey = keyof import("./settings.js").RuntimeSettings | "api_key";
type StoredSettingsUpdate = Partial<import("./settings.js").RuntimeSettings> & { api_key?: string; keyless?: boolean };
const SETTINGS_UPDATE_KEYS: SettingsUpdateKey[] = ["provider", "api_format", "model", "base_url", "api_key", "max_output_tokens", "temperature", "top_p", "reasoning_effort", "timeout_s", "max_retries", "context_window", "cache_control", "permission_mode"];

export function normalizeSettingsUpdate(input: Record<string, unknown>, current: Awaited<ReturnType<SettingsStore["getProviderConfig"]>>): { update: StoredSettingsUpdate; updated: SettingsUpdateKey[] } {
  const update: StoredSettingsUpdate = {}; const updated: SettingsUpdateKey[] = []; const next = { ...current };
  for (const key of SETTINGS_UPDATE_KEYS) {
    const value = input[key];
    if (value === undefined || value === null) continue;
    validateSetting(key, value);
  }
  if (typeof input.provider === "string" && input.provider !== next.provider) {
    next.provider = input.provider as typeof next.provider; next.api_format = next.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions";
    update.provider = next.provider; update.api_format = next.api_format; update.keyless = false; updated.push("provider");
  }
  if (typeof input.api_format === "string" && input.api_format !== next.api_format) {
    next.api_format = input.api_format as typeof next.api_format; next.provider = next.api_format === "anthropic_messages" ? "anthropic" : "openai";
    update.api_format = next.api_format; update.provider = next.provider; updated.push("api_format");
  }
  const remaining: SettingsUpdateKey[] = ["model", "base_url", "api_key", "max_output_tokens", "temperature", "top_p", "reasoning_effort", "timeout_s", "max_retries", "context_window", "cache_control", "permission_mode"];
  for (const key of remaining) {
    const value = input[key];
    if (value === undefined || value === null || value === next[key]) continue;
    (next as Record<string, unknown>)[key] = value; (update as Record<string, unknown>)[key] = value; updated.push(key);
  }
  if (updated.some((key) => key === "model" || key === "base_url")) update.keyless = false;
  return { update, updated };
}

export function validateSetting(key: SettingsUpdateKey, value: unknown): void {
  const oneOf = (values: readonly unknown[]) => { if (!values.includes(value)) throw new Error(`${key} must be one of: ${values.join(", ")}`); };
  const text = (min: number, max: number) => { if (typeof value !== "string" || value.length < min || value.length > max) throw new Error(`${key} must be a string with length ${min}..${max}`); };
  const number = (min: number, max: number, integer = false, exclusiveMin = false) => {
    const validRange = typeof value === "number" && (exclusiveMin ? value > min : value >= min) && value <= max;
    if (!validRange || !Number.isFinite(value) || integer && !Number.isInteger(value)) throw new Error(`${key} must be ${integer ? "an integer" : "a number"} in range ${exclusiveMin ? "(" : "["}${min}, ${max}]`);
  };
  if (key === "provider") oneOf(["anthropic", "openai"]);
  else if (key === "api_format") oneOf(["openai_chat_completions", "anthropic_messages", "openai_responses"]);
  else if (key === "permission_mode") oneOf(["normal", "accept_edits", "plan", "auto"]);
  else if (key === "reasoning_effort") validateReasoningEffort(value);
  else if (key === "model") text(1, 200);
  else if (key === "base_url") text(0, 2_000);
  else if (key === "api_key") text(1, 4_000);
  else if (key === "max_output_tokens") number(1, 128_000, true);
  else if (key === "temperature" || key === "top_p") number(0, 1);
  else if (key === "timeout_s") number(0, 600, false, true);
  else if (key === "max_retries") number(0, 10, true);
  else if (key === "context_window") number(0, 10_000_000, true);
  else if (key === "cache_control" && typeof value !== "boolean") throw new Error("cache_control must be a boolean");
}

export async function probeModel(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  const started = Date.now(); const apiFormat = String(input.api_format ?? (input.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions")); const model = String(input.model ?? "").trim();
  if (!model) return { success: false, api_format: apiFormat, model, elapsed_ms: Date.now() - started, input_tokens: 0, output_tokens: 0, error: "model is required" };
  const base = String(input.base_url ?? "").replace(/\/$/, "") || (apiFormat === "anthropic_messages" ? "https://api.anthropic.com/v1" : "https://api.openai.com/v1");
  const headers: Record<string, string> = { "content-type": "application/json" }; const apiKey = typeof input.api_key === "string" ? input.api_key : "";
  if (input.keyless !== true && apiKey) { if (apiFormat === "anthropic_messages") { headers["x-api-key"] = apiKey; headers["anthropic-version"] = "2023-06-01"; } else headers.authorization = `Bearer ${apiKey}`; }
  const url = `${base}/${apiFormat === "anthropic_messages" ? "messages" : apiFormat === "openai_responses" ? "responses" : "chat/completions"}`;
  const effort = input.reasoning_effort ?? "";
  validateReasoningEffort(effort);
  const maxTokens = effort ? Number(input.max_output_tokens ?? 8192) : 64;
  validateSetting("max_output_tokens", maxTokens);
  const body = apiFormat === "anthropic_messages" ? { model, ...anthropicReasoningParams(effort, maxTokens), messages: [{ role: "user", content: "Reply OK." }] } : apiFormat === "openai_responses" ? { model, input: "Reply OK.", max_output_tokens: maxTokens, ...openaiReasoningParams(effort, true) } : { model, messages: [{ role: "user", content: "Reply OK." }], max_completion_tokens: maxTokens, ...openaiReasoningParams(effort, false) };
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), Math.min(300, Math.max(1, Number(input.timeout_s ?? 30))) * 1000);
  try {
    const response = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    if (!response.ok) throw new Error(`Model request failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
    const payload = await response.json() as { usage?: Record<string, unknown> }; const usage = payload.usage ?? {};
    return { success: true, api_format: apiFormat, model, elapsed_ms: Date.now() - started, input_tokens: Number(usage.input_tokens ?? usage.prompt_tokens ?? 0), output_tokens: Number(usage.output_tokens ?? usage.completion_tokens ?? 0), error: null };
  } catch (cause) {
    return { success: false, api_format: apiFormat, model, elapsed_ms: Date.now() - started, input_tokens: 0, output_tokens: 0, error: cause instanceof Error ? cause.message : String(cause) };
  } finally { clearTimeout(timeout); }
}

export async function benchmarkModel(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  const samples = Math.min(10, Math.max(1, Number(input.samples ?? 3) || 3));
  const results = await Promise.all(Array.from({ length: samples }, () => probeModel(input)));
  const successful = results.filter((item) => item.success);
  const elapsed = successful.map((item) => Number(item.elapsed_ms || 0)).sort((a, b) => a - b);
  const percentile = (p: number) => elapsed.length ? elapsed[Math.min(elapsed.length - 1, Math.ceil(elapsed.length * p) - 1)] : 0;
  return { api_format: results[0]?.api_format ?? input.api_format ?? "", model: results[0]?.model ?? input.model ?? "", samples, successful: successful.length, failed: results.length - successful.length, min_ms: elapsed[0] ?? 0, median_ms: percentile(0.5), p95_ms: percentile(0.95), max_ms: elapsed.at(-1) ?? 0, average_ttft_ms: elapsed.length ? elapsed.reduce((sum, value) => sum + value, 0) / elapsed.length : 0, errors: results.filter((item) => !item.success).map((item) => item.error).filter(Boolean) };
}
