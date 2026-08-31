import assert from "node:assert/strict";
import test from "node:test";
import { CodeSplitter, MarkdownSplitter, TextSplitter, createChunker, extractSymbols } from "../src/chunking/index.js";

test("代码分块保留声明边界、行号和语言元数据", () => {
  const content = [
    "const prefix = true;",
    "",
    "export function authenticate(user: string): boolean {",
    "  return user.length > 0;",
    "}",
    "",
    "function compactContext(input: string): string {",
    "  return input.trim();",
    "}",
  ].join("\n");
  const chunks = new CodeSplitter({ maxChars: 90, overlapLines: 2 }, "typescript").split(content, { source: "auth.ts" });
  assert.ok(chunks.length >= 2);
  assert.match(chunks[0]!.text, /authenticate/);
  assert.ok(chunks.some((chunk) => chunk.text.includes("compactContext")));
  assert.equal(chunks[0]!.metadata.type, "code");
  assert.equal(chunks[0]!.metadata.language, "typescript");
  assert.equal(chunks[0]!.metadata.source, "auth.ts");
  assert.equal(chunks[0]!.metadata.start_line, 1);
  assert.equal(chunks[0]!.metadata.chunk_index, 0);
  assert.match(String(chunks.find((chunk) => chunk.text.includes("authenticate"))?.metadata.symbol), /authenticate/);
  assert.match(String(chunks.find((chunk) => chunk.text.includes("compactContext"))?.metadata.symbol), /compactContext/);
  if (chunks.length > 1) assert.ok(Number(chunks[1]!.metadata.start_line) <= Number(chunks[0]!.metadata.end_line));
});

test("代码符号提取支持常见语言声明", () => {
  const symbols = extractSymbols([
    "export class AuthService {}",
    "def load_profile(value):",
    "func checkAccess() {}",
    "pub fn compact_context() {}",
  ].join("\n"));
  assert.deepEqual(symbols, [
    { name: "AuthService", kind: "class" },
    { name: "load_profile", kind: "python_function" },
    { name: "checkAccess", kind: "go_function" },
    { name: "compact_context", kind: "rust_function" },
  ]);
});

test("短代码不会被过度拆分，CRLF 会标准化", () => {
  const chunks = new CodeSplitter().split("function one() {\r\n  return 1;\r\n}\r\n", { source: "one.js" });
  assert.equal(chunks.length, 1);
  assert.match(chunks[0]!.text, /function one\(\) \{\n  return 1;/);
});

test("Markdown 按标题拆分，但围栏代码中的标题不作为边界", () => {
  const content = [
    "# 总览",
    "介绍内容。",
    "## 示例",
    "```ts",
    "# 这不是标题",
    "const value = 1;",
    "```",
    "示例说明。",
    "## 结论",
    "最终内容。",
  ].join("\n");
  const chunks = new MarkdownSplitter({ maxChars: 200 }).split(content, { source: "guide.md" });
  assert.equal(chunks.length, 3);
  assert.match(chunks[0]!.text, /^# 总览/);
  assert.match(chunks[1]!.text, /# 这不是标题/);
  assert.match(chunks[1]!.text, /示例说明/);
  assert.match(chunks[2]!.text, /^## 结论/);
  assert.equal(chunks[1]!.metadata.type, "markdown");
});

test("纯文本按段落合并并限制块大小，工厂按扩展名选择分块器", () => {
  const chunks = new TextSplitter({ maxChars: 15 }).split("第一段内容。\n\n第二段内容。\n\n第三段内容。", { source: "notes.txt" });
  assert.ok(chunks.length >= 2);
  assert.ok(chunks.every((chunk) => chunk.text.length <= 15));
  assert.equal(createChunker("main.ts").constructor, CodeSplitter);
  assert.equal(createChunker("README.md").constructor, MarkdownSplitter);
  assert.equal(createChunker("notes.txt").constructor, TextSplitter);
});

test("分块来源和参数错误会被明确拒绝", () => {
  assert.throws(() => new CodeSplitter({ overlapLines: -1 }), /overlapLines/);
  assert.throws(() => new MarkdownSplitter().split("内容", {}), /source/);
});
