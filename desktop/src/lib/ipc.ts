import { invoke, listen, IS_TAURI } from "./tauri-shim";
import type { UnlistenFn } from "./tauri-shim";
import type { EventEnvelope, JsonRpcResponse, RuntimeEvent } from "../protocol";

export type IpcEvent = RuntimeEvent;

type PendingRequest = {
  resolve: (value: Record<string, unknown>) => void;
  reject: (reason: Error) => void;
  timeout: number;
};

const REQUEST_TIMEOUT_MS = 20_000;

function isTauriEnv(): boolean {
  return IS_TAURI;
}

export class IpcRequestError extends Error {
  constructor(public readonly code: number, message: string) {
    super(message);
    this.name = "IpcRequestError";
  }
}

export class IpcClient {
  private pending = new Map<string, PendingRequest>();
  private eventHandlers = new Set<(event: IpcEvent) => void>();
  private disconnectHandlers = new Set<(reason: string) => void>();
  private unlistenMessage: UnlistenFn | null = null;
  private unlistenDisconnect: UnlistenFn | null = null;
  private connected = false;
  private connecting: Promise<void> | null = null;

  // WebSocket 直连模式（浏览器开发用）
  private ws: WebSocket | null = null;
  private wsBuffer: string[] = [];
  private useWs = false;

  async connect(host: string, port: number): Promise<void> {
    if (this.connected) return;
    if (this.connecting) return this.connecting;
    this.connecting = this.connectInternal(host, port);
    try {
      await this.connecting;
    } finally {
      this.connecting = null;
    }
  }

  onEvent(handler: (event: IpcEvent) => void): () => void {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  onDisconnect(handler: (reason: string) => void): () => void {
    this.disconnectHandlers.add(handler);
    return () => this.disconnectHandlers.delete(handler);
  }

  async request(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    if (!this.connected) throw new Error("本地服务尚未连接");
    const id = crypto.randomUUID();
    const payload = JSON.stringify({ jsonrpc: "2.0", id, method, params });
    const result = new Promise<Record<string, unknown>>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        if (!this.pending.delete(id)) return;
        reject(new Error(`${method} 请求超时，请检查本地服务状态`));
      }, REQUEST_TIMEOUT_MS);
      this.pending.set(id, { resolve, reject, timeout });
    });
    try {
      if (this.useWs) {
        this.wsSend(payload);
      } else {
        await invoke("ipc_send", { payload });
      }
    } catch (error) {
      this.rejectPending(id, error instanceof Error ? error : new Error(String(error)));
      this.markDisconnected("与本地服务的连接已中断");
    }
    return result;
  }

  dispose(): void {
    this.unlistenMessage?.();
    this.unlistenDisconnect?.();
    this.unlistenMessage = null;
    this.unlistenDisconnect = null;
    if (this.ws) {
      try { this.ws.close(); } catch { /* ignore */ }
      this.ws = null;
    }
    this.markDisconnected("客户端已关闭");
  }

  private async connectInternal(host: string, port: number): Promise<void> {
    this.useWs = !isTauriEnv();

    if (this.useWs) {
      await this.connectWs(host, port);
    } else {
      await this.connectTauri(host, port);
    }
    this.connected = true;
  }

  private async connectTauri(host: string, port: number): Promise<void> {
    if (!this.unlistenMessage) {
      this.unlistenMessage = await listen<string>("sztu:message", ({ payload }) => this.receive(payload));
      this.unlistenDisconnect = await listen<string>("sztu:disconnected", ({ payload }) => this.markDisconnected(payload));
    }
    await invoke("ipc_connect", { host, port });
  }

  private connectWs(_host: string, _port: number): Promise<void> {
    return new Promise((resolve, reject) => {
      // 通过独立的 WebSocket 代理服务器连接（由 Vite 插件启动在 7439 端口）
      const wsPort = 7439;
      const wsUrl = `ws://127.0.0.1:${wsPort}`;
      console.log("[ipc] connecting via WebSocket:", wsUrl);

      const ws = new WebSocket(wsUrl);
      this.ws = ws;
      this.wsBuffer = [];

      // 代理只转发文本帧；默认 blob 会导致事件无法按文本解析，保持显式默认值
      ws.binaryType = "blob";

      ws.onopen = () => {
        console.log("[ipc] WebSocket connected");
        // 发送缓冲中的消息
        for (const msg of this.wsBuffer) {
          ws.send(msg);
        }
        this.wsBuffer = [];
        resolve();
      };

      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          this.receive(event.data);
        }
      };

      ws.onerror = (event) => {
        console.error("[ipc] WebSocket error:", event);
        reject(new Error("无法连接到本地服务（WebSocket），请确认 Vite 开发服务器已启动"));
      };

      ws.onclose = (event) => {
        console.log("[ipc] WebSocket closed:", event.code, event.reason);
        this.markDisconnected(event.reason || "WebSocket 连接已关闭");
      };
    });
  }

  private wsSend(payload: string): void {
    if (!this.ws) throw new Error("WebSocket 未连接");
    if (this.ws.readyState === WebSocket.CONNECTING) {
      this.wsBuffer.push(payload);
      return;
    }
    if (this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket 未就绪");
    }
    this.ws.send(payload);
  }

  private receive(line: string): void {
    let message: JsonRpcResponse<Record<string, unknown>> | EventEnvelope;
    try {
      message = JSON.parse(line) as JsonRpcResponse<Record<string, unknown>> | EventEnvelope;
    } catch {
      return;
    }
    if ("jsonrpc" in message && typeof message.id === "string") {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      window.clearTimeout(pending.timeout);
      if ("error" in message) pending.reject(new IpcRequestError(message.error.code, message.error.message));
      else pending.resolve(message.result ?? {});
      return;
    }
    if ("kind" in message && message.kind === "event") {
      this.eventHandlers.forEach((handler) => handler(message.event));
    }
  }

  private rejectPending(id: string, error: Error): void {
    const pending = this.pending.get(id);
    if (!pending) return;
    this.pending.delete(id);
    window.clearTimeout(pending.timeout);
    pending.reject(error);
  }

  private markDisconnected(reason: string): void {
    const wasConnected = this.connected || this.pending.size > 0;
    this.connected = false;
    for (const [id] of this.pending) this.rejectPending(id, new Error(reason));
    if (wasConnected) this.disconnectHandlers.forEach((handler) => handler(reason));
  }
}
