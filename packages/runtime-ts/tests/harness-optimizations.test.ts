import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import type { ChatMessage, ModelInvocation, ModelProvider } from "../src/agent-loop.js";
import { bufferedEmitter } from "../src/agent-loop.js";
import { ToolRegistry } from "../src/tools.js";
import { AnthropicMessagesProvider } from "../src/providers/anthropic.js";
import { ConfigurableProvider } from "../src/providers/configurable.js";
import { detectModelCapabilities, promptCacheMechanism } from "../src/providers/model-capabilities.js";
import { SettingsStore } from "../src/settings.js";
import { buildSystemPrompt } from "../src/prompt-loader.js";

function registry(names: string[]): ToolRegistry {
  const tools = new ToolRegistry();
  for (const name of names) tools.register({ name, description: name, schema: { type: "object" }, permission: "read_only", invoke: async () => ({ ok: true, output: "ok" }) });
  return tools;
}

test("rolling breakpoint keeps the previous request's suffix reachable after steering-style user injection", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: any[] = [];
  globalThis.fetch = (async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }));
  }) as typeof fetch;
  try {
    const provider = new AnthropicMessagesProvider({ apiKey: "test", model: "test", cacheControl: true });
    const base: ChatMessage[] = [
      { role: "system", content: "stable" },
      { role: "user", content: "goal" },
      { role: "assistant", content: "plan", tool_calls: [{ id: "c1", name: "read_file", input: {} }] },
      { role: "tool", tool_call_id: "c1", content: "tool result payload" },
    ];
    await provider.complete(structuredClone(base), registry(["read_file"]));
    // 模拟 steering/干预/错误回注：在旧 assistant 之后追加 user 消息（而非 append-only 的
    // assistant→tool 轮次）。推导边界会漂移到新消息上，滚动锚点必须仍指向旧请求末块。
    await provider.complete([...structuredClone(base), { role: "user", content: "change direction" }], registry(["read_file"]));
    const blocks = bodies[1].messages.flatMap((m: any) => m.content);
    const marked = blocks.filter((b: any) => b.cache_control);
    assert.equal(marked.length, 2, "exactly two conversation anchors are marked");
    assert.deepEqual(marked[0], { type: "tool_result", tool_use_id: "c1", content: "tool result payload", cache_control: { type: "ephemeral" } }, "previous request's last block stays marked");
    assert.deepEqual(marked[1], { type: "text", text: "change direction", cache_control: { type: "ephemeral" } }, "new suffix is marked for the following request");
    assert.equal(blocks.find((b: any) => b.type === "text" && b.text === "goal")?.cache_control, undefined, "derived boundary no longer steals the read anchor");
  } finally { globalThis.fetch = originalFetch; }
});

test("append-only turns keep the derived boundary equivalent to the rolling anchor", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: any[] = [];
  globalThis.fetch = (async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ content: [{ type: "text", text: "ok" }] }));
  }) as typeof fetch;
  try {
    const provider = new AnthropicMessagesProvider({ apiKey: "test", model: "test", cacheControl: true });
    const first: ChatMessage[] = [
      { role: "system", content: "stable" },
      { role: "user", content: "goal" },
      { role: "assistant", content: "plan", tool_calls: [{ id: "c1", name: "read_file", input: {} }] },
      { role: "tool", tool_call_id: "c1", content: "result-1" },
    ];
    await provider.complete(structuredClone(first), registry(["read_file"]));
    const second: ChatMessage[] = [...structuredClone(first), { role: "assistant", content: "next", tool_calls: [{ id: "c2", name: "read_file", input: {} }] }, { role: "tool", tool_call_id: "c2", content: "result-2" }];
    await provider.complete(second, registry(["read_file"]));
    const blocks = bodies[1].messages.flatMap((m: any) => m.content);
    const marked = blocks.filter((b: any) => b.cache_control);
    assert.equal(marked.length, 2);
    assert.equal(marked[0].type, "tool_result");
    assert.equal(marked[0].content, "result-1", "anchor stays on the previous request's suffix");
    assert.equal(marked[1].content, "result-2");
  } finally { globalThis.fetch = originalFetch; }
});

