import alibabaCloudLogo from "@lobehub/icons-static-svg/icons/alibabacloud-color.svg";
import anthropicLogo from "@lobehub/icons-static-svg/icons/anthropic.svg";
import bedrockLogo from "@lobehub/icons-static-svg/icons/bedrock-color.svg";
import byteDanceLogo from "@lobehub/icons-static-svg/icons/bytedance-color.svg";
import deepSeekLogo from "@lobehub/icons-static-svg/icons/deepseek-color.svg";
import minimaxLogo from "@lobehub/icons-static-svg/icons/minimax-color.svg";
import modelScopeLogo from "@lobehub/icons-static-svg/icons/modelscope-color.svg";
import moonshotLogo from "@lobehub/icons-static-svg/icons/moonshot.svg";
import openAiLogo from "@lobehub/icons-static-svg/icons/openai.svg";
import openRouterLogo from "@lobehub/icons-static-svg/icons/openrouter-color.svg";
import ppioLogo from "@lobehub/icons-static-svg/icons/ppio-color.svg";
import siliconCloudLogo from "@lobehub/icons-static-svg/icons/siliconcloud-color.svg";
import tencentCloudLogo from "@lobehub/icons-static-svg/icons/tencentcloud-color.svg";
import volcengineLogo from "@lobehub/icons-static-svg/icons/volcengine-color.svg";
import zaiLogo from "@lobehub/icons-static-svg/icons/zai.svg";
import zhipuLogo from "@lobehub/icons-static-svg/icons/zhipu-color.svg";

export type ModelVendor = {
  name: string;
  logo: string | null;
  mark: string;
  provider: "anthropic" | "openai";
  baseUrl: string;
  apiKeyUrl: string | null;
};

export const modelVendors: ModelVendor[] = [
  { name: "自定义模型", logo: null, mark: "+", provider: "openai", baseUrl: "", apiKeyUrl: null },
  { name: "AWS", logo: bedrockLogo, mark: "A", provider: "anthropic", baseUrl: "", apiKeyUrl: "https://console.aws.amazon.com/iam/home#/security_credentials" },
  { name: "OpenRouter", logo: openRouterLogo, mark: "O", provider: "openai", baseUrl: "https://openrouter.ai/api/v1", apiKeyUrl: "https://openrouter.ai/settings/keys" },
  { name: "MiniMax-CN", logo: minimaxLogo, mark: "M", provider: "openai", baseUrl: "https://api.minimaxi.com/v1", apiKeyUrl: "https://platform.minimaxi.com/user-center/basic-information/interface-key" },
  { name: "MiniMax-Global", logo: minimaxLogo, mark: "M", provider: "openai", baseUrl: "https://api.minimax.io/v1", apiKeyUrl: "https://platform.minimax.io/user-center/basic-information/interface-key" },
  { name: "Bigmodel", logo: zhipuLogo, mark: "Z", provider: "openai", baseUrl: "https://open.bigmodel.cn/api/paas/v4", apiKeyUrl: "https://open.bigmodel.cn/usercenter/apikeys" },
  { name: "Z.ai", logo: zaiLogo, mark: "Z", provider: "openai", baseUrl: "https://api.z.ai/api/paas/v4", apiKeyUrl: "https://z.ai/manage-apikey/apikey-list" },
  { name: "Kimi-CN", logo: moonshotLogo, mark: "K", provider: "openai", baseUrl: "https://api.moonshot.cn/v1", apiKeyUrl: "https://platform.moonshot.cn/console/api-keys" },
  { name: "Kimi-Global", logo: moonshotLogo, mark: "K", provider: "openai", baseUrl: "https://api.moonshot.ai/v1", apiKeyUrl: "https://platform.moonshot.ai/console/api-keys" },
  { name: "DeepSeek", logo: deepSeekLogo, mark: "D", provider: "openai", baseUrl: "https://api.deepseek.com/v1", apiKeyUrl: "https://platform.deepseek.com/api_keys" },
  { name: "火山引擎", logo: volcengineLogo, mark: "火", provider: "openai", baseUrl: "", apiKeyUrl: "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey" },
  { name: "阿里云", logo: alibabaCloudLogo, mark: "阿", provider: "openai", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKeyUrl: "https://bailian.console.aliyun.com/?apiKey=1#/api-key" },
  { name: "腾讯云", logo: tencentCloudLogo, mark: "腾", provider: "openai", baseUrl: "", apiKeyUrl: "https://console.cloud.tencent.com/cam/capi" },
  { name: "模力方舟", logo: modelScopeLogo, mark: "模", provider: "openai", baseUrl: "https://api-inference.modelscope.cn/v1", apiKeyUrl: "https://modelscope.cn/my/myaccesstoken" },
  { name: "硅基流动", logo: siliconCloudLogo, mark: "S", provider: "openai", baseUrl: "https://api.siliconflow.cn/v1", apiKeyUrl: "https://cloud.siliconflow.cn/account/ak" },
  { name: "PPIO", logo: ppioLogo, mark: "P", provider: "openai", baseUrl: "", apiKeyUrl: "https://ppio.com/user/api-key" },
  { name: "BytePlus", logo: byteDanceLogo, mark: "B", provider: "openai", baseUrl: "", apiKeyUrl: "https://console.byteplus.com/ark/region:ark+ap-southeast-1/apiKey" },
  { name: "Anthropic", logo: anthropicLogo, mark: "A", provider: "anthropic", baseUrl: "https://api.anthropic.com", apiKeyUrl: "https://console.anthropic.com/settings/keys" },
  { name: "OpenAI", logo: openAiLogo, mark: "O", provider: "openai", baseUrl: "https://api.openai.com/v1", apiKeyUrl: "https://platform.openai.com/api-keys" },
];

export function logoForVendor(vendor: string) {
  return modelVendors.find((item) => item.name === vendor)?.logo ?? null;
}
