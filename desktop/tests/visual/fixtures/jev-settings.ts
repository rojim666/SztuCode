import { createApp, h, ref } from "vue";
import type { RuntimeSettings } from "../../../src/services/sztu-runtime";
import { i18n } from "../../../src/i18n";
import { defaultAppearanceSettings } from "../../../src/services/appearance";
import "../../../src/sztu.css";
import "../../../src/workbench.css";
import "../../../src/appearance.css";

const callbacks = new Map<number, (event: { payload: string }) => void>();
const listeners = new Map<string, number>();
let callbackId = 0;
let fail = false;
let settings = { provider: "openai", model: "test", permission_mode: "normal", experimental_jev: false, jev_model: "jev-latest", jev_confidence_threshold: 0.8, jev_api_key_configured: false } as RuntimeSettings;
const scenario = new URLSearchParams(location.search).get("scenario");
if (scenario === "legacy") {
  delete settings.experimental_jev;
  delete settings.jev_model;
  delete settings.jev_confidence_threshold;
  delete settings.jev_api_key_configured;
}
const updates: Record<string, unknown>[] = [];
const globalWindow = window as unknown as Record<string, unknown>;
globalWindow.__jevFixture = { updates, setFailure(value: boolean) { fail = value; } };
globalWindow.__TAURI_INTERNALS__ = {
  transformCallback(callback: (event: { payload: string }) => void) { const id = ++callbackId; callbacks.set(id, callback); return id; },
  unregisterCallback(id: number) { callbacks.delete(id); },
  async invoke(command: string, args: Record<string, unknown> = {}) {
    if (command === "plugin:event|listen") { listeners.set(String(args.event), Number(args.handler)); return args.handler; }
    if (command === "plugin:app|version") return "1.0.4";
    if (command === "native_settings_get") return { supported: false };
    if (command !== "ipc_send") return null;
    const request = JSON.parse(String(args.payload));
    let error: { code: number; message: string } | undefined;
    if (request.method === "settings.update") {
      updates.push(request.params);
      if (fail) error = { code: -32603, message: "Test connection failure" };
      else if (scenario !== "ignored") {
        const { jev_api_key, ...publicUpdate } = request.params;
        settings = { ...settings, ...publicUpdate, jev_api_key_configured: settings.jev_api_key_configured || Boolean(jev_api_key) };
      }
    }
    const response = { jsonrpc: "2.0", id: request.id, ...(error ? { error } : { result: { settings } }) };
    callbacks.get(listeners.get("sztu:message") ?? -1)?.({ payload: JSON.stringify(response) });
    return null;
  },
};
globalWindow.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };

const { connectRuntime } = await import("../../../src/services/sztu-runtime");
const { default: SettingsDialog } = await import("../../../src/components/Settings/SettingsDialog.vue");
await connectRuntime();
i18n.global.locale.value = "zh-CN";
const current = ref(settings);
createApp({ setup: () => () => h(SettingsDialog, {
  appearance: defaultAppearanceSettings, runtimeSettings: current.value, permissionError: "", initialSection: "general",
  onRuntimeUpdated: (value: RuntimeSettings) => { current.value = value; },
}) }).use(i18n).mount("#app");
