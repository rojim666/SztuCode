import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile, rename, readdir } from "node:fs/promises";
import path from "node:path";
import { Workspace } from "./workspace.js";

export type ArtifactStatus = "draft" | "ready" | "failed";
export type VerificationStatus = "unverified" | "passed" | "failed";
export interface ArtifactVersion { version: number; hash: string; size: number; created_at: string; path: string; }
export interface ArtifactRecord { artifact_id: string; workspace_id: string; session_id?: string; run_id?: string; type: "docx" | "pptx" | "pdf" | "xlsx" | "csv" | "other"; path: string; summary: string; hash: string; version: number; input_sources: Array<{ path: string; version?: string; hash?: string }>; generation_status: ArtifactStatus; verification_status: VerificationStatus; preview?: { mime_type: string; text?: string; thumbnail_path?: string }; delivery_ids: string[]; versions: ArtifactVersion[]; created_at: string; updated_at: string; }

export class ArtifactStore {
  constructor(private readonly root: string) {}
  private file(workspaceId: string) { return path.join(this.root, `${workspaceId}.json`); }
  private async load(workspaceId: string): Promise<ArtifactRecord[]> { try { return JSON.parse(await readFile(this.file(workspaceId), "utf8")) as ArtifactRecord[]; } catch { return []; } }
  private async save(workspaceId: string, records: ArtifactRecord[]) { await mkdir(this.root, { recursive: true }); const target = this.file(workspaceId); const tmp = `${target}.${process.pid}.tmp`; await writeFile(tmp, JSON.stringify(records, null, 2)); await rename(tmp, target); }
  async list(workspaceId: string) { return this.load(workspaceId); }
  async get(workspaceId: string, artifactId: string) { const item = (await this.load(workspaceId)).find(a => a.artifact_id === artifactId); if (!item) throw new Error("artifact not found"); return item; }
  async register(workspaceId: string, workspaceRoot: string, relativePath: string, options: Partial<Pick<ArtifactRecord, "type" | "summary" | "session_id" | "run_id" | "input_sources" | "preview">> = {}) {
    const workspace = new Workspace(workspaceRoot); const absolute = await workspace.resolveExisting(relativePath); const bytes = await readFile(absolute); const hash = createHash("sha256").update(bytes).digest("hex"); const records = await this.load(workspaceId); const existing = records.find(a => a.path === relativePath);
    const now = new Date().toISOString(); const version = (existing?.version ?? 0) + 1; const entry: ArtifactVersion = { version, hash, size: bytes.length, created_at: now, path: relativePath };
    if (existing) { existing.version = version; existing.hash = hash; existing.updated_at = now; existing.versions.push(entry); existing.summary = options.summary ?? existing.summary; existing.input_sources = options.input_sources ?? existing.input_sources; existing.preview = options.preview ?? existing.preview; await this.save(workspaceId, records); return existing; }
    const created: ArtifactRecord = { artifact_id: randomUUID(), workspace_id: workspaceId, session_id: options.session_id, run_id: options.run_id, type: options.type ?? "other", path: relativePath, summary: options.summary ?? "", hash, version, input_sources: options.input_sources ?? [], generation_status: "ready", verification_status: "unverified", preview: options.preview, delivery_ids: [], versions: [entry], created_at: now, updated_at: now }; records.push(created); await this.save(workspaceId, records); return created;
  }
  async updateVerification(workspaceId: string, artifactId: string, status: VerificationStatus, summary?: string) { const records = await this.load(workspaceId); const item = records.find(a => a.artifact_id === artifactId); if (!item) throw new Error("artifact not found"); item.verification_status = status; if (summary !== undefined) item.summary = summary; item.updated_at = new Date().toISOString(); await this.save(workspaceId, records); return item; }
}