test("adaptive token batching coalesces dense streams and stays responsive on sparse streams", async () => {
  const dense: string[] = [];
  {
    const batcher = bufferedEmitter((text) => dense.push(text));
    for (let index = 0; index < 60; index += 1) batcher.push(`t${index};`);
    await new Promise((resolve) => setTimeout(resolve, 220));
  }
  assert.ok(dense.length <= 8, `dense stream should coalesce into few frames, got ${dense.length}`);
  assert.equal(dense.join(""), Array.from({ length: 60 }, (_, index) => `t${index};`).join(""), "no tokens are lost");

  const sparse: string[] = [];
  {
    const batcher = bufferedEmitter((text) => sparse.push(text));
    for (let index = 0; index < 3; index += 1) {
      batcher.push(`s${index}`);
      await new Promise((resolve) => setTimeout(resolve, 260));
    }
    await new Promise((resolve) => setTimeout(resolve, 220));
  }
  assert.equal(sparse.join(""), "s0s1s2");
  assert.ok(sparse.length >= 2, "sparse stream should not merge distant tokens into long-held frames");

  const burst: string[] = [];
  {
    const batcher = bufferedEmitter((text) => burst.push(text));
    batcher.push("x".repeat(4096));
    assert.equal(burst.length, 1, "size threshold flushes immediately without waiting for the timer");
    batcher.push("tail");
    batcher.flush();
    assert.deepEqual(burst, ["x".repeat(4096), "tail"]);
  }
});

test("model capabilities map families to cache mechanisms and reasoning styles", () => {
  assert.equal(promptCacheMechanism("anthropic_messages", "https://open.bigmodel.cn/api/anthropic"), "anthropic_cache_control");
  assert.equal(promptCacheMechanism("openai_chat_completions", "https://api.openai.com/v1"), "openai_prompt_cache_key");
  assert.equal(promptCacheMechanism("openai_responses", "https://api.openai.com/v1"), "openai_prompt_cache_key");
  assert.equal(promptCacheMechanism("openai_chat_completions", "https://api.deepseek.com/v1"), "server_auto_prefix");
  assert.equal(promptCacheMechanism("openai_chat_completions", undefined), "openai_prompt_cache_key", "default endpoint is official OpenAI");

  const deepseek = detectModelCapabilities("deepseek-reasoner", "openai_chat_completions", "https://api.deepseek.com/v1");
  assert.equal(deepseek.family, "deepseek");
  assert.equal(deepseek.cache, "server_auto_prefix");
  assert.equal(deepseek.suppressSampling, true, "deepseek-reasoner rejects sampling params");

  const gpt = detectModelCapabilities("gpt-4o", "openai_chat_completions", "https://api.openai.com/v1");
  assert.equal(gpt.suppressSampling, false);
  assert.equal(gpt.cache, "openai_prompt_cache_key");

  const oSeries = detectModelCapabilities("o3-mini", "openai_chat_completions", "https://api.openai.com/v1");
  assert.equal(oSeries.suppressSampling, true);
  assert.equal(oSeries.reasoning, "openai_effort");

  const claude = detectModelCapabilities("claude-sonnet-4-5", "anthropic_messages");
  assert.equal(claude.reasoning, "anthropic_thinking");
  assert.equal(claude.cache, "anthropic_cache_control");

  const glm = detectModelCapabilities("glm-4.6", "anthropic_messages", "https://open.bigmodel.cn/api/anthropic");
  assert.equal(glm.family, "glm");
  assert.equal(glm.cache, "anthropic_cache_control", "GLM's anthropic-compatible endpoint honors cache_control");
});

