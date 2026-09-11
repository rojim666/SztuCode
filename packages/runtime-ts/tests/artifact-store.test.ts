import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, readFile, rm, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { ArtifactStore, artifactTypeForPath } from "../src/artifact-store.js";

test("artifact types cover editable and media deliverables", () => {
  assert.equal(artifactTypeForPath("report.docx"), "docx");
  assert.equal(artifactTypeForPath("dashboard.html"), "web");
  assert.equal(artifactTypeForPath("cover.png"), "image");
  assert.equal(artifactTypeForPath("narration.wav"), "audio");
  assert.equal(artifactTypeForPath("demo.mp4"), "video");
  assert.equal(artifactTypeForPath("scene.glb"), "model3d");
  assert.equal(artifactTypeForPath("installer.exe"), "app");
  assert.equal(artifactTypeForPath("project.zip"), "archive");
  assert.equal(artifactTypeForPath("src/main.ts"), "code");
});

test("artifact store registers versions, enforces workspace boundary, and reloads", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-artifact-"));
  try {
    await mkdir(path.join(root, "out")); await writeFile(path.join(root, "out/report.docx"), "v1");
    const store = new ArtifactStore(path.join(root, "meta"));
    const first = await store.register("ws", root, "out/report.docx", { type: "docx", session_id: "s", run_id: "r", input_sources: [{ path: "sales.csv", version: "1" }] });
    assert.equal(first.version, 1); assert.equal(first.generation_status, "ready"); assert.equal(first.verification_status, "unverified");
    await writeFile(path.join(root, "out/report.docx"), "v2"); const second = await store.register("ws", root, "out/report.docx", { summary: "updated" });
    assert.equal(second.artifact_id, first.artifact_id); assert.equal(second.version, 2); assert.equal(second.versions.length, 2);
    await store.updateVerification("ws", first.artifact_id, "passed");
    const restored = await store.restore("ws", root, first.artifact_id, 1, second.hash);
    assert.equal(await readFile(path.join(root, "out/report.docx"), "utf8"), "v1");
    assert.equal(restored.verification_status, "unverified");
    assert.equal(restored.version, 4);
    await writeFile(path.join(root, "out/report.docx"), "manual edit");
    await assert.rejects(() => store.restore("ws", root, first.artifact_id, 2, restored.hash), /changed since/);
    assert.equal(await readFile(path.join(root, "out/report.docx"), "utf8"), "manual edit");
    await assert.rejects(() => store.register("ws", root, "../outside.docx"));
    const reloaded = new ArtifactStore(path.join(root, "meta")); assert.equal((await reloaded.get("ws", first.artifact_id)).version, 4);
    await writeFile(path.join(root, "out/demo.mp4"), "video");
    assert.equal((await store.register("ws", root, "out/demo.mp4")).type, "video");
  } finally { await rm(root, { recursive: true, force: true }); }
});
