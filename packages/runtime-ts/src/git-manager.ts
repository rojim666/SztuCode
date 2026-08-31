import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { WorkspaceManager } from "./workspace-manager.js";

const exec = promisify(execFile);
export type ChangeSummary = { path: string; index_status: string; worktree_status: string; additions?: number; deletions?: number; run_id?: string | null; agent_owned?: boolean; revertible?: boolean };

export class GitManager {
  constructor(private readonly workspaces: WorkspaceManager) {}
  private async cwd(id: string): Promise<string> { return (await this.workspaces.get(id)).path; }
  private parseNumstat(output: string): { additions: number; deletions: number } {
    const row = output.split(/\r?\n/).find((line) => line.trim());
    if (!row) return { additions: 0, deletions: 0 };
    const [added, deleted] = row.split("\t");
    const additions = Number.parseInt(added ?? "", 10);
    const deletions = Number.parseInt(deleted ?? "", 10);
    return { additions: Number.isFinite(additions) ? additions : 0, deletions: Number.isFinite(deletions) ? deletions : 0 };
  }
  private async stats(cwd: string, file: string, untracked: boolean): Promise<{ additions: number; deletions: number }> {
    if (untracked) {
      try {
        // --no-index exits with status 1 when files differ; execFile still exposes its stdout on the error.
        await exec("git", ["diff", "--no-index", "--numstat", "--", process.platform === "win32" ? "NUL" : "/dev/null", file], { cwd });
      } catch (reason) {
        return this.parseNumstat(String((reason as { stdout?: string }).stdout ?? ""));
      }
      return { additions: 0, deletions: 0 };
    }
    try {
      return this.parseNumstat((await exec("git", ["diff", "HEAD", "--numstat", "--", file], { cwd })).stdout);
    } catch {
      try {
        return this.parseNumstat((await exec("git", ["diff", "--cached", "--numstat", "--", file], { cwd })).stdout);
      } catch { return { additions: 0, deletions: 0 }; }
    }
  }
  async list(id: string): Promise<ChangeSummary[]> {
    const cwd = await this.cwd(id);
    try {
      const { stdout } = await exec("git", ["status", "--porcelain=v1"], { cwd });
      const entries = stdout.split(/\r?\n/).filter(Boolean).map((line) => ({ index_status: line[0] ?? " ", worktree_status: line[1] ?? " ", path: line.slice(3).trim() }));
      return await Promise.all(entries.map(async (entry) => ({ ...entry, ...await this.stats(cwd, entry.path, entry.index_status === "?" && entry.worktree_status === "?") })));
    } catch { return []; }
  }
  async diff(id: string, file?: string | null): Promise<string> { const cwd = await this.cwd(id); const args = ["diff", "--no-ext-diff", "--", ...(file ? [file] : [])]; try { return (await exec("git", args, { cwd, maxBuffer: 16 * 1024 * 1024 })).stdout; } catch { return ""; } }
  async stage(id: string, paths: string[]): Promise<string[]> { const cwd = await this.cwd(id); await exec("git", ["add", "--", ...paths], { cwd }); return paths; }
  async unstage(id: string, paths: string[]): Promise<string[]> { const cwd = await this.cwd(id); await exec("git", ["restore", "--staged", "--", ...paths], { cwd }); return paths; }
  async discard(id: string, paths: string[]): Promise<string[]> { const cwd = await this.cwd(id); await exec("git", ["restore", "--worktree", "--", ...paths], { cwd }); return paths; }
  async commit(id: string, message: string): Promise<string> { const cwd = await this.cwd(id); const result = await exec("git", ["commit", "-m", message], { cwd }); return (await exec("git", ["rev-parse", "HEAD"], { cwd })).stdout.trim() || result.stdout.trim(); }
  async history(id: string, limit = 100, skip = 0): Promise<{ commits: Array<Record<string, unknown>>; has_more: boolean }> {
    const cwd = await this.cwd(id);
    const output = async (args: string[]): Promise<string> => { try { return (await exec("git", args, { cwd })).stdout.trim(); } catch { return ""; } };
    const headHash = await output(["rev-parse", "HEAD"]);
    const upstream = await output(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]);
    const outgoing = new Set(upstream ? (await output(["rev-list", `${upstream}..HEAD`])).split(/\r?\n/).filter(Boolean) : []);
    const refsByHash = new Map<string, Array<{ name: string; kind: "head" | "remote" | "tag" }>>();
    for (const line of (await output(["show-ref", "--dereference"])).split(/\r?\n/).filter(Boolean)) {
      const separator = line.indexOf(" ");
      if (separator < 0) continue;
      const hash = line.slice(0, separator); let fullName = line.slice(separator + 1); const peeled = fullName.endsWith("^{}"); fullName = fullName.replace(/\^\{\}$/, "");
      let kind: "head" | "remote" | "tag"; let name: string;
      if (fullName.startsWith("refs/heads/")) { kind = "head"; name = fullName.slice("refs/heads/".length); }
      else if (fullName.startsWith("refs/remotes/")) { kind = "remote"; name = fullName.slice("refs/remotes/".length); }
      else if (fullName.startsWith("refs/tags/")) { kind = "tag"; name = fullName.slice("refs/tags/".length); }
      else continue;
      const item = { name, kind };
      if (peeled) for (const values of refsByHash.values()) { const index = values.findIndex((value) => value.name === name && value.kind === kind); if (index >= 0) values.splice(index, 1); }
      const values = refsByHash.get(hash) ?? []; if (!values.some((value) => value.name === name && value.kind === kind)) values.push(item); refsByHash.set(hash, values);
    }
    const { stdout } = await exec("git", ["log", "--all", "--topo-order", `--max-count=${limit + 1}`, `--skip=${skip}`, "--format=%H%x1f%h%x1f%P%x1f%an%x1f%aI%x1f%s"], { cwd });
    const rows = stdout.split(/\r?\n/).filter(Boolean).map((row) => { const [hash, short_hash, parents, author, date, subject] = row.split("\x1f"); return { hash, short_hash, parents: parents ? parents.split(" ") : [], author, date, subject, is_head: hash === headHash, is_outgoing: outgoing.has(hash), refs: refsByHash.get(hash) ?? [] }; });
    return { commits: rows.slice(0, limit), has_more: rows.length > limit };
  }
}