test("system prompt memo returns byte-identical output across runs and tool orders", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-prompt-memo-"));
  try {
    const first = await buildSystemPrompt(root, "coder", { toolNames: ["read_file", "bash"] });
    // 相同集合不同顺序（MCP 异步注册）+ 不同 workspaceRoot：静态层字节不受影响
    const second = await buildSystemPrompt(path.join(root, "other"), "coder", { toolNames: ["bash", "read_file"] });
    assert.equal(first, second);
    const third = await buildSystemPrompt(root, "coder", { toolNames: ["read_file"] });
    assert.notEqual(third, first, "a different tool set changes the tool-usage policy section");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("auxiliary model routes compaction calls and falls back to the primary provider", async () => {
  const originalFetch = globalThis.fetch;
  const settingsDir = await mkdtemp(path.join(os.tmpdir(), "sztu-aux-route-"));
  const originalKey = process.env.OPENAI_API_KEY;
  process.env.OPENAI_API_KEY = "test";
  try {
    const requests: string[] = [];
    globalThis.fetch = (async (input) => {
      const url = String(input);
      requests.push(url);
      if (url.includes("aux")) return new Response("overloaded", { status: 503, headers: { "retry-after": "0" } });
      return Response.json({ choices: [{ message: { content: "ok" }, finish_reason: "stop" }], usage: {} });
    }) as typeof fetch;
    const settings = new SettingsStore(path.join(settingsDir, "runtime-settings.json"));
    await settings.update({ model: "gpt-main", base_url: "https://api.openai.com/v1", max_retries: 2, timeout_s: 1, aux_model: "fast-aux", aux_base_url: "https://aux.example/v1" });
    const provider: ModelProvider = new ConfigurableProvider(settings);
    const compaction: ModelInvocation = { runId: "r", step: 1, purpose: "compaction" };

    const result = await provider.complete([{ role: "user", content: "summarize" }], new ToolRegistry(), undefined, undefined, compaction);
    assert.equal(result.text, "ok");
    assert.match(requests[0], /aux\.example/, "compaction routes to the auxiliary model first");
    assert.match(requests[1], /api\.openai\.com/, "aux failure falls back to the primary model");

    requests.length = 0;
    await provider.complete([{ role: "user", content: "main task" }], new ToolRegistry());
    assert.equal(requests.length, 1);
    assert.match(requests[0], /api\.openai\.com/, "agent traffic always hits the primary model");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.OPENAI_API_KEY; else process.env.OPENAI_API_KEY = originalKey;
    await rm(settingsDir, { recursive: true, force: true });
  }
});

test("provider instance cache reuses instances until settings change", async () => {
  const originalFetch = globalThis.fetch;
  const settingsDir = await mkdtemp(path.join(os.tmpdir(), "sztu-provider-cache-"));
  const originalKey = process.env.OPENAI_API_KEY;
  process.env.OPENAI_API_KEY = "test";
  try {
    globalThis.fetch = (async () => Response.json({ choices: [{ message: { content: "ok" }, finish_reason: "stop" }], usage: {} })) as typeof fetch;
    const settings = new SettingsStore(path.join(settingsDir, "runtime-settings.json"));
    await settings.update({ model: "gpt-a", base_url: "https://api.openai.com/v1", timeout_s: 1 });
    const provider = new ConfigurableProvider(settings);
    await provider.complete([{ role: "user", content: "1" }], new ToolRegistry());
    // 模型热切换：settings 变更后下一次调用重建 provider 并打到新模型
    const bodies: string[] = [];
    globalThis.fetch = (async (_input, init) => {
      bodies.push(String(init?.body));
      return Response.json({ choices: [{ message: { content: "ok" }, finish_reason: "stop" }], usage: {} });
    }) as typeof fetch;
    await settings.update({ model: "gpt-b" });
    await provider.complete([{ role: "user", content: "2" }], new ToolRegistry());
    assert.match(bodies[0], /"model":"gpt-b"/, "hot model switch rebuilds the cached provider");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.OPENAI_API_KEY; else process.env.OPENAI_API_KEY = originalKey;
    await rm(settingsDir, { recursive: true, force: true });
  }
});

// --- 缓存命中率端到端测量 ----------------------------------------------------
//
// Anthropic 前缀缓存的命中单位是「语义块」而非 JSON 字节，并且 system/tools/messages
// 三段是独立缓存、独立计算 cache_read 的。每段内部按有序块序列做最长前缀匹配：
// 从该段开头起，到该段最后一个 cache_control 断点之间的所有块，必须与上一次请求在相同
// 位置出现、内容完全相同才会命中 cache_read。
//
// 测量方法：
//   1) 将请求体拆为 system/tools/messages 三个有序块序列，剥离 cache_control 注解；
//   2) 对每段分别做相邻两轮的逐块深度相等 LCP，得到该段命中块数；
//   3) 用「字符数/4」粗略估算每块 token；三段命中之和 / 三段总 token = 命中率。
// 首轮为冷启动（无任何缓存可命中），从第二轮（i=1）起计入。

type LogicalBlock = { role?: string; payload: unknown };

function stripCacheControl(block: any): any {
  if (block == null || typeof block !== "object") return block;
  if (Array.isArray(block)) return block.map(stripCacheControl);
  const out: any = {};
  for (const [key, value] of Object.entries(block)) {
    if (key === "cache_control") continue;
    out[key] = stripCacheControl(value);
  }
  return out;
}

function blocksOf(section: any[] | undefined, role?: string): LogicalBlock[] {
  if (!section) return [];
  return section.map((b) => ({ role, payload: stripCacheControl(b) }));
}

function splitBody(body: any): { system: LogicalBlock[]; tools: LogicalBlock[]; messages: LogicalBlock[] } {
  return {
    system: blocksOf(body.system),
    tools: blocksOf(body.tools),
    messages: (body.messages ?? []).flatMap((m: any) => blocksOf(m.content, m.role)),
  };
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return a === b;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) if (!deepEqual(a[i], b[i])) return false;
    return true;
  }
  if (typeof a === "object" && typeof b === "object") {
    const ak = Object.keys(a as object);
    const bk = Object.keys(b as object);
    if (ak.length !== bk.length) return false;
    // block payload 由我们自己构造，key 顺序固定（V8 按插入顺序），无需排序。
    for (let i = 0; i < ak.length; i += 1) if (ak[i] !== bk[i]) return false;
    for (const key of ak) if (!deepEqual((a as any)[key], (b as any)[key])) return false;
    return true;
  }
  return false;
}

