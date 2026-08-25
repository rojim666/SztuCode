import assert from "node:assert/strict";
import test from "node:test";
import {
  JSON_RPC_ERROR_CODES,
  PROTOCOL_CAPABILITIES,
  PROTOCOL_VERSION,
  isClientHello,
  isEventEnvelope,
  isJsonRpcResponse,
  isServerHello,
  isServerHelloError,
  isWireMessage,
  validateJsonRpcRequest,
  validateRequestParams,
  type KnownJsonRpcRequest,
  type SessionAttachResult,
  type SessionDetachResult,
} from "../src/index.ts";

test("legacy JSON-RPC 2.0 request remains valid and accepts an idempotency key", () => {
  const request = {
    jsonrpc: "2.0",
    id: "request-1",
    method: "core.ping",
    params: { client: "test" },
    idempotency_key: "retry-1",
  };
  const result = validateJsonRpcRequest(request);
  assert.equal(result.ok, true);
  if (result.ok) assert.deepEqual(result.value, request);

  const response = { jsonrpc: "2.0", id: "request-1", result: { ok: true } };
  assert.equal(isJsonRpcResponse(response), true);
  assert.equal(isWireMessage(response), true);
});

test("hello handshake advertises a stable version and capabilities", () => {
  const clientHello = { type: "hello", version: PROTOCOL_VERSION, client: "desktop", capabilities: [...PROTOCOL_CAPABILITIES] } as const;
  const serverHello = { type: "hello", version: PROTOCOL_VERSION, server_version: "ts-0.3.0", capabilities: [...PROTOCOL_CAPABILITIES], connection_id: "c1" } as const;
  assert.equal(isClientHello(clientHello), true);
  assert.equal(isServerHello(serverHello), true);
  assert.equal(isWireMessage(clientHello), true);
  assert.equal(isWireMessage(serverHello), true);
  assert.equal(isClientHello({ ...clientHello, version: 99 }), false);
});

test("hello errors and unified error codes are validated", () => {
  const message = { type: "hello_error", error: { code: JSON_RPC_ERROR_CODES.VERSION_UNSUPPORTED, message: "unsupported version" } };
  assert.equal(isServerHelloError(message), true);
  assert.equal(isWireMessage(message), true);
  assert.equal(isServerHelloError({ ...message, error: { code: -1, message: "" } }), false);
  assert.equal(isJsonRpcResponse({ jsonrpc: "2.0", id: "1", result: {}, error: message.error }), false);
});

test("session attach/detach result types are discriminated by attached", () => {
  const attached: SessionAttachResult = {
    session_id: "s1",
    attached: true,
    session: {
      session_id: "s1", mode: "chat", status: "active", title: "Chat", updated_at: "2026-01-01T00:00:00Z",
      run_count: 0, archived: false, pinned: false, workspace_id: null, latest_run_id: null, attached: true, locked: true,
    },
  };
  const detached: SessionDetachResult = { session_id: "s1", attached: false };
  assert.equal(attached.attached, true);
  assert.equal(detached.attached, false);
});

test("known request union keeps method and parameter discriminants", () => {
  const attach: KnownJsonRpcRequest = { jsonrpc: "2.0", id: "1", method: "session.attach", params: { session_id: "s1" } };
  if (attach.method === "session.attach") assert.equal(attach.params.session_id, "s1");
  const cancel: KnownJsonRpcRequest = { jsonrpc: "2.0", id: "2", method: "request.cancel", params: { request_id: "1", reason: "user" } };
  if (cancel.method === "request.cancel") assert.equal(cancel.params.request_id, "1");
});

test("runtime validation covers cancellation, session lifecycle and invalid values", () => {
  assert.equal(validateRequestParams("request.cancel", { request_id: "request-1" }).ok, true);
  assert.equal(validateRequestParams("session.attach", { session_id: "session-1" }).ok, true);
  assert.equal(validateRequestParams("session.detach", { session_id: "session-1" }).ok, true);
  assert.equal(validateRequestParams("session.send_message", { session_id: "s1", content: "hello", images: [{ type: "image", media_type: "image/png", data: "abc" }] }).ok, true);
  assert.equal(validateRequestParams("run.replay", { run_id: "r1", max_events: -1 }).ok, false);
  assert.equal(validateRequestParams("session.attach", { session_id: "" }).ok, false);
  assert.equal(validateRequestParams("core.ping", { client: "" }).ok, false);
  assert.equal(validateJsonRpcRequest({ jsonrpc: "2.0", id: "1", method: "agent.run", params: { goal: "" } }).ok, false);
  assert.equal(validateJsonRpcRequest({ jsonrpc: "2.0", id: "1", method: "core.ping", params: { client: "ok" }, idempotency_key: "" }).ok, false);
  assert.equal(validateJsonRpcRequest({ jsonrpc: "1.0", id: "1", method: "core.ping", params: { client: "ok" } }).ok, false);
});

test("runtime event envelope remains NDJSON event-compatible", () => {
  const envelope = { kind: "event", event: { type: "session.snapshot", session_id: "s1", snapshot: { session_id: "s1", mode: "chat", status: "active", title: "Chat", updated_at: "2026-01-01T00:00:00Z", run_count: 0, archived: false, pinned: false, workspace_id: null, latest_run_id: null }, ts: "2026-01-01T00:00:00Z" } };
  assert.equal(isEventEnvelope(envelope), true);
  assert.equal(isWireMessage(envelope), true);
});
