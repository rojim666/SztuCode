import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createSemanticSearchTool, createWorkspaceTools } from "../src/tools.js";
import type { Embedder } from "../src/embedding/index.js";
import { Workspace } from "../src/workspace.js";

function fixedEmbedder(loads: { count: number }): Embedder {
  return {
    name: "fixed",
    dimensions: 2,
    maxTokens: 128,
    async embed(texts) { return texts.map((text) => text.includes("权限") || text.includes("permission") ? [1, 0] : [0, 1]); },
    async embedQuery(text) { loads.count += 1; return text.includes("权限") ? [1, 0] : [0, 1]; },
  };
}

test("semantic_search 首次调用自动索引并返回文件、行号和预览", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-semantic-tool-"));
  try {
    await writeFile(path.join(root, "auth.ts"), "export function checkPermission() {\n  // 权限检查\n  return true;\n}\n", "utf8");
    await writeFile(path.join(root, "notes.md"), "# 说明\n普通内容。", "utf8");
    const loads = { count: 0 };
    const tool = createSemanticSearchTool({ createEmbedder: () => fixedEmbedder(loads) });
    assert.equal(loads.count, 0);
    const result = await tool.invoke({ query: "权限检查", top_k: 2 }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    assert.match(result.output, /Semantic search results/);
    assert.match(result.output, /auth\.ts:\d+-\d+/);
    assert.match(result.output, /checkPermission/);
    assert.equal(loads.count, 1);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("semantic_search 支持路径、类型、分数和空索引选项", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-semantic-filter-"));
  try {
    await mkdir(path.join(root, "src"));
    await writeFile(path.join(root, "src", "auth.ts"), "// 权限 permission\n", "utf8");
    await writeFile(path.join(root, "README.md"), "权限说明", "utf8");
    const tool = createSemanticSearchTool({ createEmbedder: () => fixedEmbedder({ count: 0 }) });
    const context = { workspace: new Workspace(root) };
    const noIndex = await tool.invoke({ query: "权限", auto_index: false }, context);
    assert.match(noIndex.output, /index is empty/);
    const filtered = await tool.invoke({ query: "权限", path: "src", file_type: "code", min_score: 0.9 }, context);
    assert.equal(filtered.ok, true);
    assert.match(filtered.output, /src[\\/]auth\.ts/);
    assert.doesNotMatch(filtered.output, /README\.md/);
    const noMatch = await tool.invoke({ query: "权限", min_score: 1.1 }, context);
    assert.equal(noMatch.ok, false);
    assert.match(noMatch.error ?? "", /min_score/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("semantic_search 混合排序会提升精确符号命中", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-semantic-hybrid-"));
  try {
    await writeFile(path.join(root, "generic.ts"), "export function handleRequest() { return true; }", "utf8");
    await writeFile(path.join(root, "auth.ts"), "export function checkPermission() { return true; }", "utf8");
    const embedder: Embedder = {
      name: "hybrid-test",
      dimensions: 2,
      maxTokens: 128,
      async embed(texts) { return texts.map((text) => text.includes("handleRequest") ? [1, 0] : [0.8, 0.6]); },
      async embedQuery() { return [1, 0]; },
    };
    const tool = createSemanticSearchTool({ createEmbedder: () => embedder });
    const result = await tool.invoke({ query: "checkPermission", top_k: 1 }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    const firstResult = result.output.split("\n")[3] ?? "";
    assert.match(firstResult, /auth\.ts/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("createWorkspaceTools 注册 semantic_search 且保持只读权限", () => {
  const tool = createWorkspaceTools().get("semantic_search");
  assert.ok(tool);
  assert.equal(tool.permission, "read_only");
  assert.equal(tool.timeoutMs, 120_000);
  assert.deepEqual(tool.schema.required, ["query"]);
});
