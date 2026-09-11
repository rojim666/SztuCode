import { randomUUID } from "node:crypto";
import { appendFile, mkdir, readFile, realpath, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Tool } from "./tools.js";

export type OffloadRecord = {
  id: string;
  run_id: string;
  tool_name: string;
  tool_use_id: string;
  ref_path: string;
  summary: string;
  char_count: number;
  line_count: number;
  is_error: boolean;
  ts: string;
};

export type OffloadOptions = { enabled?: boolean; minChars?: number; minLines?: number; forceTools?: ReadonlySet<string>; summaryMaxChars?: number };

const defaultForceTools = new Set<string>();

export class OffloadManager {
  readonly enabled: boolean;
  private readonly minChars: number;
  private readonly minLines: number;
  private readonly forceTools: ReadonlySet<string>;
  private readonly summaryMaxChars: number;

  constructor(private readonly runDir: string, options: OffloadOptions = {}) {
    this.enabled = options.enabled ?? true;
    this.minChars = options.minChars ?? 2_000;
    this.minLines = options.minLines ?? 50;
    this.forceTools = options.forceTools ?? defaultForceTools;
    this.summaryMaxChars = options.summaryMaxChars ?? 300;
  }

  shouldOffload(toolName: string, content: string): boolean {
    if (!this.enabled || toolName === "memory_read" || toolName === "read_ref") return false;
    return this.forceTools.has(toolName) || content.length > this.minChars || countNewlines(content) >= this.minLines;
  }

  async offload(toolName: string, toolUseId: string, content: string, runId: string, isError = false): Promise<OffloadRecord> {
    const refsDir = path.join(this.runDir, "refs");
    const offloadDir = path.join(this.runDir, "offload");
    await mkdir(refsDir, { recursive: true });
    await mkdir(offloadDir, { recursive: true });
    const stamp = compactTimestamp();
    const refPath = `refs/${safeSegment(toolName)}_${stamp}_${randomUUID().slice(0, 8)}.md`;
    const ts = new Date().toISOString();
    const record: OffloadRecord = {
      id: `off_${stamp}_${randomUUID().slice(0, 8)}`,
      run_id: runId,
      tool_name: toolName,
      tool_use_id: toolUseId,
      ref_path: refPath,
      summary: makeOffloadSummary(toolName, content, this.summaryMaxChars),
      char_count: content.length,
      line_count: countNewlines(content) + 1,
      is_error: isError,
      ts,
    };
    const header = `# ${toolName} @ ${ts}\n# run_id: ${runId}\n# tool_use_id: ${toolUseId}\n# chars: ${record.char_count} | lines: ${record.line_count}\n\n`;
    await writeFile(path.join(this.runDir, ...refPath.split("/")), header + content, "utf8");
    try { await appendFile(path.join(offloadDir, "offload.jsonl"), `${JSON.stringify(record)}\n`, "utf8"); } catch { /* The ref file remains the source of truth. */ }
    return record;
  }

  placeholder(record: OffloadRecord): string {
    return `[上下文卸载: ${record.ref_path}]\n摘要: ${record.summary}\n统计: ${record.char_count} 字符, ${record.line_count} 行\n使用 read_ref(\"${record.ref_path}\") 读取完整输出`;
  }

  async readRef(refPath: string): Promise<string> {
    const normalized = refPath.replaceAll("\\", "/");
    if (!/^refs\/[^/]+\.md$/.test(normalized)) throw new Error(`Invalid ref_path: ${refPath}`);
    const refsRoot = await realpath(path.join(this.runDir, "refs"));
    const target = await realpath(path.join(this.runDir, ...normalized.split("/")));
    if (path.dirname(target) !== refsRoot) throw new Error(`Invalid ref_path: ${refPath}`);
    const text = await readFile(target, "utf8");
    const separator = text.indexOf("\n\n");
    return text.startsWith("# ") && separator >= 0 ? text.slice(separator + 2) : text;
  }
}

export function createReadRefTool(manager: OffloadManager): Tool {
  return {
    name: "read_ref",
    description: "Read a paged excerpt from a complete tool result referenced by an offload marker",
    permission: "read_only",
    schema: { type: "object", properties: { ref_path: { type: "string" }, offset: { type: "integer", minimum: 0 }, limit: { type: "integer", minimum: 1, maximum: 8_000 } }, required: ["ref_path"] },
    async invoke(params) {
      const refPath = typeof params.ref_path === "string" ? params.ref_path : "";
      const offset = params.offset === undefined ? 0 : Number(params.offset);
      const limit = params.limit === undefined ? 4_000 : Number(params.limit);
      if (!refPath || !Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 8_000) return { ok: false, output: "", error: "ref_path, offset, or limit is invalid", errorType: "schema_error" };
      try {
        const full = await manager.readRef(refPath);
        const content = full.slice(offset, offset + limit);
        const nextOffset = offset + content.length;
        return { ok: true, output: `${content}\n\n[ref page: chars ${offset}:${nextOffset}/${full.length}${nextOffset < full.length ? `, next_offset=${nextOffset}` : ", end"}]` };
      } catch (error) { return { ok: false, output: "", error: error instanceof Error ? error.message : String(error), errorType: "runtime_error" }; }
    },
  };
}

export function makeOffloadSummary(toolName: string, content: string, maxChars = 300): string {
  const lines = content.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!content.trim()) return "(empty output)";
  if (toolName === "bash") {
    const marked = lines.slice(-15).filter((line) => /passed|failed|error|test|success|done|\bok\b/i.test(line));
    return bounded(marked.at(-1) ?? [...lines].reverse().find((line) => line.length > 10) ?? `bash output: ${lines.length} lines`, maxChars);
  }
  if (toolName === "read_file" || toolName === "list_dir") return `${toolName} output: ${lines.length} lines, ${content.length} chars${content.endsWith("[truncated]") ? " (truncated)" : ""}`;
  if (["grep", "glob", "grep_search", "glob_search"].includes(toolName)) {
    const matches = lines.filter((line) => !line.startsWith("#") && !line.startsWith("//"));
    const preview = bounded(matches.slice(0, 3).map((line) => line.slice(0, 120)).join("; "), maxChars);
    return `${toolName}: ${matches.length} result(s)${preview ? `. Preview: ${preview}` : ""}`;
  }
  return bounded(lines[0] ?? content, maxChars) + (lines.length > 1 ? ` (${lines.length} lines)` : "");
}

const bounded = (value: string, maxChars: number) => value.length <= maxChars ? value : `${value.slice(0, Math.max(0, maxChars - 3))}...`;
const countNewlines = (value: string) => (value.match(/\n/g) ?? []).length;
const safeSegment = (value: string) => value.replace(/[^A-Za-z0-9_.-]/g, "_") || "tool";
const compactTimestamp = () => new Date().toISOString().replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
