/**
 * Tauri API 浏览器兼容层
 *
 * 在非 Tauri 环境（纯浏览器开发模式）下提供空实现，
 * 避免在浏览器中直接调用 Tauri API 时报错。
 */

export type UnlistenFn = () => void;

const IS_TAURI = "__TAURI_INTERNALS__" in window;

export { IS_TAURI };

// 直接静态导入 Tauri API（Vite 构建时会打包，Tauri 包本身能安全在浏览器中导入）
import { getCurrentWindow as tauriGetCurrentWindow } from "@tauri-apps/api/window";
import { getCurrentWebview as tauriGetCurrentWebview } from "@tauri-apps/api/webview";

// 浏览器环境空实现
const browserWindowStub = {
  setTitle: () => {},
  minimize: () => Promise.resolve(),
  toggleMaximize: () => Promise.resolve(),
  maximize: () => Promise.resolve(),
  unmaximize: () => Promise.resolve(),
  close: () => Promise.resolve(),
  show: () => Promise.resolve(),
  hide: () => Promise.resolve(),
  setFocus: () => Promise.resolve(),
  startDragging: () => Promise.resolve(),
  onFocusChanged: () => () => {},
  onResized: () => () => {},
  onMoved: () => () => {},
  outerPosition: () => Promise.resolve({ x: 0, y: 0 }),
  outerSize: () => Promise.resolve({ width: window.outerWidth, height: window.outerHeight }),
  innerSize: () => Promise.resolve({ width: window.innerWidth, height: window.innerHeight }),
  label: "main",
  setTitleBarVisibility: () => Promise.resolve(),
};

const browserWebviewStub = {
  setZoom: () => Promise.resolve(),
  position: () => Promise.resolve({ x: 0, y: 0 }),
  size: () => Promise.resolve({ width: window.innerWidth, height: window.innerHeight }),
  setPosition: () => Promise.resolve(),
  setSize: () => Promise.resolve(),
  show: () => {},
  hide: () => {},
  setBackgroundColor: () => Promise.resolve(),
};

let _windowInstance: ReturnType<typeof tauriGetCurrentWindow> | null = null;
let _webviewInstance: ReturnType<typeof tauriGetCurrentWebview> | null = null;

export function getCurrentWindow() {
  if (!IS_TAURI) return browserWindowStub;
  if (!_windowInstance) _windowInstance = tauriGetCurrentWindow();
  return _windowInstance;
}

export function getCurrentWebview() {
  if (!IS_TAURI) return browserWebviewStub;
  if (!_webviewInstance) _webviewInstance = tauriGetCurrentWebview();
  return _webviewInstance;
}

// invoke 兼容实现
export async function invoke<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (IS_TAURI) {
    const { invoke: tauriInvoke } = await import("@tauri-apps/api/core");
    return tauriInvoke<T>(cmd, args);
  }
  console.warn("[tauri-shim] invoke() called in browser mode:", cmd, args);
  throw new Error(`Tauri 命令 "${cmd}" 在浏览器模式下不可用`);
}

// listen 兼容实现
export async function listen<T = unknown>(
  _event: string,
  _handler: (event: { payload: T }) => void,
): Promise<() => void> {
  if (IS_TAURI) {
    const { listen: tauriListen } = await import("@tauri-apps/api/event");
    return tauriListen<T>(_event, _handler);
  }
  console.warn("[tauri-shim] listen() called in browser mode");
  return () => {};
}

// dialog 兼容实现
type DialogKind = "info" | "warning" | "error";

export async function confirm(message: string, options?: { title?: string; kind?: DialogKind }): Promise<boolean> {
  if (IS_TAURI) {
    const { confirm: tauriConfirm } = await import("@tauri-apps/plugin-dialog");
    return tauriConfirm(message, options);
  }
  return window.confirm(message);
}

export async function message(message: string, options?: { title?: string; kind?: DialogKind }): Promise<void> {
  if (IS_TAURI) {
    const { message: tauriMessage } = await import("@tauri-apps/plugin-dialog");
    await tauriMessage(message, options);
    return;
  }
  window.alert(message);
}

export async function open(options?: { multiple?: boolean; directory?: boolean; filters?: Array<{ name: string; extensions: string[] }> }): Promise<string | string[] | null> {
  if (IS_TAURI) {
    const { open: tauriOpen } = await import("@tauri-apps/plugin-dialog");
    return tauriOpen(options);
  }
  console.warn("[tauri-shim] open() file dialog not available in browser mode");
  return null;
}
