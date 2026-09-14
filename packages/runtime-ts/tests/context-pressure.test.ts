import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { AgentLoop, type ModelProvider, type ChatMessage } from "../src/agent-loop.js";
import { ContextManager } from "../src/context.js";
import { EventBus } from "../src/event-bus.js";
import { ToolRegistry } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";

const summary = "Goal: finish the requested investigation. Progress: older evidence reviewed. Decisions: keep investigating. Open Issues: remaining checks. Next Steps: continue with the latest results.";

test("long tool runs wait for slow compaction and preserve new tool results", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-pressure-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let agents = 0; let summaries = 0; let summarizing = false;
    const tools = new ToolRegistry();
    tools.register({ name: "inspect", description: "inspect", permission: "read_only", schema: { type: "object" }, async invoke() { return { ok: true, output: `result-${agents} ` + "evidence about the next file. ".repeat(220) }; } });
    const provider: ModelProvider = { async complete(messages, _tools, signal, _token, invocation) {
      if (invocation?.purpose === "compaction") {
        summaries += 1; summarizing = true;
        await new Promise((resolve) => setTimeout(resolve, 20));
        signal?.throwIfAborted(); summarizing = false;
        return { text: summary, tool_calls: [], stop_reason: "end_turn" };
      }
      const context = new ContextManager(messages);
      const input = context.tokenEstimate() + context.counter.countJson(tools.list());
      assert.ok(input < 7_000, `request must leave output headroom: ${input}`);
      if (agents > 0) assert.ok(messages.some((message) => message.role === "tool" && String(message.content).includes(`result-${agents} `)), "latest result must survive background compaction");
      agents += 1;
      return agents === 31
        ? { text: "done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: input } }
        : { text: "", tool_calls: [{ id: `call-${agents}`, name: "inspect", input: {} }], stop_reason: "tool_use", usage: { input_tokens: input } };
    } };
    const result = await new AgentLoop(provider, tools, { workspace: new Workspace(root) }, events, { check: async () => true }, { contextWindow: 8_000, maxOutputTokens: 1_000 }).run("long", "Investigate all files", 32);
    assert.equal(result.text, "done");
    assert.ok(summaries >= 2, "long run should compact repeatedly");
    assert.equal(summarizing, false);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("oversized resumed history is summarized before the first agent request", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-resume-pressure-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    const purposes: string[] = [];
    const provider: ModelProvider = { async complete(messages, _tools, _signal, _token, invocation) {
      purposes.push(invocation?.purpose ?? "agent");
      if (invocation?.purpose === "compaction") return { text: summary, tool_calls: [], stop_reason: "end_turn" };
      assert.ok(new ContextManager(messages).tokenEstimate() < 3_000);
      return { text: "resumed", tool_calls: [], stop_reason: "end_turn" };
    } };
    const history: ChatMessage[] = [{ role: "user", content: "Original task" }, ...Array.from({ length: 20 }, (_, i): ChatMessage => ({ role: i % 2 ? "user" : "assistant", content: "historical detail ".repeat(180) }))];
    const result = await new AgentLoop(provider, new ToolRegistry(), { workspace: new Workspace(root) }, events, { check: async () => true }, { contextWindow: 4_000, maxOutputTokens: 1_000 }).run("resume", "Continue", 1, history);
    assert.equal(result.text, "resumed");
    assert.equal(purposes[0], "compaction");
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});
