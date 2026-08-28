import assert from "node:assert/strict";
import test from "node:test";
import { classifyTool, createPhaseTracker } from "../src/phase.js";

test("classifyTool 区分只读、写入与验证工具", () => {
  assert.equal(classifyTool("read_file", { path: "a.ts" }), "read");
  assert.equal(classifyTool("list_dir", {}), "read");
  assert.equal(classifyTool("glob_search", {}), "read");
  assert.equal(classifyTool("write_file", {}), "write");
  assert.equal(classifyTool("edit_file", {}), "write");
  // bash 的归类取决于命令本身
  assert.equal(classifyTool("bash", { command: "npm test" }), "verify");
  assert.equal(classifyTool("bash", { command: "uv run pytest -q" }), "verify");
  assert.equal(classifyTool("bash", { command: "ls -la" }), "other");
  assert.equal(classifyTool("bash", {}), "other");
  // 未登记的工具按名字兜底，且必须按词匹配：frobnicate 里的 cat 不能算只读
  assert.equal(classifyTool("frobnicate", {}), "other");
});

test("阶段从理解开始，只读探查不推进", () => {
  const phases = createPhaseTracker();
  assert.equal(phases.current(), "understanding");
  assert.equal(phases.observeTool("read_file", { path: "a.ts" }), null);
  assert.equal(phases.observeTool("grep_search", { pattern: "foo" }), null);
  assert.equal(phases.current(), "understanding");
});

test("写入推进到执行，验证推进到验证，只在变化时回报", () => {
  const phases = createPhaseTracker();
  phases.observeTool("read_file", {});
  const first = phases.observeTool("edit_file", { path: "a.ts" });
  assert.deepEqual(first, { from: "understanding", to: "executing", reason: "edit_file 属于写入类操作" });
  // 连续同类工具不应重复回报
  assert.equal(phases.observeTool("write_file", {}), null);
  const second = phases.observeTool("bash", { command: "npm test" });
  assert.deepEqual(second, { from: "executing", to: "verifying", reason: "bash 属于验证类操作" });
  assert.equal(phases.current(), "verifying");
});

test("finish 进入交付且只回报一次", () => {
  const phases = createPhaseTracker();
  const changed = phases.finish();
  assert.deepEqual(changed, { from: "understanding", to: "delivering", reason: "本轮无待执行工具，进入收尾" });
  assert.equal(phases.finish(), null);
  assert.equal(phases.current(), "delivering");
});