function blockTokenEstimate(block: LogicalBlock): number {
  // 粗略 token 估计：1 token ≈ 4 字符；role 固定开销约 1 token。
  return Math.max(1, Math.ceil(JSON.stringify(block.payload).length / 4)) + (block.role ? 1 : 0);
}

function sectionOverlap(prev: LogicalBlock[], cur: LogicalBlock[]): { hitTokens: number; totalTokens: number; matched: number; total: number } {
  let n = 0;
  while (n < prev.length && n < cur.length && deepEqual(prev[n]!.payload, cur[n]!.payload)) n += 1;
  const hitTokens = cur.slice(0, n).reduce((s, b) => s + blockTokenEstimate(b), 0);
  const totalTokens = cur.reduce((s, b) => s + blockTokenEstimate(b), 0);
  return { hitTokens, totalTokens, matched: n, total: cur.length };
}

function cacheHitRatio(prev: any, cur: any): { ratio: number; hit: number; total: number; details: Record<string, { hit: number; total: number; matched: number; totalBlocks: number }> } {
  const p = splitBody(prev);
  const c = splitBody(cur);
  const sections = {
    system: sectionOverlap(p.system, c.system),
    tools: sectionOverlap(p.tools, c.tools),
    messages: sectionOverlap(p.messages, c.messages),
  };
  let hit = 0, total = 0;
  const details: any = {};
  for (const [name, s] of Object.entries(sections)) {
    hit += s.hitTokens;
    total += s.totalTokens;
    details[name] = { hit: s.hitTokens, total: s.totalTokens, matched: s.matched, totalBlocks: s.total };
  }
  return { ratio: total === 0 ? 1 : hit / total, hit, total, details };
}

type MockTurn =
  | { kind: "tool"; name: string; output: string; thinking?: string }
  | { kind: "text"; text: string; thinking?: string };

