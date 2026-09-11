import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { IpcClient } from "../../cli/src/client.js";
import type { ChatMessage, ModelProvider } from "../src/agent-loop.js";
import { RuntimeServer } from "../src/server.js";

test("session images reach the first model call exactly once and survive history", { timeout: 30_000 }, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-images-"));
  const previous = process.env.SZTU_DATA_DIR;
  process.env.SZTU_DATA_DIR = root;
  const calls: ChatMessage[][] = [];
  const provider: ModelProvider = { complete: async (messages) => {
    calls.push(structuredClone(messages));
    return { text: "Image received", tool_calls: [], stop_reason: "end_turn" };
  } };
  const server = new RuntimeServer("127.0.0.1", 0, provider);
  server.mcp.load = async () => {};
  let client: IpcClient | undefined;
  try {
    const address = await server.listen();
    client = new IpcClient("127.0.0.1", Number(address.split(":").at(-1)));
    await client.connect();
    await client.request("settings.update", { supports_vision: true });
    const session = await client.request("session.create", { mode: "chat" });
    const image = { media_type: "image/png", data: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN9sAAAAASUVORK5CYII=" };
    const run = await client.request("session.send_message", { session_id: session.session_id, content: "Describe this screenshot", images: [image] });
    for (let i = 0; i < 200; i++) {
      const status = await client.request("session.get", { session_id: session.session_id });
      if ((status.session as { status: string }).status === "waiting_for_input") break;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    assert.ok(calls.length > 0);
    const users = calls[0]!.filter((message) => message.role === "user" && JSON.stringify(message.content).includes("Describe this screenshot"));
    assert.equal(users.length, 1);
    // 动态上下文以尾部 system-reminder 文本块追加到目标消息，不改变图像块的顺序与唯一性。
    const blocks = users[0]!.content as Array<{ type: string; text?: string }>;
    assert.deepEqual(blocks[0], { type: "text", text: "Describe this screenshot" });
    assert.deepEqual(blocks[1], { type: "image", source: { type: "base64", ...image } });
    for (const block of blocks.slice(2)) assert.equal(block.type, "text");
    const history = await client.request("session.get_history", { session_id: session.session_id });
    assert.ok(JSON.stringify(history.messages).includes(image.data));
  } finally {
    client?.close();
    await server.close();
    if (previous === undefined) delete process.env.SZTU_DATA_DIR;
    else process.env.SZTU_DATA_DIR = previous;
    await rm(root, { recursive: true, force: true });
  }
});
