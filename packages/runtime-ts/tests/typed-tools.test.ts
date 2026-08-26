import assert from "node:assert/strict";
import { test } from "node:test";
import { toTypedTool } from "../src/typed-tools.js";
import type { Tool } from "../src/tools.js";
import type { Workspace } from "../src/workspace.js";

test("legacy Tool adapts to typed tool with aliases, permission, and details", async () => {
  const legacy: Tool = {
    name: "legacy",
    aliases: ["old"],
    description: "legacy tool",
    permission: "workspace_write",
    schema: { type: "object", required: ["value"] },
    async invoke(params) { return { ok: true, output: `value:${params.value}` }; },
  };
  const typed = toTypedTool(legacy, (signal) => ({ workspace: {} as Workspace, signal }));
  assert.deepEqual(typed.aliases, ["old"]); assert.equal(typed.permission, "workspace_write"); assert.deepEqual(typed.parameters, legacy.schema);
  const result = await typed.execute({ value: 3 }, { callId: "call", signal: new AbortController().signal, onUpdate() {} });
  assert.equal(result.content, "value:3"); assert.deepEqual(result.details, { output: "value:3" });
});

test("legacy failed result preserves structured error code", async () => {
  const legacy: Tool = { name: "fails", description: "", permission: "read_only", schema: { type: "object" }, async invoke() { return { ok: false, output: "", error: "timed out", errorType: "timeout" }; } };
  const typed = toTypedTool(legacy, (signal) => ({ workspace: {} as Workspace, signal }));
  const result = await typed.execute({}, { callId: "call", signal: new AbortController().signal, onUpdate() {} });
  assert.equal(result.isError, true); assert.equal(result.errorCode, "TIMEOUT");
});