function sequentialMockProvider(turns: MockTurn[], opts: { stream?: boolean } = {}): { provider: AnthropicMessagesProvider; bodies: any[]; restore: () => void } {
  const bodies: any[] = [];
  let index = 0;
  const fetchMock = (async (_url: any, init: any) => {
    const body = JSON.parse(String(init?.body));
    bodies.push(body);
    const turn = turns[index] ?? { kind: "text", text: "[done]" };
    index += 1;
    const callId = `call_${index}`;
    if (opts.stream) {
      // SSE 流：message_start + content_block(s) + delta(s) + message_delta
      const encoder = new TextEncoder();
      const chunks: string[] = [];
      chunks.push(`event: message_start\ndata: ${JSON.stringify({ type: "message_start", message: { id: "m", type: "message", role: "assistant", model: "test", stop_sequence: null, usage: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }, content: [], stop_reason: null } })}\n\n`);
      let blockIdx = 0;
      if (turn.thinking) {
        chunks.push(`event: content_block_start\ndata: ${JSON.stringify({ type: "content_block_start", index: blockIdx, content_block: { type: "thinking", thinking: "" } })}\n\n`);
        chunks.push(`event: content_block_delta\ndata: ${JSON.stringify({ type: "content_block_delta", index: blockIdx, delta: { type: "thinking_delta", thinking: turn.thinking } })}\n\n`);
        chunks.push(`event: content_block_delta\ndata: ${JSON.stringify({ type: "content_block_delta", index: blockIdx, delta: { type: "signature_delta", signature: "sig" } })}\n\n`);
        blockIdx += 1;
      }
      const text = turn.kind === "text" ? turn.text : `calling ${turn.name}`;
      if (text) {
        chunks.push(`event: content_block_start\ndata: ${JSON.stringify({ type: "content_block_start", index: blockIdx, content_block: { type: "text", text: "" } })}\n\n`);
        chunks.push(`event: content_block_delta\ndata: ${JSON.stringify({ type: "content_block_delta", index: blockIdx, delta: { type: "text_delta", text } })}\n\n`);
        blockIdx += 1;
      }
      if (turn.kind === "tool") {
        const input = { path: "f.txt" };
        chunks.push(`event: content_block_start\ndata: ${JSON.stringify({ type: "content_block_start", index: blockIdx, content_block: { type: "tool_use", id: callId, name: turn.name, input: {} } })}\n\n`);
        chunks.push(`event: content_block_delta\ndata: ${JSON.stringify({ type: "content_block_delta", index: blockIdx, delta: { type: "input_json_delta", partial_json: JSON.stringify(input) } })}\n\n`);
        blockIdx += 1;
      }
      const stopReason = turn.kind === "tool" ? "tool_use" : "end_turn";
      chunks.push(`event: message_delta\ndata: ${JSON.stringify({ type: "message_delta", delta: { stop_reason: stopReason, stop_sequence: null }, usage: { output_tokens: 10 } })}\n\n`);
      chunks.push(`event: message_stop\ndata: ${JSON.stringify({ type: "message_stop" })}\n\n`);
      const stream = new ReadableStream({
        start(controller) { for (const c of chunks) controller.enqueue(encoder.encode(c)); controller.close(); },
      });
      return new Response(stream, { headers: { "content-type": "text/event-stream" } });
    }
    const content: any[] = [];
    if (turn.thinking) content.push({ type: "thinking", thinking: turn.thinking, signature: "sig" });
    if (turn.kind === "text") {
      content.push({ type: "text", text: turn.text });
    } else {
      content.push({ type: "text", text: `calling ${turn.name}` });
      content.push({ type: "tool_use", id: callId, name: turn.name, input: { path: "f.txt" } });
    }
    return Response.json({
      content,
      stop_reason: turn.kind === "tool" ? "tool_use" : "end_turn",
      usage: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
    });
  }) as typeof fetch;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = fetchMock;
  const provider = new AnthropicMessagesProvider({ apiKey: "test", model: "claude-test", cacheControl: true, reasoningEffort: "high" });
  return {
    provider,
    bodies,
    restore: () => { globalThis.fetch = originalFetch; },
  };
}

function runTurn(history: ChatMessage[], turn: MockTurn, step: number): void {
  const callId = `call_${step + 1}`;
  const assistantContent: any[] = [];
  if (turn.thinking) assistantContent.push({ type: "thinking", thinking: turn.thinking, signature: "sig" });
  const text = turn.kind === "text" ? turn.text : `calling ${turn.name}`;
  if (text) assistantContent.push({ type: "text", text });
  if (turn.kind === "tool") {
    history.push({ role: "assistant", content: assistantContent as any, tool_calls: [{ id: callId, name: turn.name, input: { path: "f.txt" } }] });
    history.push({ role: "tool", tool_call_id: callId, content: turn.output });
  } else {
    history.push({ role: "assistant", content: assistantContent as any });
  }
}

