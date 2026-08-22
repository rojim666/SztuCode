import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import type { ToolPermission } from "./tools-types.js";
import type { Workspace } from "./workspace.js";
import type { EventBus } from "./event-bus.js";
import { TaskManager, type TaskStatus } from "./task-manager.js";
import { classifyBashPermission } from "./bash-permission.js";

export type { ToolPermission } from "./tools-types.js";
export type ToolResult = { ok: boolean; output: string; error?: string; errorType?: "runtime_error" | "rate_limited" | "timeout" | "schema_error" | "permission_denied" };
export type ToolContext = { workspace: Workspace; signal?: AbortSignal; onFileChanged?: (relativePath: string) => void };
export interface Tool { readonly name: string; readonly aliases?: readonly string[]; readonly description: string; readonly permission: ToolPermission; readonly schema: Record<string, unknown>; classifyPermission?(params: Record<string, unknown>): ToolPermission; invoke(params: Record<string, unknown>, context: ToolContext): Promise<ToolResult>; }

const ok = (output: string): ToolResult => ({ ok: true, output });
const fail = (error: string, errorType: ToolResult["errorType"] = "runtime_error"): ToolResult => ({ ok: false, output: "", error, errorType });
const str = (params: Record<string, unknown>, key: string): string | null => typeof params[key] === "string" ? params[key] as string : null;
const ignored = new Set([".git", "node_modules", "__pycache__", ".venv", ".codegraph", "dist", "build"]);
const escapeRegex = (value: string) => value.replace(/[.+^${}()|[\]\\]/g, "\\$&");
const globMatch = (value: string, pattern: string): boolean => new RegExp(`^${pattern.split("**").map((part) => part.split("*").map(escapeRegex).join("[^/]*")).join(".*")}$`).test(value);
const builtinAliases: Readonly<Record<string, string>> = {
  read: "read_file", Read: "read_file",
  write: "write_file", Write: "write_file",
  edit: "edit_file", Edit: "edit_file",
  glob: "glob_search", Glob: "glob_search",
  grep: "grep_search", Grep: "grep_search",
  ls: "list_dir", List: "list_dir",
};

export class ToolRegistry {
  private readonly tools = new Map<string, Tool>();
  private readonly aliases = new Map<string, string>();
  register(tool: Tool): void { if (this.tools.has(tool.name)) throw new Error(`Tool already registered: ${tool.name}`); this.tools.set(tool.name, tool); this.registerAliases(tool); }
  replace(tool: Tool): void { this.tools.set(tool.name, tool); for (const [alias, target] of this.aliases) if (target === tool.name) this.aliases.delete(alias); this.registerAliases(tool); }
  get(name: string): Tool | undefined { const canonical = this.tools.has(name) ? name : this.aliases.get(name) ?? builtinAliases[name]; return canonical ? this.tools.get(canonical) : undefined; }
  canonicalName(name: string): string | undefined { return this.get(name)?.name; }
  list(): Tool[] { return [...this.tools.values()]; }
  restrictTo(names: string[]): this { if (!names.length) return this; const allowed = new Set(names.map((name) => this.canonicalName(name) ?? name)); for (const name of this.tools.keys()) if (!allowed.has(name)) this.tools.delete(name); return this; }
  private registerAliases(tool: Tool): void { for (const alias of tool.aliases ?? []) this.aliases.set(alias, tool.name); }
}

export function registerQuestionTool(registry: ToolRegistry, ask: (questions: Array<Record<string, unknown>>) => Promise<unknown[]>): void {
  registry.register({ name: "ask_user_question", description: "Ask the user one to three structured questions and wait for an answer", permission: "read_only", schema: { type: "object", properties: { questions: { type: "array", minItems: 1, maxItems: 3 } }, required: ["questions"] }, async invoke(params) { try { return ok(JSON.stringify({ answers: await ask(Array.isArray(params.questions) ? params.questions as Array<Record<string, unknown>> : []) })); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); } } });
}

