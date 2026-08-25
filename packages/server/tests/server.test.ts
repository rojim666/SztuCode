import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { Server, SessionBusyError } from "../src/index.js";
import type { PiSessionRuntime, SessionMetadata, SessionService, SessionSnapshot, SessionRuntimeEvent } from "../src/index.js";

const waitConnect = (socket: net.Socket) => new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
const frames = (socket: net.Socket) => {
  let buffer = "";
  const pending: Array<(value: any) => void> = [];
  const queued: any[] = [];
  socket.setEncoding("utf8");
  socket.on("data", (chunk: string) => {
    buffer += chunk;
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
      if (line) { const value = JSON.parse(line); const resolve = pending.shift(); if (resolve) resolve(value); else queued.push(value); }
      newline = buffer.indexOf("\n");
    }
  });
  return { next: () => queued.length ? Promise.resolve(queued.shift()) : new Promise<any>((resolve) => pending.push(resolve)) };
};
const hello = async (socket: net.Socket, next: () => Promise<any>) => { socket.write(JSON.stringify({ type: "hello", version: 1 }) + "\n"); const welcome = await next(); assert.equal(welcome.type, "hello"); };
const rpc = async (socket: net.Socket, next: () => Promise<any>, id: string, method: string, params?: unknown) => { socket.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n"); let result = await next(); while (result.id !== id) result = await next(); if (result.error) throw Object.assign(new Error(result.error.message), { code: result.error.code }); return result.result; };

class FakeRuntime implements PiSessionRuntime {
  readonly id: string;
  phase: SessionSnapshot["phase"] = "idle";
  disposed = false;
  promptEntered?: () => void;
  promptRelease?: Promise<void>;
  private readonly listeners = new Set<(event: SessionRuntimeEvent) => void>();
  constructor(id: string) { this.id = id; }
  snapshot(): SessionSnapshot { return { id: this.id, createdAt: 1, updatedAt: 1, phase: this.phase, attached: false, locked: false }; }
  getPhase(): SessionSnapshot["phase"] { return this.phase; }
  async prompt(): Promise<void> { this.phase = "running"; this.promptEntered?.(); await this.promptRelease; this.phase = "idle"; this.listeners.forEach((listener) => listener({ type: "snapshot" })); }
  async steer(): Promise<void> { if (this.phase === "running") throw new SessionBusyError(); }
  async abort(): Promise<void> { this.phase = "idle"; }
  async setModel(): Promise<void> {}
  async setThinking(): Promise<void> {}
  subscribe(listener: (event: SessionRuntimeEvent) => void): () => void { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  async dispose(): Promise<void> { this.disposed = true; }
}

class FakeService implements SessionService {
  readonly runtimes = new Map<string, FakeRuntime>();
  async listSessions(): Promise<SessionMetadata[]> { return [...this.runtimes.keys()].map((id) => ({ id })); }
  async createSession(options: { id: string }): Promise<FakeRuntime> { const runtime = new FakeRuntime(options.id); this.runtimes.set(options.id, runtime); return runtime; }
  async openSession(id: string): Promise<FakeRuntime> { const runtime = this.runtimes.get(id); if (!runtime) throw new Error("session not found"); return runtime; }
}

async function start(service = new FakeService()) {
  const server = new Server(service, { host: "127.0.0.1", port: 0 });
  const address = await server.listen();
  const port = Number(address.split(":").at(-1));
  return { server, service, port };
}

test("multiple connections attach to one live session and receive snapshots", async () => {
  const { server, service, port } = await start();
  const first = net.createConnection({ host: "127.0.0.1", port }); const second = net.createConnection({ host: "127.0.0.1", port });
  await Promise.all([waitConnect(first), waitConnect(second)]);
  const firstFrames = frames(first); const secondFrames = frames(second);
  try {
    await Promise.all([hello(first, firstFrames.next), hello(second, secondFrames.next)]);
    const created = await rpc(first, firstFrames.next, "create", "session.command", { command: "create" });
    const id = created.session.id;
    const attached = await rpc(second, secondFrames.next, "attach", "session.command", { command: "attach", sessionId: id });
    assert.equal(attached.session.id, id);
    await rpc(second, secondFrames.next, "sub", "event.subscribe", { topics: ["demo.*"], scope: "global" });
    server.publish({ type: "demo.updated", sessionId: id });
    const event = await secondFrames.next();
    assert.equal(event.kind, "event"); assert.equal(event.event.type, "demo.updated");
    assert.equal(service.runtimes.get(id)?.disposed, false);
  } finally { first.destroy(); second.destroy(); await server.close(); }
});

test("repeated attach is idempotent and disconnect/reconnect preserves a running session", async () => {
  const { server, service, port } = await start();
  const first = net.createConnection({ host: "127.0.0.1", port }); await waitConnect(first); const firstFrames = frames(first);
  let id = "";
  try {
    await hello(first, firstFrames.next);
    id = (await rpc(first, firstFrames.next, "create", "session.command", { command: "create" })).session.id;
    await rpc(first, firstFrames.next, "attach", "session.command", { command: "attach", sessionId: id });
    const runtime = service.runtimes.get(id)!; runtime.phase = "running";
    first.destroy(); await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(runtime.disposed, false);
    const second = net.createConnection({ host: "127.0.0.1", port }); await waitConnect(second); const secondFrames = frames(second);
    try { await hello(second, secondFrames.next); const result = await rpc(second, secondFrames.next, "reattach", "session.command", { command: "attach", sessionId: id }); assert.equal(result.session.id, id); }
    finally { second.destroy(); }
  } finally { first.destroy(); await server.close(); }
});

test("concurrent operations on one session return a busy conflict", async () => {
  const { server, service, port } = await start();
  const first = net.createConnection({ host: "127.0.0.1", port }); const second = net.createConnection({ host: "127.0.0.1", port }); await Promise.all([waitConnect(first), waitConnect(second)]);
  const a = frames(first); const b = frames(second);
  try {
    await Promise.all([hello(first, a.next), hello(second, b.next)]);
    const id = (await rpc(first, a.next, "create", "session.command", { command: "create" })).session.id;
    await rpc(second, b.next, "attach", "session.command", { command: "attach", sessionId: id });
    const runtime = service.runtimes.get(id)!; let entered!: () => void; let release!: () => void; const started = new Promise<void>((resolve) => { entered = resolve; }); runtime.promptEntered = entered; runtime.promptRelease = new Promise<void>((resolve) => { release = resolve; });
    const firstPrompt = rpc(first, a.next, "prompt", "session.command", { command: "prompt", sessionId: id, text: "wait" }); await started;
    await assert.rejects(() => rpc(second, b.next, "busy", "session.command", { command: "prompt", sessionId: id, text: "conflict" }), (error: any) => error.code === -32012);
    release(); await firstPrompt; first.destroy();
  } finally { first.destroy(); second.destroy(); await server.close(); }
});

test("core.shutdown closes listeners and is idempotent", async () => {
  const { server, port } = await start();
  const socket = net.createConnection({ host: "127.0.0.1", port }); await waitConnect(socket); const stream = frames(socket);
  await hello(socket, stream.next);
  const result = await rpc(socket, stream.next, "shutdown", "core.shutdown"); assert.equal(result.stopping, true);
  await server.close(); await server.close();
  await assert.rejects(() => new Promise<void>((resolve, reject) => { const retry = net.createConnection({ host: "127.0.0.1", port }); retry.once("connect", () => { retry.destroy(); resolve(); }); retry.once("error", reject); }), /ECONNREFUSED/);
});
