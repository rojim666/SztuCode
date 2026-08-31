import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { WorkflowGraph, WorkflowTask } from "@sztucode/protocol";
import { JsonlSessionBackend } from "@sztucode/session-fs";
import { EventBus } from "../src/event-bus.js";
import { PermissionManager } from "../src/permissions.js";
import { SubagentManager } from "../src/subagent.js";
import { createSubagentResultTool } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";
import type { ModelProvider } from "../src/agent-loop.js";

const task = (id: string, dependencies: string[] = [], owner: "planner" | "coder" | "tester" | "reviewer" = "coder"): WorkflowTask => ({ id, title: id, description: id, owner, dependencies, completion_criteria: ["done"], allowed_paths: ["src"], depth: dependencies.length, token_budget: 0, time_budget_s: 0, max_retries: 0 });

async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-subagent-runtime-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  const backend = new JsonlSessionBackend(path.join(root, "sessions"));
  const permissions = new PermissionManager(events, 20); permissions.setMode("auto");
  return { root, events, backend, permissions };
}

test("subagents create independent child sessions with parent links and subscriptions", async () => {
  const { root, events, backend, permissions } = await setup();
  try {
    const seen: string[] = [];
    const provider: ModelProvider = { complete: async () => ({ text: "child done", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 2, output_tokens: 3 } }) };
    const manager = new SubagentManager(provider, root, events, permissions, backend);
    const started = new Promise<{ runId: string; childSessionId: string; parentSessionId?: string }>((resolve) => events.subscribe((event) => { if (event.type === "subagent.started") resolve({ runId: event.run_id, childSessionId: event.child_session_id!, parentSessionId: event.parent_session_id }); }));
    const result = await manager.run("coder", "child goal", [], "parent-run", { parentSessionId: "parent-session" });
    const correlation = await started;
    assert.equal(result.runId, correlation.runId); assert.equal(result.sessionId, correlation.childSessionId);
    assert.equal(correlation.parentSessionId, "parent-session");
    const snapshot = await backend.get(result.sessionId);
    assert.deepEqual((await manager.snapshotChildSession(result.sessionId)).header, snapshot.header);
    assert.equal(snapshot.header.parentSessionId, "parent-session");
    assert.equal(snapshot.header.metadata?.parentRunId, "parent-run");
    assert.ok(snapshot.entries.some((entry) => entry.type === "message" && entry.message.role === "assistant"));
    assert.equal(result.tokens, 5);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("child cancellation and parent cancellation abort the SessionRuntime", async () => {
  const { root, events, backend, permissions } = await setup();
  try {
    let release: (() => void) | undefined;
    const provider: ModelProvider = { complete: async (_messages, _tools, signal) => await new Promise((resolve, reject) => { release = () => resolve({ text: "done", tool_calls: [], stop_reason: "end_turn" }); signal?.addEventListener("abort", () => reject(new Error("aborted")), { once: true }); }) };
    const manager = new SubagentManager(provider, root, events, permissions, backend);
    const childStarted = new Promise<string>((resolve) => events.subscribe((event) => { if (event.type === "subagent.started") resolve(event.child_session_id!); }));
    const childRun = manager.run("planner", "wait"); const childId = await childStarted; const childEvents: string[] = []; const unsubscribe = manager.subscribeChildEvents(childId, (event) => childEvents.push(event.type)); await manager.abortChildSession(childId);
    await assert.rejects(childRun, /aborted|cancelled/i);
    unsubscribe(); assert.ok(childEvents.includes("run.finished"));
    release = undefined;

    const controller = new AbortController();
    const parentRun = manager.run("planner", "wait for parent", [], "parent", { signal: controller.signal });
    await new Promise((resolve) => setTimeout(resolve, 10)); controller.abort();
    await assert.rejects(parentRun, /aborted|cancelled/i);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("workflow persists node state and propagates DAG failure to dependents", async () => {
  const { root, events, backend, permissions } = await setup();
  try {
    let active = 0; let peak = 0;
    const provider: ModelProvider = { complete: async (messages, _tools, signal) => {
      active += 1; peak = Math.max(peak, active);
      await new Promise((resolve, reject) => { const timer = setTimeout(resolve, 100); signal?.addEventListener("abort", () => { clearTimeout(timer); reject(new Error("aborted")); }, { once: true }); });
      active -= 1;
      const prompt = String(messages.at(-1)?.content ?? "");
      const failed = /fail-me/.test(prompt);
      return { text: JSON.stringify({ status: failed ? "failed" : "succeeded", summary: failed ? "failed" : "done", conclusion: failed ? "failed" : "done" }), tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 1 } };
    } };
    const manager = new SubagentManager(provider, root, events, permissions, backend, path.join(root, "workflows"));
    const graph: WorkflowGraph = { workflow_id: "dag", goal: "dag", planner_summary: "planned", tasks: [task("a"), task("b"), { ...task("c", ["a"]), description: "fail-me" }, task("d", ["c"]) ] };
    let workflowRunId = ""; events.subscribe((event) => { if (event.type === "workflow.started") workflowRunId = event.run_id; });
    const result = await manager.runWorkflow(graph, { parentSessionId: "parent" });
    assert.ok(peak >= 2, `expected independent DAG tasks to overlap, peak=${peak}`);
    assert.equal(result.status, "failed"); assert.equal(result.tasks.find((item) => item.task.id === "c")?.status, "failed"); assert.equal(result.tasks.find((item) => item.task.id === "d")?.status, "blocked");
    const persisted = await manager.loadWorkflow(workflowRunId);
    assert.equal(persisted.status, "failed"); assert.equal(persisted.parent_session_id, "parent");
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("spawn returns a handle immediately; handleResult is async and handleList tracks handles", async () => {
  const { root, events, backend, permissions } = await setup();
  try {
    const provider: ModelProvider = { complete: async () => { await new Promise((resolve) => setTimeout(resolve, 50)); return { text: "child output", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 2 } }; } };
    const manager = new SubagentManager(provider, root, events, permissions, backend);
    const { handle } = manager.spawn("coder", "child goal");
    assert.ok(handle, "spawn must return a handle immediately");
    const early = manager.handleResult(handle);
    assert.equal((early as { status?: string }).status, "running");
    assert.ok((early as { note?: string }).note, "still-running result must carry a note");
    assert.equal(manager.handleList().length, 1);
    const deadline = Date.now() + 3000;
    let done: { status?: string; text?: string } = {};
    while (Date.now() < deadline) { done = manager.handleResult(handle) as { status?: string; text?: string }; if (done.status === "completed") break; await new Promise((resolve) => setTimeout(resolve, 20)); }
    assert.equal(done.status, "completed");
    assert.equal(done.text, "child output");
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("subagent_result validates planner output as a WorkflowGraph after completion", async () => {
  const { root, events, backend, permissions } = await setup();
  try {
    const graph: WorkflowGraph = { workflow_id: "wf", goal: "g", planner_summary: "s", tasks: [task("a")] };
    const provider: ModelProvider = { complete: async () => ({ text: JSON.stringify(graph), tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 1 } }) };
    const manager = new SubagentManager(provider, root, events, permissions, backend);
    const resultTool = createSubagentResultTool(manager);
    const { handle } = manager.spawn("planner", "plan it");
    const deadline = Date.now() + 3000;
    let done: { status?: string } = {};
    while (Date.now() < deadline) { done = manager.handleResult(handle) as { status?: string }; if (done.status === "completed") break; await new Promise((resolve) => setTimeout(resolve, 20)); }
    assert.equal(done.status, "completed");
    const toolResult = await resultTool.invoke({ handle }, { workspace: new Workspace(root) });
    assert.equal(toolResult.ok, true);
    assert.deepEqual(JSON.parse(toolResult.output).workflow, graph);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});
