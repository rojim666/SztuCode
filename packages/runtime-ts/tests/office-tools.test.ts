import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Workspace } from "../src/workspace.js";
import { createWorkspaceTools } from "../src/tools.js";

for (const [format, payload, operations] of [
  ["docx", { blocks: [{ kind: "heading", text: "季度总结" }, { kind: "paragraph", text: "中文办公测试" }] }, [{ kind: "replace_text", find: "季度总结", replace: "年度总结" }]],
  ["xlsx", { sheets: [{ name: "预算", rows: [["项目", "金额"], ["收入", 100]] }] }, [{ kind: "set_cell", sheet: "预算", cell: "B2", value: 200 }]],
  ["pptx", { slides: [{ title: "季度总结", bullets: ["中文办公测试"], notes: "演讲备注" }] }, [{ kind: "replace_text", find: "季度总结", replace: "年度总结" }]],
] as const) {
  test(`desktop agent can create, read and edit ${format} through Python`, async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "sztu-office-"));
    try {
      const changed: string[] = [];
      const context = { workspace: new Workspace(root), onFileChanged: (file: string) => changed.push(file) };
      const tools = createWorkspaceTools();
      assert.equal(tools.get("read_document")!.permission, "read_only");
      assert.equal(tools.get("create_document")!.permission, "workspace_write");
      const file = `中文 资料.${format}`;
      const created = await tools.get("create_document")!.invoke({ path: file, ...payload }, context);
      assert.equal(created.ok, true, created.error);
      const original = await readFile(path.join(root, file));
      const read = await tools.get("read_document")!.invoke({ path: file }, context);
      assert.equal(read.ok, true, read.error);
      const source = JSON.parse(read.output);
      assert.ok(source.blocks.length > 0);
      if (format === "pptx") {
        const parsed = await tools.get("parse_document")!.invoke({ path: file }, context);
        assert.equal(parsed.ok, true, parsed.error);
        assert.match(parsed.output, /演讲备注/);
      }
      const edited = await tools.get("edit_document")!.invoke({
        source: file, path: `edited.${format}`, source_sha256: source.sha256, operations,
      }, context);
      assert.equal(edited.ok, true, edited.error);
      assert.deepEqual(await readFile(path.join(root, file)), original);
      const reread = await tools.get("read_file")!.invoke({ path: `edited.${format}` }, context);
      assert.equal(reread.ok, true, reread.error);
      assert.match(reread.output, format === "xlsx" ? /200/ : /年度总结/);
      assert.deepEqual(changed, [file, `edited.${format}`]);
      const escaped = await tools.get("create_document")!.invoke({ path: `../escape.${format}`, ...payload }, context);
      assert.equal(escaped.ok, false);
    } finally { await rm(root, { recursive: true, force: true }); }
  });
}

test("cancelled office operations do not start", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-office-abort-"));
  try {
    const abort = new AbortController();
    abort.abort();
    const result = await createWorkspaceTools().get("create_document")!.invoke({
      path: "output.docx", blocks: [{ kind: "paragraph", text: "test" }],
    }, { workspace: new Workspace(root), signal: abort.signal });
    assert.equal(result.ok, false);
    assert.match(result.error!, /取消/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
