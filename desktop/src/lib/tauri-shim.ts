/**
 * Tauri API 浏览器兼容层
 *
 * 在非 Tauri 环境（纯浏览器开发模式）下提供空实现，
 * 避免 import 语句在浏览器中报错。
 */

export type UnlistenFn = () => void;

const IS_TAURI = "__TAURI_INTERNALS__" in window;

// 统一的 Tauri 环境检测导出
export { IS_TAURI };

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

// window 兼容实现
export function getCurrentWindow() {
  if (IS_TAURI) {
    // 动态导入但同步返回代理对象... 这里简化处理
    // 实际使用中这些 API 只在 Tauri 环境下被调用
    return {};
  }
  return {
    setTitle: () => {},
    minimize: () => {},
    toggleMaximize: () => {},
    close: () => {},
    onFocusChanged: () => () => {},
    onResized: () => () => {},
    onMoved: () => () => {},
    outerPosition: () => Promise.resolve({ x: 0, y: 0 }),
    outerSize: () => Promise.resolve({ width: window.outerWidth, height: window.outerHeight }),
    innerSize: () => Promise.resolve({ width: window.innerWidth, height: window.innerHeight }),
    setFocus: () => {},
  };
}

// webview 兼容实现
export function getCurrentWebview() {
  if (IS_TAURI) {
    return {};
  }
  return {
    setZoom: () => Promise.resolve(),
    position: () => Promise.resolve({ x: 0, y: 0 }),
    size: () => Promise.resolve({ width: window.innerWidth, height: window.innerHeight }),
    setPosition: () => Promise.resolve(),
    setSize: () => Promise.resolve(),
    show: () => {},
    hide: () => {},
  };
}
