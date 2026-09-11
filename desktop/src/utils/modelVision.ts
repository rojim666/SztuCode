/**
 * 模型视觉能力检测
 *
 * 根据模型名称自动判断是否支持视觉/多模态输入（图片等）。
 * 识别列表覆盖主流多模态模型，未匹配的模型默认视为支持视觉（向后兼容，
 * 避免误判导致已有视觉能力的模型降级为 OCR 文本）。
 */

// 明确支持视觉/多模态的模型名称模式（不区分大小写）
const VISION_MODEL_PATTERNS: RegExp[] = [
  // OpenAI
  /gpt-4o/i,                    // GPT-4o, GPT-4o mini, gpt-4o-2024-xx
  /gpt-4-vision/i,              // gpt-4-vision-preview
  /o1-vision/i,                 // hypothetical future
  // Anthropic
  /claude-3[-.]?/i,             // claude-3-opus, claude-3-sonnet, claude-3-haiku, claude-3.5-sonnet
  /claude-4/i,                  // claude-4 opus/sonnet
  // Google
  /gemini.*(vision|pro|flash|1\.5|2\.0|2\.5)/i,  // gemini-pro-vision, gemini-1.5-pro/flash, gemini-2.0/2.5
  /gemini\s*(pro|flash|ultra)/i, // gemini pro / flash / ultra (multimodal)
  // Qwen / Alibaba
  /qwen-vl/i,                   // qwen-vl, qwen-vl-plus, qwen-vl-max
  /qvq/i,                       // QVQ (visual reasoning)
  /qwen2?\d*-vl/i,              // qwen2-vl, qwen2.5-vl
  // Zhipu / GLM
  /glm-4v/i,                    // glm-4v, glm-4v-plus
  /cogvlm/i,                    // cogvlm, cogvlm2
  /glm-\d*v/i,                  // glm-4v, glm-4.5v etc
  // Mistral
  /pixtral/i,                   // pixtral, pixtral-large
  /mistral.*(vision|multimodal)/i,
  // Llama vision
  /llama.*vision/i,             // llama-3.2-vision, llama-4-vision
  /llama-?3\.2-.*(11b|90b)/i,   // llama-3.2-11b-vision, llama-3.2-90b-vision
  // Moondream
  /moondream/i,
  // Yi-VL
  /yi-vl/i,
  // MiniCPM-V
  /minicpm-v/i,
  // InternVL
  /internvl/i,
  // Phi-3 vision
  /phi-3-vision/i,
  // Florence
  /florence/i,
  // LLaVA
  /llava/i,
  // OpenRouter / generic
  /vision/i,
  /multimodal/i,
  /v\d*-?l/i,                   // v-l, vl (catch-all for VL suffixed models)
];

// 明确不支持视觉的纯文本模型（命中后直接返回 false，优先级高于上面的通用模式）
const NON_VISION_MODEL_PATTERNS: RegExp[] = [
  // DeepSeek (no vision support as of 2026)
  /deepseek-(chat|reasoner|r1|v3|coder|llm)/i,
  // GPT-4 non-vision
  /^gpt-4[^o0-9]/i,             // gpt-4-turbo (no vision), gpt-4-0314 etc
  /^gpt-3\.5/i,                 // all gpt-3.5 models
  /gpt-4-0314|gpt-4-0613/i,     // old gpt-4 base
  /^o1(-mini|-preview)?$/i,      // o1, o1-mini (text-only reasoning)
  /^o3(-mini)?$/i,              // o3, o3-mini
  // Claude < 3
  /claude-?[12]/i,              // claude-1, claude-2, claude-2.0, claude-2.1
  /claude-instant/i,
  // Moonshot / Kimi
  /moonshot[-_]?v?\d*$/i,       // moonshot-v1-8k/32k/128k
  /kimi/i,                      // Kimi (currently text-only, but may add vision)
  // LLaMA text-only (non-vision)
  /^llama-?3[-.]?\d*-?\d+b[^-]*$/i,  // llama-3-70b, llama-3.1-70b (non-vision variants)
  /^llama-?3[-.]?1/i,           // llama-3.1 (text-only)
  /^llama-?3\.3/i,              // llama-3.3 (text-only)
  // Yi text-only
  /^yi-?(?!vl)/i,               // yi-34b, yi-6b etc (but not yi-vl)
  // Mistral text-only
  /^(mistral-?(small|medium|large|nemo)|open-mistral|mistral-?7b)/i,
  // Generic text-only markers
  /text-?(only|bison|davinci|curie|babbage|ada)/i,
  /instruct(?!.*vision)/i,      // instruct models that aren't vision
  /^gpt-oss/i,                  // hypothetical
  // Cerebras / Groq text models
  /deepseek-r1-distill/i,       // distilled r1 (text only)
];

/**
 * 检测模型是否支持视觉/多模态输入。
 *
 * 匹配策略：
 * 1. 先检查明确的非视觉模型模式（黑名单）→ 返回 false
 * 2. 再检查明确的视觉模型模式（白名单）→ 返回 true
 * 3. 未匹配的模型默认返回 true（保守假设：宁可不 OCR 直接发图，
 *    API 报错比丢失信息好；用户可以在模型设置里手动关闭视觉支持）
 */
export function detectVisionSupport(model: string, explicitValue?: boolean | null): boolean {
  if (explicitValue !== undefined && explicitValue !== null) {
    return explicitValue;
  }
  if (!model) return true;
  const name = model.toLowerCase();
  if (NON_VISION_MODEL_PATTERNS.some((p) => p.test(name))) {
    return false;
  }
  if (VISION_MODEL_PATTERNS.some((p) => p.test(name))) {
    return true;
  }
  return true;
}

export type ImageProcessingMode = "direct" | "ocr";

/** Keep the UI wording tied to the same explicit capability used to build the daemon request. */
export function imageProcessingMode(model: string, explicitValue?: boolean | null): ImageProcessingMode {
  return detectVisionSupport(model, explicitValue) ? "direct" : "ocr";
}

export const MAX_IMAGE_ATTACHMENTS = 20;
export function canAddImageAttachments(existing: number, incoming = 1): boolean {
  return existing >= 0 && incoming >= 0 && existing + incoming <= MAX_IMAGE_ATTACHMENTS;
}
