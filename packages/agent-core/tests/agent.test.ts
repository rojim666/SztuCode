import assert from "node:assert/strict";
import { test } from "node:test";
import type { AssistantMessage, Model, ModelEvent } from "@sztucode/ai";
import { Agent, createStreamFn, type AgentEvent, type AgentTool } from "../src/index.js";

const model: Model = { provider: "test", id: "agent-model", api: "test", contextWindow: 4096, maxTokens: 512, reasoning: false };

function streamResponses(responses: AssistantMessage[], seen: Array<readonly unknown[]> = []) {
  let index = 0;
  return async function* (_model: Model, context: { messages: readonly unknown[] }): AsyncIterable<ModelEvent> {
    seen.push(context.messages);
    const response = responses[Math.min(index++, responses.length - 1)]!;
    if (response.text) yield { type: "token", text: response.text };
    for (const call of response.toolCalls) yield { type: "tool_call", call };
    yield { type: "completed", message: response };
  };
}

test("prompt emits lifecycle events, executes tools, and runs hooks", async () => {
  const events: AgentEvent[] = [];
  const hooks: string[] = [];
  const responses: AssistantMessage[] = [
    { role: "assistant", text: "", toolCalls: [{ id: "call-1", name: "echo", input: { value: "x" } }], stopReason: "tool_use" },
    { role: "assistant", text: "done", toolCalls: [], stopReason: "end_turn" },
  ];
  const tool: AgentTool = { name: "echo", description: "echo", parameters: { type: "object" }, async execute(args, context) { context.onUpdate({ details: { progress: 1 } }); return { content: `echo:${(args as Record<string, unknown>).value}` }; } };
  const agent = new Agent({ model, streamFn: streamResponses(responses), tools: [tool], toolExecution: "sequential", beforeToolCall: () => { hooks.push("before"); return undefined; }, afterToolCall: () => { hooks.push("after"); return { details: { ok: true } }; }, prepareNextTurn: () => { hooks.push("prepare"); }, shouldStopAfterTurn: ({ message }) => { hooks.push(`stop:${message.text}`); return false; } });
  agent.subscribe((event) => { events.push(event); });
  await agent.prompt("start");
  assert.equal(agent.state.isStreaming, false);
  assert.deepEqual(hooks, ["before", "after", "prepare", "stop:", "prepare", "stop:done"]);
  assert.deepEqual(events.map((event) => event.type), [
    "agent_start", "message_start", "message_end", "turn_start", "message_start", "message_update", "message_end",
    "tool_execution_start", "tool_execution_update", "tool_execution_end", "message_start", "message_end", "turn_end", "turn_start", "message_start", "message_update", "message_end", "turn_end", "agent_end",
  ]);
  assert.deepEqual(agent.state.messages.at(-1)?.content, [{ type: "text", text: "done" }]);
  assert.equal(agent.state.messages.find((message) => message.role === "tool")?.content, "echo:x");
});

test("parallel tools emit completion order while preserving result message order", async () => {
  const events: AgentEvent[] = [];
  const response: AssistantMessage = { role: "assistant", text: "", toolCalls: [{ id: "slow", name: "slow", input: {} }, { id: "fast", name: "fast", input: {} }], stopReason: "tool_use" };
  const final: AssistantMessage = { role: "assistant", text: "finished", toolCalls: [], stopReason: "end_turn" };
  const tool = (name: string, delay: number): AgentTool => ({ name, description: name, parameters: { type: "object" }, async execute() { await new Promise((resolve) => setTimeout(resolve, delay)); return { content: name }; } });
  const agent = new Agent({ model, streamFn: streamResponses([response, final]), tools: [tool("slow", 20), tool("fast", 1)], toolExecution: "parallel" });
  agent.subscribe((event) => events.push(event));
  await agent.prompt("run");
  assert.deepEqual(events.filter((event): event is Extract<AgentEvent, { type: "tool_execution_end" }> => event.type === "tool_execution_end").map((event) => event.toolCallId), ["fast", "slow"]);
  assert.deepEqual(agent.state.messages.filter((message) => message.role === "tool").map((message) => message.tool_call_id), ["slow", "fast"]);
});

test("steering, follow-up, abort, continue, and reset are stateful", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const events: AgentEvent[] = [];
  let calls = 0;
  const stream = async function* (_model: Model, context: { messages: readonly { role: string; content: unknown }[] }, options: { signal?: AbortSignal }): AsyncIterable<ModelEvent> {
    calls += 1;
    if (calls === 1) { await gate; if (options.signal?.aborted) yield { type: "aborted", reason: "cancelled" }; else yield { type: "completed", message: { role: "assistant", text: "first", toolCalls: [], stopReason: "end_turn" } }; return; }
    yield { type: "completed", message: { role: "assistant", text: context.messages.at(-1)?.content === "next" ? "continued" : "followed", toolCalls: [], stopReason: "end_turn" } };
  };
  const agent = new Agent({ model, streamFn: stream }); agent.subscribe((event) => events.push(event));
  const running = agent.prompt("start");
  agent.steer("steer"); agent.followUp("follow");
  assert.equal(agent.state.steeringQueueSize, 1); assert.equal(agent.state.followUpQueueSize, 1); agent.abort(); release(); await running; await agent.waitForIdle();
  assert.equal(events.at(-1)?.type, "agent_end"); assert.equal(agent.state.errorMessage, "Agent aborted");
  agent.reset(); assert.equal(agent.state.messages.length, 0); assert.equal(agent.state.steeringQueueSize, 0);
  const continuationAgent = new Agent({ model, streamFn: async function* () { yield { type: "completed", message: { role: "assistant", text: "continued", toolCalls: [], stopReason: "end_turn" } }; } });
  continuationAgent.state.messages = [{ role: "user", content: "next" }];
  await continuationAgent.continue(); assert.deepEqual(continuationAgent.state.messages.at(-1)?.content, [{ type: "text", text: "continued" }]);
});

test("legacy provider adapter exposes the new stream contract", async () => {
  const streamFn = createStreamFn({
    async complete(_messages, _tools, _signal, onToken) { onToken?.("legacy"); return { text: "legacy", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 2 } }; },
  });
  const events: ModelEvent[] = [];
  for await (const event of streamFn(model, { messages: [] }, {})) events.push(event);
  assert.deepEqual(events.map((event) => event.type), ["token", "usage", "completed"]);
  assert.equal(events.at(-1)?.type === "completed" ? events.at(-1).message.text : "", "legacy");
});
