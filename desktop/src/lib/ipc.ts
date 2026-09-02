import { invoke, listen } from "./tauri-shim";
import type { UnlistenFn } from "./tauri-shim";
import type { EventEnvelope, JsonRpcResponse, RuntimeEvent } from "../protocol";

export type IpcEvent = RuntimeEvent;

type PendingRequest = {
  resolve: (value: Record<string, unknown>) => void;
  reject: (reason: Error) => void;
  timeout: number;
};

const REQUEST_TIMEOUT_MS = 20_000;

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

  async connect(host: string, port: number): Promise<void> {
    if (this.connected) return;
    if (this.connecting) return this.connecting;
    this.connecting = this.connectTauri(host, port);
    try {
      await this.connecting;
      this.connected = true;
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
      await invoke("ipc_send", { payload });
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
    this.markDisconnected("客户端已关闭");
  }

  private async connectTauri(host: string, port: number): Promise<void> {
    if (!this.unlistenMessage) {
      this.unlistenMessage = await listen<string>("sztu:message", ({ payload }) => this.receive(payload));
      this.unlistenDisconnect = await listen<string>("sztu:disconnected", ({ payload }) => this.markDisconnected(payload));
    }
    await invoke("ipc_connect", { host, port });
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
