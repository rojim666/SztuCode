import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import type { ToolPermission } from "./tools-types.js";
import type { Workspace } from "./workspace.js";
import type { EventBus } from "./event-bus.js";
import { TaskManager, type TaskStatus } from "./task-manager.js";
import { classifyBashPermission } from "./bash-permission.js";
import { SkillLoader } from "./skills.js";
import { detectDocumentFormat } from "./document-parser/detect.js";
import type { ParsedDocument } from "./document-parser/types.js";

export type { ToolPermission } from "./tools-types.js";
export type ToolResult = { ok: boolean; output: string; error?: string; errorType?: "runtime_error" | "rate_limited" | "timeout" | "schema_error" | "permission_denied" };
export type ToolOutputStream = "stdout" | "stderr" | "combined";
export type ToolOutputChunk = { tool_use_id?: string; stream: ToolOutputStream; data: string; ts: string };
export type ToolContext = {
  workspace: Workspace;
  signal?: AbortSignal;
  onFileChanged?: (relativePath: string) => void;
  /** 实时输出回调：用于 bash 等工具推送流式输出 */
  onOutput?: (chunk: ToolOutputChunk) => void;
  /** 当前工具调用 ID，用于关联输出事件 */
  toolUseId?: string;
  /** EventBus 引用，用于直接发布事件 */
  events?: EventBus;
  /** runId 用于事件发布 */
  runId?: string;
};
export interface Tool { readonly name: string; readonly aliases?: readonly string[]; readonly description: string; readonly permission: ToolPermission; readonly schema: Record<string, unknown>; readonly executionMode?: "parallel" | "sequential"; readonly timeoutMs?: number; /** false 表示工具失败不自动重试（如 bash：exit≠0 是业务结果而非基础设施故障，且命令可能非幂等） */ readonly retryable?: boolean; classifyPermission?(params: Record<string, unknown>): ToolPermission; invoke(params: Record<string, unknown>, context: ToolContext): Promise<ToolResult>; }

const ok = (output: string): ToolResult => ({ ok: true, output });
const fail = (error: string, errorType: ToolResult["errorType"] = "runtime_error"): ToolResult => ({ ok: false, output: "", error, errorType });
const str = (params: Record<string, unknown>, key: string): string | null => typeof params[key] === "string" ? params[key] as string : null;
// 扩展忽略目录：覆盖常见构建产物、缓存、虚拟环境、IDE 配置等
const ignored = new Set([
  ".git", "node_modules", "__pycache__", ".venv", ".codegraph", "dist", "build",
  ".next", ".nuxt", ".svelte-kit", "target", "out", "coverage",
  ".cache", ".parcel-cache", ".turbo", ".eslintcache",
  ".idea", ".vscode", ".vs",
  "venv", "env", ".env", "virtualenv",
  "bower_components", "jspm_packages",
  ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
  "bin", "obj", "Debug", "Release",  // .NET build artifacts
]);
const escapeRegex = (value: string) => value.replace(/[.+^${}()|[\]\\]/g, "\\$&");
// glob 正则缓存：避免每次匹配都重新编译正则
const globRegexCache = new Map<string, RegExp>();
const globMatch = (value: string, pattern: string): boolean => {
  let regex = globRegexCache.get(pattern);
  if (!regex) {
    regex = new RegExp(`^${pattern.split("**").map((part) => part.split("*").map(escapeRegex).join("[^/]*")).join(".*")}$`);
    globRegexCache.set(pattern, regex);
  }
  return regex.test(value);
};
// 文件系统并发控制
const FILE_READ_CONCURRENCY = 8;
const MAX_RESULTS = 200;
// 简单二进制文件检测：检查文件头部是否有 null 字节
const isBinaryFile = (buffer: Buffer): boolean => buffer.includes(0);

