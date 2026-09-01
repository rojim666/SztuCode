import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { CanvasDocumentEvent } from "@sztucode/protocol";
import { EventBus } from "../src/event-bus.js";
import { CanvasDocumentStore, canvasStoreFor, createCanvasTools, resetCanvasStores } from "../src/canvas-document.js";

test("canvas store creates, updates, appends and evicts documents", () => {
  const store = new CanvasDocumentStore();
  const first = store.create({ title: "调研报告", content: "# 标题\n\n| A | B |\n|---|---|" });
  assert.equal(first.id, "doc-01");
  assert.equal(first.version, 1);

  const updated = store.update(first.id, { content: "新内容", title: "  新标题  " });
  assert.equal(updated?.version, 2);
  assert.equal(updated?.title, "新标题");
  assert.equal(updated?.content, "新内容");

  const appended = store.update(first.id, { content: "追加段落", append: true });
  assert.equal(appended?.content, "新内容\n\n追加段落");
  assert.equal(appended?.version, 3);

  assert.equal(store.update("missing", { content: "x" }), null);
  assert.equal(store.list().length, 1);

  // 显式 ID 冲突时自动加后缀，不覆盖既有文档
  const a = store.create({ title: "A", content: "a", id: "Report v1!" });
  const b = store.create({ title: "B", content: "b", id: "report-v1" });
  assert.equal(a.id, "report-v1");
  assert.equal(b.id, "report-v1-2");

  // 容量上限：超过 20 篇时淘汰最旧
  for (let i = 0; i < 25; i++) store.create({ title: `T${i}`, content: "x" });
  assert.equal(store.list().length, 20);
});

test("canvas tools publish canvas.document events and enforce schema", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-canvas-"));
  try {
    resetCanvasStores();
    const events = new EventBus(path.join(root, "events.jsonl"));
    const published: CanvasDocumentEvent[] = [];
    events.subscribe((event) => { if (event.type === "canvas.document") published.push(event as CanvasDocumentEvent); });
    const tools = createCanvasTools(events, "run-1", "session-1");
    const byName = (name: string) => tools.find((tool) => tool.name === name)!;

    assert.equal(byName("canvas_create").permission, "workspace_write");
    assert.equal(byName("canvas_update").permission, "workspace_write");
    assert.equal(byName("canvas_get").permission, "read_only");
    assert.equal(byName("canvas_list").permission, "read_only");

    // 参数校验：缺 title/content 报 schema_error
    const invalid = await byName("canvas_create").invoke({ title: "", content: "" }, { workspace: undefined as never });
    assert.equal(invalid.ok, false);
    assert.equal(invalid.errorType, "schema_error");

    const created = await byName("canvas_create").invoke({ title: "发布方案", content: "# 方案\n\n正文", document_id: "Release Plan" }, { workspace: undefined as never });
    assert.equal(created.ok, true);
    const createdMeta = JSON.parse(created.output) as { document_id: string; version: number };
    assert.equal(createdMeta.document_id, "release-plan");
    assert.equal(createdMeta.version, 1);

    assert.equal(published.length, 1);
    assert.equal(published[0]!.action, "create");
    assert.equal(published[0]!.run_id, "run-1");
    assert.equal(published[0]!.session_id, "session-1");
    assert.equal(published[0]!.document.kind, "markdown");
    assert.equal(published[0]!.document.content, "# 方案\n\n正文");

    // 更新：版本递增并再次发布事件
    const updated = await byName("canvas_update").invoke({ document_id: "release-plan", content: "# 方案 v2", mode: "replace" }, { workspace: undefined as never });
    assert.equal(updated.ok, true);
    assert.equal((JSON.parse(updated.output) as { version: number }).version, 2);
    assert.equal(published.length, 2);
    assert.equal(published[1]!.action, "update");

    // 更新不存在的文档：明确失败
    const missing = await byName("canvas_update").invoke({ document_id: "nope", content: "x" }, { workspace: undefined as never });
    assert.equal(missing.ok, false);

    // get / list
    const got = await byName("canvas_get").invoke({ document_id: "release-plan" }, { workspace: undefined as never });
    assert.equal(got.ok, true);
    assert.equal((JSON.parse(got.output) as { content: string }).content, "# 方案 v2");
    const listed = await byName("canvas_list").invoke({}, { workspace: undefined as never });
    const docs = JSON.parse(listed.output) as Array<{ document_id: string }>;
    assert.deepEqual(docs.map((doc) => doc.document_id), ["release-plan"]);

    // 同一会话跨 run 复用文档集合（新一轮 run 的工具仍能读到上一轮的文档）
    const nextRunTools = createCanvasTools(events, "run-2", "session-1");
    const relisted = await nextRunTools.find((tool) => tool.name === "canvas_list")!.invoke({}, { workspace: undefined as never });
    assert.equal((JSON.parse(relisted.output) as Array<unknown>).length, 1);
    // 不同会话互不可见
    const otherSession = canvasStoreFor("session-2");
    assert.equal(otherSession.list().length, 0);
    resetCanvasStores();
  } finally { await rm(root, { recursive: true, force: true }); }
});
