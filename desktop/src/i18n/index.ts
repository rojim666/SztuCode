import { computed } from "vue";
import { createI18n } from "vue-i18n";
import { enUS } from "./locales/en-US";
import { zhCN } from "./locales/zh-CN";

export type AppLocale = "zh-CN" | "en-US";

const STORAGE_KEY = "sztu.locale";
const SUPPORTED_LOCALES: AppLocale[] = ["zh-CN", "en-US"];

export const localeOptions: Array<{ id: AppLocale; nativeLabel: string }> = [
  { id: "zh-CN", nativeLabel: "简体中文" },
  { id: "en-US", nativeLabel: "English" },
];

function resolveInitialLocale(): AppLocale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "zh-CN" || stored === "en-US") return stored;
  } catch {
    // localStorage 不可用时回退默认语言
  }
  return "zh-CN";
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: resolveInitialLocale(),
  fallbackLocale: "zh-CN",
  messages: {
    "zh-CN": zhCN,
    "en-US": enUS,
  },
});

/** 当前语言标签(zh-CN / en-US),用于日期时间与数字本地化。 */
export const localeTag = computed(() => i18n.global.locale.value as AppLocale);

/** 在非组件上下文(.ts 模块、事件回调)中取文案;组件内请使用 useI18n 或 $t 以保持响应式。 */
export function t(key: string, params?: Record<string, unknown>): string {
  return i18n.global.t(key, params ?? {});
}

/** 切换界面语言并持久化。 */
export function setLocale(value: AppLocale) {
  if (!SUPPORTED_LOCALES.includes(value)) return;
  if (i18n.global.locale.value === value) return;
  i18n.global.locale.value = value;
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // 忽略持久化失败
  }
  document.documentElement.lang = value;
}

document.documentElement.lang = i18n.global.locale.value;