// 异步信号量实现
class AsyncSemaphore {
  private permits: number;
  private queue: Array<() => void> = [];
  constructor(permits: number) { this.permits = permits; }
  async acquire(): Promise<void> {
    if (this.permits > 0) { this.permits--; return; }
    await new Promise<void>(resolve => this.queue.push(resolve));
  }
  release(): void {
    if (this.queue.length > 0) {
      const next = this.queue.shift()!;
      next();
    } else {
      this.permits++;
    }
  }
}

// 流式文件遍历：异步生成器，边遍历边产出文件路径，支持提前终止
async function* walkFiles(
  root: string,
  current: string,
  signal?: AbortSignal
): AsyncGenerator<string, void, unknown> {
  signal?.throwIfAborted();
  let entries;
  try {
    entries = await readdir(current, { withFileTypes: true });
  } catch {
    return; // 无权限或目录不存在时跳过
  }
  for (const entry of entries) {
    signal?.throwIfAborted();
    // 跳过符号链接：防止目录树跟随链接逃逸到工作区外
    if (entry.isSymbolicLink()) continue;
    const fullPath = path.join(current, entry.name);
    if (entry.isDirectory()) {
      if (!ignored.has(entry.name)) {
        yield* walkFiles(root, fullPath, signal);
      }
    } else if (entry.isFile()) {
      yield path.relative(root, fullPath).split(path.sep).join("/");
    }
  }
}

const builtinAliases: Readonly<Record<string, string>> = {
  read: "read_file", Read: "read_file",
  write: "write_file", Write: "write_file",
  edit: "edit_file", Edit: "edit_file",
  glob: "glob_search", Glob: "glob_search",
  grep: "grep_search", Grep: "grep_search",
  ls: "list_dir", List: "list_dir",
};

// Bash 工具配置（与 Python 版对齐）
const MAX_BASH_OUTPUT = 64 * 1024; // 64 KB（Python 版一致）
const DEFAULT_TIMEOUT = 30;
const DEFAULT_GIT_TIMEOUT = 20;

// 安装/更新依赖命令拦截正则
const BLOCKED_INSTALL_RE = /(^|;|&&|\|\|)\s*(?:python(\d|3)?\s+-m\s+pip\s+install|pip(\d|3)?\s+install|uv\s+pip\s+install|pipenv\s+install|poetry\s+install|npm\s+(?:install|i|add)\b|yarn\s+(?:install|add)\b|pnpm\s+(?:install|add)\b|apt(-get)?\s+(?:install|update)|brew\s+install|conda\s+install|python(\d|3)?\s+-m\s+ensurepip|ensurepip)(?=\s|$)/i;

// 只读命令白名单（用于 classifyBashPermission）
const READ_ONLY_COMMANDS = new Set([
  "cat", "head", "tail", "less", "more", "ls", "dir",
  "grep", "rg", "awk", "sed", "wc", "file", "stat",
  "find", "which", "where", "whereis", "type", "echo", "printf",
  "date", "env", "printenv", "pwd", "whoami", "uname", "cls",
  "git", "python", "python3", "node",
]);

