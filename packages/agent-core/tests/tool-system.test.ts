import assert from "node:assert/strict";
import { test } from "node:test";
import type { AssistantMessage, Model, ModelEvent } from "@sztucode/ai";
import { Agent, validateToolParameters, type AgentEvent, type AgentTool } from "../src/index.js";

const model: Model = { provider: "test", id: "tool-model", api: "test", contextWindow: 1000, maxTokens: 100, reasoning: false };

test("typed JSON schema validates generic tool parameters", () => {
  const result = validateToolParameters({ count: 0 }, { type: "object", properties: { count: { type: "integer", minimum: 1 } }, required: ["count"] });
  assert.equal(result.valid, false); assert.match(result.error ?? "", /count/);
  const valid = validateToolParameters({ count: 2 }, { type: "object", properties: { count: { type: "integer" } }, required: ["count"] });
  assert.deepEqual(valid.value, { count: 2 });
});

test("aliases resolve to the canonical typed tool", async () => {
  let executed = false;
  const tool: AgentTool = { name: "canonical", aliases: ["alias"], description: "", parameters: { type: "object" }, async execute() { executed = true; return { content: "ok" }; } };
  const events = await runToolCase(tool, {}, "alias", {});
  assert.equal(executed, true); assert.equal(events.some((event) => event.type === "tool_execution_end"), true);
});

test("tool results preserve non-text content blocks and details", async () => {
  const events = await runToolCase({ name: "media", description: "", parameters: { type: "object" }, async execute() { return { content: [{ type: "image", source: { media_type: "image/png", data: "abc" } }], details: { mime: "image/png" } }; } });
  const end = events.find((event): event is Extract<AgentEvent, { type: "tool_execution_end" }> => event.type === "tool_execution_end");
  assert.deepEqual(end?.result.content, [{ type: "image", source: { media_type: "image/png", data: "abc" } }]); assert.deepEqual(end?.result.details, { mime: "image/png" });
});

async function runToolCase(tool: AgentTool, options: { checkToolPermission?: Agent["options"]["checkToolPermission"] } = {}, callName = tool.name, input: Record<string, unknown> = { count: 1 }): Promise<AgentEvent[]> {
  let call = 0;
  const response = (text: string): AssistantMessage => ({ role: "assistant", text, toolCalls: [], stopReason: "end_turn" });
  const stream = async function* (_model: Model, _context: unknown, _options: unknown): AsyncIterable<ModelEvent> {
    call += 1;
    yield { type: "completed", message: call === 1 ? { role: "assistant", text: "", toolCalls: [{ id: "call", name: callName, input }], stopReason: "tool_use" } : response("done") };
  };
  const events: AgentEvent[] = []; const agent = new Agent({ model, streamFn: stream, tools: [tool], checkToolPermission: options.checkToolPermission }); agent.subscribe((event) => events.push(event)); await agent.prompt("run"); return events;
}

const schema = { type: "object" as const, properties: { count: { type: "integer" as const, minimum: 2 } }, required: ["count"] };

test("invalid parameters produce INVALID_ARGUMENTS without executing", async () => {
  let executed = false;
  const events = await runToolCase({ name: "invalid", description: "", parameters: schema, async execute() { executed = true; return { content: "ok" }; } });
  assert.equal(executed, false); assert.equal(events.find((event) => event.type === "tool_execution_end")?.type === "tool_execution_end" ? events.find((event) => event.type === "tool_execution_end")?.result.errorCode : undefined, "INVALID_ARGUMENTS");
});

test("permission denial produces PERMISSION_DENIED", async () => {
  const events = await runToolCase({ name: "protected", description: "", parameters: { type: "object" }, async execute() { return { content: "ok" }; } }, { checkToolPermission: async () => false });
  const end = events.find((event): event is Extract<AgentEvent, { type: "tool_execution_end" }> => event.type === "tool_execution_end"); assert.equal(end?.result.errorCode, "PERMISSION_DENIED");
});

test("execution failures produce EXECUTION_FAILED", async () => {
  const events = await runToolCase({ name: "failing", description: "", parameters: { type: "object" }, async execute() { throw new Error("boom"); } });
  const end = events.find((event): event is Extract<AgentEvent, { type: "tool_execution_end" }> => event.type === "tool_execution_end"); assert.equal(end?.result.errorCode, "EXECUTION_FAILED");
});

test("tool timeout produces TIMEOUT", async () => {
  const events = await runToolCase({ name: "slow", description: "", parameters: { type: "object" }, timeoutMs: 5, async execute() { await new Promise(() => undefined); return { content: "never" }; } });
  const end = events.find((event): event is Extract<AgentEvent, { type: "tool_execution_end" }> => event.type === "tool_execution_end"); assert.equal(end?.result.errorCode, "TIMEOUT");
});
