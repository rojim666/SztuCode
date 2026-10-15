import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { IpcClient } from "../../cli/src/client.js";
import { RuntimeServer } from "../src/server.js";

test("索引 RPC 校验工作区，后台构建可查询状态，清除不删除源目录", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-rpc-"));
  const previous = process.env.SZTU_DATA_DIR;
  process.env.SZTU_DATA_DIR = path.join(root, "data");
  const server = new RuntimeServer("127.0.0.1", 0);
  server.mcp.load = async () => {};
  let client: IpcClient | undefined;
  try {
    const workspacePath = path.join(root, "workspace");
    await mkdir(workspacePath);
    const address = await server.listen();
    client = new IpcClient("127.0.0.1", Number(address.split(":").at(-1)));
    await client.connect();
    const opened = await client.request("workspace.open", { path: workspacePath });
    const workspace_id = (opened.workspace as { workspace_id: string } | undefined)?.workspace_id ?? opened.workspace_id;
    assert.ok(workspace_id);
    assert.equal((await client.request("index.status", { workspace_id })).state, "not_started");
    assert.equal((await client.request("index.build", { workspace_id })).state, "indexing");
    let status: Record<string, unknown> = {};
    for (let attempt = 0; attempt < 100; attempt += 1) {
      status = await client.request("index.stats", { workspace_id });
      if (status.state !== "indexing") break;
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    assert.equal(status.state, "ready");
    assert.equal(status.chunks, 0);
    await assert.rejects(client.request("index.update", { workspace_id, files: ["../outside.ts"] }), /escapes/);
    await assert.rejects(client.request("index.update", { workspace_id, files: "invalid" }), /array/);
    await assert.rejects(client.request("index.status", { workspace_id: "missing" }));
    assert.equal((await client.request("index.clear", { workspace_id })).state, "not_started");
  } finally {
    client?.close();
    await server.close();
    if (previous === undefined) delete process.env.SZTU_DATA_DIR; else process.env.SZTU_DATA_DIR = previous;
    await rm(root, { recursive: true, force: true, maxRetries: 5 });
  }
});
