import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { RuntimeServer } from "../src/server.js";

test("ServerService creates and opens transport-free AgentSession handles", async () => {
  const dataRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-server-service-"));
  const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = dataRoot;
  const server = new RuntimeServer("127.0.0.1", 0);
  try {
    await server.listen();
    const created = await server.service.createSession({ mode: "chat", title: "service session" });
    const snapshot = await created.snapshot();
    assert.equal(snapshot.session_id, created.id);
    assert.equal(snapshot.title, "service session");
    const opened = await server.service.openSession(created.id);
    assert.deepEqual(await opened.snapshot(true), { ...snapshot, attached: true, locked: true });
    assert.deepEqual(await opened.history(), []);
    opened.detach();
  } finally {
    await server.close();
    if (previous === undefined) delete process.env.SZTU_DATA_DIR; else process.env.SZTU_DATA_DIR = previous;
    await rm(dataRoot, { recursive: true, force: true });
  }
});
