import assert from "node:assert/strict";
import test from "node:test";
import { AgentLoop, type ModelProvider } from "../src/agent-loop.js";
import { EventBus } from "../src/event-bus.js";
import { validateSchema } from "../src/schema-validator.js";
import { createWorkspaceTools } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

test("schema validator enforces nested types, ranges, enums, and required fields", () => {
  const schema = { type: "object", required: ["name", "items"], properties: { name: { type: "string", minLength: 2 }, mode: { type: "string", enum: ["a", "b"] }, items: { type: "array", minItems: 1, items: { type: "integer", minimum: 1 } } } };
  assert.equal(validateSchema({ name: "ok", mode: "a", items: [1, 2] }, schema).valid, true);
  assert.match((validateSchema({ name: "x", mode: "c", items: [0] }, schema) as { error: string }).error, /name/);
  assert.match((validateSchema({ name: "ok" }, schema) as { error: string }).error, /items is required/);
  assert.equal(validateSchema({ name: "ok", items: [1], extra: true }, schema).valid, true);
});

test("agent loop rejects invalid tool JSON before permission or invocation", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-schema-boundary-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let permissions = 0; let calls = 0; const failures: Array<{ error_class: string; error_message: string }> = [];
    events.subscribe((event) => { if (event.type === "tool.call_failed") failures.push(event); });
    const provider: ModelProvider = { complete: async () => { calls += 1; return calls === 1 ? { text: "", tool_calls: [{ id: "bad", name: "bash", input: { command: 42, timeout: 500 } }], stop_reason: "tool_use" } : { text: "fixed", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => { permissions += 1; return true; } });
    assert.equal((await loop.run("schema", "run", 3)).text, "fixed");
    assert.equal(permissions, 0); assert.equal(failures[0]?.error_class, "schema_error"); assert.match(failures[0]?.error_message ?? "", /command must be string/);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});
