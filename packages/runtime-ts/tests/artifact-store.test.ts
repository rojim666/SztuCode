import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, rm, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { ArtifactStore } from "../src/artifact-store.js";

test("artifact store registers versions, enforces workspace boundary, and reloads", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-artifact-"));
  try {
    await mkdir(path.join(root, "out")); await writeFile(path.join(root, "out/report.docx"), "v1");
    const store = new ArtifactStore(path.join(root, "meta"));
    const first = await store.register("ws", root, "out/report.docx", { type: "docx", session_id: "s", run_id: "r", input_sources: [{ path: "sales.csv", version: "1" }] });
    assert.equal(first.version, 1); assert.equal(first.generation_status, "ready"); assert.equal(first.verification_status, "unverified");
    await writeFile(path.join(root, "out/report.docx"), "v2"); const second = await store.register("ws", root, "out/report.docx", { summary: "updated" });
    assert.equal(second.artifact_id, first.artifact_id); assert.equal(second.version, 2); assert.equal(second.versions.length, 2);
    await assert.rejects(() => store.register("ws", root, "../outside.docx"));
    const reloaded = new ArtifactStore(path.join(root, "meta")); assert.equal((await reloaded.get("ws", first.artifact_id)).version, 2);
  } finally { await rm(root, { recursive: true, force: true }); }
});
