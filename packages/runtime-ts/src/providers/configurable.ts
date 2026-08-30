import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import type { ToolRegistry } from "../tools.js";
import { SettingsStore } from "../settings.js";
import { AnthropicMessagesProvider } from "./anthropic.js";
import { OpenAiCompatibleProvider } from "./openai.js";
import { ProviderError, abortableDelay, retryDelayMs, retryableProviderError } from "./errors.js";

export class ConfigurableProvider implements ModelProvider {
  constructor(private readonly settings: SettingsStore) {}
  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const config = await this.settings.getProviderConfig();
    const completeOnce = async () => {
      if (config.provider === "anthropic" || config.api_format === "anthropic_messages") {
        const apiKey = config.api_key ?? process.env.ANTHROPIC_API_KEY;
        if (!apiKey) throw new Error("Anthropic API key is not configured");
        return new AnthropicMessagesProvider({ apiKey, baseUrl: config.base_url || process.env.ANTHROPIC_BASE_URL, model: config.model, maxTokens: config.max_output_tokens, timeoutMs: config.timeout_s * 1000, temperature: config.temperature, topP: config.top_p, reasoningEffort: config.reasoning_effort, cacheControl: config.cache_control }).complete(messages, tools, signal, onToken, invocation, onThinking);
      }
      const baseUrl = config.base_url || (process.env.OPENAI_BASE_URL ?? process.env.DEEPSEEK_BASE_URL);
      const envKey = process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
      const apiKey = config.keyless ? undefined : config.api_key ?? envKey;
      if (!config.keyless && !apiKey) throw new Error("OpenAI-compatible API key is not configured");
      const shared = { apiKey, baseUrl, model: config.model, maxOutputTokens: config.max_output_tokens, temperature: config.temperature, topP: config.top_p, reasoningEffort: config.reasoning_effort, timeoutMs: config.timeout_s * 1000, stream: true, cacheControl: config.cache_control };
      return new OpenAiCompatibleProvider({ ...shared, apiFormat: config.api_format }).complete(messages, tools, signal, onToken, invocation, onThinking);
    };
    let lastError: unknown;
    const maxAttempts = Math.min(10, Math.max(1, config.max_retries ?? 2));
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try { return await completeOnce(); } catch (error) {
        lastError = error;
        if (signal?.aborted || !retryableProviderError(error)) throw error;
        if (attempt >= maxAttempts - 1) {
          if (error instanceof ProviderError) throw new ProviderError(error.message, { ...error.details, retryExhausted: true });
          throw new ProviderError(error instanceof Error ? error.message : String(error), { retryable: retryableProviderError(error), billingEffect: "unknown", retryExhausted: true });
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
