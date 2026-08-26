import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { JsonlSessionBackend, SessionStoreBackendAdapter } from "../src/index.js";
import type { SessionHeader } from "@sztucode/session";

const makeHeader = (id: string): SessionHeader => ({ type: "session", version: 1, id, parentSessionId: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), title: "Test" });
const temp = async () => mkdtemp(path.join(os.tmpdir(), "sztu-session-"));

test("append is durable, ordered, and rejects duplicate IDs", async () => {
  const root = await temp(); const backend = new JsonlSessionBackend(root); await backend.create(makeHeader("s1"));
  const first = await backend.append("s1", { type: "message", message: { role: "user", content: "hello" } });
  await backend.append("s1", { type: "message", message: { role: "assistant", content: "world" } });
  assert.deepEqual((await backend.history("s1")).map((entry) => entry.id), [first.id, (await backend.get("s1")).entries[1]!.id]);
  await assert.rejects(() => backend.append("s1", { type: "message", id: first.id, message: { role: "user", content: "duplicate" } }));
  assert.equal((await backend.get("s1")).entries.length, 2);
});

test("fork copies a branch and records parent session", async () => {
  const backend = new JsonlSessionBackend(await temp()); await backend.create(makeHeader("s1")); const a = await backend.append("s1", { type: "message", message: { role: "user", content: "a" } }); const b = await backend.append("s1", { type: "message", parentId: a.id, message: { role: "assistant", content: "b" } }); await backend.append("s1", { type: "message", parentId: a.id, message: { role: "assistant", content: "c" } });
  const fork = await backend.fork("s1", { entryId: b.id, id: "fork" }); assert.equal(fork.header.parentSessionId, "s1"); assert.equal(fork.entries.length, 2); assert.equal((await backend.get("s1")).entries.length, 3); assert.deepEqual((await backend.history("s1")).map((entry) => entry.id), [a.id, (await backend.get("s1")).entries[2]!.id]);
});

test("recovers an incomplete final line but rejects a corrupt middle line", async () => {
  const root = await temp(); const backend = new JsonlSessionBackend(root); await backend.create(makeHeader("s1")); await backend.append("s1", { type: "message", message: { role: "user", content: "ok" } }); const file = path.join(root, "s1.jsonl"); await writeFile(file, `${await readFile(file, "utf8")}{{incomplete`, "utf8"); assert.equal((await backend.get("s1")).entries.length, 1); await writeFile(file, `${JSON.stringify(makeHeader("s1"))}\nnot-json\n`, "utf8"); await assert.rejects(() => backend.get("s1"));
});

test("reads and migrates the legacy ~/.sztu session layout without deleting it", async () => {
  const root = await temp(); const directory = path.join(root, "legacy"); await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, "meta.json"), JSON.stringify({ id: "legacy", mode: "chat", status: "waiting_for_input", title: "Old", created_at: "2024-01-01T00:00:00.000Z", updated_at: "2024-01-01T00:00:01.000Z", workspace_id: null }), "utf8");
  await writeFile(path.join(directory, "thread.jsonl"), `${JSON.stringify({ role: "user", content: "old prompt", ts: "2024-01-01T00:00:01.000Z" })}\n`, "utf8");
  const backend = new JsonlSessionBackend(root); const legacy = await backend.get("legacy"); assert.equal(legacy.entries[0]!.type, "message"); await backend.migrateLegacy("legacy"); assert.equal((await backend.get("legacy")).entries.length, 1); await backend.append("legacy", { type: "message", message: { role: "assistant", content: "new reply" } }); assert.equal((await backend.get("legacy")).entries.length, 2);
});

test("legacy adapter preserves visible history semantics", async () => {
  const sessions = new Map<string, any>([["old", { id: "old", title: "Old", created_at: "2024-01-01", updated_at: "2024-01-01", workspace_id: null }]]);
  const rows: Array<{ role: "user" | "assistant"; content: string; ts: string }> = [{ role: "user", content: "hello", ts: "2024-01-01" }];
  const store = { async create() { return sessions.get("old"); }, async get(id: string) { return sessions.get(id); }, async history() { return rows; }, async appendMessage(_id: string, message: any) { rows.push(message); }, async fork() { return sessions.get("old"); }, async delete() {}, async list() { return [...sessions.values()]; } };
  const adapter = new SessionStoreBackendAdapter(store); assert.equal((await adapter.history("old")).length, 1); const entry = await adapter.append("old", { type: "message", message: { role: "assistant", content: "reply" } }); assert.equal(entry.type, "message"); assert.equal((await adapter.history("old")).length, 2);
});
