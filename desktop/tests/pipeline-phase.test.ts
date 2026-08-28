import assert from "node:assert/strict";
import test from "node:test";
import type { TimelineStep, ToolCallEntry } from "../src/components/timeline/types";
import { buildPipelineSegments, classifyTool, phaseStates } from "../src/components/timeline/pipeline/phase";

function step(step: number, patch: Partial<TimelineStep> = {}): TimelineStep {
  return { step, status: "done", tokens: [], toolCalls: [], ...patch };
}

function call(id: string, name: string, params: Record<string, unknown> = {}, status: ToolCallEntry["status"] = "done"): ToolCallEntry {
  return { id, name, params, status };
}

test("classifyTool 区分只读、写入与验证工具", () => {
  assert.equal(classifyTool("read_file", { path: "a.ts" }), "read");
  assert.equal(classifyTool("list_dir", {}), "read");
  assert.equal(classifyTool("glob_search", {}), "read");
  assert.equal(classifyTool("write_file", {}), "write");
  assert.equal(classifyTool("edit_file", {}), "write");
  // bash 的归类取决于命令本身
  assert.equal(classifyTool("bash", { command: "npm test" }), "verify");
  assert.equal(classifyTool("bash", { command: "uv run pytest -q" }), "verify");
  assert.equal(classifyTool("bash", { command: "tsc --noEmit" }), "verify");
  assert.equal(classifyTool("bash", { command: "ls -la" }), "other");
  assert.equal(classifyTool("bash", {}), "other");
  // 未登记的工具按名字兜底，不应退化成误判
  assert.equal(classifyTool("frobnicate", {}), "other");
});

test("相邻 token 事件合并成一段正文，不会拆成上百张卡片", () => {
  const segments = buildPipelineSegments([
    step(1, {
      events: [
        { id: "t1", kind: "text", text: "我先" },
        { id: "t2", kind: "text", text: "看看" },
        { id: "t3", kind: "text", text: "代码" },
      ],
    }),
  ]);
  assert.equal(segments.length, 1);
  assert.equal(segments[0].kind, "text");
  assert.equal(segments[0].kind === "text" && segments[0].text, "我先看看代码");
});

test("连续同类工具收成一组，不同类则分开", () => {
  const segments = buildPipelineSegments([
    step(1, {
      toolCalls: [call("a", "read_file", { path: "a.ts" }), call("b", "read_file", { path: "b.ts" }), call("c", "write_file", { path: "b.ts" })],
      events: [
        { id: "e1", kind: "tool", toolCallId: "a" },
        { id: "e2", kind: "tool", toolCallId: "b" },
        { id: "e3", kind: "tool", toolCallId: "c" },
      ],
    }),
  ]);
  assert.deepEqual(segments.map((segment) => [segment.kind, segment.kind === "tools" ? segment.calls.length : 0]), [["tools", 2], ["tools", 1]]);
});

test("阶段随工具类型推进：理解 → 执行 → 验证 → 交付", () => {
  const segments = buildPipelineSegments([
    step(1, {
      toolCalls: [call("r", "read_file", { path: "a.ts" }), call("w", "edit_file", { path: "a.ts" }), call("v", "bash", { command: "npm test" })],
      events: [
        { id: "e1", kind: "tool", toolCallId: "r" },
        { id: "e2", kind: "tool", toolCallId: "w" },
        { id: "e3", kind: "tool", toolCallId: "v" },
      ],
    }),
    step(2, { events: [{ id: "t", kind: "text", text: "改完并验证通过了" }] }),
  ]);
  assert.deepEqual(segments.map((segment) => segment.phase), ["understanding", "executing", "verifying", "delivering"]);
});

test("工具仍在运行时不进入交付阶段", () => {
  const segments = buildPipelineSegments([
    step(1, { status: "acting", toolCalls: [call("r", "read_file", {}, "running")], events: [{ id: "e1", kind: "tool", toolCallId: "r" }] }),
    step(2, { status: "thinking", events: [{ id: "t", kind: "text", text: "正在处理" }] }),
  ]);
  assert.equal(segments.at(-1)?.phase, "understanding");
});

test("phaseStates 标出已到达的阶段与当前阶段", () => {
  const segments = buildPipelineSegments([
    step(1, {
      toolCalls: [call("w", "edit_file", {})],
      events: [{ id: "e1", kind: "tool", toolCallId: "w" }],
    }),
    step(2, { events: [{ id: "t", kind: "text", text: "完成" }] }),
  ]);
  const states = phaseStates(segments, true);
  assert.deepEqual(states.map((state) => state.phase), ["understanding", "executing", "verifying", "delivering"]);
  assert.equal(states.find((state) => state.phase === "executing")?.reached, true);
  assert.equal(states.find((state) => state.phase === "verifying")?.reached, false);
  assert.equal(states.find((state) => state.phase === "delivering")?.active, true);
});

test("无事件时按 thinking / 正文 / 工具兜底构造，与经典视图一致", () => {
  const segments = buildPipelineSegments([
    step(1, { thinking: "想想", toolCalls: [call("a", "read_file", {})], finalText: "结论" }),
  ]);
  assert.deepEqual(segments.map((segment) => segment.kind), ["thinking", "text", "tools"]);
});