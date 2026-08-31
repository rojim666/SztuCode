import assert from "node:assert/strict";
import test from "node:test";
import type { HandoffArtifact, WorkflowGraph, WorkflowTask } from "@sztucode/protocol";
import { WorkflowOrchestrator, type WorkflowTaskExecutor } from "../src/workflow.js";

const task = (id: string, dependencies: string[] = [], time_budget_s = 0): WorkflowTask => ({ id, title: id, description: id, owner: "planner", dependencies, completion_criteria: ["done"], allowed_paths: [], depth: dependencies.length, token_budget: 0, time_budget_s, max_retries: 0 });

const succeeded = (workflowId: string, t: WorkflowTask): HandoffArtifact => ({ workflow_id: workflowId, task_id: t.id, role: t.owner, status: "succeeded", summary: "done", changed_paths: [], scope_escalations: [], commands: [], output: "", conclusion: "done", diff_summary: "", test_summary: "", security_summary: "", review_decision: null, tokens: 0, elapsed_s: 0, attempt: 0, child_run_id: "" });

test("event-driven scheduler backfills ready tasks as soon as one settles instead of waiting for the slowest in wave", async () => {
  const starts = new Map<string, number>();
  const finishes = new Map<string, number>();
  const delays: Record<string, number> = { a: 200, b: 10, c: 10, d: 10 };
  const graph: WorkflowGraph = { workflow_id: "wf", goal: "g", planner_summary: "s", tasks: [task("a"), task("b"), task("c", ["b"]), task("d", ["a"])] };
  const executor: WorkflowTaskExecutor = async (t) => {
    starts.set(t.id, Date.now());
    await new Promise((resolve) => setTimeout(resolve, delays[t.id] ?? 5));
    finishes.set(t.id, Date.now());
    return succeeded("wf", t);
  };
  const result = await new WorkflowOrchestrator(executor, 4).run(graph);
  assert.equal(result.status, "succeeded");
  assert.ok(starts.has("c") && finishes.has("a"), "expected both c and a to run");
  // c 依赖短任务 b，d 依赖长任务 a：事件驱动下 c 应在 a 完成之前就启动（旧波次模型会等到 a 完成才重算 ready）
  assert.ok(starts.get("c")! < finishes.get("a")!, `expected c to start (${starts.get("c")}) before a finishes (${finishes.get("a")})`);
});

test("time_budget_s <= 0 honors the default timeout instead of never timing out", async () => {
  const previous = process.env.SZTU_WORKFLOW_DEFAULT_TIMEOUT_S;
  process.env.SZTU_WORKFLOW_DEFAULT_TIMEOUT_S = "1";
  try {
    const graph: WorkflowGraph = { workflow_id: "wf", goal: "g", planner_summary: "s", tasks: [task("a", [], 0)] };
    const executor: WorkflowTaskExecutor = async (t, execution) => {
      // 响应 abort，避免超时后台定时器拖住进程
      await new Promise<never>((resolve, reject) => {
        const timer = setTimeout(resolve, 3000);
        execution.signal.addEventListener("abort", () => { clearTimeout(timer); reject(execution.signal.reason ?? new Error("aborted")); }, { once: true });
      });
      return succeeded("wf", t);
    };
    const started = Date.now();
    const result = await new WorkflowOrchestrator(executor, 4).run(graph);
    const elapsed = (Date.now() - started) / 1000;
    assert.equal(result.status, "timed_out");
    assert.equal(result.tasks[0]!.status, "timed_out");
    assert.ok(elapsed < 2.5, `expected the 1s default timeout to fire, elapsed=${elapsed}`);
  } finally {
    if (previous === undefined) delete process.env.SZTU_WORKFLOW_DEFAULT_TIMEOUT_S; else process.env.SZTU_WORKFLOW_DEFAULT_TIMEOUT_S = previous;
  }
});

test("upstream failure blocks dependents instead of stalling", async () => {
  const graph: WorkflowGraph = { workflow_id: "wf", goal: "g", planner_summary: "s", tasks: [task("a"), task("b", ["a"])] };
  const executor: WorkflowTaskExecutor = async (t) => { if (t.id === "a") throw new Error("boom"); return succeeded("wf", t); };
  const result = await new WorkflowOrchestrator(executor, 4).run(graph);
  assert.equal(result.status, "failed");
  assert.equal(result.tasks.find((item) => item.task.id === "a")?.status, "failed");
  assert.equal(result.tasks.find((item) => item.task.id === "b")?.status, "blocked");
});