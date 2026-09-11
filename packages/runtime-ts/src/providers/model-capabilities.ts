/**
 * 模型能力画像：把"系统对不同模型的输出性能"从散落的字符串特判升级为
 * 统一的能力声明。Provider 层据此决定采样参数抑制、推理参数形态与
 * prompt 缓存机制，新增模型家族时只需补一条 pattern。
 */

export type ModelFamily =
  | "anthropic" | "openai" | "deepseek" | "glm" | "qwen" | "moonshot"
  | "gemini" | "doubao" | "minimax" | "llama" | "unknown";

/** Provider 侧 prompt 缓存的可用机制。 */
export type PromptCacheMechanism =
  /** Anthropic Messages 格式：显式 cache_control 断点（含第三方兼容网关）。 */
  | "anthropic_cache_control"
  /** OpenAI 官方端点：prompt_cache_key 路由提示，提高同前缀请求的节点亲和。 */
  | "openai_prompt_cache_key"
  /** DeepSeek/Kimi/Qwen 等端点：服务端自动前缀缓存，harness 只需保证前缀字节稳定。 */
  | "server_auto_prefix";

export type ReasoningStyle =
  | "none"
  /** Claude extended thinking：thinking: { type, budget_tokens }。 */
  | "anthropic_thinking"
  /** OpenAI o 系列/gpt-5：reasoning_effort / reasoning: { effort }。 */
  | "openai_effort"
  /** DeepSeek R 系列：thinking: { type: "enabled" }（chat 格式）。 */
  | "deepseek_thinking";

export type ModelCapabilities = {
  family: ModelFamily;
  cache: PromptCacheMechanism;
  reasoning: ReasoningStyle;
  /** 推理/思考模型拒绝 temperature/top_p 等采样参数，必须整体抑制。 */
  suppressSampling: boolean;
};

const FAMILY_PATTERNS: Array<[ModelFamily, RegExp]> = [
  ["anthropic", /claude/i],
  ["openai", /^(?:o[1-9](?:-|$)|gpt-[3-9](?:[.-]|$)|chatgpt)/i],
  ["deepseek", /deepseek/i],
  ["glm", /glm/i],
  ["qwen", /qwen|qwq|qvq/i],
  ["moonshot", /kimi|moonshot/i],
  ["gemini", /gemini/i],
  ["doubao", /doubao/i],
  ["minimax", /minimax|abab/i],
  ["llama", /llama/i],
];

export function detectModelFamily(model: string): ModelFamily {
  for (const [family, pattern] of FAMILY_PATTERNS) if (pattern.test(model)) return family;
  return "unknown";
}

/** 与既有行为保持等价：o 系列 / gpt-5+ / 名字带 reasoning 的模型按推理模型处理。 */
function openaiReasoningModel(model: string): boolean {
  return /^o[1-9]|^gpt-5|reasoning/i.test(model);
}

/** 推理风格：决定 reasoning_effort 的落参形态（与 reasoning.ts 的模型特判对齐）。 */
function reasoningStyleFor(model: string): ReasoningStyle {
  const family = detectModelFamily(model);
  if (family === "anthropic") return "anthropic_thinking";
  if (family === "deepseek") return /^deepseek-reasoner/i.test(model) ? "deepseek_thinking" : "none";
  if (family === "openai" && openaiReasoningModel(model)) return "openai_effort";
  if (openaiReasoningModel(model)) return "openai_effort";
  return "none";
}

function suppressSamplingFor(model: string): boolean {
  const style = reasoningStyleFor(model);
  if (style !== "none") return true;
  // DeepSeek-R 的 chat 端点同样拒绝采样参数（与 openai.ts 的采样抑制口径一致）。
  return /^deepseek-reasoner/i.test(model);
}

/**
 * 识别端点的 prompt 缓存机制。Anthropic 格式一律显式断点（官方与兼容网关均支持
 * cache_control）；OpenAI 格式仅官方端点确认支持 prompt_cache_key，其余端点保守
 * 交给服务端自动前缀缓存，避免未知网关对陌生字段返回 400。
 */
export function promptCacheMechanism(apiFormat: "anthropic_messages" | "openai_chat_completions" | "openai_responses", baseUrl?: string): PromptCacheMechanism {
  if (apiFormat === "anthropic_messages") return "anthropic_cache_control";
  try {
    const hostname = baseUrl ? new URL(baseUrl).hostname : "api.openai.com";
    return hostname === "api.openai.com" ? "openai_prompt_cache_key" : "server_auto_prefix";
  } catch {
    return "server_auto_prefix";
  }
}

export function detectModelCapabilities(model: string, apiFormat: "anthropic_messages" | "openai_chat_completions" | "openai_responses", baseUrl?: string): ModelCapabilities {
  return {
    family: detectModelFamily(model),
    cache: promptCacheMechanism(apiFormat, baseUrl),
    reasoning: reasoningStyleFor(model),
    suppressSampling: suppressSamplingFor(model),
  };
}
