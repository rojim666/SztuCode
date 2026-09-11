import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { appendGoalReminder, buildDynamicContext, buildSystemPrompt } from "../src/prompt-loader.js";
import { loadMemoryCatalog } from "../src/memory.js";
import { RunManager } from "../src/run-manager.js";
import { EventBus } from "../src/event-bus.js";
import type { ChatMessage, ModelProvider } from "../src/agent-loop.js";
import { ToolRegistry } from "../src/tools.js";
import { AnthropicMessagesProvider } from "../src/providers/anthropic.js";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { AgentLoop } from "../src/agent-loop.js";
import { PermissionManager } from "../src/permissions.js";
import { Workspace } from "../src/workspace.js";
import { WorkingState } from "../src/memory-evolution.js";

test("system is byte-stable across builds, tasks, dates and workspace edits", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-cache-"));
  try {
    await mkdir(path.join(root, ".sztu"));
    const skillFile = path.join(root, ".sztu", "skills", "cache-test", "SKILL.md");
    await mkdir(path.dirname(skillFile), { recursive: true });
    await writeFile(skillFile, "---\nname: cache-test\ndescription: SKILL_SENTINEL_A\n---\nInstructions");
    await writeFile(path.join(root, "AGENTS.md"), "PROJECT_SENTINEL_A");
    await writeFile(path.join(root, ".sztu/context.md"), "MEMORY_SENTINEL_A");
    const first = await buildSystemPrompt(root, "coder", { taskText: "read" });
    const second = await buildSystemPrompt(root, "coder", { taskText: "delete and deploy", permissionMode: "auto", memoryEnabled: true });
    assert.deepEqual(Buffer.from(first), Buffer.from(second));
    const memory = await loadMemoryCatalog(root);
    const before = await buildDynamicContext(root, {}, [memory.prompt()]);
    await writeFile(path.join(root, "AGENTS.md"), "PROJECT_SENTINEL_B");
    await writeFile(skillFile, "---\nname: cache-test\ndescription: SKILL_SENTINEL_B\n---\nUpdated instructions");
    await writeFile(path.join(root, "new-file.txt"), "changed workspace");
    await writeFile(path.join(root, ".sztu/context.md"), "MEMORY_SENTINEL_B");
    // A fake next day affects only the reminder, never the system prefix.
    const RealDate = Date;
    let third: string;
    let after: string;
    try {
      globalThis.Date = class extends RealDate { override toISOString() { return "2099-01-02T00:00:00.000Z"; } } as DateConstructor;
      third = await buildSystemPrompt(root);
      after = await buildDynamicContext(root, {}, [memory.prompt()]);
    } finally { globalThis.Date = RealDate; }
    assert.deepEqual(Buffer.from(third), Buffer.from(first));
    assert.doesNotMatch(first, /Date:|2099-01-02|Persistent memory|MEMORY_SENTINEL|PROJECT_SENTINEL|Current git status snapshot|# Available skills/);
    assert.notEqual(before, after);
    assert.match(after, /Date: 2099-01-02/);
    assert.match(after, /PROJECT_SENTINEL_B/);
    assert.match(after, /SKILL_SENTINEL_B/);
    assert.match(after, /MEMORY_SENTINEL_A/);
    assert.doesNotMatch(after, /MEMORY_SENTINEL_B/);
    assert.match(await memory.readLive("project", "MEMORY_SENTINEL_B"), /MEMORY_SENTINEL_B/);
    t.diagnostic(`system_bytes=${Buffer.byteLength(first)} sha256=${createHash("sha256").update(first).digest("hex")} equal_builds=3`);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("git snapshot changes only the reminder", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-cache-git-"));
  try {
    try { execFileSync("git", ["init", root]); }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code === "EPERM") { t.skip("sandbox denies git subprocess creation"); return; }
      throw error;
    }
    const first = await buildSystemPrompt(root);
    await writeFile(path.join(root, "new-file.txt"), "changed");
    assert.equal(await buildSystemPrompt(root), first);
    assert.doesNotMatch(first, /Current git status snapshot/);
    assert.match(await buildDynamicContext(root), /Current git status snapshot:[\s\S]*new-file.txt/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("goal reminder preserves multimodal content and appends a text block", () => {
  const content = [{ type: "text", text: "goal" }, { type: "image", source: { type: "base64", data: "test" } }];
  assert.deepEqual(appendGoalReminder(content, "reminder"), [...content, { type: "text", text: "reminder" }]);
  assert.equal(content.length, 2);
  assert.equal(appendGoalReminder("goal", "reminder"), "goal\n\nreminder");
});

test("RunManager requests are append-only across steps and resumed runs", { timeout: 30_000 }, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-cache-run-"));
  const requests: ChatMessage[][] = [];
  const previousData = process.env.SZTU_DATA_DIR;
  process.env.SZTU_DATA_DIR = path.join(root, ".sztu", "data");
  const events = new EventBus(path.join(root, ".sztu", "events.jsonl"));
  try {
    await mkdir(path.join(root, ".sztu"));
    await writeFile(path.join(root, ".sztu/context.md"), "FROZEN_MEMORY");
    const provider: ModelProvider = { async complete(messages) {
      requests.push(structuredClone(messages));
      if (requests.length === 1) {
        await writeFile(path.join(root, ".sztu/context.md"), "UPDATED_MEMORY");
        return { text: "Inspect", tool_calls: [{ id: "read-1", name: "list_dir", input: { path: "." } }], stop_reason: "tool_use" };
      }
      if (requests.length === 2) return { text: "Inspect again", tool_calls: [{ id: "read-2", name: "list_dir", input: { path: "." } }], stop_reason: "tool_use" };
      return { text: "done", tool_calls: [], stop_reason: "end_turn" };
    } };
    const manager = new RunManager(events, provider, root);
    const run = (goal: string, history: ChatMessage[]) => new Promise<ChatMessage[]>((resolve, reject) => {
      let completed: ChatMessage[] = [];
      const unsubscribe = events.subscribe((event) => {
        if (event.type === "run.finished") {
          unsubscribe();
          if (event.status === "success") resolve(completed);
          else reject(new Error(`run failed: ${event.reason}`));
        }
      });
      manager.start(goal, history, async (messages) => { completed = structuredClone(messages); }, root);
    });
    const history: ChatMessage[] = [{ role: "user", content: "old goal" }, { role: "assistant", content: "old answer" }];
    const completed = await run("inspect workspace", history);
    assert.equal(requests.length, 3);
    assert.deepEqual(requests[1]!.slice(0, requests[0]!.length), requests[0]);
    assert.deepEqual(requests[2]!.slice(0, requests[1]!.length), requests[1]);
    assert.deepEqual(requests[0]!.slice(1, 3), history);
    assert.match(String(requests[0]![3]!.content), /^inspect workspace\n\n<system-reminder>/);
    assert.match(String(requests[1]![3]!.content), /FROZEN_MEMORY/);
    assert.doesNotMatch(String(requests[1]![3]!.content), /UPDATED_MEMORY/);
    await run("continue", completed.filter((message) => message.role !== "system"));
    assert.deepEqual(requests[3]!.slice(0, requests[2]!.length), requests[2]);
    assert.match(String(requests[3]!.at(-1)!.content), /UPDATED_MEMORY/);
  } finally {
    if (previousData === undefined) delete process.env.SZTU_DATA_DIR; else process.env.SZTU_DATA_DIR = previousData;
    await events.flush();
    await rm(root, { recursive: true, force: true });
  }
});

function registry(names: string[]): ToolRegistry {
  const tools = new ToolRegistry();
  for (const name of names) tools.register({ name, description: name, schema: { type: "object" }, permission: "read_only", invoke: async () => ({ ok: true, output: "ok" }) });
  return tools;
}

test("working state sends only fresh evidence while full state remains available after compaction", () => {
  const state = new WorkingState("goal");
  state.absorb("old fact", "hard");
  const count = state.factCount;
  state.absorb("new fact", "hard");
  assert.match(state.render(count), /new fact/);
  assert.doesNotMatch(state.render(count), /old fact|Goal:/);
  assert.match(state.render(), /old fact/);
  assert.match(state.render(), /new fact/);
});

test("Anthropic caches conversation history across large tool batches within four breakpoints", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: any[] = [];
  globalThis.fetch = (async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }));
  }) as typeof fetch;
  const history: ChatMessage[] = [
    { role: "system", content: "stable" },
    { role: "user", content: [{ type: "text", text: "previous request boundary", cache_control: { type: "ephemeral" } }] },
    { role: "assistant", content: "tool batch", tool_calls: Array.from({ length: 30 }, (_, i) => ({ id: `c${i}`, name: "a", input: {} })) },
    ...Array.from({ length: 30 }, (_, i): ChatMessage => ({ role: "tool", tool_call_id: `c${i}`, content: "result" })),
  ];
  const frozen = structuredClone(history);
  try {
    for (const enabled of [true, true, false]) await new AnthropicMessagesProvider({ apiKey: "test", model: "test", cacheControl: enabled }).complete(history, registry(["a"]));
    assert.deepEqual(bodies[0], bodies[1]);
    const blocks = bodies[0].messages.flatMap((m: any) => m.content);
    assert.equal(blocks.filter((b: any) => b.cache_control).length, 2);
    assert.ok(blocks[0].cache_control, "previous request boundary stays reachable beyond 20 blocks");
    assert.ok(blocks.at(-1).cache_control, "new suffix is written for the following request");
    assert.equal((JSON.stringify(bodies[0]).match(/cache_control/g) ?? []).length, 4);
    assert.equal(JSON.stringify(bodies[2]).includes("cache_control"), false);
    assert.deepEqual(history, frozen);
  } finally { globalThis.fetch = originalFetch; }
});

