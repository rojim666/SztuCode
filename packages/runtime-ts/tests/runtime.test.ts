import assert from "node:assert/strict";
import test from "node:test";
import { validateWorkflowGraph, readyTaskIds } from "@sztucode/protocol/workflow";
import { Workspace, WorkspaceBoundaryError } from "../src/workspace.js";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { buildSystemPrompt, loadAgentProfile } from "../src/prompt-loader.js";
import { parseRolePayload, scopedWorkflowPermissions, SubagentManager } from "../src/subagent.js";
import { PermissionManager } from "../src/permissions.js";
import { EventBus } from "../src/event-bus.js";
import type { ModelProvider } from "../src/agent-loop.js";
import { createWorkspaceTools } from "../src/tools.js";
import { WorkflowOrchestrator } from "../src/workflow.js";
import type { HandoffArtifact, WorkflowTask } from "@sztucode/protocol";
import { normalizeWorkflowPath, workflowPathIsAllowed } from "../src/workflow-scope.js";
import { AgentLoop } from "../src/agent-loop.js";
import { createMemoryTools, MemoryCatalog } from "../src/memory.js";
import { SessionStore } from "../src/session-store.js";
import { RunManager } from "../src/run-manager.js";
import { StuckLoopTracker, stuckSignature } from "../src/stuck-tracker.js";
import { runtimePromptEntries } from "../src/prompt-harness.js";

const task = (id: string, dependencies: string[] = []) => ({ id, title: id, description: id, owner: "coder" as const, dependencies, completion_criteria: ["done"], allowed_paths: ["src"], depth: 0, token_budget: 0, time_budget_s: 0, max_retries: null });
const artifact = (workflowTask: WorkflowTask, status: HandoffArtifact["status"] = "succeeded", tokens = 0): HandoffArtifact => ({ workflow_id: "w", task_id: workflowTask.id, role: workflowTask.owner, status, summary: status === "succeeded" ? "done" : "failed", changed_paths: [], scope_escalations: [], commands: [], output: "", conclusion: status, diff_summary: "", test_summary: "", security_summary: "", review_decision: null, tokens, elapsed_s: 0, attempt: 0, child_run_id: "" });

test("workflow validation rejects dependency cycles", () => {
  const graph = { workflow_id: "w", goal: "g", planner_summary: "p", tasks: [task("a", ["b"]), task("b", ["a"])] };
  assert.deepEqual(validateWorkflowGraph(graph), ["workflow graph contains a cycle"]);
});

test("workflow scheduler returns only tasks whose dependencies succeeded", () => {
  assert.deepEqual(readyTaskIds([{ id: "a", dependencies: [], status: "succeeded" }, { id: "b", dependencies: ["a"], status: "pending" }, { id: "c", dependencies: ["b"], status: "pending" }]), ["b"]);
});

test("workflow paths reject traversal and match assigned files, directories, and globs", () => {
  assert.equal(normalizeWorkflowPath("./src\\core.ts"), "src/core.ts");
  assert.equal(workflowPathIsAllowed("src/core.ts", ["src"]), true);
  assert.equal(workflowPathIsAllowed("tests/core.test.ts", ["tests/*.test.ts"]), true);
  assert.equal(workflowPathIsAllowed("docs/readme.md", ["src"]), false);
  assert.throws(() => normalizeWorkflowPath("C:\\outside.txt"), /inside the assigned workspace scope/);
  assert.throws(() => normalizeWorkflowPath("../outside.txt"), /inside the assigned workspace scope/);
});

test("workflow scope upgrades only out-of-scope file writes", async () => {
  const observed: Array<{ toolName: string; permission: string }> = [];
  const gate = scopedWorkflowPermissions({ check: async (_runId, _permissionId, toolName, _params, permission) => { observed.push({ toolName, permission }); return true; } }, ["src"]);
  await gate.check("r", "1", "write_file", { path: "src/main.ts" }, "workspace_write");
  await gate.check("r", "2", "edit_file", { path: "docs/readme.md" }, "workspace_write");
  assert.deepEqual(observed, [{ toolName: "write_file", permission: "workspace_write" }, { toolName: "edit_file", permission: "danger_full_access" }]);
});

