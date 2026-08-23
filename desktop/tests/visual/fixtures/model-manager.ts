import { createApp } from "vue";
import ModelManager from "../../../src/components/ModelConfig/ModelManager.vue";
import { connectRuntime, type ModelProfile } from "../../../src/services/sztu-runtime";
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
let deleteMode: "success" | "error" = "success";
let deleteDelayMs = 0;
let selectDelayMs = 0;
const deleteCalls: string[] = [];
const callbacks = new Map<number, Callback>();
const listeners = new Map<string, number>();
let callbackId = 0;

async function handleRpc(request: RpcRequest): Promise<Record<string, unknown>> {
  if (request.method === "event.subscribe") return { subscribed: true };
  if (request.method === "provider.model_list") return { models: [...models] };
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
    if (selectDelayMs) await new Promise((resolve) => window.setTimeout(resolve, selectDelayMs));
    return { result: { settings: {}, models: selectedModels } };
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
  setDeleteMode(mode: "success" | "error") { deleteMode = mode; },
  setDeleteDelay(delay: number) { deleteDelayMs = delay; },
  setSelectDelay(delay: number) { selectDelayMs = delay; },
};

await connectRuntime();
createApp(ModelManager).mount("#app");
