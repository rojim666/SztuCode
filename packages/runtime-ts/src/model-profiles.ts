import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { RuntimeSettings, SettingsStore } from "./settings.js";

type ProfileSettings = Omit<RuntimeSettings, "permission_mode">;
export type ModelProfile = ProfileSettings & { id: string; name: string; vendor: string; has_api_key: boolean; is_current: boolean; builtin: boolean };
type StoredProfile = ProfileSettings & { id: string; name: string; vendor: string; builtin: boolean; api_key?: string; keyless?: boolean };
type ProfileFile = { profiles: StoredProfile[]; active_model_id: string };

const BUILTIN_PROFILES: StoredProfile[] = [];

export class ModelProfileStore {
  private profiles: StoredProfile[] = []; private activeId = ""; private loaded = false;
  constructor(private readonly settings: SettingsStore, private readonly filePath = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "model-profiles.json")) {}

  async list(): Promise<ModelProfile[]> {
    await this.load(); const current = await this.settings.get();
    if (!this.activeId) this.activeId = this.all().find((profile) => profile.provider === current.provider && profile.model === current.model && profile.base_url === current.base_url)?.id ?? "";
    return this.all().map(({ api_key, keyless, ...profile }) => ({ ...profile, has_api_key: Boolean(keyless || api_key || providerKey(profile)), is_current: profile.id === this.activeId }));
  }

  async save(input: Partial<StoredProfile> & { name: string; vendor: string; provider: "anthropic" | "openai"; model: string; base_url: string; select?: boolean }): Promise<{ settings: RuntimeSettings; models: ModelProfile[] }> {
    await this.load(); const id = input.id || randomUUID(); if (BUILTIN_PROFILES.some((profile) => profile.id === id)) throw new Error("builtin profiles cannot be edited");
    let profile = this.profiles.find((item) => item.id === id);
    if (!profile) {
      profile = { id, name: input.name, vendor: input.vendor, provider: input.provider, model: input.model, base_url: input.base_url, builtin: false, api_format: input.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions", context_window: 128_000, max_output_tokens: 8192, temperature: null, top_p: null, reasoning_effort: "", timeout_s: 120, max_retries: 2, cache_control: true };
      this.profiles.push(profile);
    }
    const { select: _select, builtin: _builtin, api_key: apiKey, keyless, ...values } = input;
    Object.assign(profile, values, { id, builtin: false, keyless: Boolean(keyless) }); if (apiKey !== undefined) profile.api_key = apiKey;
    const settings = input.select === false ? await this.settings.get() : await this.activate(profile); await this.persist(); return { settings, models: await this.list() };
  }

  async select(id: string): Promise<RuntimeSettings> { await this.load(); const profile = this.all().find((item) => item.id === id); if (!profile) throw new Error(`Unknown model profile: ${id}`); const settings = await this.activate(profile); await this.persist(); return settings; }
  async delete(id: string): Promise<ModelProfile[]> { await this.load(); if (BUILTIN_PROFILES.some((profile) => profile.id === id)) throw new Error("builtin profiles cannot be deleted"); if (id === this.activeId) throw new Error("current model profile cannot be deleted"); const before = this.profiles.length; this.profiles = this.profiles.filter((item) => item.id !== id); if (before === this.profiles.length) throw new Error(`Unknown model profile: ${id}`); await this.persist(); return this.list(); }

  private all(): StoredProfile[] { const builtinIds = new Set(BUILTIN_PROFILES.map((profile) => profile.id)); return [...this.profiles.filter((profile) => !builtinIds.has(profile.id)), ...BUILTIN_PROFILES]; }
  private async activate(profile: StoredProfile): Promise<RuntimeSettings> {
    const settings = await this.settings.update({ provider: profile.provider, api_format: profile.api_format, model: profile.model, base_url: profile.base_url, context_window: profile.context_window, max_output_tokens: profile.max_output_tokens, temperature: profile.temperature, top_p: profile.top_p, reasoning_effort: profile.reasoning_effort, timeout_s: profile.timeout_s, max_retries: profile.max_retries, cache_control: profile.cache_control, api_key: profile.api_key ?? "", keyless: Boolean(profile.keyless) }); this.activeId = profile.id; return settings;
  }
  private async load(): Promise<void> {
    if (this.loaded) return; this.loaded = true;
    try { const value = JSON.parse(await readFile(this.filePath, "utf8")) as StoredProfile[] | Partial<ProfileFile>; if (Array.isArray(value)) this.profiles = value; else { this.profiles = Array.isArray(value.profiles) ? value.profiles : []; this.activeId = value.active_model_id ?? ""; } } catch { this.profiles = []; }
    // 过滤掉旧的内置模型（opencode zen、orcarouter等）
    this.profiles = this.profiles.filter(p => !p.builtin && !p.id.startsWith("builtin-"));
    if (!this.profiles.length) { const current = await this.settings.getProviderConfig(); this.profiles.push({ id: "default", name: current.model, vendor: current.provider === "anthropic" ? "Anthropic" : "OpenAI", provider: current.provider, api_format: current.api_format, model: current.model, base_url: current.base_url, builtin: false, api_key: current.api_key, keyless: current.keyless, context_window: current.context_window, max_output_tokens: current.max_output_tokens, temperature: current.temperature, top_p: current.top_p, reasoning_effort: current.reasoning_effort, timeout_s: current.timeout_s, max_retries: current.max_retries, cache_control: current.cache_control }); this.activeId = "default"; }
  }
  private async persist(): Promise<void> { await mkdir(path.dirname(this.filePath), { recursive: true }); await writeFile(this.filePath, `${JSON.stringify({ profiles: this.profiles, active_model_id: this.activeId }, null, 2)}\n`, "utf8"); }
}

function providerKey(profile: { provider: "anthropic" | "openai"; base_url?: string }): string | undefined {
  if (profile.provider === "anthropic") return process.env.ANTHROPIC_API_KEY;
  return process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
}
