import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, rm, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { SessionStore } from "../src/session-store.js";

test("session store offloads large image base64 and hydrates it on read", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-session-image-"));
  try {
    const store = new SessionStore(root); const session = await store.create();
    const data = Buffer.alloc(128 * 1024, 7).toString("base64");
    await store.appendMessage(session.id, { role: "user", content: [{ type: "image", source: { media_type: "image/png", data } }] });
    const raw = await readFile(path.join(root, session.id, "thread.jsonl"), "utf8");
    assert.doesNotMatch(raw, new RegExp(data.slice(0, 128)));
    assert.match(raw, /image_ref/);
    const restored = await store.history(session.id);
    assert.equal((restored[0]!.content as any[])[0].source.data, data);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("session store degrades a missing offloaded image reference without losing the session", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-session-image-missing-"));
  try {
    const store = new SessionStore(root); const session = await store.create();
    const data = Buffer.alloc(128 * 1024, 3).toString("base64");
    await store.appendMessage(session.id, { role: "user", content: [{ type: "image", source: { media_type: "image/png", data } }] });
    const raw = JSON.parse((await readFile(path.join(root, session.id, "thread.jsonl"), "utf8")).trim());
    await unlink(path.join(root, session.id, raw.content[0].source.image_ref));
    const restored = await store.history(session.id);
    assert.equal((restored[0]!.content as any[])[0].type, "text");
    assert.match((restored[0]!.content as any[])[0].text, /Image unavailable/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
