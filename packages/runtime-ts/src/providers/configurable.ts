import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import type { ToolRegistry } from "../tools.js";
import { SettingsStore } from "../settings.js";
import { AnthropicMessagesProvider } from "./anthropic.js";
import { OpenAiCompatibleProvider } from "./openai.js";
import { OrcaRouterProvider, isOrcaRouterUrl } from "./orcarouter.js";

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
      const envKey = isOrcaRouterUrl(baseUrl) ? process.env.ORCAROUTER_API_KEY ?? process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY : process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
      const apiKey = config.keyless ? undefined : config.api_key ?? envKey;
      if (!config.keyless && !apiKey) throw new Error("OpenAI-compatible API key is not configured");
      const shared = { apiKey, baseUrl, model: config.model, maxOutputTokens: config.max_output_tokens, temperature: config.temperature, topP: config.top_p, reasoningEffort: config.reasoning_effort, timeoutMs: config.timeout_s * 1000, stream: true, cacheControl: config.cache_control };
      // OrcaRouter 的 Messages 端点只覆盖 Claude，chat-completions 端点覆盖全部上游，故统一降级到后者。
      if (isOrcaRouterUrl(baseUrl)) return new OrcaRouterProvider({ ...shared, apiFormat: config.api_format }).complete(messages, tools, signal, onToken, invocation, onThinking);
      return new OpenAiCompatibleProvider({ ...shared, apiFormat: config.api_format }).complete(messages, tools, signal, onToken, invocation, onThinking);
    };
    let lastError: unknown;
    for (let attempt = 0; attempt <= Math.max(0, Math.min(10, config.max_retries)); attempt += 1) {
      try { return await completeOnce(); } catch (error) { lastError = error; if (signal?.aborted || attempt >= config.max_retries || !isRetryable(error)) throw error; await new Promise((resolve) => setTimeout(resolve, Math.min(2_000, 200 * 2 ** attempt))); }
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }
}

/** 无配置文件时的兜底入口：OrcaRouter 密钥优先，其次 OpenAI / DeepSeek，最后 Anthropic。 */
export function providerFromEnvironment(): ModelProvider {
  const model = process.env.SZTU_MODEL;
  if (process.env.ORCAROUTER_API_KEY) return new OrcaRouterProvider({ apiKey: process.env.ORCAROUTER_API_KEY, baseUrl: process.env.ORCAROUTER_BASE_URL, model: model ?? "orcarouter/auto" });
  if ((process.env.SZTU_PROVIDER ?? "").toLowerCase() === "anthropic" || process.env.ANTHROPIC_API_KEY && !process.env.OPENAI_API_KEY && !process.env.DEEPSEEK_API_KEY) {
    return new AnthropicMessagesProvider({ apiKey: process.env.ANTHROPIC_API_KEY ?? "", baseUrl: process.env.ANTHROPIC_BASE_URL, model: model ?? "claude-3-5-sonnet-latest" });
  }
  const apiKey = process.env.OPENAI_API_KEY ?? process.env.DEEPSEEK_API_KEY;
  if (!apiKey) return { async complete() { throw new Error("ORCAROUTER_API_KEY, OPENAI_API_KEY or DEEPSEEK_API_KEY is required"); } };
  return new OpenAiCompatibleProvider({ apiKey, baseUrl: process.env.OPENAI_BASE_URL ?? process.env.DEEPSEEK_BASE_URL, model: model ?? "gpt-4o-mini" });
}

function isRetryable(error: unknown): boolean { const message = error instanceof Error ? error.message : String(error); return /\b(429|500|502|503|504)\b|timeout|aborted|fetch failed|network|socket|ECONN|ETIMEDOUT/i.test(message); }
