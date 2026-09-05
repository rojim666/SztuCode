import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { PermissionMode } from "@sztucode/protocol";
import { validateReasoningEffort } from "./providers/reasoning.js";

export type RuntimeSettings = { provider: "anthropic" | "openai"; api_format: "openai_chat_completions" | "anthropic_messages" | "openai_responses"; model: string; permission_mode: PermissionMode; base_url: string; context_window: number; max_output_tokens: number; temperature: number | null; top_p: number | null; reasoning_effort: string; timeout_s: number; max_retries: number; cache_control: boolean };
type StoredSettings = RuntimeSettings & { api_key?: string; keyless?: boolean };
const provider = (process.env.SZTU_LLM_PROVIDER ?? process.env.SZTU_PROVIDER ?? "openai").toLowerCase() === "anthropic" ? "anthropic" : "openai";
const defaults: StoredSettings = { provider, api_format: provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions", model: process.env.SZTU_LLM_DEFAULT_MODEL ?? process.env.SZTU_MODEL ?? "gpt-4o-mini", permission_mode: (process.env.SZTU_PERMISSION_MODE as PermissionMode | undefined) ?? "normal", base_url: provider === "anthropic" ? process.env.ANTHROPIC_BASE_URL ?? "" : process.env.OPENAI_BASE_URL ?? process.env.DEEPSEEK_BASE_URL ?? "", context_window: Number(process.env.SZTU_LLM_CONTEXT_WINDOW ?? 128_000), max_output_tokens: 8192, temperature: null, top_p: null, reasoning_effort: "", timeout_s: 120, max_retries: 2, cache_control: true, keyless: /^(1|true|yes)$/i.test(process.env.SZTU_LLM_KEYLESS ?? "") };

export class SettingsStore {
  private settings: StoredSettings = { ...defaults };
  private loaded = false;
  constructor(private readonly filePath = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "runtime-settings.json")) {}
  async get(): Promise<RuntimeSettings> { await this.load(); const { api_key: _secret, keyless: _keyless, ...publicSettings } = this.settings; return publicSettings; }
  async getProviderConfig(): Promise<StoredSettings> { await this.load(); return { ...this.settings }; }
  async update(update: Partial<StoredSettings>): Promise<RuntimeSettings> { if (update.reasoning_effort !== undefined) validateReasoningEffort(update.reasoning_effort); await this.load(); this.settings = { ...this.settings, ...update }; await this.save(); return this.get(); }
  private async load(): Promise<void> { if (this.loaded) return; this.loaded = true; try { this.settings = { ...defaults, ...(JSON.parse(await readFile(this.filePath, "utf8")) as Partial<RuntimeSettings>) }; } catch { /* defaults */ } }
  private async save(): Promise<void> { await mkdir(path.dirname(this.filePath), { recursive: true }); await writeFile(this.filePath, `${JSON.stringify(this.settings, null, 2)}\n`, "utf8"); }
}
