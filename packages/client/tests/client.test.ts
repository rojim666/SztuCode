import assert from "node:assert/strict";
import test from "node:test";
import type { ClientTransport, ClientTransportFactory } from "../src/index.js";
import { ClientDisconnectedError, ClientProtocolError, ClientRequestError, ClientTimeoutError, DaemonClient } from "../src/index.js";

type Handler = Parameters<ClientTransportFactory>[0];
function fixture(options: { delayMs?: number; closeAfterHello?: boolean; malformed?: boolean } = {}) {
  let nextConnection = 0; let requests: Array<Record<string, unknown>> = []; let activeHandlers!: Handler;
  const factory: ClientTransportFactory = (handlers: Handler): ClientTransport => {
    const connection = ++nextConnection; let closed = false; activeHandlers = handlers;
    const send = async (frame: Uint8Array) => {
      if (closed) throw new Error("transport closed");
      const message = JSON.parse(new TextDecoder().decode(frame).trim()) as Record<string, any>;
      if (options.malformed) { handlers.onData("not-json\n"); return; }
      if (message.type === "hello") {
        if (options.closeAfterHello && connection === 1) { handlers.onClose(); return; }
        handlers.onData(JSON.stringify({ type: "hello", version: 1, server_version: "fixture", capabilities: ["jsonrpc", "ndjson"], connection_id: `c${connection}` }) + "\n"); return;
      }
      requests.push(message);
      if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs));
      if (message.method === "core.ping") handlers.onData(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { server_version: "fixture" } }) + "\n");
      else if (message.method === "event.subscribe") handlers.onData(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { subscribed: ["*"], scope: "global" } }) + "\n");
      else if (message.method === "session.command") {
        const command = message.params.command.command;
        if (command === "list") handlers.onData(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { command: "list", sessions: [] } }) + "\n");
        else if (command === "attach" || command === "create") handlers.onData(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { command, session: { session_id: command === "create" ? "s1" : message.params.command.sessionId, mode: "chat", status: "active", title: "test", updated_at: new Date().toISOString(), run_count: 0, archived: false, pinned: false, workspace_id: null, latest_run_id: null, attached: true, locked: true } } }) + "\n");
        else handlers.onData(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { command, session: { session_id: message.params.command.sessionId, mode: "chat", status: "active", title: "test", updated_at: new Date().toISOString(), run_count: 0, archived: false, pinned: false, workspace_id: null, latest_run_id: null, attached: true, locked: true } } }) + "\n");
      } else handlers.onData(JSON.stringify({ jsonrpc: "2.0", id: message.id, error: { code: -32012, message: "session busy" } }) + "\n");
    };
    return { send, close: () => { closed = true; } };
  };
  return { factory, requests: () => requests, emit: (event: unknown) => activeHandlers?.onData(JSON.stringify({ kind: "event", event }) + "\n") };
}

test("connect performs hello, request ids and idempotency keys use protocol envelopes", async () => {
  const server = fixture(); const client = await DaemonClient.connect({ transportFactory: server.factory });
  assert.equal(client.connected, true); await client.ping({ idempotencyKey: "retry-1", requestId: "fixed-1" });
  assert.equal(server.requests()[0].id, "fixed-1"); assert.equal(server.requests()[0].idempotency_key, "retry-1"); await client.close();
});

test("session SDK methods stay on the daemon session.command boundary", async () => {
  const server = fixture(); const client = await DaemonClient.connect({ transportFactory: server.factory });
  const created = await client.createSession({ name: "sdk" }); assert.equal(created.session_id, "s1");
  const unsubscribe = await client.subscribeEvents({ topics: ["run.*"] }, () => undefined); unsubscribe();
  assert.deepEqual(await client.listSessions(), []);
  assert.equal((await client.attachSession("s1")).session_id, "s1");
  assert.equal((await client.prompt("s1", "hello")).session_id, "s1");
  assert.equal((await client.steer("s1", "more")).session_id, "s1");
  assert.equal((await client.abort("s1")).session_id, "s1");
  assert.equal((await client.setModel("s1", "model")).session_id, "s1");
  assert.equal((await client.setThinking("s1", "high")).session_id, "s1");
  await client.detachSession("s1");
  assert.ok(server.requests().every((request) => request.method === "session.command" || request.method === "event.subscribe" || request.method === "core.ping"));
  await client.close();
});

test("protocol errors and request timeouts are explicit typed errors", async () => {
  const server = fixture({ delayMs: 30 }); const client = await DaemonClient.connect({ transportFactory: server.factory, requestTimeoutMs: 5 });
  await assert.rejects(() => client.ping(), (error) => error instanceof ClientTimeoutError);
  const bad = fixture({ malformed: true }); await assert.rejects(() => DaemonClient.connect({ transportFactory: bad.factory }), (error) => error instanceof ClientProtocolError);
  await client.close();
});

test("reconnect establishes a fresh transport and events preserve wire order", async () => {
  const server = fixture(); const client = await DaemonClient.connect({ transportFactory: server.factory }); const events: string[] = [];
  client.onEvent((event) => events.push(event.type));
  server.emit({ type: "run.started", run_id: "r1", goal: "a", ts: "1" }); server.emit({ type: "run.finished", run_id: "r1", status: "success", steps: 1, total_input_tokens: 0, total_output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0, elapsed_s: 0, context_pct: 0, ts: "2" });
  await new Promise((resolve) => setTimeout(resolve, 0)); assert.deepEqual(events, ["run.started", "run.finished"]);
  await client.reconnect(); assert.equal(client.connected, true); await client.close(); assert.deepEqual(events, ["run.started", "run.finished"]);
});

test("disconnect rejects in-flight operations with a clear error", async () => {
  const server = fixture({ delayMs: 50 }); const client = await DaemonClient.connect({ transportFactory: server.factory });
  const pending = client.ping(); await client.disconnect(); await assert.rejects(() => pending, (error) => error instanceof ClientDisconnectedError); await client.close();
});