// 真实规模的静态前缀：
//   - system prompt：典型 coding agent 的系统提示词通常在 2000-4000 token，
//     涵盖角色、工具策略、代码风格、输出规范等；
//   - tools schema：注册 6 个常用工具（read_file/write_file/bash/list_dir/edit_file/grep），
//     每个工具含名称/描述/JSON Schema，合计约 1500-2500 token；
//   - 单轮新增（assistant 输出 + tool_result）通常 100-400 token。
// 在这样的比例下，稳态（第 2 轮起）每轮前缀/新增 ≥ 98%。
const SYS = "You are SztuCode, an expert software engineer agent operating inside the user's IDE on a local workspace. "
  + "Your job is to help the user with coding tasks: debugging, implementing features, refactoring, explaining code, "
  + "running tests, and making incremental, minimal edits. Always prefer reading the existing code before proposing changes. "
  + "Follow the repository's existing conventions—import style, error handling, naming, type annotations, file layout. "
  + "Do not introduce new dependencies unless the user explicitly asks. When you make a change, run the relevant tests "
  + "to verify nothing is broken; if tests fail, iterate until they pass. "
  + "Tool usage protocol: "
  + "1. Start by exploring the project structure (list_dir, read_file on key entry points) to build a mental model. "
  + "2. Before writing code, articulate a short plan in scratchpad. "
  + "3. Prefer read-only tools (grep, read_file, list_dir) before mutating tools (write_file, edit_file, bash). "
  + "4. When running bash commands, prefer non-destructive reads; never run rm -rf, force-push, or drop tables without "
  + "explicit user confirmation. "
  + "5. Cite exact file paths and line ranges when referencing code. "
  + "6. When a tool returns an error, surface the error verbatim and propose a diagnosis before retrying. "
  + "7. Keep edits scoped to the user's request; do not opportunistically refactor unrelated code. "
  + "Output style: be concise. Present code changes as diffs or edited snippets with surrounding context. When done, "
  + "give a brief summary of what changed and why, plus any commands the user should run to verify. "
  + "If the requirements are ambiguous, ask one focused question at a time rather than guessing. "
  + "When the user asks you to fix a bug, first reproduce the failing scenario, then identify the root "
  + "cause (not just the symptom), then apply the minimal fix, and finally verify with a test. "
  + "When the user asks for a new feature, write tests first where practical, then implement, then run tests. "
  + "When editing code, preserve existing comments and JSDoc unless they become inaccurate. "
  + "When adding imports, follow the existing import grouping convention (external → internal → relative). "
  + "Prefer composition over inheritance; prefer pure functions where possible; avoid global mutable state. "
  + "When creating new files, mirror the naming and barrel-export conventions of neighboring files. "
  + "Error handling: never silently swallow errors. Log context or rethrow with a wrapped message. "
  + "Security: never log API keys, tokens, or credentials. Never execute commands that exfiltrate data. "
  + "When the user asks for performance work, measure before optimizing and cite the measurement. "
  + "When presenting results, lead with the answer, then show evidence (file paths, commands run, test output). "
  + "x".repeat(16000);