export function createPlanTools(events: EventBus, runId: string, sessionId = "", tasksDir = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu"), "runs", runId.replace(/[^A-Za-z0-9_.-]/g, "_"), "tasks")): Tool[] {
  const manager = new TaskManager(tasksDir);
  const publish = async () => { const items = await manager.listAll(); events.publish({ type: "plan.updated", run_id: runId, session_id: sessionId, items: items.map(({ id, subject, status, blocked_by }) => ({ id, subject, status, blocked_by })), ts: new Date().toISOString() }); };
  const ids = (value: unknown) => Array.isArray(value) ? value.map(Number) : [];
  const failure = (error: unknown): ToolResult => fail(error instanceof Error ? error.message : String(error));
  return [
    { name: "task_create", description: "Create a trackable task for complex work", permission: "workspace_write", schema: { type: "object", properties: { subject: { type: "string" }, description: { type: "string" }, blocked_by: { type: "array", items: { type: "integer" } } }, required: ["subject"] }, async invoke(params) { try { const task = await manager.create(String(params.subject ?? ""), String(params.description ?? ""), ids(params.blocked_by)); await publish(); return ok(JSON.stringify(task)); } catch (error) { return failure(error); } } },
    { name: "task_update", description: "Update a task status or dependencies", permission: "workspace_write", schema: { type: "object", properties: { task_id: { type: "integer" }, status: { type: "string", enum: ["pending", "in_progress", "completed"] }, add_blocked_by: { type: "array", items: { type: "integer" } }, remove_blocked_by: { type: "array", items: { type: "integer" } } }, required: ["task_id"] }, async invoke(params) { try { const task = await manager.update(Number(params.task_id), { ...(params.status === undefined ? {} : { status: String(params.status) as TaskStatus }), addBlockedBy: ids(params.add_blocked_by), removeBlockedBy: ids(params.remove_blocked_by) }); await publish(); return ok(JSON.stringify(task)); } catch (error) { return failure(error); } } },
    { name: "task_list", description: "List current plan tasks", permission: "read_only", schema: { type: "object", properties: {} }, async invoke() { return ok(await manager.formatList()); } },
    { name: "task_get", description: "Get full details of a task by its integer ID", permission: "read_only", schema: { type: "object", properties: { task_id: { type: "integer" } }, required: ["task_id"] }, async invoke(params) { try { return ok(JSON.stringify(await manager.get(Number(params.task_id)))); } catch (error) { return failure(error); } } },
  ];
}

async function collectFiles(root: string, current: string, output: string[]): Promise<void> {
  for (const entry of await readdir(current, { withFileTypes: true })) {
    // 跳过符号链接：防止目录树跟随链接逃逸到工作区外（list/glob/grep 读外部文件）
    if (entry.isSymbolicLink()) continue;
    if (entry.isDirectory() && !ignored.has(entry.name)) await collectFiles(root, path.join(current, entry.name), output);
    else if (entry.isFile()) output.push(path.relative(root, path.join(current, entry.name)).split(path.sep).join("/"));
  }
}