test("agent loop publishes thinking deltas and preserves signed blocks in history", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-thinking-loop-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    const thinking: string[] = [];
    events.subscribe((event) => { if (event.type === "llm.thinking") thinking.push(event.thinking); });
    const provider: ModelProvider = { complete: async (_messages, _tools, _signal, _onToken, _invocation, onThinking) => {
      onThinking?.("inspect "); onThinking?.("files");
      return { text: "done", thinking_blocks: [{ type: "thinking", thinking: "inspect files", signature: "signed-1" }], tool_calls: [], stop_reason: "end_turn" };
    } };
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }).run("thinking-run", "work", 1);
    assert.deepEqual(thinking, ["inspect ", "files"]);
    assert.deepEqual(result.messages.at(-1)?.content, [{ type: "thinking", thinking: "inspect files", signature: "signed-1" }, { type: "text", text: "done" }]);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop continues after a max_tokens response without tool calls", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-max-tokens-loop-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let calls = 0;
    const provider: ModelProvider = { complete: async () => {
      calls += 1;
      return calls === 1
        ? { text: "partial", tool_calls: [], stop_reason: "max_tokens" }
        : { text: "recovered", tool_calls: [], stop_reason: "end_turn" };
    } };
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }).run("max-tokens-run", "work", 2);
    assert.equal(calls, 2);
    assert.equal(result.text, "recovered");
    assert.equal(result.messages.some((message) => message.role === "assistant" && message.content === "partial"), true);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop interrupts only the active generation for steering and preserves partial text", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-stream-steering-")); const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let calls = 0; let controller = new AbortController(); let steering: Array<{ role: "user"; content: string }> = [];
    const provider: ModelProvider = { complete: async (messages, _tools, signal, onToken) => {
      calls += 1;
      if (calls === 1) {
        onToken?.("partial work"); steering.push({ role: "user", content: "change direction" }); controller.abort(new Error("steered"));
        if (signal?.aborted) throw signal.reason;
        await new Promise<void>((_resolve, reject) => signal?.addEventListener("abort", () => reject(signal.reason), { once: true }));
      }
      assert.equal(messages.some((message) => message.role === "assistant" && message.content === "partial work"), true);
      assert.equal(messages.some((message) => message.role === "user" && message.content === "change direction"), true);
      return { text: "redirected", tool_calls: [], stop_reason: "end_turn" };
    } };
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }).run("steering-run", "work", 2, [], undefined, () => { const queued = steering.splice(0); if (controller.signal.aborted) controller = new AbortController(); return queued; }, () => controller.signal);
    assert.equal(result.text, "redirected"); assert.equal(calls, 2);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop feeds malformed truncated tool arguments back as schema_error", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-schema-repair-loop-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let calls = 0;
    const failures: string[] = [];
    events.subscribe((event) => { if (event.type === "tool.call_failed") failures.push(event.error_class); });
    const provider: ModelProvider = { complete: async (messages) => {
      calls += 1;
      if (calls === 1) return { text: "", tool_calls: [{ id: "bad-read", name: "read_file", input: {} }], stop_reason: "max_tokens" };
      const toolResult = messages.find((message) => message.role === "tool" && message.tool_call_id === "bad-read");
      assert.equal(toolResult?.is_error, true);
      assert.match(String(toolResult?.content), /path.*required/i);
      return { text: "recovered", tool_calls: [], stop_reason: "end_turn" };
    } };
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }).run("schema-repair-run", "read a file", 2);
    assert.equal(result.text, "recovered");
    assert.ok(failures.includes("schema_error"));
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop auto-compacts at the configured threshold and preserves the initial goal", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-auto-compact-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    const compacted: any[] = []; const purposes: string[] = [];
    events.subscribe((event) => { if (event.type === "context.compacted") compacted.push(event); });
    let agentCalls = 0; const provider: ModelProvider = { complete: async (_messages, _tools, _signal, _onToken, invocation) => {
      purposes.push(invocation?.purpose ?? "agent");
      if (invocation?.purpose === "compaction") return { text: "Goal\nKeep the original task.\nProgress\nOld turns are summarized.\nDecisions\nPreserve recent turns.\nOpen Issues\nNone.\nNext Steps\nFinish.", tool_calls: [], stop_reason: "end_turn", usage: { output_tokens: 24 } };
      agentCalls += 1; return agentCalls === 1 ? { text: "", tool_calls: [{ id: "read", name: "read_file", input: { path: "package.json" } }], stop_reason: "tool_use", usage: { input_tokens: 80, output_tokens: 2 } } : { text: "done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 80, output_tokens: 2 } };
    } };
    await writeFile(path.join(root, "package.json"), "{}", "utf8");
    const history = [{ role: "user" as const, content: "original goal" }, ...Array.from({ length: 8 }, (_, index) => ({ role: index % 2 ? "user" as const : "assistant" as const, content: `turn-${index} ${"detail ".repeat(20)}` }))];
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { sessionId: "session-1", contextWindow: 100, compactThreshold: 0.70, slidingWindowSize: 2, compactMinimumOldTokens: 0 }).run("compact-run", "continue", 2, history);
    assert.deepEqual(purposes, ["agent", "compaction", "agent"]); assert.equal(result.compacted, true); assert.equal(result.contextPct, 0.8); assert.equal(result.messages.some((message) => message.content === "original goal"), true); assert.equal(compacted.length, 1);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop treats a 0 context window as auto and never reports 100% usage", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-zero-window-"));
  try {
    const events = new EventBus(path.join(root, "events.jsonl")); let calls = 0;
    const provider: ModelProvider = { complete: async (_messages, _tools, _signal, _onToken, _invocation) => {
      calls += 1; return calls === 1 ? { text: "", tool_calls: [{ id: "read", name: "read_file", input: { path: "package.json" } }], stop_reason: "tool_use", usage: { input_tokens: 800, output_tokens: 2 } } : { text: "done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 800, output_tokens: 2 } };
    } };
    await writeFile(path.join(root, "package.json"), "{}", "utf8");
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { contextWindow: 0 }).run("zero-window", "inspect", 2);
    assert.equal(result.contextPct, 800 / 128_000); assert.ok(result.contextPct < 1);
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop falls back to hard-drop compaction after the circuit breaker opens", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-compact-breaker-"));
  try {
    let compactions = 0; let agents = 0;
    const provider: ModelProvider = { complete: async (_messages, _tools, _signal, _onToken, invocation) => {
      if (invocation?.purpose === "compaction") { compactions += 1; return { text: "invalid", tool_calls: [], stop_reason: "end_turn" }; }
      agents += 1; return agents < 3 ? { text: "", tool_calls: [{ id: `read-${agents}`, name: "read_file", input: { path: "package.json" } }], stop_reason: "tool_use", usage: { input_tokens: 90, output_tokens: 1 } } : { text: "done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 90, output_tokens: 1 } };
    } };
    await writeFile(path.join(root, "package.json"), "{}", "utf8");
    const history = [{ role: "user" as const, content: "goal" }, ...Array.from({ length: 6 }, (_, index) => ({ role: index % 2 ? "user" as const : "assistant" as const, content: `old-${index} ${"detail ".repeat(20)}` }))];
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async () => true }, { contextWindow: 100, compactThreshold: 0.70, compactCooldownSteps: 0, compactCircuitBreaker: 2, compactMinimumOldTokens: 0 }).run("breaker", "continue", 4, history);
    // LLM 摘要连续失败触发熔断后退化为无模型硬丢弃，上下文不再只增不减
    assert.equal(result.text, "done"); assert.equal(result.compacted, true); assert.equal(compactions, 2);
    assert.ok(result.messages.some((message) => String(message.content).includes("Earlier conversation compacted")));
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop feeds LLM API failures back into the conversation and recovers", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-llm-failure-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let calls = 0; let sawFailureNotice = false;
    const provider: ModelProvider = { complete: async (messages) => {
      calls += 1;
      if (calls === 1) throw new Error("LLM request failed (500): gateway exploded");
      sawFailureNotice = messages.some((message) => message.role === "user" && String(message.content).includes("gateway exploded"));
      return { text: "recovered", tool_calls: [], stop_reason: "end_turn" };
    } };
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { maxLlmFailures: 3 }).run("llm-failure", "work", 3);
    assert.equal(result.text, "recovered");
    // 错误成为对话的一部分：模型下一轮能看到失败原因
    assert.ok(sawFailureNotice);
    assert.ok(result.messages.some((message) => message.role === "user" && String(message.content).includes("attempt 1 of 3")));
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop gives up after consecutive LLM failures and carries partial messages", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-llm-dead-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let calls = 0;
    const provider: ModelProvider = { complete: async () => { calls += 1; throw new Error("LLM request failed (429): rate limited"); } };
    let caught: NodeJS.ErrnoException | undefined;
    try { await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { maxLlmFailures: 2 }).run("llm-dead", "work", 10); }
    catch (error) { caught = error as NodeJS.ErrnoException; }
    assert.ok(caught);
    assert.match(caught!.message, /429/);
    assert.equal(calls, 2);
    // 失败也带上已积累的对话状态，供上层持久化
    const partial = (caught as Error & { partialMessages?: unknown }).partialMessages as unknown[] | undefined;
    assert.ok(Array.isArray(partial) && partial.length >= 1);
    assert.ok(partial!.some((message) => String((message as { content: unknown }).content).includes("rate limited")));
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop does not auto-retry tools marked retryable false", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-bash-no-retry-"));
  try {
    let toolCalls = 0; let modelCalls = 0;
    const tools = createWorkspaceTools([{ name: "non_retryable", description: "non-idempotent command", permission: "workspace_write", retryable: false, schema: { type: "object" }, async invoke() { toolCalls += 1; return { ok: false, output: "[exit 1]", error: "command exited with code 1", errorType: "runtime_error" }; } }]);
    const provider: ModelProvider = { complete: async () => { modelCalls += 1; return modelCalls === 1 ? { text: "", tool_calls: [{ id: "cmd", name: "non_retryable", input: {} }], stop_reason: "tool_use" } : { text: "seen failure", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, tools, { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async () => true }, { toolRetryBaseMs: 0 });
    assert.equal((await loop.run("no-retry", "run", 3)).text, "seen failure");
    // exit≠0 是业务结果：只执行一次，不自动重跑
    assert.equal(toolCalls, 1);
    assert.equal(tools.get("bash")?.retryable, false);
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop uses a tool-free conclusion when the final allowed step calls tools", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-max-step-conclusion-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    const toolCounts: number[] = []; const progress: Array<{ steps: number; output: number }> = []; let calls = 0;
    const provider: ModelProvider = { complete: async (_messages, tools) => {
      calls += 1; toolCounts.push(tools.list().length);
      if (calls === 1) return { text: "", tool_calls: [{ id: "read", name: "read_file", input: { path: "package.json" } }], stop_reason: "tool_use", usage: { input_tokens: 10, output_tokens: 2 } };
      return { text: "[COMPLETE] finished at the boundary", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 12, output_tokens: 4 } };
    } };
    await writeFile(path.join(root, "package.json"), "{}", "utf8");
    const result = await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { onProgress: ({ steps, usage }) => progress.push({ steps, output: usage.output_tokens }) }).run("max-step", "inspect", 1);
    assert.equal(result.text, "finished at the boundary"); assert.equal(result.steps, 1); assert.equal(result.usage.output_tokens, 6);
    assert.ok(toolCounts[0]! > 0); assert.equal(toolCounts[1], 0); assert.deepEqual(progress, [{ steps: 1, output: 2 }, { steps: 1, output: 6 }]);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("run manager reports real progress when a step-limited run remains incomplete", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-max-step-progress-")); const previous = process.env.SZTU_MAX_STEPS; process.env.SZTU_MAX_STEPS = "1";
  try {
    let calls = 0; const events = new EventBus(path.join(root, "events.jsonl")); const finished = new Promise<any>((resolve) => events.subscribe((event) => { if (event.type === "run.finished") resolve(event); }));
    const provider: ModelProvider = { complete: async () => { calls += 1; return calls === 1 ? { text: "", tool_calls: [{ id: "read", name: "read_file", input: { path: "package.json" } }], stop_reason: "tool_use", usage: { input_tokens: 7, output_tokens: 2 } } : { text: "[INCOMPLETE] more work remains", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 9, output_tokens: 3 } }; } };
    await writeFile(path.join(root, "package.json"), "{}", "utf8"); new RunManager(events, provider, root).start("inspect", [], undefined, root);
    const event = await finished; assert.equal(event.status, "failed"); assert.equal(event.steps, 1); assert.equal(event.total_input_tokens, 16); assert.equal(event.total_output_tokens, 5); assert.match(event.reason, /more work remains/);
  } finally { if (previous === undefined) delete process.env.SZTU_MAX_STEPS; else process.env.SZTU_MAX_STEPS = previous; await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop applies dynamic bash permission before approval", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-bash-permission-"));
  try {
    const observed: string[] = []; let calls = 0;
    const provider: ModelProvider = { complete: async () => { calls += 1; if (calls === 1) return { text: "", tool_calls: [{ id: "safe", name: "bash", input: { command: "git status --short" } }], stop_reason: "tool_use" }; if (calls === 2) return { text: "", tool_calls: [{ id: "unsafe", name: "bash", input: { command: "git clean -fd" } }], stop_reason: "tool_use" }; return { text: "done", tool_calls: [], stop_reason: "end_turn" }; } };
    const tools = createWorkspaceTools(); const bash = tools.get("bash")!;
    bash.invoke = async () => ({ ok: true, output: "ok" });
    const loop = new AgentLoop(provider, tools, { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async (_runId, _callId, _toolName, _params, permission) => { observed.push(permission); return true; } });
    assert.equal((await loop.run("bash-permission", "inspect", 4)).text, "done");
    // git status 是只读 git 子命令，动态分类降级为 read_only；git clean 不在白名单，保持 danger_full_access
    assert.deepEqual(observed, ["read_only", "danger_full_access"]);
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("permission always decisions persist while full-access calls still require approval", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-permission-policy-"));
  const eventBuses: EventBus[] = [];
  try {
    const policyPath = path.join(root, "policy.toml");
    const firstEvents = new EventBus(path.join(root, "first-events.jsonl")); eventBuses.push(firstEvents);
    const first = new PermissionManager(firstEvents, 100, policyPath);
    const pending = first.check("run-1", "permission-1", "write_file", { path: "src/a.ts" }, "workspace_write");
    assert.equal(first.respond("permission-1", "always_allow"), true);
    assert.equal(await pending, true);

    const secondEvents = new EventBus(path.join(root, "second-events.jsonl")); eventBuses.push(secondEvents);
    const second = new PermissionManager(secondEvents, 10, policyPath);
    assert.equal(await second.check("run-2", "permission-2", "write_file", { path: "src/b.ts" }, "workspace_write"), true);
    assert.equal(await second.check("run-2", "permission-3", "write_file", { path: "docs/b.ts" }, "danger_full_access"), false);
    assert.match(await readFile(policyPath, "utf8"), /write_file = "allow"/);

    const denyPending = second.check("run-2", "permission-4", "edit_file", { path: "src/a.ts" }, "workspace_write");
    assert.equal(second.respond("permission-4", "always_deny"), true);
    assert.equal(await denyPending, false);
    const thirdEvents = new EventBus(path.join(root, "third-events.jsonl")); eventBuses.push(thirdEvents);
    const third = new PermissionManager(thirdEvents, 10, policyPath);
    assert.equal(await third.check("run-3", "permission-5", "edit_file", { path: "src/b.ts" }, "workspace_write"), false);
  } finally { await Promise.all(eventBuses.map((bus) => bus.flush())); await rm(root, { recursive: true, force: true }); }
});