const TOOL_DEFS: Array<{ name: string; description: string; schema: any; permission?: "read_only" | "write" }> = [
  {
    name: "read_file",
    description: "Read the contents of a file at the given absolute path, optionally within a line range. Returns UTF-8 text. "
      + "Use this to inspect source code, configuration, package manifests, and documentation before planning edits. "
      + "Prefer setting offset/limit for large files to keep responses small. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file. Must be inside the workspace root." },
        offset: { type: "integer", minimum: 0, description: "0-based line offset to start reading from (default 0)." },
        limit: { type: "integer", minimum: 1, maximum: 2000, description: "Maximum number of lines to return (default 400)." },
      },
      required: ["path"],
    },
    permission: "read_only",
  },
  {
    name: "write_file",
    description: "Overwrite the file at the given absolute path with the provided contents. Creates parent directories if needed. "
      + "Use this to create new files or fully replace existing files; for small targeted edits prefer edit_file. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file." },
        content: { type: "string", description: "Complete file contents to write (UTF-8)." },
      },
      required: ["path", "content"],
    },
    permission: "write",
  },
  {
    name: "bash",
    description: "Execute a shell command in the workspace root and return stdout+stderr. Use this to run tests, builds, "
      + "package managers, git operations, and other CLI tooling. Long-running commands should be avoided; prefer commands "
      + "that complete within 30 seconds. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        command: { type: "string", description: "The shell command to execute." },
        timeout_ms: { type: "integer", minimum: 1000, maximum: 120000, description: "Timeout in milliseconds (default 30000)." },
      },
      required: ["command"],
    },
    permission: "write",
  },
  {
    name: "list_dir",
    description: "List the entries in a directory, returning file names, subdirectory names, and their sizes. Use this to "
      + "explore project structure before reading individual files. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the directory (workspace root by default)." },
      },
      required: ["path"],
    },
    permission: "read_only",
  },
  {
    name: "edit_file",
    description: "Apply a targeted text replacement in a file, replacing old_string with new_string. The replacement is "
      + "exact-match; old_string must appear exactly once in the file. Use this for small, scoped edits. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file." },
        old_string: { type: "string", description: "Exact text to find and replace." },
        new_string: { type: "string", description: "Replacement text." },
      },
      required: ["path", "old_string", "new_string"],
    },
    permission: "write",
  },
  {
    name: "grep",
    description: "Search files in the workspace for a regex pattern. Returns matching file paths with line numbers and snippets. "
      + "Use this to locate symbol definitions, usages, configuration keys, and TODOs across the codebase. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Regular expression pattern to search for." },
        path: { type: "string", description: "Directory or file to limit the search to (default workspace root)." },
        glob: { type: "string", description: "Optional glob pattern to filter files (e.g. '*.ts')." },
      },
      required: ["pattern"],
    },
    permission: "read_only",
  },
  {
    name: "glob",
    description: "Find files matching a glob pattern relative to the workspace root. Returns a list of absolute paths. "
      + "Use this to discover files by name pattern (e.g. '*.test.ts', '**/package.json') before reading them. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Glob pattern, supports ** for recursive matching." },
      },
      required: ["pattern"],
    },
    permission: "read_only",
  },
  {
    name: "web_fetch",
    description: "Fetch a URL and return its contents as markdown or text. Use this for looking up documentation, "
      + "package READMEs, or public API references. Respects rate limits; do not call in tight loops. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        url: { type: "string", description: "The URL to fetch (http/https)." },
        format: { type: "string", enum: ["markdown", "text", "html"], description: "Desired output format." },
      },
      required: ["url"],
    },
    permission: "read_only",
  },
  {
    name: "ask_user",
    description: "Ask the user a clarifying question. Use this only when requirements are genuinely ambiguous and "
      + "cannot be resolved by reading the code. Keep questions concise and offer concrete choices where possible. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        question: { type: "string", description: "The question to present to the user." },
        options: { type: "array", items: { type: "string" }, description: "Optional list of answer choices." },
      },
      required: ["question"],
    },
    permission: "read_only",
  },
  {
    name: "todo_write",
    description: "Maintain an in-session todo list so the user can see progress. Call this when starting a multi-step task, "
      + "and update it as steps complete. Keep entries short and action-oriented. "
      + "y".repeat(300),
    schema: {
      type: "object",
      properties: {
        todos: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              content: { type: "string" },
              status: { type: "string", enum: ["pending", "in_progress", "completed"] },
              priority: { type: "string", enum: ["high", "medium", "low"] },
            },
            required: ["id", "content", "status", "priority"],
          },
        },
      },
      required: ["todos"],
    },
    permission: "read_only",
  },
];

function realRegistry(): ToolRegistry {
  const tools = new ToolRegistry();
  for (const def of TOOL_DEFS) {
    tools.register({
      name: def.name,
      description: def.description,
      schema: def.schema,
      permission: (def.permission as any) ?? "read_only",
      invoke: async () => ({ ok: true, output: "ok" }),
    });
  }
  return tools;
}

test("multi-turn tool loop (non-streaming) achieves ≥98% prefix cache hit ratio across a ten-turn agent run", async () => {
  const tools = realRegistry();
  // 10 轮工具调用：真实 coding agent 一次任务通常 10-30 个工具调用，前缀累积到几千 token
  // 后，单轮新增占比自然 < 2%。
  const fileNames = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];
  const turns: MockTurn[] = [
    ...fileNames.map((name) => ({ kind: "tool" as const, name: "read_file", output: `${name} contents\n` + "x".repeat(180) })),
    { kind: "text", text: "final answer: summary of all files.\n" + "f".repeat(200) },
  ];
  const { provider, bodies, restore } = sequentialMockProvider(turns);
  try {
    const history: ChatMessage[] = [
      { role: "system", content: SYS },
      { role: "user", content: "please read the files under src/ and summarize them. " + "g".repeat(300) },
    ];
    for (let step = 0; step < turns.length; step += 1) {
      await provider.complete(structuredClone(history), tools);
      runTurn(history, turns[step]!, step);
    }
    assert.equal(bodies.length, turns.length);
    // 前 2 轮为预热（首轮冷启动、第二轮首次热轮）；从第 3 轮（i=2）起进入稳态，
    // 每轮必须 ≥98%。
    for (let i = 2; i < bodies.length; i += 1) {
      const r = cacheHitRatio(bodies[i - 1], bodies[i]);
      assert.ok(r.ratio >= 0.98, `turn ${i} ratio ${r.ratio.toFixed(4)} < 0.98 — details: ${JSON.stringify(r.details)}`);
    }
  } finally { restore(); }
});

