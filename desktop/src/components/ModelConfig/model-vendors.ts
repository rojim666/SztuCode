import alibabaCloudLogo from "@lobehub/icons-static-svg/icons/alibabacloud-color.svg";
import anthropicLogo from "@lobehub/icons-static-svg/icons/anthropic.svg";
import bedrockLogo from "@lobehub/icons-static-svg/icons/bedrock-color.svg";
import byteDanceLogo from "@lobehub/icons-static-svg/icons/bytedance-color.svg";
import cerebrasLogo from "@lobehub/icons-static-svg/icons/cerebras-color.svg";
import deepSeekLogo from "@lobehub/icons-static-svg/icons/deepseek-color.svg";
import githubLogo from "@lobehub/icons-static-svg/icons/github.svg";
import googleLogo from "@lobehub/icons-static-svg/icons/google-color.svg";
import groqLogo from "@lobehub/icons-static-svg/icons/groq.svg";
import minimaxLogo from "@lobehub/icons-static-svg/icons/minimax-color.svg";
import mistralLogo from "@lobehub/icons-static-svg/icons/mistral-color.svg";
import modelScopeLogo from "@lobehub/icons-static-svg/icons/modelscope-color.svg";
import moonshotLogo from "@lobehub/icons-static-svg/icons/moonshot.svg";
import nvidiaLogo from "@lobehub/icons-static-svg/icons/nvidia-color.svg";
import openAiLogo from "@lobehub/icons-static-svg/icons/openai.svg";
import openRouterLogo from "@lobehub/icons-static-svg/icons/openrouter-color.svg";
import ppioLogo from "@lobehub/icons-static-svg/icons/ppio-color.svg";
import siliconCloudLogo from "@lobehub/icons-static-svg/icons/siliconcloud-color.svg";
import tencentCloudLogo from "@lobehub/icons-static-svg/icons/tencentcloud-color.svg";
import volcengineLogo from "@lobehub/icons-static-svg/icons/volcengine-color.svg";
import zaiLogo from "@lobehub/icons-static-svg/icons/zai.svg";
import zhipuLogo from "@lobehub/icons-static-svg/icons/zhipu-color.svg";

export type ModelVendor = {
  /** 稳定标识，用于 i18n 文案 key（model.vendor.* / model.freeTier.*）与组件内判断 */
  id: string;
  /** 服务商名称；会作为 vendor 字段发送给后端存储，是数据标识，保持原值不做本地化 */
  name: string;
  logo: string | null;
  mark: string;
  provider: "anthropic" | "openai";
  baseUrl: string;
  apiKeyUrl: string | null;
  /** 免费额度标记；存在即表示该平台有免费额度可用，说明文案见 model.freeTier.* */
  freeTier?: boolean;
};

/** 自定义模型服务商的稳定标识 */
export const CUSTOM_VENDOR_ID = "custom";

