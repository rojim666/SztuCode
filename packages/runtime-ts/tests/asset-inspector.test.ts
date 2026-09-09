import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { inspectAsset } from "../src/asset-inspector.js";

function zipWithEntry(name: string, data: Buffer): Buffer {
  const fileName = Buffer.from(name);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt32LE(data.length, 18);
  local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(fileName.length, 26);
  const centralOffset = local.length + fileName.length + data.length;
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt32LE(data.length, 20);
  central.writeUInt32LE(data.length, 24);
  central.writeUInt16LE(fileName.length, 28);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(1, 8);
  eocd.writeUInt16LE(1, 10);
  eocd.writeUInt32LE(central.length + fileName.length, 12);
  eocd.writeUInt32LE(centralOffset, 16);
  return Buffer.concat([local, fileName, data, central, fileName, eocd]);
}

function oneSecondWav(): Buffer {
  const sampleRate = 8_000;
  const samples = Buffer.alloc(sampleRate * 2);
  const header = Buffer.alloc(44);
  header.write("RIFF", 0); header.writeUInt32LE(36 + samples.length, 4); header.write("WAVE", 8);
  header.write("fmt ", 12); header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22); header.writeUInt32LE(sampleRate, 24); header.writeUInt32LE(sampleRate * 2, 28);
  header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34); header.write("data", 36); header.writeUInt32LE(samples.length, 40);
  return Buffer.concat([header, samples]);
}

test("asset inspector safely describes archives, recordings, and editable 3D sources", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-assets-"));
  try {
    const archive = path.join(root, "materials.zip");
    const recording = path.join(root, "recording.wav");
    const model = path.join(root, "model.obj");
    await writeFile(archive, zipWithEntry("notes/readme.txt", Buffer.from("hello")));
    await writeFile(recording, oneSecondWav());
    await writeFile(model, "o Cube\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n");

    const archiveResult = await inspectAsset(archive);
    assert.equal(archiveResult.kind, "archive");
    assert.equal((archiveResult.details as { entries: number }).entries, 1);
    assert.equal(((archiveResult.details as { files: Array<{ path: string }> }).files)[0].path, "notes/readme.txt");

    const audioResult = await inspectAsset(recording);
    assert.equal(audioResult.kind, "audio");
    assert.equal((audioResult.details as { duration_seconds: number }).duration_seconds, 1);

    const modelResult = await inspectAsset(model);
    assert.equal(modelResult.kind, "model3d");
    assert.equal((modelResult.details as { vertices: number }).vertices, 3);
    assert.equal((modelResult.details as { faces: number }).faces, 1);
    assert.match(String(modelResult.sha256), /^[a-f0-9]{64}$/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
