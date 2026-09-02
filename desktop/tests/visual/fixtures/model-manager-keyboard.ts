import { createApp, defineComponent, h, ref } from "vue";
import ModelManager from "../../../src/components/ModelConfig/ModelManager.vue";
import { connectRuntime, type ModelProfile } from "../../../src/services/sztu-runtime";
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

const callbacks = new Map<number, Callback>();
const listeners = new Map<string, number>();
let callbackId = 0;

async function handleRpc(request: RpcRequest): Promise<Record<string, unknown>> {
  if (request.method === "event.subscribe") return { subscribed: true };
  if (request.method === "provider.model_list") return { models: [...models] };
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
  const response = { jsonrpc: "2.0", id: request.id, result: handled.result ?? handled };
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

await connectRuntime();

// 包装组件：模拟 App.vue 的打开/关闭模式。
// "打开模型管理"按钮持有引用，关闭 ModelManager 后焦点回到该按钮（验收标准：关闭后焦点返回触发按钮）。
const Host = defineComponent({
  setup() {
    const open = ref(false);
    const trigger = ref<HTMLButtonElement | null>(null);

    function openManager() {
      open.value = true;
    }
    function closeManager() {
      open.value = false;
      // 与 App.vue 的 modelManagerOpen 行为一致：关闭后焦点回到触发按钮
      requestAnimationFrame(() => trigger.value?.focus());
    }

    return () =>
      h("div", { class: "mmk-host", style: "padding:24px;font-family:system-ui,sans-serif" }, [
        h("button", {
          ref: trigger,
          type: "button",
          id: "open-model-manager",
          onClick: openManager,
        }, "打开模型管理"),
        open.value ? h(ModelManager, { onClose: closeManager }) : null,
      ]);
  },
});

createApp(Host).use(i18n).mount("#app");
