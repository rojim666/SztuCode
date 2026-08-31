import assert from "node:assert/strict";
import test from "node:test";
import { LexicalIndex, tokenizeSearchText } from "../src/retrieval/index.js";
import type { Chunk } from "../src/chunking/index.js";

function chunk(source: string, text: string, metadata: Record<string, string | number> = {}): Chunk {
  return { text, metadata: { source, type: "code", chunk_index: 0, ...metadata } };
}

test("关键词分词同时支持中文短语、下划线和驼峰标识符", () => {
  const tokens = tokenizeSearchText("权限检查 checkPermission");
  assert.ok(tokens.includes("权限检查"));
  assert.ok(tokens.includes("权限"));
  assert.ok(tokens.includes("checkpermission"));
  assert.ok(tokens.includes("permission"));
});

test("关键词索引优先返回精确符号和短语命中", () => {
  const index = new LexicalIndex();
  index.replace("src/permissions.ts", [chunk("src/permissions.ts", "export function checkPermission() {}", { symbol: "checkPermission", symbol_kind: "function" })]);
  index.replace("src/context.ts", [chunk("src/context.ts", "检查上下文是否需要压缩。", { symbol: "compactContext" })]);
  const exact = index.search("checkPermission", 5);
  assert.equal(exact[0]!.metadata.symbol, "checkPermission");
  const chinese = index.search("上下文压缩", 5);
  assert.equal(chinese[0]!.metadata.source, "src/context.ts");
});

test("关键词索引在排序前应用目录和类型过滤", () => {
  const index = new LexicalIndex();
  index.replace("src/auth.ts", [chunk("src/auth.ts", "权限检查 permission", { symbol: "checkPermission" })]);
  index.replace("docs/auth.md", [{ ...chunk("docs/auth.md", "权限检查 permission", { type: "markdown" }), metadata: { source: "docs/auth.md", type: "markdown", chunk_index: 0 } }]);
  const results = index.search("permission", 5, { pathPrefix: "src", fileType: "code" });
  assert.equal(results.length, 1);
  assert.equal(results[0]!.metadata.source, "src/auth.ts");
});
