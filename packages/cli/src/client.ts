import net from "node:net";
import { randomUUID } from "node:crypto";
import type { EventEnvelope, JsonRpcResponse, RuntimeEvent } from "@sztucode/protocol";

export class IpcClient {
  private socket: net.Socket | null = null; private buffer = ""; private pending = new Map<string, { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void }>();
  constructor(readonly host = process.env.SZTU_TS_HOST ?? process.env.SZTU_HOST ?? "127.0.0.1", readonly port = Number(process.env.SZTU_TS_PORT ?? process.env.SZTU_PORT ?? 7438), private readonly eventHandler: (event: RuntimeEvent) => void = () => undefined) {}
  async connect(attempts = 20): Promise<void> {
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try { await this.connectOnce(); return; } catch (error) { lastError = error instanceof Error ? error : new Error(String(error)); if (attempt + 1 < attempts) await new Promise((resolve) => setTimeout(resolve, 100)); }
    }
    throw lastError ?? new Error(`Unable to connect to ${this.host}:${this.port}`);
  }
  request(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> { if (!this.socket) throw new Error("not connected"); const id = randomUUID(); this.socket.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`); return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject })); }
  close(): void { this.socket?.destroy(); }
  private connectOnce(): Promise<void> { return new Promise((resolve, reject) => { const socket = net.createConnection({ host: this.host, port: this.port }); const onError = (error: Error) => { socket.destroy(); reject(error); }; socket.once("error", onError); socket.once("connect", () => { socket.off("error", onError); this.socket = socket; socket.setEncoding("utf8"); socket.on("data", (chunk: string) => this.receive(chunk)); socket.on("error", () => undefined); socket.on("close", () => { if (this.socket === socket) this.socket = null; this.failPending(new Error("connection closed")); }); resolve(); }); }); }
  // 连接关闭（daemon 退出/崩溃）时拒绝所有未决请求，避免 CLI 永久挂起
  private failPending(reason: Error): void {
    if (!this.pending.size) return;
    for (const { reject } of this.pending.values()) reject(reason);
    this.pending.clear();
  }
  private receive(chunk: string): void { this.buffer += chunk; let newline = this.buffer.indexOf("\n"); while (newline >= 0) { const line = this.buffer.slice(0, newline); this.buffer = this.buffer.slice(newline + 1); newline = this.buffer.indexOf("\n"); let message: JsonRpcResponse<Record<string, unknown>> | EventEnvelope; try { message = JSON.parse(line) as JsonRpcResponse<Record<string, unknown>> | EventEnvelope; } catch { continue; } if ("kind" in message) this.eventHandler(message.event); else if (typeof message.id === "string") { const pending = this.pending.get(message.id); if (!pending) continue; this.pending.delete(message.id); if ("error" in message) pending.reject(new Error(message.error.message)); else pending.resolve(message.result); } } }
}