// 危险路径模式
const DANGEROUS_PATH_PATTERNS = [
  /(^|\s)\/[^\s]/,              // 绝对路径
  /(^|\s)~/,                     // tilde home
  /(^|\s)\.\.(\/|$|\s)/,         // 父目录穿越
  /\$\{?HOME\b/,
  /\$\{?PWD\b/,
  /\bLD_PRELOAD\b/,
  /\bLD_LIBRARY_PATH\b/,
  /(^|\s|;|&&|\|\|)sudo\b/,
];

// 返回 Windows 上可用的 git-bash 路径
function gitBashPath(): string | null {
  const envPath = process.env.SZTU_BASH_PATH;
  if (envPath && existsSync(envPath)) return envPath;
  const candidates = [
    "C:\\Program Files\\Git\\bin\\bash.exe",
    "C:\\Program Files (x86)\\Git\\bin\\bash.exe",
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

// 预处理 agent 常见的 Windows/cmd 风格命令，让其在 git-bash 下可用
function preprocessCommand(command: string): string {
  let cmd = command;
  // cmd 风格 `cd /d X` → `cd X`
  cmd = cmd.replace(/\bcd\s+\/d\b/gi, "cd");
  // cmd 的 `dir /s`（递归）/`/b`（裸名）标志 → ls 的 -R/-1
  cmd = cmd.replace(/^\s*dir(\s+\/[sb]){1,2}\b/i, (match) => {
    return /\/s/i.test(match) ? "ls -R" : "ls -1";
  });
  // 前导 `dir` → `ls`
  cmd = cmd.replace(/^\s*dir(?=\s|$)/i, "ls");
  // cmd 的 `where X` → git-bash `which X`
  cmd = cmd.replace(/\bwhere\s+(?=[A-Za-z0-9_./\\-])/gi, "which ");
  // cmd 的重定向到 NUL 设备 → /dev/null
  cmd = cmd.replace(/(?<![\w.])2>nul\b/gi, "2>/dev/null");
  cmd = cmd.replace(/(?<![\w.])>nul\b/gi, ">/dev/null");
  // cmd 的 `set VAR=val` → bash 环境变量导出
  cmd = cmd.replace(/\bset\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)/gi, "export $1=$2");
  // cmd 的 `%VAR%` → bash `$VAR`
  cmd = cmd.replace(/%([A-Za-z_][A-Za-z0-9_]*)%/g, "$$$1");
  // cmd 的 `cls` → `clear`
  cmd = cmd.replace(/^\s*cls(?=\s|$)/i, "clear");
  // cmd 的 `type <文件>`（读文件）→ `cat`
  cmd = cmd.replace(/^\s*type\s+(?=[^\s;|&]*[./\\])/i, "cat ");
  // cmd 的 del/copy/move/ren → bash 的 rm/cp/mv
  cmd = cmd.replace(/^\s*del\s+/i, "rm ");
  cmd = cmd.replace(/^\s*copy\s+/i, "cp ");
  cmd = cmd.replace(/^\s*move\s+/i, "mv ");
  cmd = cmd.replace(/^\s*ren\s+/i, "mv ");
  // 含 Windows 盘符路径时转成 git-bash 风格
  if (/[A-Za-z]:[\\/]/.test(cmd)) {
    cmd = cmd.replace(/([A-Za-z]):([\\/])/g, (_m, drive: string, _sep: string) => `/${drive.toLowerCase()}/`);
    cmd = cmd.replace(/\\/g, "/");
  }
  return cmd;
}

// 提取命令名
function extractCmdName(command: string): string {
  let stripped = command.trim();
  const parts = stripped.split(/\s+/);
  if (parts.length > 0 && parts[0]!.includes("=")) {
    stripped = parts.slice(1).join(" ");
  }
  const word = stripped.split(/\s+/)[0] ?? "";
  if (word.includes("/")) return word.split("/").pop() ?? word;
  return word;
}

// 检测危险路径
function hasDangerousPaths(command: string): boolean {
  return DANGEROUS_PATH_PATTERNS.some(p => p.test(command));
}

// 推送输出块（通过回调或 EventBus）
function emitOutput(context: ToolContext, stream: ToolOutputStream, data: string): void {
  const ts = new Date().toISOString();
  const chunk: ToolOutputChunk = { tool_use_id: context.toolUseId, stream, data, ts };
  context.onOutput?.(chunk);
  // 通过 log.line 事件推送（前端可实时显示）
  if (context.events && context.runId) {
    context.events.publish({
      type: "log.line",
      run_id: context.runId,
      level: "DEBUG",
      source: `bash:${stream}`,
      message: data,
      ts,
    });
  }
}

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
  registry.register({ name: "ask_user_question", description: "Ask the user one to three structured questions and wait for an answer", permission: "read_only", schema: { type: "object", properties: { questions: { type: "array", minItems: 1, maxItems: 3, items: { type: "object", properties: { id: { type: "string" }, header: { type: "string" }, question: { type: "string" }, options: { type: "array", minItems: 2, maxItems: 4, items: { type: "object", properties: { label: { type: "string" }, description: { type: "string" } }, required: ["label"] } }, multi_select: { type: "boolean" } }, required: ["question", "options"] } } }, required: ["questions"] }, async invoke(params) { try { return ok(JSON.stringify({ answers: await ask(Array.isArray(params.questions) ? params.questions as Array<Record<string, unknown>> : []) })); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); } } });
}

export function createSpawnAgentTool(run: (role: string, goal: string, context?: string) => Promise<unknown>): Tool {
  return { name: "spawn_agent", description: "Delegate a focused task to a specialist subagent and return its evidence", permission: "workspace_write", schema: { type: "object", properties: { role: { type: "string", enum: ["planner", "coder", "tester", "reviewer"] }, goal: { type: "string", minLength: 1 }, context: { type: "string" } }, required: ["role", "goal"] }, async invoke(params) { const role = String(params.role ?? ""); const goal = String(params.goal ?? ""); if (!/^(planner|coder|tester|reviewer)$/.test(role) || !goal.trim()) return fail("role and goal are required", "schema_error"); try { return ok(JSON.stringify(await run(role, goal, typeof params.context === "string" ? params.context : undefined))); } catch (error) { return fail(error instanceof Error ? error.message : String(error)); } } };
}

export function createSkillTool(workspaceRoot: string): Tool {
  return { name: "skill", description: "Load the full instructions for an enabled skill by name", permission: "read_only", schema: { type: "object", properties: { name: { type: "string", minLength: 1 } }, required: ["name"] }, async invoke(params) { try { const skill = await new SkillLoader(workspaceRoot).get(String(params.name ?? "")); return ok(JSON.stringify({ name: skill.name, description: skill.description, instructions: skill.system_prompt_template, allowed_tools: skill.allowed_tools })); } catch (error) { return fail(error instanceof Error ? error.message : String(error), "schema_error"); } } };
}

export function createWorkflowTool(run: (graph: unknown) => Promise<unknown>): Tool {
  return { name: "run_workflow", description: "Execute a validated planner WorkflowGraph as a parallel specialist workflow", permission: "workspace_write", schema: { type: "object", properties: { workflow: { type: "object" } }, required: ["workflow"] }, async invoke(params) { try { return ok(JSON.stringify(await run(params.workflow))); } catch (error) { return fail(error instanceof Error ? error.message : String(error), "schema_error"); } } };
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

export function createWorkspaceTools(extraTools: Tool[] = []): ToolRegistry {
  const registry = new ToolRegistry();
  registry.register({ name: "read_file", description: "Read a UTF-8 file inside the workspace with line numbers and optional line pagination", permission: "read_only", schema: { type: "object", properties: { path: { type: "string" }, offset: { type: "integer", minimum: 0, description: "Zero-based first line" }, limit: { type: "integer", minimum: 1, maximum: 2000, description: "Maximum lines" } }, required: ["path"] }, async invoke(params, context) {
    const file = str(params, "path"); if (!file) return fail("path is required", "schema_error");
    try {
      const target = await context.workspace.resolveExisting(file);
      // 二进制办公文档（PDF/DOCX/XLSX/PPTX）按 UTF-8 读只会得到乱码：给出指向 parse_document 的提示
      const documentHint = detectDocumentFormat(path.basename(target));
      if (documentHint) {
        return ok(`${file} is a binary ${documentHint.toUpperCase()} document; read_file cannot render its content. Use the parse_document tool ({"path": "${file}"}) to extract text, tables and metadata.`);
      }
      const data = await readFile(target); const byteLimit = 2 * 1024 * 1024;
      const content = data.subarray(0, byteLimit).toString("utf8"); const lines = content.split(/\r?\n/);
      if (lines.at(-1) === "") lines.pop();
      const offset = Number.isInteger(params.offset) ? Math.max(0, Number(params.offset)) : 0;
      const limit = Number.isInteger(params.limit) ? Math.min(2000, Math.max(1, Number(params.limit))) : 2000;
      const page = lines.slice(offset, offset + limit);
      const numbered = page.map((line, index) => `${String(offset + index + 1).padStart(6, " ")}\t${line}`).join("\n");
      const end = Math.min(lines.length, offset + page.length);
      const suffix = end < lines.length || data.length > byteLimit ? `\n\n[${end < lines.length ? `lines ${offset + 1}-${end}/${lines.length}` : `end of file`}${data.length > byteLimit ? `; file truncated at ${byteLimit} bytes` : ""}]` : "";
      return ok(`${numbered}${suffix}`.trimEnd());
    } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "parse_document", description: "Extract readable text, tables and metadata from binary documents (PDF, DOCX, XLSX) as Markdown", permission: "read_only", schema: { type: "object", properties: { path: { type: "string", description: "Path to the document, relative to workspace root" }, format: { type: "string", enum: ["auto", "pdf", "docx", "xlsx"], description: "Force a parser instead of extension/magic detection", default: "auto" }, max_pages: { type: "integer", minimum: 1, maximum: 200, description: "PDF: parse only the first N pages (default: all)" }, max_rows: { type: "integer", minimum: 1, maximum: 5000, description: "XLSX: maximum rows per sheet (default: 500)" } }, required: ["path"] }, async invoke(params, context) {
    const file = str(params, "path"); if (!file) return fail("path is required", "schema_error");
    try {
      const target = await context.workspace.resolveExisting(file);
      const buffer = await readFile(target); const sizeLimit = 50 * 1024 * 1024;
      if (buffer.length > sizeLimit) return fail(`document too large: ${buffer.length} bytes (limit ${sizeLimit})`);
      const requested = str(params, "format") ?? "auto";
      const format = requested === "auto" ? detectDocumentFormat(path.basename(target), buffer) : requested as ParsedDocument["format"];
      if (!format || format === "unknown") return fail(`unsupported document format: ${path.extname(file) || "(no extension)"} — supported: pdf, docx, xlsx`, "schema_error");
      // 懒加载：pdf/docx/xlsx 解析库较重，仅在真正解析文档时装入，不拖慢 daemon 启动
      const { documentParsers, formatDocumentMarkdown } = await import("./document-parser/index.js");
      if (!documentParsers.hasParser(format)) return fail(`parsing for ${format.toUpperCase()} is not supported yet`, "schema_error");
      const doc = await documentParsers.parse(buffer, format, {
        max_pages: Number.isInteger(params.max_pages) ? Number(params.max_pages) : undefined,
        max_rows: Number.isInteger(params.max_rows) ? Number(params.max_rows) : undefined,
      });
      return ok(formatDocumentMarkdown(doc));
    } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
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
    try {
      const root = context.workspace.resolve(str(params, "path") ?? ".");
      const workspaceRoot = context.workspace.root;
      const matches: string[] = [];

      // 单文件情况直接返回
      const rootStat = await stat(root);
      if (rootStat.isFile()) {
        const rel = path.relative(workspaceRoot, root).split(path.sep).join("/");
        if (globMatch(rel, pattern)) return ok(rel);
        return ok("No files found.");
      }

      // 流式遍历：边遍历边匹配，达到结果上限立即停止
      for await (const file of walkFiles(workspaceRoot, root, context.signal)) {
        if (globMatch(file, pattern)) {
          matches.push(file);
          if (matches.length >= MAX_RESULTS) break;
        }
      }

      matches.sort();
      return ok(matches.length ? matches.join("\n") : "No files found.");
    } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "grep_search", description: "Search workspace files with a regular expression", permission: "read_only", schema: { type: "object", properties: { pattern: { type: "string" }, path: { type: "string" }, glob: { type: "string" } }, required: ["pattern"] }, async invoke(params, context) {
    const pattern = str(params, "pattern"); if (!pattern) return fail("pattern is required", "schema_error");
    let matcher: RegExp;
    try { matcher = new RegExp(pattern, params.case_sensitive === true ? "" : "i"); }
    catch (error) { return fail(error instanceof Error ? error.message : String(error), "schema_error"); }

    try {
      const root = context.workspace.root;
      const target = context.workspace.resolve(str(params, "path") ?? ".");
      const globPattern = params.glob ? String(params.glob) : null;
      const result: string[] = [];
      const filesToSearch: string[] = [];
      let filesTruncated = false;

      // 收集需要搜索的文件（流式遍历，提前终止）
      const targetStat = await stat(target);
      if (targetStat.isFile()) {
        filesToSearch.push(path.relative(root, target).split(path.sep).join("/"));
      } else {
        for await (const file of walkFiles(root, target, context.signal)) {
          if (globPattern && !globMatch(file, globPattern)) continue;
          filesToSearch.push(file);
          // 限制待搜索文件数量，防止遍历超大仓库
          if (filesToSearch.length >= 2000) { filesTruncated = true; break; }
        }
      }

      // 并发读取并搜索文件（带信号量限流）
      const semaphore = new AsyncSemaphore(FILE_READ_CONCURRENCY);
      const searchFile = async (file: string): Promise<string[]> => {
        await semaphore.acquire();
        try {
          context.signal?.throwIfAborted();
          const data = await readFile(path.join(root, file));
          // 跳过二进制文件和超大文件
          if (data.length > 512 * 1024 || isBinaryFile(data.subarray(0, 512))) return [];
          const text = data.toString("utf8");
          const matches: string[] = [];
          const lines = text.split(/\r?\n/);
          for (let index = 0; index < lines.length; index++) {
            const line = lines[index]!;
            if (matcher.test(line)) {
              matches.push(`${file}:${index + 1}: ${line}`);
            }
          }
          return matches;
        } catch {
          return []; // 无法读取的文件跳过
        } finally {
          semaphore.release();
        }
      };

      const searchResults = await Promise.all(filesToSearch.map(searchFile));
      for (const matches of searchResults) {
        for (const match of matches) {
          result.push(match);
          if (result.length >= MAX_RESULTS) break;
        }
        if (result.length >= MAX_RESULTS) break;
      }

      const matchesTruncated = result.length >= MAX_RESULTS;
      const footer = filesTruncated || matchesTruncated ? `\n[search truncated: files=${filesToSearch.length}${filesTruncated ? "+" : ""}, matches=${result.length}${matchesTruncated ? "+" : ""}; narrow path/glob/pattern to continue]` : "";
      return ok((result.length ? result.join("\n") : "No matches found.") + footer);
    } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  const editSchema = { type: "object", properties: { old_string: { type: "string" }, new_string: { type: "string" }, replace_all: { type: "boolean" }, start_line: { type: "integer", minimum: 1 }, end_line: { type: "integer", minimum: 1 } }, required: ["old_string", "new_string"] };
  registry.register({ name: "edit_file", description: "Atomically apply one or more exact replacements; optional line anchors prevent edits to the wrong occurrence", permission: "workspace_write", schema: { type: "object", properties: { path: { type: "string" }, ...editSchema.properties, edits: { type: "array", minItems: 1, items: editSchema } }, required: ["path"], anyOf: [{ required: ["old_string", "new_string"] }, { required: ["edits"] }] }, async invoke(params, context) {
    const file = str(params, "path"); if (!file) return fail("path is required", "schema_error");
    const edits = Array.isArray(params.edits) ? params.edits as Array<Record<string, unknown>> : [params];
    try {
      const target = await context.workspace.resolveExisting(file); let updated = (await readFile(target, "utf8")).replace(/\r\n/g, "\n"); let replacements = 0;
      for (const edit of edits) {
        const oldString = str(edit, "old_string"); const newString = str(edit, "new_string");
        if (oldString === null || newString === null || oldString === newString) return fail("each edit requires distinct old_string and new_string", "schema_error");
        const start = Number.isInteger(edit.start_line) ? Math.max(1, Number(edit.start_line)) : 1; const end = Number.isInteger(edit.end_line) ? Math.max(start, Number(edit.end_line)) : Number.MAX_SAFE_INTEGER;
        const lines = updated.split("\n"); const scoped = lines.slice(start - 1, end).join("\n"); const count = scoped.split(oldString).length - 1;
        if (!count) return fail(`old_string not found in ${file} within lines ${start}-${end === Number.MAX_SAFE_INTEGER ? "end" : end}; re-read the file with line numbers`);
        if (count > 1 && edit.replace_all !== true) return fail(`old_string appears ${count} times in ${file}; re-read and provide line anchors`, "schema_error");
        const replaced = edit.replace_all === true ? scoped.split(oldString).join(newString) : scoped.replace(oldString, newString);
        lines.splice(start - 1, end === Number.MAX_SAFE_INTEGER ? lines.length : end - start + 1, ...replaced.split("\n")); updated = lines.join("\n"); replacements += edit.replace_all === true ? count : 1;
      }
      await writeFile(target, updated, "utf8"); context.onFileChanged?.(path.relative(context.workspace.root, target).split(path.sep).join("/")); return ok(`applied ${edits.length} edit(s), replacing ${replacements} occurrence(s) in ${file}`);
    } catch (error) { return fail(error instanceof Error ? error.message : String(error)); }
  }});
  registry.register({ name: "bash", description: "Execute a non-interactive shell command with real-time streaming output. Output is truncated at 64KB. Windows uses Git Bash if available.", permission: "danger_full_access", retryable: false, classifyPermission: classifyBashPermission, schema: { type: "object", properties: { command: { type: "string", minLength: 1, description: "Shell command to execute" }, timeout: { type: "integer", minimum: 1, maximum: 120, description: "Maximum seconds to wait (default 30, max 120)" }, background: { type: "boolean", description: "Run in background (not yet supported, reserved for future use)" } }, required: ["command"] }, async invoke(params, context) {
    const command = str(params, "command");
    if (!command) return fail("command is required", "schema_error");

    // 拦截安装/更新依赖命令。
    // 评测场景（Terminal-Bench 等 bench harness）任务本身常要求安装依赖，
    // 由 SZTU_EVAL_ALLOW_INSTALL=1 显式放开（与 py-runtime bash.py 行为一致）。
    if (BLOCKED_INSTALL_RE.test(command) && !/^(1|true|yes)$/i.test(process.env.SZTU_EVAL_ALLOW_INSTALL ?? "")) {
      return fail("[blocked] Installing/updating packages is not allowed in this environment — dependencies are already provisioned. Do not run install/update commands; use the existing packages directly.");
    }

    // Windows 下使用 Git Bash（如果可用），否则使用 cmd.exe
    const isWindows = process.platform === "win32";
    const bashPath = isWindows ? gitBashPath() : null;
    const processedCommand = isWindows && bashPath ? preprocessCommand(command) : command;

    // 确定超时时间（git 命令默认 20s）
    let timeoutSec = Math.min(120, Math.max(1, Number(params.timeout ?? DEFAULT_TIMEOUT)));
    if (params.timeout === undefined && extractCmdName(command).toLowerCase() === "git") {
      timeoutSec = DEFAULT_GIT_TIMEOUT;
    }

    return new Promise((resolve) => {
      if (context.signal?.aborted) { resolve(fail("Run cancelled")); return; }

      let child: ChildProcessWithoutNullStreams;
      try {
        if (bashPath) {
          // Windows + Git Bash：使用 bash --login -c 执行
          child = spawn(bashPath, ["--login", "-c", processedCommand], {
            cwd: context.workspace.root,
            windowsHide: true,
            env: { ...process.env, TERM: "dumb" },
          });
        } else if (isWindows) {
          // Windows 无 Git Bash：使用 cmd.exe
          child = spawn("cmd.exe", ["/d", "/s", "/c", command], {
            cwd: context.workspace.root,
            windowsHide: true,
          });
        } else {
          // Unix/Linux/macOS：使用系统 shell
          const shell = process.env.SHELL || "/bin/sh";
          child = spawn(shell, ["-c", command], {
            cwd: context.workspace.root,
            windowsHide: true,
            env: { ...process.env, TERM: "dumb" },
          });
        }
      } catch (error) {
        return resolve(fail(error instanceof Error ? error.message : String(error)));
      }

      let output = "";
      let truncated = false;
      let settled = false;
      let lastNewlineIndex = 0;
      // 行缓冲：按行推送输出，避免逐字符推送造成事件风暴
      let lineBuffer = "";

      const MAX_LINE_BUFFER = 4096; // 单行最大缓冲（无换行时强制刷新）

      const processData = (stream: ToolOutputStream, chunk: Buffer) => {
        const text = chunk.toString("utf8");
        // 追加到总输出（带截断）
        if (!truncated) {
          const newLength = output.length + text.length;
          if (newLength > MAX_BASH_OUTPUT) {
            output += text.slice(0, MAX_BASH_OUTPUT - output.length);
            truncated = true;
          } else {
            output += text;
          }
        }
        // 行缓冲推送实时输出
        lineBuffer += text;
        let newlinePos: number;
        while ((newlinePos = lineBuffer.indexOf("\n")) !== -1) {
          const line = lineBuffer.slice(0, newlinePos + 1);
          lineBuffer = lineBuffer.slice(newlinePos + 1);
          emitOutput(context, stream, line);
        }
        // 无换行但缓冲过长，强制刷新
        if (lineBuffer.length > MAX_LINE_BUFFER) {
          emitOutput(context, stream, lineBuffer);
          lineBuffer = "";
        }
      };

      const finish = (result: ToolResult) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeoutHandle);
        context.signal?.removeEventListener("abort", abortHandler);
        // 推送剩余缓冲
        if (lineBuffer.length > 0) {
          emitOutput(context, "combined", lineBuffer);
          lineBuffer = "";
        }
        // 推送截断通知
        if (truncated) {
          emitOutput(context, "combined", `\n[output truncated at ${MAX_BASH_OUTPUT} bytes]\n`);
        }
        resolve(result);
      };

      const abortHandler = () => {
        if (!settled) {
          try { child.kill("SIGTERM"); } catch { /* ignore */ }
          // 强制杀死进程树（Windows）
          setTimeout(() => { if (!settled) try { child.kill("SIGKILL"); } catch { /* ignore */ } }, 1000);
          finish(fail("Run cancelled"));
        }
      };

      const timeoutHandle = setTimeout(() => {
        if (!settled) {
          try { child.kill("SIGTERM"); } catch { /* ignore */ }
          setTimeout(() => { if (!settled) try { child.kill("SIGKILL"); } catch { /* ignore */ } }, 1000);
          finish(fail(`[timeout after ${timeoutSec}s]`, "timeout"));
        }
      }, timeoutSec * 1000);

      context.signal?.addEventListener("abort", abortHandler, { once: true });

      child.stdout.on("data", (chunk: Buffer) => processData("stdout", chunk));
      child.stderr.on("data", (chunk: Buffer) => processData("stderr", chunk));

      child.on("error", (error) => {
        finish(fail(error.message));
      });

      child.on("close", (code) => {
        const truncatedMsg = truncated ? `\n\n[output truncated at ${MAX_BASH_OUTPUT} bytes]` : "";
        if (code === 0) {
          finish(ok(output + truncatedMsg || "[no output]"));
        } else {
          const exitMsg = output ? `[exit ${code}]\n${output}` : `[exit ${code}]`;
          finish({
            ok: false,
            output: exitMsg + truncatedMsg,
            error: `command exited with code ${code}`,
            errorType: "runtime_error",
          });
        }
      });
    });
  }});
  for (const tool of extraTools) registry.register(tool);
  return registry;
}
