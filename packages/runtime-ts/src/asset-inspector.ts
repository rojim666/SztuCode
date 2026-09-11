import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { open, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { artifactTypeForPath } from "./artifact-store.js";

const DEEP_READ_LIMIT = 16 * 1024 * 1024;
const SAMPLE_BYTES = 1024 * 1024;

async function sha256(file: string): Promise<string> {
  const hash = createHash("sha256");
  await new Promise<void>((resolve, reject) => {
    const stream = createReadStream(file);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", resolve);
  });
  return hash.digest("hex");
}

function wavDetails(buffer: Buffer): Record<string, unknown> | null {
  if (buffer.length < 44 || buffer.toString("ascii", 0, 4) !== "RIFF" || buffer.toString("ascii", 8, 12) !== "WAVE") return null;
  let offset = 12;
  let channels = 0; let sampleRate = 0; let bitsPerSample = 0; let byteRate = 0; let dataBytes = 0;
  while (offset + 8 <= buffer.length) {
    const id = buffer.toString("ascii", offset, offset + 4);
    const length = buffer.readUInt32LE(offset + 4);
    if (id === "fmt " && offset + 8 + Math.min(length, 16) <= buffer.length) {
      channels = buffer.readUInt16LE(offset + 10);
      sampleRate = buffer.readUInt32LE(offset + 12);
      byteRate = buffer.readUInt32LE(offset + 16);
      bitsPerSample = buffer.readUInt16LE(offset + 22);
    } else if (id === "data") { dataBytes = length; break; }
    offset += 8 + length + (length % 2);
  }
  return { format: "wav", channels, sample_rate_hz: sampleRate, bits_per_sample: bitsPerSample, duration_seconds: byteRate ? Number((dataBytes / byteRate).toFixed(3)) : null };
}

function mp4Details(buffer: Buffer): Record<string, unknown> | null {
  const marker = buffer.indexOf(Buffer.from("mvhd"));
  if (marker < 0 || marker + 32 > buffer.length) return null;
  const version = buffer[marker + 4];
  const timescaleOffset = version === 1 ? marker + 24 : marker + 16;
  const durationOffset = version === 1 ? marker + 28 : marker + 20;
  if (durationOffset + (version === 1 ? 8 : 4) > buffer.length) return null;
  const timescale = buffer.readUInt32BE(timescaleOffset);
  const duration = version === 1 ? Number(buffer.readBigUInt64BE(durationOffset)) : buffer.readUInt32BE(durationOffset);
  return { container: "mp4", duration_seconds: timescale ? Number((duration / timescale).toFixed(3)) : null };
}

function modelDetails(file: string, buffer: Buffer, complete: boolean): Record<string, unknown> | null {
  const extension = path.extname(file).toLowerCase();
  if (extension === ".gltf") {
    try {
      const value = JSON.parse(buffer.toString("utf8")) as Record<string, unknown>;
      const count = (key: string) => Array.isArray(value[key]) ? value[key].length : 0;
      return { format: "gltf", version: (value.asset as Record<string, unknown> | undefined)?.version ?? null, scenes: count("scenes"), nodes: count("nodes"), meshes: count("meshes"), materials: count("materials"), animations: count("animations"), images: count("images"), partial: !complete };
    } catch { return { format: "gltf", parse_error: "invalid JSON or truncated file", partial: !complete }; }
  }
  if (extension === ".glb" && buffer.length >= 20 && buffer.readUInt32LE(0) === 0x46546c67) {
    const jsonLength = buffer.readUInt32LE(12);
    try {
      const value = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString("utf8").replace(/\0+$/g, "")) as Record<string, unknown>;
      const count = (key: string) => Array.isArray(value[key]) ? value[key].length : 0;
      return { format: "glb", version: buffer.readUInt32LE(4), scenes: count("scenes"), nodes: count("nodes"), meshes: count("meshes"), materials: count("materials"), animations: count("animations") };
    } catch { return { format: "glb", version: buffer.readUInt32LE(4), parse_error: "JSON chunk is unavailable or invalid" }; }
  }
  if (extension === ".obj") {
    const lines = buffer.toString("utf8").split(/\r?\n/);
    const count = (prefix: string) => lines.filter((line) => line.startsWith(prefix)).length;
    return { format: "obj", vertices: count("v "), texture_coordinates: count("vt "), normals: count("vn "), faces: count("f "), objects: count("o "), groups: count("g "), partial: !complete };
  }
  if (extension === ".stl" && buffer.length >= 84 && !buffer.subarray(0, 5).toString("ascii").toLowerCase().startsWith("solid")) return { format: "stl-binary", triangles: buffer.readUInt32LE(80) };
  return null;
}

