import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { JsonlSessionBackend } from "@sztucode/session-fs";
import type { SessionHeader } from "@sztucode/session";
import type { AssistantMessage, Model, ModelEvent } from "@sztucode/ai";
import { AgentSession, type AgentEvent } from "../src/agent-session.js";

const model = (id: string): Model => ({ provider: "test", id, api: "test", contextWindow: 4096, maxTokens: 512, reasoning: true });
const header = (id: string): SessionHeader => ({ type: "session", version: 1, id, parentSessionId: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), title: "Integration" });

test("AgentSession composes agent, backend, resources, permissions, extensions and compaction", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-agent-session-")); const backend = new JsonlSessionBackend(root); await backend.create(header("s1"));
  const seenThinking: string[] = []; const events: AgentEvent[] = []; const extensionEvents: string[] = [];
  const stream = async function* (current: Model, context: { messages: readonly { role: string; content: unknown }[] }, options: { thinkingLevel?: string }): AsyncIterable<ModelEvent> {
    seenThinking.push(`${current.id}:${options.thinkingLevel}`); const text = String(context.messages.at(-1)?.content ?? ""); const message: AssistantMessage = { role: "assistant", text: `reply:${text}`, toolCalls: [], stopReason: "end_turn" }; yield { type: "token", text: message.text }; yield { type: "completed", message };
  };
  const session = await AgentSession.open({
    id: "s1", backend, modelRuntime: { model: model("m1"), stream },
    resourceLoader: { loadSystemPrompt: () => "system" },
    tools: { list: () => [] }, permissionGate: { check: async () => true },
    extensions: { onEvent: (event) => { extensionEvents.push(event.type); } },
    contextCompaction: { compact: async (messages) => ({ messages: messages.slice(-1) as any, summary: "kept latest" }) },
  });
  session.subscribe((event) => events.push(event)); await session.prompt("hello");
  assert.equal(session.state.messages.at(-1)?.role, "assistant"); assert.deepEqual((await backend.history("s1")).map((entry) => entry.type), ["message", "message"]);
  session.setThinkingLevel("high"); session.setModel(model("m2")); await session.prompt("again"); assert.deepEqual(seenThinking, ["m1:off", "m2:high"]);
  const compacted = await session.compact(); assert.equal(compacted.summary, "kept latest"); assert.equal((await backend.history("s1")).at(-1)?.type, "compaction");
  const fork = await session.fork({ id: "s2" }); assert.equal((await fork.snapshot()).header.parentSessionId, "s1");
  assert.ok(events.some((event) => event.type === "agent_start")); assert.ok(extensionEvents.includes("agent_end")); session.dispose(); await assert.rejects(() => session.prompt("after dispose"));
});