export function createWorkspaceTools(extraTools: Tool[] = []): ToolRegistry {
  const registry = new ToolRegistry();
  registry.register({ name: "read_file", description: "Read a UTF-8 file inside the workspace", permission: "read_only", schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] }, async invoke(params, context) {
    const file = str(params, "path"); if (!file) return fail("path is required", "schema_error");
    try { const data = await readFile(await context.workspace.resolveExisting(file)); const limit = 2 * 1024 * 1024; const content = data.subarray(0, limit).toString("utf8"); return ok(content.length < data.length ? `${content}\n\n[truncated: file is ${data.length} bytes, showing first ${limit} bytes]` : content); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "write_file", description: "Write a UTF-8 file inside the workspace", permission: "workspace_write", schema: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] }, async invoke(params, context) {
    const file = str(params, "path"); const content = str(params, "content"); if (!file || content === null) return fail("path and content are required", "schema_error");
    try { const target = await context.workspace.resolveExisting(file); const before = await readFile(target, "utf8").catch(() => null); await import("node:fs/promises").then(({ mkdir }) => mkdir(path.dirname(target), { recursive: true })); await writeFile(target, content, "utf8"); if (before !== content) context.onFileChanged?.(path.relative(context.workspace.root, target).split(path.sep).join("/")); return ok(`wrote ${file}`); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "list_dir", description: "List a workspace directory as a tree", permission: "read_only", schema: { type: "object", properties: { path: { type: "string" }, max_depth: { type: "integer", minimum: 1, maximum: 4 } } }, async invoke(params, context) {
    try { return ok((await context.workspace.list(str(params, "path") ?? ".", typeof params.max_depth === "number" ? Math.min(4, Math.max(1, params.max_depth)) : 2)).join("\n")); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "glob_search", description: "Find files matching a glob pattern", permission: "read_only", schema: { type: "object", properties: { pattern: { type: "string" }, path: { type: "string" } }, required: ["pattern"] }, async invoke(params, context) {
    const pattern = str(params, "pattern"); if (!pattern) return fail("pattern is required", "schema_error");
    try { const root = context.workspace.resolve(str(params, "path") ?? "."); const files: string[] = []; const workspaceRoot = context.workspace.root; if ((await stat(root)).isFile()) files.push(path.relative(workspaceRoot, root).split(path.sep).join("/")); else await collectFiles(workspaceRoot, root, files); const matches = files.filter((file) => globMatch(file, pattern)).sort().slice(0, 200); return ok(matches.length ? matches.join("\n") : "No files found."); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "grep_search", description: "Search workspace files with a regular expression", permission: "read_only", schema: { type: "object", properties: { pattern: { type: "string" }, path: { type: "string" }, glob: { type: "string" } }, required: ["pattern"] }, async invoke(params, context) {
    const pattern = str(params, "pattern"); if (!pattern) return fail("pattern is required", "schema_error"); let matcher: RegExp; try { matcher = new RegExp(pattern, params.case_sensitive === true ? "" : "i"); } catch (error) { return fail(error instanceof Error ? error.message : String(error), "schema_error"); }
    try { const root = context.workspace.root; const target = context.workspace.resolve(str(params, "path") ?? "."); const files: string[] = []; if ((await stat(target)).isFile()) files.push(path.relative(root, target).split(path.sep).join("/")); else await collectFiles(root, target, files); const result: string[] = []; for (const file of files) { if (params.glob && !globMatch(file, String(params.glob))) continue; const text = (await readFile(path.join(root, file))).subarray(0, 512 * 1024).toString("utf8"); if (text.includes("\u0000")) continue; text.split(/\r?\n/).forEach((line, index) => { if (matcher.test(line) && result.length < 200) result.push(`${file}:${index + 1}: ${line}`); }); } return ok(result.length ? result.join("\n") : "No matches found."); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "edit_file", description: "Replace an exact string in a workspace file", permission: "workspace_write", schema: { type: "object", properties: { path: { type: "string" }, old_string: { type: "string" }, new_string: { type: "string" }, replace_all: { type: "boolean" } }, required: ["path", "old_string", "new_string"] }, async invoke(params, context) {
    const file = str(params, "path"); const oldString = str(params, "old_string"); const newString = str(params, "new_string"); if (!file || oldString === null || newString === null) return fail("path, old_string and new_string are required", "schema_error"); if (oldString === newString) return fail("old_string and new_string are identical", "schema_error");
    try { const target = await context.workspace.resolveExisting(file); const original = await readFile(target, "utf8"); const count = original.split(oldString).length - 1; if (!count) return fail(`old_string not found in ${file}`); if (count > 1 && params.replace_all !== true) return fail(`old_string appears ${count} times in ${file}`, "schema_error"); const updated = params.replace_all === true ? original.split(oldString).join(newString) : original.replace(oldString, newString); await writeFile(target, updated, "utf8"); context.onFileChanged?.(path.relative(context.workspace.root, target).split(path.sep).join("/")); return ok(`replaced ${params.replace_all === true ? count : 1} occurrence(s) in ${file}`); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "bash", description: "Execute a non-interactive shell command", permission: "danger_full_access", classifyPermission: classifyBashPermission, schema: { type: "object", properties: { command: { type: "string", minLength: 1 }, timeout: { type: "integer", minimum: 1, maximum: 120 } }, required: ["command"] }, async invoke(params, context) {
    const command = str(params, "command"); if (!command) return fail("command is required", "schema_error"); if (/(^|[;&|])\s*(npm|pnpm|yarn|pip|uv)\s+(install|add|update)\b/i.test(command)) return fail("Installing or updating dependencies is blocked");
    return new Promise((resolve) => {
      if (context.signal?.aborted) { resolve(fail("Run cancelled")); return; }
      const child = spawn(command, { cwd: context.workspace.root, shell: true, windowsHide: true }); let output = ""; let truncated = false; let settled = false;
      const MAX_BASH_OUTPUT = 2 * 1024 * 1024;
      const onData = (chunk: Buffer) => { if (output.length >= MAX_BASH_OUTPUT) { truncated = true; return; } const next = output + chunk.toString(); if (next.length > MAX_BASH_OUTPUT) { output = next.slice(0, MAX_BASH_OUTPUT); truncated = true; } else output = next; };
      const finish = (result: ToolResult) => { if (settled) return; settled = true; clearTimeout(timeout); context.signal?.removeEventListener("abort", abort); resolve(result); };
      const abort = () => { child.kill(); finish(fail("Run cancelled")); };
      const timeout = setTimeout(() => { child.kill(); finish(fail(`[timeout after ${params.timeout ?? 30}s]`, "timeout")); }, Math.min(120, Math.max(1, Number(params.timeout ?? 30))) * 1000);
      context.signal?.addEventListener("abort", abort, { once: true });
      child.stdout.on("data", onData); child.stderr.on("data", onData);
      child.on("error", (error) => finish(fail(error.message)));
      child.on("close", (code) => finish(code === 0 ? ok(truncated ? `${output}\n\n[output truncated at ${MAX_BASH_OUTPUT} bytes]` : output) : { ok: false, output: truncated ? `${output}\n\n[output truncated at ${MAX_BASH_OUTPUT} bytes]` : output, error: `command exited with code ${code}`, errorType: "runtime_error" }));
    });
  }});
  for (const tool of extraTools) registry.register(tool);
  return registry;
}