export const modelVendors: ModelVendor[] = [
  { id: "custom", name: "自定义模型", logo: null, mark: "+", provider: "openai", baseUrl: "", apiKeyUrl: null },
  { id: "openrouter", name: "OpenRouter", logo: openRouterLogo, mark: "O", provider: "openai", baseUrl: "https://openrouter.ai/api/v1", apiKeyUrl: "https://openrouter.ai/settings/keys", freeTier: true },
  { id: "google", name: "Google AI Studio", logo: googleLogo, mark: "G", provider: "openai", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai", apiKeyUrl: "https://aistudio.google.com/apikey", freeTier: true },
  { id: "groq", name: "Groq", logo: groqLogo, mark: "G", provider: "openai", baseUrl: "https://api.groq.com/openai/v1", apiKeyUrl: "https://console.groq.com/keys", freeTier: true },
  { id: "cerebras", name: "Cerebras", logo: cerebrasLogo, mark: "C", provider: "openai", baseUrl: "https://api.cerebras.ai/v1", apiKeyUrl: "https://cloud.cerebras.ai", freeTier: true },
  { id: "mistral", name: "Mistral", logo: mistralLogo, mark: "M", provider: "openai", baseUrl: "https://api.mistral.ai/v1", apiKeyUrl: "https://console.mistral.ai/api-keys", freeTier: true },
  { id: "github", name: "GitHub Models", logo: githubLogo, mark: "G", provider: "openai", baseUrl: "https://models.github.ai/inference", apiKeyUrl: "https://github.com/marketplace/models", freeTier: true },
  { id: "nvidia", name: "NVIDIA NIM", logo: nvidiaLogo, mark: "N", provider: "openai", baseUrl: "https://integrate.api.nvidia.com/v1", apiKeyUrl: "https://build.nvidia.com", freeTier: true },
  { id: "minimaxCn", name: "MiniMax-CN", logo: minimaxLogo, mark: "M", provider: "openai", baseUrl: "https://api.minimaxi.com/v1", apiKeyUrl: "https://platform.minimaxi.com/user-center/basic-information/interface-key" },
  { id: "minimaxGlobal", name: "MiniMax-Global", logo: minimaxLogo, mark: "M", provider: "openai", baseUrl: "https://api.minimax.io/v1", apiKeyUrl: "https://platform.minimax.io/user-center/basic-information/interface-key" },
  { id: "bigmodel", name: "Bigmodel", logo: zhipuLogo, mark: "Z", provider: "openai", baseUrl: "https://open.bigmodel.cn/api/paas/v4", apiKeyUrl: "https://open.bigmodel.cn/usercenter/apikeys", freeTier: true },
  { id: "zai", name: "Z.ai", logo: zaiLogo, mark: "Z", provider: "openai", baseUrl: "https://api.z.ai/api/paas/v4", apiKeyUrl: "https://z.ai/manage-apikey/apikey-list" },
  { id: "kimiCn", name: "Kimi-CN", logo: moonshotLogo, mark: "K", provider: "openai", baseUrl: "https://api.moonshot.cn/v1", apiKeyUrl: "https://platform.moonshot.cn/console/api-keys" },
  { id: "kimiGlobal", name: "Kimi-Global", logo: moonshotLogo, mark: "K", provider: "openai", baseUrl: "https://api.moonshot.ai/v1", apiKeyUrl: "https://platform.moonshot.ai/console/api-keys" },
  { id: "deepseek", name: "DeepSeek", logo: deepSeekLogo, mark: "D", provider: "openai", baseUrl: "https://api.deepseek.com/v1", apiKeyUrl: "https://platform.deepseek.com/api_keys", freeTier: true },
  { id: "volcengine", name: "火山引擎", logo: volcengineLogo, mark: "火", provider: "openai", baseUrl: "", apiKeyUrl: "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey", freeTier: true },
  { id: "alibaba", name: "阿里云", logo: alibabaCloudLogo, mark: "阿", provider: "openai", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKeyUrl: "https://bailian.console.aliyun.com/?apiKey=1#/api-key", freeTier: true },
  { id: "tencent", name: "腾讯云", logo: tencentCloudLogo, mark: "腾", provider: "openai", baseUrl: "", apiKeyUrl: "https://console.cloud.tencent.com/cam/capi" },
  { id: "modelark", name: "模力方舟", logo: modelScopeLogo, mark: "模", provider: "openai", baseUrl: "https://api-inference.modelscope.cn/v1", apiKeyUrl: "https://modelscope.cn/my/myaccesstoken", freeTier: true },
  { id: "siliconflow", name: "硅基流动", logo: siliconCloudLogo, mark: "S", provider: "openai", baseUrl: "https://api.siliconflow.cn/v1", apiKeyUrl: "https://cloud.siliconflow.cn/account/ak", freeTier: true },
  { id: "ppio", name: "PPIO", logo: ppioLogo, mark: "P", provider: "openai", baseUrl: "", apiKeyUrl: "https://ppio.com/user/api-key" },
  { id: "byteplus", name: "BytePlus", logo: byteDanceLogo, mark: "B", provider: "openai", baseUrl: "", apiKeyUrl: "https://console.byteplus.com/ark/region:ark+ap-southeast-1/apiKey" },
  { id: "aws", name: "AWS", logo: bedrockLogo, mark: "A", provider: "anthropic", baseUrl: "", apiKeyUrl: "https://console.aws.amazon.com/iam/home#/security_credentials" },
  { id: "anthropic", name: "Anthropic", logo: anthropicLogo, mark: "A", provider: "anthropic", baseUrl: "https://api.anthropic.com", apiKeyUrl: "https://console.anthropic.com/settings/keys" },
  { id: "openai", name: "OpenAI", logo: openAiLogo, mark: "O", provider: "openai", baseUrl: "https://api.openai.com/v1", apiKeyUrl: "https://platform.openai.com/api-keys" },
];

export function logoForVendor(vendor: string) {
  return modelVendors.find((item) => item.name === vendor)?.logo ?? null;
}

/** 按存储的服务商名称解析稳定标识；未收录的服务商返回 null */
export function vendorIdByName(name: string): string | null {
  return modelVendors.find((item) => item.name === name)?.id ?? null;
}
