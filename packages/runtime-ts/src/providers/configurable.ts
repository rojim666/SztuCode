import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import type { ToolRegistry } from "../tools.js";
import { SettingsStore } from "../settings.js";
import { AnthropicMessagesProvider } from "./anthropic.js";
import { OpenAiCompatibleProvider } from "./openai.js";
import { ProviderError, abortableDelay, retryDelayMs, retryableProviderError } from "./errors.js";

type ProviderConfig = Awaited<ReturnType<SettingsStore["getProviderConfig"]>>;

/** 配置签名：任何影响 provider 行为的字段变化都触发实例重建，保留模型热切换语义。 */
function providerSignature(config: ProviderConfig): string {
  return JSON.stringify([config.provider, config.api_format, config.model, config.base_url, config.api_key, config.keyless, config.max_output_tokens, config.temperature, config.top_p, config.reasoning_effort, config.timeout_s, config.cache_control, config.aux_provider, config.aux_model, config.aux_base_url, config.aux_api_format, config.aux_api_key, config.aux_max_output_tokens, config.aux_timeout_s]);
}

function buildPrimary(config: ProviderConfig): ModelProvider {
  if (config.provider === "anthropic" || config.api_format === "anthropic_messages") {
    const apiKey = config.api_key ?? process.env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error("Anthropic API key is not configured");
    return new AnthropicMessagesProvider({ apiKey, baseUrl: config.base_url || process.env.ANTHROPIC_BASE_URL, model: config.model, maxTokens: config.max_output_tokens, timeoutMs: config.timeout_s * 1000, temperature: config.temperature, topP: config.top_p, reasoningEffort: config.reasoning_effort, cacheControl: config.cache_control });
  }
  const baseUrl = config.base_url || (process.env.OPENAI_BASE_URL ?? process.env.DEEPSEEK_BASE_URL);
  const envKey = process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
  const apiKey = config.keyless ? undefined : config.api_key ?? envKey;
  if (!config.keyless && !apiKey) throw new Error("OpenAI-compatible API key is not configured");
  return new OpenAiCompatibleProvider({ apiKey, baseUrl, model: config.model, maxOutputTokens: config.max_output_tokens, temperature: config.temperature, topP: config.top_p, reasoningEffort: config.reasoning_effort, timeoutMs: config.timeout_s * 1000, stream: true, cacheControl: config.cache_control, apiFormat: config.api_format });
}

/** 辅助模型：压缩等后台调用卸载到独立的轻量端点；未配置或凭据缺失时返回 null 回退主模型。 */
function buildAuxiliary(config: ProviderConfig): ModelProvider | null {
  const model = config.aux_model?.trim();
  if (!model) return null;
  const provider = config.aux_provider ?? "openai";
  const apiFormat = config.aux_api_format ?? (provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions");
  const timeoutMs = (config.aux_timeout_s ?? 60) * 1000;
  if (provider === "anthropic" || apiFormat === "anthropic_messages") {
    const apiKey = config.aux_api_key ?? process.env.ANTHROPIC_API_KEY;
    if (!apiKey) return null;
    return new AnthropicMessagesProvider({ apiKey, baseUrl: config.aux_base_url || process.env.ANTHROPIC_BASE_URL, model, maxTokens: config.aux_max_output_tokens, timeoutMs, cacheControl: config.cache_control });
  }
  const apiKey = config.aux_api_key ?? process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
  if (!apiKey) return null;
  return new OpenAiCompatibleProvider({ apiKey, baseUrl: config.aux_base_url || process.env.OPENAI_BASE_URL || process.env.DEEPSEEK_BASE_URL, model, apiFormat, maxOutputTokens: config.aux_max_output_tokens, timeoutMs, stream: true, cacheControl: config.cache_control });
}

export class ConfigurableProvider implements ModelProvider {
  /**
   * 实例缓存：同一配置复用 provider 实例。除消除每请求的对象构造外，更关键的是
   * 让 Anthropic provider 的滚动缓存断点状态跨请求存活（前缀缓存的读取锚点）。
   * 配置变更时按签名失效重建，模型热切换不受影响。
   */
  private cached: { signature: string; primary: ModelProvider; aux: ModelProvider | null } | null = null;

  constructor(private readonly settings: SettingsStore) {}

  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const config = await this.settings.getProviderConfig();
    const signature = providerSignature(config);
    if (!this.cached || this.cached.signature !== signature) {
      this.cached = { signature, primary: buildPrimary(config), aux: buildAuxiliary(config) };
    }
    const { primary, aux } = this.cached;
    const run = (provider: ModelProvider) => provider.complete(messages, tools, signal, onToken, invocation, onThinking);
    let lastError: unknown;
    const maxAttempts = Math.min(10, Math.max(1, config.max_retries ?? 2));
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      // 压缩是高频后台调用：首轮路由到辅助模型（若配置），失败即回退主模型。
      const provider = attempt === 0 && aux && invocation?.purpose === "compaction" ? aux : primary;
      try { return await run(provider); } catch (error) {
        lastError = error;
        if (signal?.aborted || !retryableProviderError(error)) throw error;
        if (attempt >= maxAttempts - 1) {
          // 主模型重试耗尽且辅助模型可用时做最后一次降级，多争取一次成功的机会。
          if (aux && provider !== aux) {
            try { return await run(aux); } catch (fallbackError) { lastError = fallbackError; }
          }
          if (lastError instanceof ProviderError) throw new ProviderError(lastError.message, { ...lastError.details, retryExhausted: true });
          throw new ProviderError(lastError instanceof Error ? lastError.message : String(lastError), { retryable: retryableProviderError(lastError), billingEffect: "unknown", retryExhausted: true });
        }
        await abortableDelay(retryDelayMs(error, attempt), signal);
      }
    }
    if (lastError instanceof ProviderError) throw lastError;
    throw new ProviderError(lastError instanceof Error ? lastError.message : String(lastError), { retryable: retryableProviderError(lastError), billingEffect: "unknown", retryExhausted: true });
  }
}

/** 无配置文件时的兜底入口：优先 Anthropic，其次 OpenAI / DeepSeek。 */
export function providerFromEnvironment(): ModelProvider {
  const model = process.env.SZTU_MODEL;
  if ((process.env.SZTU_PROVIDER ?? "").toLowerCase() === "anthropic" || (process.env.ANTHROPIC_API_KEY && !process.env.OPENAI_API_KEY && !process.env.DEEPSEEK_API_KEY)) {
    return new AnthropicMessagesProvider({ apiKey: process.env.ANTHROPIC_API_KEY ?? "", baseUrl: process.env.ANTHROPIC_BASE_URL, model: model ?? "claude-3-5-sonnet-latest" });
  }
  const apiKey = process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
  if (!apiKey) return { async complete() { throw new Error("OPENAI_API_KEY or DEEPSEEK_API_KEY is required"); } };
  return new OpenAiCompatibleProvider({ apiKey, baseUrl: process.env.OPENAI_BASE_URL ?? process.env.DEEPSEEK_BASE_URL, model: model ?? "gpt-4o-mini" });
}