async function zipEntries(file: string, maxEntries: number): Promise<Record<string, unknown> | null> {
  const info = await stat(file);
  const handle = await open(file, "r");
  try {
    const tailSize = Math.min(info.size, 65_557);
    const tail = Buffer.alloc(tailSize);
    await handle.read(tail, 0, tailSize, info.size - tailSize);
    let eocd = -1;
    for (let index = tail.length - 22; index >= 0; index -= 1) {
      if (tail.readUInt32LE(index) === 0x06054b50) { eocd = index; break; }
    }
    if (eocd < 0) return null;
    const totalEntries = tail.readUInt16LE(eocd + 10);
    const centralSize = tail.readUInt32LE(eocd + 12);
    const centralOffset = tail.readUInt32LE(eocd + 16);
    if (centralSize > DEEP_READ_LIMIT || centralOffset + centralSize > info.size) return { format: "zip", entries: totalEntries, listing_truncated: true };
    const central = Buffer.alloc(centralSize);
    await handle.read(central, 0, centralSize, centralOffset);
    const entries: Array<Record<string, unknown>> = [];
    let offset = 0;
    while (offset + 46 <= central.length && entries.length < maxEntries && central.readUInt32LE(offset) === 0x02014b50) {
      const compressedSize = central.readUInt32LE(offset + 20);
      const size = central.readUInt32LE(offset + 24);
      const nameLength = central.readUInt16LE(offset + 28);
      const extraLength = central.readUInt16LE(offset + 30);
      const commentLength = central.readUInt16LE(offset + 32);
      const name = central.subarray(offset + 46, offset + 46 + nameLength).toString("utf8");
      entries.push({ path: name, size, compressed_size: compressedSize, directory: name.endsWith("/") });
      offset += 46 + nameLength + extraLength + commentLength;
    }
    return { format: "zip", entries: totalEntries, listing_truncated: totalEntries > entries.length, files: entries };
  } finally { await handle.close(); }
}

export async function inspectAsset(file: string, maxEntries = 200): Promise<Record<string, unknown>> {
  const info = await stat(file);
  const kind = artifactTypeForPath(file);
  const complete = info.size <= DEEP_READ_LIMIT;
  const head = complete ? await readFile(file) : await (async () => {
    const handle = await open(file, "r");
    try { const data = Buffer.alloc(Math.min(info.size, SAMPLE_BYTES)); await handle.read(data, 0, data.length, 0); return data; }
    finally { await handle.close(); }
  })();
  let details: Record<string, unknown> | null = null;
  if (path.extname(file).toLowerCase() === ".zip") details = await zipEntries(file, Math.min(1000, Math.max(1, maxEntries)));
  else if (kind === "audio") details = wavDetails(head);
  else if (kind === "video") details = mp4Details(head);
  else if (kind === "model3d") details = modelDetails(file, head, complete);
  else if (kind === "image" && head.length >= 24 && head.toString("hex", 0, 8) === "89504e470d0a1a0a") details = { format: "png", width: head.readUInt32BE(16), height: head.readUInt32BE(20) };
  return { name: path.basename(file), extension: path.extname(file).toLowerCase(), kind, size: info.size, modified_at: info.mtime.toISOString(), sha256: await sha256(file), details };
}
