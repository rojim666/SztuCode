import { createApp, h } from "vue";
import { i18n } from "../../../src/i18n";
import "../../../src/sztu.css";

const callbacks = new Map<number, (event: { payload: string }) => void>();
const listeners = new Map<string, number>();
let callbackId = 0;
let state = "not_started";
const globalWindow = window as unknown as Record<string, unknown>;
globalWindow.__TAURI_INTERNALS__ = {
  transformCallback(callback: (event: { payload: string }) => void) { const id = ++callbackId; callbacks.set(id, callback); return id; },
  unregisterCallback(id: number) { callbacks.delete(id); },
  async invoke(command: string, args: Record<string, unknown> = {}) {
    if (command === "plugin:event|listen") { listeners.set(String(args.event), Number(args.handler)); return args.handler; }
    if (command !== "ipc_send") return null;
    const request = JSON.parse(String(args.payload));
    if (request.method === "index.build") { state = "indexing"; setTimeout(() => { state = "ready"; }, 150); }
    if (request.method === "index.clear") state = "not_started";
    const failed = new URLSearchParams(location.search).has("failed");
    const result = { state: failed ? "failed" : state, files: state === "ready" ? 3 : 0, chunks: state === "ready" ? 8 : 0, processed: 1, total: 3, updated_at: null, error: failed ? "本地模型加载失败" : null };
    callbacks.get(listeners.get("sztu:message") ?? -1)?.({ payload: JSON.stringify({ jsonrpc: "2.0", id: request.id, result }) });
    return null;
  },
};
globalWindow.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
const { connectRuntime } = await import("../../../src/services/sztu-runtime");
const { default: SemanticIndexStatus } = await import("../../../src/components/SemanticIndexStatus.vue");
await connectRuntime();
i18n.global.locale.value = "zh-CN";
createApp({ render: () => h(SemanticIndexStatus, { workspaceId: "workspace", connected: true }) }).use(i18n).mount("#app");