test("DeepSeek native cache usage is counted once in streaming and non-streaming requests", async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const stream of [false, true]) {
      const usage = { prompt_tokens: 10_000, prompt_cache_hit_tokens: 9_900, prompt_cache_miss_tokens: 100, prompt_tokens_details: { cached_tokens: 9_900 }, completion_tokens: 5 };
      globalThis.fetch = (async () => new Response(stream
        ? `data: ${JSON.stringify({ choices: [{ delta: { content: "ok" }, finish_reason: "stop" }], usage })}\n\ndata: [DONE]\n\n`
        : JSON.stringify({ choices: [{ message: { content: "ok" } }], usage }), { headers: { "content-type": stream ? "text/event-stream" : "application/json" } })) as typeof fetch;
      const result = await new OpenAiCompatibleProvider({ model: "deepseek-chat", stream }).complete([{ role: "user", content: "hello" }], registry([]));
      assert.equal(result.usage?.input_tokens, 100);
      assert.equal(result.usage?.cache_read_input_tokens, 9_900);
      assert.equal(result.usage?.output_tokens, 5);
    }
  } finally { globalThis.fetch = originalFetch; }
});

test("history stays append-only below the compaction threshold with many tool results", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-cache-pressure-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  const requests: ChatMessage[][] = [];
  const tools = new ToolRegistry();
  tools.register({ name: "inspect", description: "inspect", schema: { type: "object" }, permission: "read_only", invoke: async () => ({ ok: true, output: "useful tool output\n".repeat(100) }) });
  const provider: ModelProvider = { async complete(messages) {
    requests.push(structuredClone(messages));
    return { text: "ok", tool_calls: requests.length < 8 ? [{ id: `c${requests.length}`, name: "inspect", input: {} }] : [], stop_reason: requests.length < 8 ? "tool_use" : "end_turn", usage: { input_tokens: 600, cache_read_input_tokens: 59_400, output_tokens: 1 } };
  } };
  try {
    const result = await new AgentLoop(provider, tools, { workspace: new Workspace(root) }, events, new PermissionManager(events), { contextWindow: 100_000, maxOutputTokens: 1000, offloadEnabled: false, compactThreshold: 0.7 }).run("cache-pressure", "inspect", 10, [{ role: "system", content: "stable" }]);
    assert.equal(result.compacted, false);
    assert.equal(requests.length, 8);
    for (let i = 1; i < requests.length; i++) assert.deepEqual(requests[i]!.slice(0, requests[i - 1]!.length), requests[i - 1]);
    const ratios = events.replay().filter((e) => e.type === "log.line" && e.source === "prompt-cache");
    assert.equal(ratios.length, 8);
    assert.ok(ratios.every((e) => e.type === "log.line" && JSON.parse(e.message).cache_read_ratio === 0.99));
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("99 percent cache target offloads a fresh tool tail before the next request", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-cache-target-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  const requests: ChatMessage[][] = [];
  const tools = new ToolRegistry();
  tools.register({ name: "inspect", description: "inspect", schema: { type: "object" }, permission: "read_only", invoke: async () => ({ ok: true, output: "x".repeat(1_000) }) });
  const provider: ModelProvider = { async complete(messages) {
    requests.push(structuredClone(messages));
    return requests.length === 1
      ? { text: "", tool_calls: [{ id: "c1", name: "inspect", input: {} }], stop_reason: "tool_use", usage: { input_tokens: 10_000, output_tokens: 1 } }
      : { text: "done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 100, cache_read_input_tokens: 10_000, output_tokens: 1 } };
  } };
  try {
    await new AgentLoop(provider, tools, { workspace: new Workspace(root) }, events, new PermissionManager(events), { contextWindow: 100_000, maxOutputTokens: 1_000, offloadMinChars: 2_000, offloadMinLines: 50, cacheHitTarget: 0.99 }).run("cache-target", "inspect", 3, [{ role: "system", content: "stable" }]);
    const toolResult = requests[1]!.find((message) => message.role === "tool");
    assert.match(String(toolResult?.content), /^\[上下文卸载:/);
    assert.ok(String(toolResult?.content).length < 600);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("providers keep sorted tools, fixed Anthropic boundaries and stable OpenAI cache keys", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: any[] = [];
  globalThis.fetch = (async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }], choices: [{ message: { content: "ok" } }], output_text: "ok" }), { headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  const messages: ChatMessage[] = [{ role: "system", content: "stable" }, { role: "system", content: "volatile tail" }, { role: "user", content: "goal" }];
  try {
    const anthropic = new AnthropicMessagesProvider({ apiKey: "test", model: "test", cacheControl: true });
    await anthropic.complete(messages, registry(["z", "a"]));
    await anthropic.complete([{ ...messages[0]! }, { role: "system", content: "changed tail" }, messages[2]!], registry(["a", "z"]));
    assert.deepEqual(bodies[0].tools, bodies[1].tools);
    assert.deepEqual(bodies[0].tools.map((tool: any) => tool.name), ["a", "z"]);
    assert.equal(bodies[0].tools[0].cache_control, undefined);
    assert.deepEqual(bodies[0].tools[1].cache_control, { type: "ephemeral" });
    assert.deepEqual(bodies[0].system[0], bodies[1].system[0]);
    assert.deepEqual(bodies[0].system[0].cache_control, { type: "ephemeral" });
    assert.equal(bodies[0].system[1].cache_control, undefined);
    for (const apiFormat of ["openai_chat_completions", "openai_responses"] as const) {
      const openai = new OpenAiCompatibleProvider({ model: "gpt-test", apiFormat, cacheControl: true });
      await openai.complete(messages, registry(["z", "a"]));
      await openai.complete([...messages, { role: "assistant", content: "ok" }, { role: "user", content: "next" }], registry(["a", "z"]));
      const [first, second] = bodies.slice(-2);
      assert.equal(first.prompt_cache_key, second.prompt_cache_key);
      assert.match(first.prompt_cache_key, /^[a-f0-9]{64}$/);
      assert.deepEqual(first.tools, second.tools);
      assert.equal(JSON.stringify(first).includes("cache_control"), false);
      const key = apiFormat === "openai_responses" ? "input" : "messages";
      assert.deepEqual(second[key].slice(0, first[key].length), first[key]);
    }
    await new OpenAiCompatibleProvider({ baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat", cacheControl: true }).complete(messages, registry(["z", "a"]));
    assert.equal(bodies.at(-1).prompt_cache_key, undefined);
    assert.equal(JSON.stringify(bodies.at(-1)).includes("cache_control"), false);
  } finally { globalThis.fetch = originalFetch; }
});
