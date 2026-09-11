import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile, rename, unlink, stat, chmod } from "node:fs/promises";
import path from "node:path";
import type { ArtifactType } from "@sztucode/protocol";
import { Workspace } from "./workspace.js";

export type ArtifactStatus = "draft" | "ready" | "failed";
export type VerificationStatus = "unverified" | "passed" | "failed";
export interface ArtifactVersion { version: number; hash: string; size: number; created_at: string; path: string; snapshot?: string; }
export interface ArtifactRecord { artifact_id: string; workspace_id: string; session_id?: string; run_id?: string; type: ArtifactType; path: string; summary: string; hash: string; version: number; input_sources: Array<{ path: string; version?: string; hash?: string }>; generation_status: ArtifactStatus; verification_status: VerificationStatus; preview?: { mime_type: string; text?: string; thumbnail_path?: string }; delivery_ids: string[]; versions: ArtifactVersion[]; created_at: string; updated_at: string; }

export function artifactTypeForPath(filePath: string): ArtifactType {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === ".docx") return "docx";
  if (extension === ".pptx") return "pptx";
  if (extension === ".pdf") return "pdf";
  if ([".xlsx", ".xlsm", ".ods"].includes(extension)) return "xlsx";
  if ([".csv", ".tsv"].includes(extension)) return "csv";
  if ([".html", ".htm", ".xhtml"].includes(extension)) return "web";
  if ([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp"].includes(extension)) return "image";
  if ([".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"].includes(extension)) return "audio";
  if ([".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"].includes(extension)) return "video";
  if ([".glb", ".gltf", ".obj", ".fbx", ".stl", ".ply", ".dae", ".3mf"].includes(extension)) return "model3d";
  if ([".exe", ".msi", ".apk", ".dmg", ".deb", ".appimage"].includes(extension)) return "app";
  if ([".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"].includes(extension)) return "archive";
  if ([".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".css", ".scss", ".vue", ".svelte", ".swift", ".kt"].includes(extension)) return "code";
  return "other";
}

export class ArtifactStore {
  private static queues = new Map<string, Promise<unknown>>();
  constructor(private readonly root: string) {}
  private file(workspaceId: string) { if (!/^[\w-]+$/.test(workspaceId)) throw new Error("invalid workspace id"); return path.join(this.root, `${workspaceId}.json`); }
  private async serial<T>(workspaceId: string, action: () => Promise<T>): Promise<T> {
    const key = path.resolve(this.file(workspaceId));
    const current = (ArtifactStore.queues.get(key) ?? Promise.resolve()).catch(() => {}).then(action);
    ArtifactStore.queues.set(key, current);
    try { return await current; } finally { if (ArtifactStore.queues.get(key) === current) ArtifactStore.queues.delete(key); }
  }
  private async load(workspaceId: string): Promise<ArtifactRecord[]> { try { return JSON.parse(await readFile(this.file(workspaceId), "utf8")) as ArtifactRecord[]; } catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return []; throw error; } }
  private async save(workspaceId: string, records: ArtifactRecord[]) { await mkdir(this.root, { recursive: true }); const target = this.file(workspaceId); const tmp = `${target}.${randomUUID()}.tmp`; await writeFile(tmp, JSON.stringify(records, null, 2)); await rename(tmp, target); }
  async list(workspaceId: string) { return this.load(workspaceId); }
  async get(workspaceId: string, artifactId: string) { const item = (await this.load(workspaceId)).find(a => a.artifact_id === artifactId); if (!item) throw new Error("artifact not found"); return item; }
  async register(workspaceId: string, workspaceRoot: string, relativePath: string, options: Partial<Pick<ArtifactRecord, "type" | "summary" | "session_id" | "run_id" | "input_sources" | "preview">> = {}) {
    return this.serial(workspaceId, () => this.registerUnlocked(workspaceId, workspaceRoot, relativePath, options));
  }
  private async registerUnlocked(workspaceId: string, workspaceRoot: string, relativePath: string, options: Partial<Pick<ArtifactRecord, "type" | "summary" | "session_id" | "run_id" | "input_sources" | "preview">> = {}) {
    const workspace = new Workspace(workspaceRoot); const absolute = await workspace.resolveExisting(relativePath); const bytes = await readFile(absolute); const hash = createHash("sha256").update(bytes).digest("hex"); const records = await this.load(workspaceId); const existing = records.find(a => a.path === relativePath);
    const snapshot = path.join("snapshots", `${hash}.bin`);
    const snapshotPath = path.join(this.root, snapshot);
    await mkdir(path.dirname(snapshotPath), { recursive: true });
    try { await writeFile(snapshotPath, bytes, { flag: "wx" }); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; if (createHash("sha256").update(await readFile(snapshotPath)).digest("hex") !== hash) throw new Error("snapshot integrity failure"); }
    const now = new Date().toISOString(); const version = (existing?.version ?? 0) + 1; const entry: ArtifactVersion = { version, hash, size: bytes.length, created_at: now, path: relativePath, snapshot };
    if (existing) { existing.verification_status = "unverified"; existing.type = options.type ?? existing.type; }
    if (existing) { existing.version = version; existing.hash = hash; existing.updated_at = now; existing.versions.push(entry); existing.summary = options.summary ?? existing.summary; existing.input_sources = options.input_sources ?? existing.input_sources; existing.preview = options.preview ?? existing.preview; await this.save(workspaceId, records); return existing; }
    const created: ArtifactRecord = { artifact_id: randomUUID(), workspace_id: workspaceId, session_id: options.session_id, run_id: options.run_id, type: options.type ?? artifactTypeForPath(relativePath), path: relativePath, summary: options.summary ?? "", hash, version, input_sources: options.input_sources ?? [], generation_status: "ready", verification_status: "unverified", preview: options.preview, delivery_ids: [], versions: [entry], created_at: now, updated_at: now }; records.push(created); await this.save(workspaceId, records); return created;
  }
  async restore(workspaceId: string, workspaceRoot: string, artifactId: string, version: number, expectedHash: string) {
    return this.serial(workspaceId, async () => {
      const item = await this.get(workspaceId, artifactId);
      const selected = item.versions.find(entry => entry.version === version);
      if (!selected?.snapshot || !/^[a-f0-9]{64}$/.test(selected.hash)) throw new Error("historical file content is unavailable for this version");
      const bytes = await readFile(path.join(this.root, "snapshots", `${selected.hash}.bin`));
      if (createHash("sha256").update(bytes).digest("hex") !== selected.hash) throw new Error("snapshot integrity failure");
      const target = await new Workspace(workspaceRoot).resolveExisting(item.path);
      const currentHash = () => readFile(target).then(data => createHash("sha256").update(data).digest("hex"));
      if (await currentHash() !== expectedHash) throw new Error("file changed since version selection");
      // Capture manual edits before restoring so restoration itself can be undone.
      await this.registerUnlocked(workspaceId, workspaceRoot, item.path);
      const temporary = `${target}.${randomUUID()}.tmp`;
      try {
        await writeFile(temporary, bytes, { flag: "wx" });
        await chmod(temporary, (await stat(target)).mode);
        if (await currentHash() !== expectedHash) throw new Error("file changed while preparing restoration");
        await rename(temporary, target);
      } finally { await unlink(temporary).catch(error => { if (error.code !== "ENOENT") throw error; }); }
      return this.registerUnlocked(workspaceId, workspaceRoot, item.path);
    });
  }
  async updateVerification(workspaceId: string, artifactId: string, status: VerificationStatus, summary?: string) { return this.serial(workspaceId, async () => { const records = await this.load(workspaceId); const item = records.find(a => a.artifact_id === artifactId); if (!item) throw new Error("artifact not found"); item.verification_status = status; if (summary !== undefined) item.summary = summary; item.updated_at = new Date().toISOString(); await this.save(workspaceId, records); return item; }); }
}
