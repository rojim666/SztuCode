import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";
import type { ChatMessage } from "../src/agent-loop.js";
import { TokenCounter } from "../src/context.js";
import { toAnthropicMessages } from "../src/providers/anthropic.js";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { preprocessImage } from "../src/providers/image-utils.js";
import { SessionStore } from "../src/session-store.js";
import { createWorkspaceTools, ToolRegistry } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";

const image = { type: "image" as const, source: { media_type: "image/png", data: "aW1hZ2U=", width: 1600, height: 800 } };
const messages: ChatMessage[] = [
  { role: "user", content: "查看截图" },
  { role: "assistant", content: "", tool_calls: [{ id: "first", name: "view_image", input: { path: "a.png" } }, { id: "second", name: "read_file", input: { path: "a.txt" } }] },
  { role: "tool", tool_call_id: "first", content: [{ type: "text", text: "截图" }, image] },
  { role: "tool", tool_call_id: "second", content: "文字" },
];

test("Anthropic 工具结果保留真实图片块，不把 base64 序列化成文字", () => {
  const result = toAnthropicMessages(messages).at(-1)!.content[0]!;
  assert.deepEqual(result.content, [{ type: "text", text: "截图" }, { type: "image", source: { type: "base64", media_type: "image/png", data: image.source.data } }]);
});

for (const apiFormat of ["openai_chat_completions", "openai_responses"] as const) {
  test(`${apiFormat} 在全部工具结果后发送一次图片，保留调用顺序`, async () => {
    const originalFetch = globalThis.fetch;
    let body: any;
    const originalMessages = structuredClone(messages);
    globalThis.fetch = async (_input, init) => {
      body = JSON.parse(String(init?.body));
      return new Response(JSON.stringify(apiFormat === "openai_responses" ? { output_text: "收到", output: [] } : { choices: [{ message: { content: "收到" }, finish_reason: "stop" }] }), { status: 200 });
    };
    try {
      await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "vision", apiFormat }).complete(messages, new ToolRegistry());
      const rows = apiFormat === "openai_responses" ? body.input : body.messages;
      const tools = rows.filter((row: any) => row.role === "tool" || row.type === "function_call_output");
      assert.equal(tools.length, 2);
      assert.equal(tools[0].content ?? tools[0].output, "截图");
      const last = rows.at(-1);
      assert.equal(last.role, "user");
      assert.ok(JSON.stringify(last).includes(`data:image/png;base64,${image.source.data}`));
      assert.equal(JSON.stringify(rows).split(image.source.data).length - 1, 1);
      assert.deepEqual(messages, originalMessages);
    } finally { globalThis.fetch = originalFetch; }
  });
}

test("图片预算包含 URL 和嵌套工具结果，且不按 base64 文本计数", () => {
  const counter = TokenCounter.forModel("anthropic");
  const expected = counter.rawCountBlock(image);
  assert.equal(counter.rawCountBlock({ type: "tool_result", tool_use_id: "first", content: [image] }), expected);
  assert.ok(counter.rawCountBlock({ type: "image_url", image_url: "https://example.com/a.png" }) > 0);
  assert.equal(counter.rawCountBlock({ ...image, source: { ...image.source, data: "x".repeat(500_000) } }), expected);
});

test("图片存入独立文件，恢复尺寸信息和事件预览，重复保存不复制图片", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-image-persistence-"));
  try {
    const sessions = new SessionStore(root);
    const session = await sessions.create("chat");
    const data = Buffer.alloc(120 * 1024, 42).toString("base64");
    const block = { ...image, source: { ...image.source, data } };
    await sessions.replaceModelHistory(session.id, [{ role: "tool", tool_call_id: "first", content: [block] }]);
    await sessions.replaceModelHistory(session.id, [{ role: "tool", tool_call_id: "first", content: [block] }]);
    await sessions.appendRunEvent(session.id, { type: "tool.call_finished", run_id: "run", images: [{ mimeType: "image/png", data }] });
    for (const file of ["context.json", "runs/run.jsonl"]) assert.ok((await readFile(path.join(root, session.id, file), "utf8")).length < 2000);
    assert.equal((await readdir(path.join(root, session.id, "images"))).length, 1);
    const restored = new SessionStore(root);
    const content = (await restored.modelHistory(session.id))[0]!.content as any[];
    assert.equal(content[0].source.width, 1600);
    assert.equal(content[0].source.data, data);
    assert.equal(((await restored.runEvents(session.id, "run"))[0]!.images as any[])[0].data, data);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("view_image 缩放大图并同时返回桌面预览，拒绝伪造类型", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-image-tool-"));
  try {
    const png = await sharp({ create: { width: 3000, height: 1500, channels: 3, background: "red" } }).png().toBuffer();
    await writeFile(path.join(root, "large.png"), png);
    const tool = createWorkspaceTools().get("view_image")!;
    const context = { workspace: new Workspace(root) };
    const result = await tool.invoke({ path: "large.png", max_dimension: 1024 }, context);
    assert.equal(result.ok, true);
    const source = (result.content![1] as any).source;
    assert.equal(source.width, 1024);
    assert.equal(source.height, 512);
    assert.equal(result.images![0]!.data, source.data);
    assert.equal((await tool.invoke({ path: "large.png", max_dimension: 0 }, context)).ok, false);
    await assert.rejects(preprocessImage(png, "image/jpeg"), /does not match/);
    await assert.rejects(preprocessImage(png, "image/png", { maxBytes: 1 }), /too large/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
