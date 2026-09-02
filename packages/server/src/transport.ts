import net from "node:net";
import { randomUUID } from "node:crypto";
import type { ConnectionState, EventEnvelope, RpcResponse, Transport, TransportOptions } from "./types.js";

export interface TransportHandlers {
  onMessage?: (connection: ConnectionState, message: unknown) => void | Promise<void>;
  onClose?: (connection: ConnectionState) => void | Promise<void>;
  onError?: (error: Error, connection?: ConnectionState) => void;
}

/** TCP newline-delimited JSON transport. Protocol policy stays in Server. */
export class TcpNdjsonTransport implements Transport {
  readonly server: net.Server;
  readonly connections = new Set<ConnectionState>();
  readonly host: string;
  readonly port: number;
  readonly maxFrameBytes: number;
  readonly handshakeTimeoutMs: number;
  readonly compatibilityMode: boolean;
  private readonly handlers: TransportHandlers;
  private closing = false;
  private addressValue?: string;

  constructor(options: TransportOptions = {}, handlers: TransportHandlers = {}) {
    this.host = options.host ?? "127.0.0.1";
    this.port = options.port ?? 7438;
    this.maxFrameBytes = options.maxFrameBytes ?? 64 * 1024 * 1024;
    this.handshakeTimeoutMs = options.handshakeTimeoutMs ?? 5_000;
    this.compatibilityMode = options.compatibilityMode ?? false;
    if (!Number.isSafeInteger(this.maxFrameBytes) || this.maxFrameBytes <= 0) throw new TypeError("maxFrameBytes must be positive");
    this.handlers = handlers;
    this.server = net.createServer((socket) => this.accept(socket));
  }

  get address(): string | undefined { return this.addressValue; }

  async listen(): Promise<string> {
    if (this.closing) throw new Error("Transport is closing");
    return new Promise((resolve, reject) => {
      const onError = (error: Error) => { this.server.off("listening", onListening); reject(error); };
      const onListening = () => {
        this.server.off("error", onError);
        const address = this.server.address();
        this.addressValue = typeof address === "object" && address ? `${address.address}:${address.port}` : `${this.host}:${this.port}`;
        resolve(this.addressValue);
      };
      this.server.once("error", onError);
      this.server.once("listening", onListening);
      this.server.listen(this.port, this.host);
    });
  }

  async close(): Promise<void> {
    if (this.closing) return;
    this.closing = true;
    await Promise.all([...this.connections].map((connection) => this.closeConnection(connection)));
    if (this.server.listening) await new Promise<void>((resolve) => this.server.close(() => resolve()));
    this.connections.clear();
  }

  async send(connection: ConnectionState, message: unknown): Promise<boolean> {
    if (connection.disconnected || connection.socket.destroyed) return false;
    const line = `${JSON.stringify(message)}\n`;
    if (Buffer.byteLength(line, "utf8") > this.maxFrameBytes) throw new Error("Response too large");
    // 写入失败（如对端是 HTTP 探测等无效客户端，收到非 HTTP 响应后立即断开）时返回 false 而不是 reject，
    // 避免未处理的 Promise 拒绝拖垮整个 daemon 进程
    return new Promise((resolve) => {
      connection.socket.write(line, "utf8", (error) => resolve(!error));
    });
  }

  async closeConnection(connection: ConnectionState): Promise<void> {
    if (connection.disconnected) return;
    connection.stage = "closing";
    await new Promise<void>((resolve) => {
      const socket = connection.socket;
      if (socket.destroyed) { resolve(); return; }
      socket.once("close", () => resolve());
      socket.end();
    });
    if (!connection.disconnected) {
      connection.disconnected = true;
      connection.stage = "closed";
      this.connections.delete(connection);
      await this.handlers.onClose?.(connection);
    }
  }

  private accept(socket: net.Socket): void {
    if (this.closing) { socket.destroy(); return; }
    const connection: ConnectionState = {
      id: randomUUID(), socket, stage: "awaitingHello", handshakeComplete: false, disconnected: false,
      sessionIds: new Set(), subscriptions: new Set(),
    };
    this.connections.add(connection);
    const handshakeTimer = this.compatibilityMode ? undefined : setTimeout(() => {
      if (connection.handshakeComplete || connection.disconnected) return;
      void this.send(connection, { type: "hello_error", error: { code: "invalid_request", message: "Handshake timeout" } }).finally(() => this.closeConnection(connection));
    }, this.handshakeTimeoutMs);
    handshakeTimer?.unref();
    let buffer = Buffer.alloc(0);
    socket.on("data", (chunk: Buffer | string) => {
      if (connection.disconnected) return;
      buffer = Buffer.concat([buffer, Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)]);
      if (buffer.length > this.maxFrameBytes && !buffer.includes(10)) {
        void this.send(connection, { jsonrpc: "2.0", id: null, error: { code: -32600, message: "Request too large" } }).finally(() => socket.destroy());
        return;
      }
      let newline = buffer.indexOf(10);
      while (newline >= 0) {
        let frame = buffer.subarray(0, newline); buffer = buffer.subarray(newline + 1);
        if (frame.length > this.maxFrameBytes) {
          void this.send(connection, { jsonrpc: "2.0", id: null, error: { code: -32600, message: "Request too large" } }).finally(() => socket.destroy());
          return;
        }
        if (frame.length && frame[frame.length - 1] === 13) frame = frame.subarray(0, frame.length - 1);
        let message: unknown;
        try { message = JSON.parse(frame.toString("utf8")); }
        catch { void this.send(connection, { jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }); newline = buffer.indexOf(10); continue; }
        void this.handlers.onMessage?.(connection, message);
        newline = buffer.indexOf(10);
      }
    });
    const onClose = () => {
      if (handshakeTimer) clearTimeout(handshakeTimer);
      if (connection.disconnected) return;
      connection.disconnected = true; connection.stage = "closed"; this.connections.delete(connection);
      void this.handlers.onClose?.(connection);
    };
    socket.once("close", onClose);
    socket.once("error", (error) => {
      this.handlers.onError?.(error, connection);
      if (!connection.disconnected) socket.destroy();
    });
  }
}

export type NdjsonTransportMessage = RpcResponse | EventEnvelope | Record<string, unknown>;
