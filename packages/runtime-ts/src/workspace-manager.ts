import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { randomUUID } from "node:crypto";
import { Workspace } from "./workspace.js";

const execFileAsync = promisify(execFile);
export type WorkspaceRecord = { workspace_id: string; path: string; name: string; archived: boolean };

export class WorkspaceManager {
  private records = new Map<string, WorkspaceRecord>();
  private loaded = false;
  constructor(private readonly filePath = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "workspaces.json")) {}

  private async ensureLoaded(): Promise<void> {
    if (this.loaded) return;
    this.loaded = true;
    try {
      const data = JSON.parse(await readFile(this.filePath, "utf8")) as WorkspaceRecord[];
      for (const item of data) if (item.workspace_id && item.path) this.records.set(item.workspace_id, item);
    } catch { /* first run */ }
  }
  private async persist(): Promise<void> { await mkdir(path.dirname(this.filePath), { recursive: true }); await writeFile(this.filePath, `${JSON.stringify([...this.records.values()], null, 2)}\n`, "utf8"); }
  async list(): Promise<WorkspaceRecord[]> { await this.ensureLoaded(); return [...this.records.values()]; }
  async open(rawPath: string): Promise<WorkspaceRecord> {
    await this.ensureLoaded(); const resolved = path.resolve(rawPath); const existing = [...this.records.values()].find((item) => path.resolve(item.path) === resolved);
    if (existing) { existing.archived = false; await this.persist(); return existing; }
    const record = { workspace_id: randomUUID(), path: resolved, name: path.basename(resolved) || resolved, archived: false }; this.records.set(record.workspace_id, record); await this.persist(); return record;
  }
  async get(id: string): Promise<WorkspaceRecord> { await this.ensureLoaded(); const item = this.records.get(id); if (!item) throw new Error(`Unknown workspace: ${id}`); return item; }
  async archive(id: string): Promise<WorkspaceRecord> { const item = await this.get(id); item.archived = true; await this.persist(); return item; }
  async resume(id: string): Promise<WorkspaceRecord> { const item = await this.get(id); item.archived = false; await this.persist(); return item; }
  async delete(id: string): Promise<void> { await this.get(id); this.records.delete(id); await this.persist(); }
  async status(id: string): Promise<{ branch: string | null; is_git_repository: boolean; changed_file_count: number }> {
    const workspace = await this.get(id);
    try { const branch = (await execFileAsync("git", ["-C", workspace.path, "branch", "--show-current"], { timeout: 10_000 })).stdout.trim() || null; const porcelain = (await execFileAsync("git", ["-C", workspace.path, "status", "--porcelain"], { timeout: 10_000 })).stdout.trim(); return { branch, is_git_repository: true, changed_file_count: porcelain ? porcelain.split(/\r?\n/).length : 0 }; } catch { return { branch: null, is_git_repository: false, changed_file_count: 0 }; }
  }
  async tree(id: string, relative = "", maxDepth = 2, maxEntries = 300): Promise<Array<{ path: string; name: string; kind: "directory" | "file"; children?: unknown[] }>> {
    const record = await this.get(id); const workspace = new Workspace(record.path); const root = workspace.resolve(relative || "."); let count = 0;
    const walk = async (directory: string, depth: number): Promise<Array<{ path: string; name: string; kind: "directory" | "file"; children?: unknown[] }>> => {
      if (count >= maxEntries) return [];
      const { readdir } = await import("node:fs/promises"); const entries = (await readdir(directory, { withFileTypes: true })).filter((entry) => !entry.name.startsWith(".") && entry.name !== "node_modules").sort((a, b) => Number(a.isFile()) - Number(b.isFile()) || a.name.localeCompare(b.name)); const nodes = [] as Array<{ path: string; name: string; kind: "directory" | "file"; children?: unknown[] }>;
      for (const entry of entries) { if (count >= maxEntries) break; count += 1; const entryPath = path.relative(record.path, path.join(directory, entry.name)).split(path.sep).join("/"); nodes.push(entry.isDirectory() ? { path: entryPath, name: entry.name, kind: "directory", children: depth + 1 <= maxDepth ? await walk(path.join(directory, entry.name), depth + 1) : undefined } : { path: entryPath, name: entry.name, kind: "file" }); }
      return nodes;
    };
    return walk(root, 1);
  }
  async search(id: string, query: string, maxResults = 100): Promise<Array<{ path: string; line: number; preview: string }>> {
    const record = await this.get(id); const workspace = new Workspace(record.path); const rg = process.platform === "win32" ? "rg.exe" : "rg";
    try { const result = await execFileAsync(rg, ["--line-number", "--no-heading", "--color", "never", "--glob", "!.git", "--glob", "!node_modules", query, "."], { cwd: workspace.root, maxBuffer: 4 * 1024 * 1024, timeout: 15_000 }); return result.stdout.split(/\r?\n/).filter(Boolean).slice(0, maxResults).map((line) => { const match = line.match(/^\.\\?([^:]+):(\d+):(.*)$/); return match ? { path: match[1].replace(/^[\\/]+/, "").replaceAll("\\", "/"), line: Number(match[2]), preview: match[3].trim() } : { path: "", line: 0, preview: line }; }); } catch { return []; }
  }
}