test("multi-turn tool loop with streaming + thinking blocks achieves ≥98% prefix cache hit ratio", async () => {
  const tools = realRegistry();
  const turns: MockTurn[] = [
    { kind: "tool", name: "read_file", output: "file-a\n" + "a".repeat(200), thinking: "The user wants a summary. I'll start by reading file-a. " + "ta".repeat(10) },
    { kind: "tool", name: "read_file", output: "file-b\n" + "b".repeat(200), thinking: "Got file-a; next I should read file-b. " + "tb".repeat(10) },
    { kind: "tool", name: "read_file", output: "file-c\n" + "c".repeat(200), thinking: "Now file-c; still building context. " + "tc".repeat(10) },
    { kind: "text", text: "final answer\n" + "f".repeat(300), thinking: "I have enough to synthesize now. " + "tf".repeat(10) },
  ];
  const { provider, bodies, restore } = sequentialMockProvider(turns, { stream: true });
  try {
    const history: ChatMessage[] = [
      { role: "system", content: SYS },
      { role: "user", content: "please read files and summarize. " + "g".repeat(300) },
    ];
    for (let step = 0; step < turns.length; step += 1) {
      const res = await provider.complete(structuredClone(history), tools, undefined, () => {}, undefined, () => {});
      runTurn(history, { ...turns[step]!, thinking: (res.thinking_blocks?.[0]?.thinking as string) || turns[step]!.thinking }, step);
    }
    assert.equal(bodies.length, turns.length);
    // 从第 3 轮（i=2）起进入稳态；第 4 轮（i=3）是 final，仍需验证
    for (let i = 2; i < bodies.length; i += 1) {
      const r = cacheHitRatio(bodies[i - 1], bodies[i]);
      assert.ok(r.ratio >= 0.98, `stream turn ${i} ratio ${r.ratio.toFixed(4)} < 0.98 — details: ${JSON.stringify(r.details)}`);
    }
  } finally { restore(); }
});

test("prefix cache survives steering-style user injection between tool turns", async () => {
  const tools = realRegistry();
  const turns: MockTurn[] = [
    { kind: "tool", name: "read_file", output: "file-a\n" + "a".repeat(200) },
    { kind: "tool", name: "read_file", output: "file-b\n" + "b".repeat(200) },
    { kind: "tool", name: "read_file", output: "after-steering\n" + "s".repeat(200) },
    { kind: "text", text: "final after steering\n" + "f".repeat(300) },
  ];
  const { provider, bodies, restore } = sequentialMockProvider(turns);
  try {
    const history: ChatMessage[] = [
      { role: "system", content: SYS },
      { role: "user", content: "initial goal: read files. " + "g".repeat(200) },
    ];
    for (let step = 0; step < turns.length; step += 1) {
      await provider.complete(structuredClone(history), tools);
      const turn = turns[step]!;
      const callId = `call_${step + 1}`;
      if (step === 1) {
        history.push({ role: "assistant", content: `calling ${turn.name}`, tool_calls: [{ id: callId, name: turn.name, input: { path: "f.txt" } }] });
        history.push({ role: "tool", tool_call_id: callId, content: turn.output });
        history.push({ role: "user", content: "steering: also check the file after steering, and pay attention to error handling. " + "h".repeat(200) });
      } else if (turn.kind === "tool") {
        history.push({ role: "assistant", content: `calling ${turn.name}`, tool_calls: [{ id: callId, name: turn.name, input: { path: "f.txt" } }] });
        history.push({ role: "tool", tool_call_id: callId, content: turn.output });
      } else {
        history.push({ role: "assistant", content: turn.text });
      }
    }
    assert.equal(bodies.length, turns.length);
    // steering 轮（BODY1→BODY2）：滚动锚点应让 system+tools+goal+前 2 轮 assistant+tool_result 命中，
    // 新内容只有 steering 消息和后续新块，整体 ≥90%。
    const sr = cacheHitRatio(bodies[1], bodies[2]);
    assert.ok(sr.ratio >= 0.90, `steering turn ratio ${sr.ratio.toFixed(4)} < 0.90 — details: ${JSON.stringify(sr.details)}`);
    // steering 之后：append-only 恢复稳态 ≥98%
    const ar = cacheHitRatio(bodies[2], bodies[3]);
    assert.ok(ar.ratio >= 0.98, `post-steering turn ratio ${ar.ratio.toFixed(4)} < 0.98 — details: ${JSON.stringify(ar.details)}`);
  } finally { restore(); }
});