test("agent loop injects a traceable intervention after repeated permission denials", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-denial-intervention-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    const trace: string[] = [];
    events.subscribe((event) => trace.push(event.type));
    const seenMessages: string[] = [];
    let calls = 0;
    const provider: ModelProvider = { complete: async (messages) => {
      seenMessages.push(messages.map((message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content)).join("\n"));
      calls += 1;
      return calls <= 3 ? { text: "", tool_calls: [{ id: `write-${calls}`, name: "write_file", input: { path: "result.txt", content: "blocked" } }], stop_reason: "tool_use" } : { text: "changed approach", tool_calls: [], stop_reason: "end_turn" };
    } };
    const loop = new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => false });
    const result = await loop.run("denial-run", "write result", 5);
    assert.equal(result.text, "changed approach");
    assert.match(seenMessages[3] ?? "", /repeatedly rejected/);
    assert.ok(trace.includes("denial.intervention"));
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop injects a traceable intervention after the same tool failure repeats", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-stuck-intervention-"));
  try {
    const events = new EventBus(path.join(root, "events.jsonl")); const trace: string[] = []; events.subscribe((event) => trace.push(event.type));
    const prompts: string[] = []; let calls = 0;
    const provider: ModelProvider = { complete: async (messages) => { prompts.push(messages.map((message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content)).join("\n")); calls += 1; return calls <= 2 ? { text: "", tool_calls: [{ id: `missing-${calls}`, name: "read_file", input: { path: "missing.txt" } }], stop_reason: "tool_use" } : { text: "changed approach", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { toolRetryBaseMs: 0 });
    assert.equal((await loop.run("stuck-run", "read missing", 4)).text, "changed approach");
    assert.match(prompts[2] ?? "", /appears to be stuck/);
    assert.ok(trace.includes("stuck.loop"));
    await events.flush();
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop canonicalizes tool aliases before permissions and telemetry", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-tool-alias-"));
  try {
    const events = new EventBus(path.join(root, "events.jsonl")); const names: string[] = []; events.subscribe((event) => { if (event.type.startsWith("tool.call_")) names.push(event.tool_name); });
    const permissions: string[] = []; let calls = 0;
    const provider: ModelProvider = { complete: async () => { calls += 1; return calls === 1 ? { text: "", tool_calls: [{ id: "alias-write", name: "write", input: { path: "alias.txt", content: "written" } }], stop_reason: "tool_use" } : { text: "done", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async (_runId, _callId, toolName) => { permissions.push(toolName); return true; } });
    assert.equal((await loop.run("alias", "write", 3)).text, "done");
    assert.equal(await readFile(path.join(root, "alias.txt"), "utf8"), "written");
    assert.deepEqual(permissions, ["write_file"]);
    assert.deepEqual(names, ["write_file", "write_file"]);
    await events.flush();
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop retries transient tool failures once without repeating permission checks", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-tool-retry-"));
  try {
    const events = new EventBus(path.join(root, "events.jsonl")); const trace: string[] = []; events.subscribe((event) => { if (event.type === "log.line" || event.type.startsWith("tool.call_")) trace.push(event.type === "log.line" ? event.message : event.type); });
    let toolCalls = 0; let permissionChecks = 0; let modelCalls = 0;
    const tools = createWorkspaceTools([{ name: "transient", description: "transient", permission: "workspace_write", schema: { type: "object" }, async invoke() { toolCalls += 1; return toolCalls === 1 ? { ok: false, output: "", error: "temporary", errorType: "rate_limited" } : { ok: true, output: "recovered" }; } }]);
    const provider: ModelProvider = { complete: async () => { modelCalls += 1; return modelCalls === 1 ? { text: "", tool_calls: [{ id: "retry", name: "transient", input: {} }], stop_reason: "tool_use" } : { text: "done", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, tools, { workspace: new Workspace(root) }, events, { check: async () => { permissionChecks += 1; return true; } }, { toolRetryBaseMs: 0 });
    assert.equal((await loop.run("retry", "run", 3)).text, "done");
    assert.equal(toolCalls, 2); assert.equal(permissionChecks, 1);
    assert.deepEqual(trace.filter((item) => item.startsWith("tool.call_")), ["tool.call_started", "tool.call_finished"]);
    assert.ok(trace.some((item) => /Retrying transient after attempt 1: temporary/.test(item)));
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop does not retry timeout failures and contains thrown tool errors", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-tool-retry-policy-"));
  try {
    let timeoutCalls = 0; let throwingCalls = 0; let modelCalls = 0;
    const tools = createWorkspaceTools([
      { name: "times_out", description: "timeout", permission: "read_only", schema: { type: "object" }, async invoke() { timeoutCalls += 1; return { ok: false, output: "", error: "slow", errorType: "timeout" }; } },
      { name: "throws", description: "throws", permission: "read_only", schema: { type: "object" }, async invoke() { throwingCalls += 1; throw new Error("broken"); } },
    ]);
    const provider: ModelProvider = { complete: async () => { modelCalls += 1; if (modelCalls === 1) return { text: "", tool_calls: [{ id: "timeout", name: "times_out", input: {} }, { id: "throws", name: "throws", input: {} }], stop_reason: "tool_use" }; return { text: "continued", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, tools, { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async () => true }, { toolRetryBaseMs: 0 });
    assert.equal((await loop.run("retry-policy", "run", 3)).text, "continued");
    assert.equal(timeoutCalls, 1); assert.equal(throwingCalls, 2);
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("agent loop cancellation interrupts tool retry backoff", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-tool-retry-cancel-"));
  try {
    let toolCalls = 0;
    const tools = createWorkspaceTools([{ name: "fails", description: "fails", permission: "read_only", schema: { type: "object" }, async invoke() { toolCalls += 1; return { ok: false, output: "", error: "temporary", errorType: "runtime_error" }; } }]);
    const provider: ModelProvider = { complete: async () => ({ text: "", tool_calls: [{ id: "fails", name: "fails", input: {} }], stop_reason: "tool_use" }) };
    const controller = new AbortController();
    const running = new AgentLoop(provider, tools, { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async () => true }, { toolMaxRetries: 3, toolRetryBaseMs: 5_000 }).run("retry-cancel", "run", 3, [], controller.signal);
    setTimeout(() => controller.abort(new Error("cancelled")), 10);
    await assert.rejects(running, /cancelled/);
    assert.equal(toolCalls, 1);
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("stuck tracking preserves nested tool arguments and supports a hard-stop threshold", () => {
  assert.equal(stuckSignature({ id: "a", name: "custom", input: { nested: { z: 1, a: 2 }, b: true } }), stuckSignature({ id: "b", name: "custom", input: { b: true, nested: { a: 2, z: 1 } } }));
  const tracker = new StuckLoopTracker(2, 1);
  tracker.recordFailure("read_file:missing.txt"); tracker.recordFailure("read_file:missing.txt");
  const intervention = tracker.intervention();
  assert.equal(intervention?.totalInterventions, 1);
  assert.equal(intervention?.hardStop, true);
});

test("memory catalog progressively discloses long context and returns bounded excerpts", () => {
  const catalog = new MemoryCatalog([{ name: "project", source: ".sztu/context.md", content: "# Build\nsecret build details\n## Tests\nuse npm test" }], 10);
  assert.equal(catalog.requiresReader(), true);
  assert.match(catalog.prompt(), /Build/);
  assert.doesNotMatch(catalog.prompt(), /secret build details/);
  assert.match(catalog.read("project", "npm", 0, 80), /npm test/);
  assert.ok(catalog.read("project", "", 0, 10).length < 100);
});

test("session notes preserve only active versions and memory tools expose the chain", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-session-memory-"));
  try {
    const sessions = new SessionStore(root); const session = await sessions.create();
    const catalog = new MemoryCatalog([]); const tools = createMemoryTools(catalog, sessions, session.id, "run-1");
    const saved = await tools.find((tool) => tool.name === "note_save")!.invoke({ content: "Use SQLite" }, { workspace: new Workspace(root) });
    const oldId = saved.output.match(/note-[a-f0-9]+/)?.[0]; assert.ok(oldId);
    const updated = await tools.find((tool) => tool.name === "note_update")!.invoke({ note_id: oldId, content: "Use PostgreSQL" }, { workspace: new Workspace(root) });
    assert.equal(updated.ok, true);
    const notes = await sessions.readNotes(session.id);
    assert.doesNotMatch(notes, /Use SQLite/);
    assert.match(notes, /Use PostgreSQL/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("run manager exposes note tools and injects saved session memory on the next run", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-run-memory-"));
  try {
    const sessions = new SessionStore(path.join(root, "sessions")); const session = await sessions.create(); const events = new EventBus(path.join(root, "events.jsonl"));
    const prompts: string[] = []; let calls = 0;
    const provider: ModelProvider = { complete: async (messages, tools) => {
      prompts.push(messages.map((message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content)).join("\n")); calls += 1;
      if (calls === 1) { assert.ok(tools.get("note_save")); assert.ok(tools.get("note_update")); return { text: "", tool_calls: [{ id: "remember", name: "note_save", input: { content: "Use PostgreSQL" } }], stop_reason: "tool_use" }; }
      return { text: "done", tool_calls: [], stop_reason: "end_turn" };
    } };
    const manager = new RunManager(events, provider, root, undefined, () => [], async () => ({ contextWindow: 16_000, maxOutputTokens: 1_000 }), sessions);
    manager.permissions.setMode("accept_edits");
    const waitFor = async (runId: string) => { const deadline = Date.now() + 5_000; while (manager.get(runId).status === "running" && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 5)); assert.notEqual(manager.get(runId).status, "running"); };
    const first = manager.start("remember database", [], undefined, root, session.id); await waitFor(first);
    const second = manager.start("what database", [], undefined, root, session.id); await waitFor(second);
    assert.match(prompts.at(-1) ?? "", /Use PostgreSQL/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("run manager persists full model context separately from visible session history", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-model-context-")); const sessions = new SessionStore(path.join(root, "sessions")); const session = await sessions.create("chat");
  try {
    const events = new EventBus(path.join(root, "events.jsonl")); let calls = 0;
    const provider: ModelProvider = { complete: async () => { calls += 1; return calls === 1 ? { text: "", tool_calls: [{ id: "read", name: "read_file", input: { path: "package.json" } }], stop_reason: "tool_use", usage: { input_tokens: 10, output_tokens: 1 } } : { text: "done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 12, output_tokens: 2 } }; } };
    await writeFile(path.join(root, "package.json"), "{}", "utf8"); await sessions.appendMessage(session.id, { role: "user", content: "inspect" });
    const finished = new Promise<void>((resolve) => events.subscribe((event) => { if (event.type === "run.finished") resolve(); }));
    new RunManager(events, provider, root, undefined, () => [], async () => ({ contextWindow: 1_000, maxOutputTokens: 100 }), sessions).start("inspect", [], async (messages) => { const assistant = messages.at(-1); if (assistant?.role === "assistant") await sessions.appendMessage(session.id, { role: "assistant", content: assistant.content }); }, root, session.id);
    await finished;
    const modelHistory = await sessions.modelHistory(session.id); const visible = await sessions.history(session.id);
    assert.equal(modelHistory.some((message) => message.role === "tool" && message.tool_call_id === "read"), true);
    assert.deepEqual(visible.map((message) => message.role), ["user", "assistant"]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("workflow retries failed tasks exactly max_retries times", async () => {
  const workflowTask = { ...task("retry"), max_retries: 2 };
  let calls = 0;
  const result = await new WorkflowOrchestrator(async (current) => { calls += 1; return artifact(current, calls === 3 ? "succeeded" : "failed", 2); }).run({ workflow_id: "w", goal: "g", planner_summary: "p", tasks: [workflowTask] });
  assert.equal(calls, 3);
  assert.equal(result.tasks[0]?.attempts, 3);
  assert.equal(result.tasks[0]?.tokens, 6);
  assert.equal(result.tasks[0]?.artifact?.attempt, 3);
  assert.equal(result.status, "succeeded");
});

test("workflow enforces the wall clock budget on every retry attempt", async () => {
  const workflowTask = { ...task("slow"), time_budget_s: 0.02, max_retries: 2 };
  let aborted = 0;
  const result = await new WorkflowOrchestrator((_current, execution) => new Promise((_resolve, reject) => {
    execution.signal.addEventListener("abort", () => { aborted += 1; reject(execution.signal.reason); }, { once: true });
  })).run({ workflow_id: "w", goal: "g", planner_summary: "p", tasks: [workflowTask] });
  assert.equal(aborted, 3);
  assert.equal(result.tasks[0]?.status, "timed_out");
  assert.equal(result.tasks[0]?.attempts, 3);
  assert.equal(result.status, "timed_out");
});

test("workflow rejects token overages and blocks dependent tasks", async () => {
  const first = { ...task("first"), token_budget: 5 };
  const second = task("second", ["first"]);
  const result = await new WorkflowOrchestrator(async (current) => artifact(current, "succeeded", 6)).run({ workflow_id: "w", goal: "g", planner_summary: "p", tasks: [first, second] });
  assert.equal(result.tasks[0]?.status, "rejected");
  assert.match(result.tasks[0]?.error ?? "", /token budget exceeded/);
  assert.equal(result.tasks[1]?.status, "blocked");
  assert.equal(result.tasks[1]?.attempts, 0);
  assert.equal(result.total_tokens, 6);
  assert.equal(result.status, "failed");
});

test("workflow respects the concurrency limit", async () => {
  const tasks = [task("a"), task("b"), task("c"), task("d")];
  let active = 0; let peak = 0;
  const result = await new WorkflowOrchestrator(async (current) => {
    active += 1; peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, 10));
    active -= 1; return artifact(current);
  }, 2).run({ workflow_id: "w", goal: "g", planner_summary: "p", tasks });
  assert.equal(peak, 2);
  assert.equal(result.status, "succeeded");
});

test("workflow cancellation aborts running tasks and cancels pending work", async () => {
  const controller = new AbortController(); let observedAbort = false;
  const tasks = [task("running"), task("pending", ["running"])];
  const resultPromise = new WorkflowOrchestrator((_current, execution) => new Promise((_resolve, reject) => {
    execution.signal.addEventListener("abort", () => { observedAbort = true; reject(execution.signal.reason); }, { once: true });
  })).run({ workflow_id: "cancel", goal: "g", planner_summary: "p", tasks }, controller.signal);
  setTimeout(() => controller.abort(), 10);
  const result = await resultPromise;
  assert.equal(observedAbort, true);
  assert.equal(result.status, "cancelled");
  assert.deepEqual(result.tasks.map((item) => item.status), ["cancelled", "cancelled"]);
});

test("workflow rejects mismatched and incomplete handoff evidence", async () => {
  const coder = { ...task("coder"), max_retries: 1 };
  let coderCalls = 0;
  const coderResult = await new WorkflowOrchestrator(async (current) => { coderCalls += 1; return { ...artifact(current), workflow_id: "wrong" }; }).run({ workflow_id: "w", goal: "g", planner_summary: "p", tasks: [coder] });
  assert.equal(coderCalls, 2);
  assert.equal(coderResult.tasks[0]?.status, "failed");
  assert.match(coderResult.tasks[0]?.error ?? "", /does not match workflow task identity/);

  const tester = { ...task("tester"), owner: "tester" as const, allowed_paths: [] };
  const testerResult = await new WorkflowOrchestrator(async (current) => artifact(current)).run({ workflow_id: "w", goal: "g", planner_summary: "p", tasks: [tester] });
  assert.equal(testerResult.tasks[0]?.status, "failed");
  assert.match(testerResult.tasks[0]?.error ?? "", /tester handoff requires commands/);
});

test("workflow role payloads parse fenced JSON and reject narrative tester output", () => {
  assert.deepEqual(parseRolePayload('```json\n{"status":"succeeded","summary":"ok","commands":["npm test"]}\n```', "tester"), { status: "succeeded", summary: "ok", commands: ["npm test"] });
  assert.throws(() => parseRolePayload("all tests passed", "tester"), /must return a JSON handoff object/);
  assert.equal(parseRolePayload("implemented", "coder").summary, "implemented");
});

test("workspace rejects traversal outside its root", () => {
  const workspace = new Workspace("C:/workspace");
  assert.throws(() => workspace.resolve("../secrets.txt"), WorkspaceBoundaryError);
});

test("system prompt loads TypeScript-owned prompts and project instructions", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-prompt-"));
  try {
    await writeFile(path.join(root, "AGENTS.md"), "PROJECT_SENTINEL: follow repository rules", "utf8");
    const prompt = await buildSystemPrompt(root);
    assert.match(prompt, /SztuCode/);
    assert.match(prompt, /PROJECT_SENTINEL/);
    assert.match(prompt, new RegExp(root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("prompt harness injects only rules required by runtime capabilities", async () => {
  const basic = await runtimePromptEntries({ toolNames: ["read_file"], taskText: "read config" });
  assert.ok(basic.some((entry) => /read_file|读取文件/i.test(entry)));
  assert.ok(!basic.some((entry) => /自动模式已激活/.test(entry)));
  const dynamic = await runtimePromptEntries({ permissionMode: "auto", memoryEnabled: true, toolNames: ["bash", "task_get"], taskText: "删除旧分支并推送" });
  assert.ok(dynamic.some((entry) => /自动模式已激活/.test(entry)));
  assert.ok(dynamic.some((entry) => /自动内存管理/.test(entry)));
  assert.ok(dynamic.some((entry) => /谨慎执行操作/.test(entry)));
  assert.ok(dynamic.some((entry) => /任务管理/.test(entry)));
  assert.ok(dynamic.some((entry) => /并行|parallel/i.test(entry)));
});

test("agent profiles load role prompts and enforce tool allowlists", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-agent-"));
  try {
    await mkdir(path.join(root, ".sztu", "agents"), { recursive: true });
    await writeFile(path.join(root, ".sztu", "agents", "tester.toml"), '[agent]\ndescription = "test"\nsystem_prompt = """Only validate."""\nallowed_tools = [\n  "read_file",\n  "bash",\n]\nmax_steps = 7\n', "utf8");
    const profile = await loadAgentProfile(root, "tester");
    assert.equal(profile.systemPrompt, "Only validate.");
    assert.equal(profile.maxSteps, 7);
    assert.equal(profile.permissionMode, null);
    const tools = createWorkspaceTools().restrictTo(profile.allowedTools ?? []);
    assert.deepEqual(tools.list().map((tool) => tool.name).sort(), ["bash", "read_file"]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("agent profiles parse inline tool arrays and preserve the empty-means-default contract", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-inline-tools-"));
  try {
    await mkdir(path.join(root, ".sztu", "agents"), { recursive: true });
    await writeFile(path.join(root, ".sztu", "agents", "inline.toml"), '[agent]\nallowed_tools = ["read_file", "task_get"]\n', "utf8");
    assert.deepEqual((await loadAgentProfile(root, "inline")).allowedTools, ["read_file", "task_get"]);
    assert.ok(createWorkspaceTools().restrictTo([]).list().some((tool) => tool.name === "write_file"));
    await writeFile(path.join(root, ".sztu", "agents", "unspecified.toml"), "[agent]\nmax_steps = 3\n", "utf8");
    assert.equal((await loadAgentProfile(root, "unspecified")).allowedTools, null);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("subagents apply profile permission modes without mutating the global mode", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-subagent-permissions-"));
  try {
    await mkdir(path.join(root, ".sztu", "agents"), { recursive: true });
    const events = new EventBus(path.join(root, "events.jsonl"));
    const permissions = new PermissionManager(events, 20);
    const provider = (): ModelProvider => {
      let calls = 0;
      return { complete: async () => ++calls === 1
        ? { text: "", tool_calls: [{ id: "write-1", name: "write_file", input: { path: "result.txt", content: "written" } }], stop_reason: "tool_use" }
        : { text: "done", tool_calls: [], stop_reason: "end_turn" } };
    };

    permissions.setMode("auto");
    await writeFile(path.join(root, ".sztu", "agents", "coder.toml"), '[agent]\npermission_mode = "plan"\nallowed_tools = [\n  "write_file",\n]\nmax_steps = 3\n', "utf8");
    await new SubagentManager(provider(), root, events, permissions).run("coder", "write result.txt");
    await assert.rejects(() => readFile(path.join(root, "result.txt"), "utf8"));
    assert.equal(permissions.getMode(), "auto");

    permissions.setMode("plan");
    await writeFile(path.join(root, ".sztu", "agents", "coder.toml"), '[agent]\npermission_mode = "auto"\nallowed_tools = [\n  "write_file",\n]\nmax_steps = 3\n', "utf8");
    await new SubagentManager(provider(), root, events, permissions).run("coder", "write result.txt");
    assert.equal(await readFile(path.join(root, "result.txt"), "utf8"), "written");
    assert.equal(permissions.getMode(), "plan");
    await events.flush();
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("planner subagents receive the task tools declared by their profile", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-subagent-plan-tools-"));
  try {
    await mkdir(path.join(root, ".sztu", "agents"), { recursive: true });
    await writeFile(path.join(root, ".sztu", "agents", "planner.toml"), '[agent]\nallowed_tools = ["task_create", "task_get", "task_list", "task_update"]\nmax_steps = 2\n', "utf8");
    let names: string[] = [];
    const provider: ModelProvider = { complete: async (_messages, tools) => { names = tools.list().map((tool) => tool.name).sort(); return { text: "done", tool_calls: [], stop_reason: "end_turn" }; } };
    const events = new EventBus(path.join(root, "events.jsonl"));
    await new SubagentManager(provider, root, events, new PermissionManager(events, 20)).run("planner", "plan");
    assert.deepEqual(names, ["read_ref", "task_create", "task_get", "task_list", "task_update"]);
    await events.flush();
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("workflow coder records approved out-of-scope writes as changed paths and escalations", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-workflow-scope-"));
  try {
    const events = new EventBus(path.join(root, "events.jsonl"));
    const permissions = new PermissionManager(events, 20);
    permissions.setMode("auto");
    let calls = 0;
    const provider: ModelProvider = { complete: async () => ++calls === 1
      ? { text: "", tool_calls: [{ id: "write-outside", name: "write_file", input: { path: "docs/result.txt", content: "approved" } }], stop_reason: "tool_use", usage: { input_tokens: 3, output_tokens: 2 } }
      : { text: "implemented", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 4, output_tokens: 1 } } };
    const workflowTask = { ...task("code"), allowed_paths: ["src"] };
    const result = await new SubagentManager(provider, root, events, permissions).runWorkflow({ workflow_id: "w", goal: "g", planner_summary: "p", tasks: [workflowTask] });
    assert.equal(await readFile(path.join(root, "docs", "result.txt"), "utf8"), "approved");
    assert.equal(result.status, "succeeded");
    assert.deepEqual(result.tasks[0]?.artifact?.changed_paths, ["docs/result.txt"]);
    assert.deepEqual(result.tasks[0]?.artifact?.scope_escalations, ["docs/result.txt"]);
    assert.equal(result.tasks[0]?.tokens, 10);
    await events.flush();
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});
