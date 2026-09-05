import { createApp, h, ref } from "vue";
import type { ModelProfile, RuntimeSettings } from "../../../src/services/sztu-runtime";
import { i18n } from "../../../src/i18n";
import "../../../src/kimi.css";
import "../../../src/workbench.css";

type RpcRequest = { id: string; method: string; params?: Record<string, unknown> };
type Callback = (event: { payload: string }) => void;

const profile = (overrides: Partial<ModelProfile>): ModelProfile => ({
  id: "profile",
  name: "模型",
  vendor: "测试服务商",
  provider: "openai",
  model: "test-model",
  base_url: "",
  has_api_key: true,
  is_current: false,
  builtin: false,
  api_format: "openai_chat_completions",
  context_window: 0,
  max_output_tokens: 1_024,
  temperature: null,
  top_p: null,
  reasoning_effort: "",
  timeout_s: 120,
  max_retries: 2,
  cache_control: true,
  ...overrides,
});

let models: ModelProfile[] = [
  profile({ id: "current", name: "当前模型", model: "current-model", is_current: true }),
  profile({ id: "builtin", name: "内置模型", model: "builtin-model", builtin: true }),
  profile({ id: "custom", name: "自定义模型", model: "custom-model" }),
];
if (new URLSearchParams(location.search).has("many")) {
  models.push(...["ling-3.0-flash-fin-free", "mimo-v2.5-free", "nemotron-3-ultra-free", "nemotron-3.5-lightning-free", "openai-fast"].map((name, index) => profile({ id: 'extra-' + index, name, model: name, vendor: "opencode", builtin: true })));
}
let deleteMode: "success" | "error" = "success";
let deleteDelayMs = 0;
let selectDelayMs = 0;
const deleteCalls: string[] = [];
const saveCalls: Record<string, unknown>[] = [];
const testCalls: Record<string, unknown>[] = [];
const settingsCalls: Record<string, unknown>[] = [];
let settingsError = false;
let settingsDelay = 0;
let runtimeSettings = { ...models[0], permission_mode: "normal" } as RuntimeSettings;
const callbacks = new Map<number, Callback>();
const listeners = new Map<string, number>();
let callbackId = 0;

async function handleRpc(request: RpcRequest): Promise<Record<string, unknown>> {
  if (request.method === "event.subscribe") return { subscribed: true };
  if (request.method === "settings.update") {
    settingsCalls.push(request.params ?? {});
    if (settingsDelay) await new Promise(resolve => window.setTimeout(resolve, settingsDelay));
    if (settingsError) return { error: { code: 500, message: "思考强度保存失败" } };
    runtimeSettings = { ...runtimeSettings, ...request.params };
    return { settings: runtimeSettings };
  }
  if (request.method === "provider.model_list") return { models: [...models] };
  if (request.method === "provider.model_save") {
    const input = request.params ?? {};
    saveCalls.push(input);
    models = models.map(item => item.id === input.id ? { ...item, ...input, is_current: true } as ModelProfile : { ...item, is_current: false });
    return { settings: models.find(item => item.is_current), models: [...models] };
  }
  if (request.method === "provider.model_test") {
    testCalls.push(request.params ?? {});
    return { success: true, elapsed_ms: 12 };
  }
  if (request.method === "provider.status") return {};
  if (request.method === "provider.model_delete") {
    const modelId = String(request.params?.model_id ?? "");
    deleteCalls.push(modelId);
    if (deleteDelayMs) await new Promise((resolve) => window.setTimeout(resolve, deleteDelayMs));
    if (deleteMode === "error") return { error: { code: 500, message: "删除模型失败：本地服务暂时不可用" } };
    models = models.filter((item) => item.id !== modelId);
    const responseModels = [...models, profile({ id: "server-only", name: "服务端返回模型", model: "server-model" })];
    models = responseModels;
    return { result: { models: responseModels } };
  }
  if (request.method === "provider.model_select") {
    const modelId = String(request.params?.model_id ?? "");
    const selectedModels = models.map((item) => ({ ...item, is_current: item.id === modelId }));
    models = selectedModels;
    runtimeSettings = { ...runtimeSettings, ...selectedModels.find(item => item.is_current) };
    if (selectDelayMs) await new Promise((resolve) => window.setTimeout(resolve, selectDelayMs));
    return { result: { settings: runtimeSettings, models: selectedModels } };
  }
  return {};
}

const invoke = async (command: string, args: Record<string, unknown> = {}): Promise<unknown> => {
  if (command === "daemon_start" || command === "ipc_connect") return null;
  if (command === "plugin:event|listen") {
    const event = String(args.event ?? "");
    const handler = Number(args.handler);
    listeners.set(event, handler);
    return handler;
  }
  if (command === "plugin:event|unlisten") return null;
  if (command !== "ipc_send") return null;

  const request = JSON.parse(String(args.payload)) as RpcRequest;
  const handled = await handleRpc(request);
  const rpcError = handled.error as { code: number; message: string } | undefined;
  const response = rpcError
    ? { jsonrpc: "2.0", id: request.id, error: rpcError }
    : { jsonrpc: "2.0", id: request.id, result: handled.result ?? handled };
  const handler = callbacks.get(listeners.get("sztu:message") ?? -1);
  handler?.({ payload: JSON.stringify(response) });
  return null;
};

const tauriInternals = {
  invoke,
  transformCallback(callback: Callback) {
    const id = ++callbackId;
    callbacks.set(id, callback);
    return id;
  },
  unregisterCallback(id: number) { callbacks.delete(id); },
};

const globalWindow = window as unknown as Record<string, unknown>;
globalWindow.__TAURI_INTERNALS__ = tauriInternals;
globalWindow.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: () => undefined };
globalWindow.__modelManagerFixture = {
  deleteCalls,
  saveCalls,
  testCalls,
  settingsCalls,
  setSettingsError(value: boolean) { settingsError = value; },
  setSettingsDelay(value: number) { settingsDelay = value; },
  setDeleteMode(mode: "success" | "error") { deleteMode = mode; },
  setDeleteDelay(delay: number) { deleteDelayMs = delay; },
  setSelectDelay(delay: number) { selectDelayMs = delay; },
};

const { connectRuntime } = await import("../../../src/services/sztu-runtime");
const { default: ModelManager } = await import("../../../src/components/ModelConfig/ModelManager.vue");
await connectRuntime();
i18n.global.locale.value = "zh-CN";
if (new URLSearchParams(location.search).has("menu")) {
  const { default: ModelConfigMenu } = await import("../../../src/components/ModelConfig/ModelConfigMenu.vue");
  models[2].reasoning_effort = "low";
  const settings = ref(runtimeSettings);
  createApp({ setup: () => () => h("div", { style: "position:fixed;bottom:24px;right:24px" }, [
    h(ModelConfigMenu, { settings: settings.value, status: null, onUpdated: (value: RuntimeSettings) => { settings.value = value; } }),
  ]) }).use(i18n).mount("#app");
} else createApp(ModelManager).use(i18n).mount("#app");
