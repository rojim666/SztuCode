import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { InMemoryTelemetryContext, NOOP_TELEMETRY_CONTEXT, TraceTelemetryContext, TraceWriter, safeStartSpan } from "../src/index.js";

test("in-memory adapter records parent and child spans, events, attributes and status", async () => {
  const telemetry = new InMemoryTelemetryContext();
  await telemetry.startSpan({ name: "rpc.request", attributes: { method: "core.ping", ignored: undefined } }, async (parent) => {
    parent.addEvent("request.received", { count: 1 });
    parent.setAttributes({ client: "desktop" });
    await parent.startSpan({ name: "session.operation" }, (child) => {
      child.setStatus({ status: "error", error: { name: "Expected", message: "diagnostic" } });
    });
  });
  const spans = telemetry.getSpans();
  assert.equal(spans.length, 2);
  assert.equal(spans[1]?.parentId, spans[0]?.id);
  assert.deepEqual(spans[0]?.events, [{ name: "request.received", attributes: { count: 1 } }]);
  assert.deepEqual(spans[0]?.attributes, { method: "core.ping", client: "desktop" });
  assert.deepEqual(spans[1]?.status, { status: "error", error: { name: "Expected", message: "diagnostic" } });
  assert.equal(spans.every((span) => span.settled), true);
});

test("telemetry failures do not affect business execution", async () => {
  const throwing: import("../src/index.js").TelemetryContext = {
    startSpan() { throw new Error("adapter unavailable"); },
  };
  const result = await safeStartSpan(throwing, { name: "agent.run" }, () => "business result");
  assert.equal(result, "business result");
  await assert.rejects(() => NOOP_TELEMETRY_CONTEXT.startSpan({ name: "business.error" }, () => { throw new Error("business failure"); }), /business failure/);
});

test("trace adapter preserves JSONL shape while omitting sensitive attributes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-telemetry-trace-"));
  try {
    const writer = new TraceWriter(path.join(root, "trace.jsonl"));
    const telemetry = new TraceTelemetryContext(writer);
    await telemetry.startSpan({ name: "llm.request", attributes: { model: "demo", prompt: "secret prompt", api_key: "secret", count: 2 } }, (span) => {
      span.addEvent("tool.execution", { file_path: "secret.txt", ok: true });
      span.setStatus({ status: "ok" });
    });
    await writer.flush();
    const rows = (await readFile(path.join(root, "trace.jsonl"), "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line) as { direction: string; layer: string; kind: string; data: Record<string, unknown> });
    assert.deepEqual(rows.map((row) => row.kind), ["span.start", "span.event", "span.end"]);
    assert.equal(JSON.stringify(rows).includes("secret prompt"), false);
    assert.equal(JSON.stringify(rows).includes("secret.txt"), false);
    assert.equal(rows[0]?.direction, "CORE");
    assert.equal(rows[0]?.layer, "telemetry");
  } finally { await rm(root, { recursive: true, force: true }); }
});
