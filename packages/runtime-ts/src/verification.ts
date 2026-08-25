import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";

export type ContractSource = "user" | "project_config" | "ci" | "inferred" | "agent_suggested";
export type CompletionCondition = {
  id: string;
  description: string;
  source: ContractSource;
  check_command: string[] | null;
  required: boolean;
  priority: number;
};
export type CompletionContract = { run_id: string; conditions: CompletionCondition[]; created_at: string };
export type EvidenceKind = "command_exit_code" | "test_output" | "file_state" | "model_assertion";
export type Evidence = {
  condition_id: string;
  kind: EvidenceKind;
  command: string;
  exit_code: number | null;
  output_path: string;
  workspace_digests: Record<string, string>;
  collected_at: string;
  stale: boolean;
};
export type VerificationOutcome = "verified" | "partial" | "unverified" | "failed" | "env_blocked" | "stale";
export type ConditionResult = { condition_id: string; outcome: VerificationOutcome; evidence: Evidence | null; message: string };
export type VerificationResult = { run_id: string; results: ConditionResult[]; overall: VerificationOutcome; verified_at: string };

const now = () => new Date().toISOString();
const safeName = (id: string) => id.replace(/[^A-Za-z0-9._-]+/g, "_") || "condition";

function scalar(value: string): string | boolean | number | string[] {
  const trimmed = value.trim();
  if (trimmed === "true" || trimmed === "false") return trimmed === "true";
  if (/^-?\d+$/.test(trimmed)) return Number(trimmed);
  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    return trimmed.slice(1, -1).split(",").map((item) => item.trim()).filter(Boolean).map((item) => item.replace(/^(['"])(.*)\1$/, "$2"));
  }
  return trimmed.replace(/^(['"])(.*)\1$/, "$2");
}

// This intentionally supports the small [[check]] schema only. Unknown TOML is ignored
// instead of being interpreted as executable configuration.
function parseChecksToml(text: string): CompletionCondition[] {
  const entries: Record<string, unknown>[] = [];
  let current: Record<string, unknown> | null = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+#.*$/, "").trim();
    if (!line) continue;
    if (line === "[[check]]") { current = {}; entries.push(current); continue; }
    const match = /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/.exec(line);
    if (!match || !current) throw new Error("invalid checks.toml entry");
    current[match[1]!] = scalar(match[2]!);
  }
  return entries.map((entry, index) => {
    const command = entry.command;
    if (!Array.isArray(command) || !command.length || command.some((part) => typeof part !== "string" || !part)) throw new Error(`check #${index + 1}: command must be a non-empty array of strings`);
    const id = entry.id ?? `user-${index + 1}`;
    const description = entry.description ?? command.join(" ");
    const required = entry.required ?? true;
    const priority = entry.priority ?? 0;
    if (typeof id !== "string" || !id || typeof description !== "string" || typeof required !== "boolean" || typeof priority !== "number" || !Number.isInteger(priority)) throw new Error(`check #${index + 1}: invalid field`);
    return { id, description, source: "user", check_command: [...command], required, priority };
  });
}

function dedupeAndSort(conditions: CompletionCondition[]): CompletionCondition[] {
  const seen = new Set<string>();
  return conditions.filter((condition) => {
    const key = JSON.stringify(condition.check_command ?? []);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  }).sort((a, b) => b.priority - a.priority);
}

async function exists(file: string): Promise<boolean> { return stat(file).then(() => true, () => false); }

// Discover explicit user checks first; package scripts provide conservative project checks
// when no .sztu/checks.toml is present.
export async function buildCompletionContract(runId: string, workspaceRoot: string): Promise<CompletionContract | null> {
  let conditions: CompletionCondition[] = [];
  const checksPath = path.join(workspaceRoot, ".sztu", "checks.toml");
  if (await exists(checksPath)) {
    try { conditions = parseChecksToml(await readFile(checksPath, "utf8")); }
    catch { conditions = []; }
  }
  if (!conditions.length) {
    try {
      const packageJson = JSON.parse(await readFile(path.join(workspaceRoot, "package.json"), "utf8")) as { scripts?: Record<string, unknown> };
      const scripts = packageJson.scripts ?? {};
      const candidates: Array<[string, string, number, boolean]> = [["typecheck", "typecheck", 20, true], ["lint", "lint", 15, true], ["test", "test", 10, true]];
      conditions = candidates.filter(([name]) => typeof scripts[name] === "string").map(([name, command, priority, required]) => ({ id: `project-${name}`, description: `npm run ${name}`, source: "project_config", check_command: ["npm", "run", command], required, priority }));
    } catch { /* no project manifest */ }
  }
  conditions = dedupeAndSort(conditions);
  return conditions.length ? { run_id: runId, conditions, created_at: now() } : null;
}

export function aggregateOutcomes(conditions: CompletionCondition[], results: ConditionResult[]): VerificationOutcome {
  if (!results.length) return "unverified";
  const required = new Set(conditions.filter((condition) => condition.required).map((condition) => condition.id));
  if (results.some((result) => result.outcome === "failed" && required.has(result.condition_id))) return "failed";
  if (!results.some((result) => result.outcome === "verified")) return "unverified";
  return results.filter((result) => required.has(result.condition_id)).every((result) => result.outcome === "verified") ? "verified" : "partial";
}

export class VerificationExecutor {
  constructor(private readonly workspaceRoot: string, private readonly runRoot: string, private readonly timeoutMs = 60_000) {}

  async verify(contract: CompletionContract, workspaceDigests: Record<string, string> = {}): Promise<VerificationResult> {
    const results: ConditionResult[] = [];
    for (const condition of [...contract.conditions].sort((a, b) => b.priority - a.priority)) results.push(await this.check(condition, workspaceDigests));
    return { run_id: contract.run_id, results, overall: aggregateOutcomes(contract.conditions, results), verified_at: now() };
  }

  private async check(condition: CompletionCondition, digests: Record<string, string>): Promise<ConditionResult> {
    const command = condition.check_command;
    if (!command?.length) return { condition_id: condition.id, outcome: "unverified", evidence: null, message: "no check_command; cannot verify automatically" };
    const outputPath = path.join(this.runRoot, "verification", `${safeName(condition.id)}.log`);
    let child: ReturnType<typeof spawn>;
    try { child = spawn(command[0]!, command.slice(1), { cwd: this.workspaceRoot, shell: false, stdio: ["ignore", "pipe", "pipe"] }); }
    catch (error) { return { condition_id: condition.id, outcome: "env_blocked", evidence: null, message: `cannot start check command: ${String(error)}` }; }
    const chunks: Buffer[] = [];
    child.stdout?.on("data", (chunk: Buffer) => chunks.push(chunk)); child.stderr?.on("data", (chunk: Buffer) => chunks.push(chunk));
    let startupError: Error | undefined;
    const exitCode = await new Promise<number | null>((resolve) => {
      let settled = false;
      const finish = (code: number | null) => { if (settled) return; settled = true; resolve(code); };
      child.once("error", (error) => { startupError = error instanceof Error ? error : new Error(String(error)); finish(null); }); child.once("close", (code) => finish(code));
      setTimeout(() => { if (!settled) { child.kill("SIGKILL"); finish(null); } }, this.timeoutMs).unref();
    });
    if (startupError) return { condition_id: condition.id, outcome: "env_blocked", evidence: null, message: `cannot start check command: ${startupError.message}` };
    const evidence: Evidence = { condition_id: condition.id, kind: "command_exit_code", command: command.join(" "), exit_code: exitCode, output_path: await this.writeOutput(outputPath, Buffer.concat(chunks)), workspace_digests: digests, collected_at: now(), stale: false };
    if (exitCode === null) return { condition_id: condition.id, outcome: "failed", evidence, message: `check timed out or process failed after ${this.timeoutMs}ms` };
    return { condition_id: condition.id, outcome: exitCode === 0 ? "verified" : "failed", evidence, message: exitCode === 0 ? "" : `check command exited with code ${exitCode}` };
  }

  private async writeOutput(file: string, data: Buffer): Promise<string> {
    try { await mkdir(path.dirname(file), { recursive: true }); await writeFile(file, data); return file; } catch { return ""; }
  }
}

export function digestsFromChangeRecords(records: Array<{ path?: string; after_digest?: string }> | null | undefined): Record<string, string> {
  return Object.fromEntries((records ?? []).filter((record) => record.path && record.after_digest).map((record) => [record.path!, record.after_digest!]));
}

export function markStaleEvidence(result: VerificationResult, contract: CompletionContract, current: Record<string, string>): boolean {
  let changed = false;
  for (const condition of result.results) {
    if (!condition.evidence || condition.evidence.stale) continue;
    if (JSON.stringify(condition.evidence.workspace_digests) !== JSON.stringify(current)) {
      condition.evidence.stale = true; changed = true;
      if (condition.outcome === "verified") condition.outcome = "stale";
    }
  }
  if (changed) result.overall = aggregateOutcomes(contract.conditions, result.results);
  return changed;
}

export type FailureSignature = Array<[string, VerificationOutcome, number | null]>;
export const failureSignature = (result: VerificationResult): FailureSignature => result.results.map< [string, VerificationOutcome, number | null]>((item) => [item.condition_id, item.outcome, item.evidence?.exit_code ?? null]).sort((a, b) => a[0].localeCompare(b[0]));

export class RepairCircuitBreaker {
  private attempts = 0; private signatures: FailureSignature[] = []; private flips = 0;
  constructor(private readonly maxAttempts: number) {}
  record(signature: FailureSignature): void { const previous = this.signatures.at(-1); const before = this.signatures.at(-2); if (before && previous && JSON.stringify(signature) !== JSON.stringify(previous) && JSON.stringify(signature) === JSON.stringify(before)) this.flips += 1; this.signatures.push(signature); }
  noteAttempt(): void { this.attempts += 1; }
  stopReason(): string | null { if (this.attempts >= this.maxAttempts) return `max_repair_attempts reached (${this.maxAttempts})`; if (this.signatures.length > 1 && JSON.stringify(this.signatures.at(-1)) === JSON.stringify(this.signatures.at(-2))) return "identical failure signature across consecutive verifications"; if (this.flips >= 3) return `failure signature oscillation (flips=${this.flips})`; return null; }
}

export function buildRepairPrompt(result: VerificationResult, contract: CompletionContract): string {
  const descriptions = new Map(contract.conditions.map((condition) => [condition.id, condition.description]));
  const sections = ["[Verification failed] Independent verification FAILED; the task is NOT complete yet.", "Fix the failed conditions below, then stop. Verification will run again automatically."];
  for (const item of result.results.filter((entry) => entry.outcome === "failed")) {
    const tail = item.evidence?.output_path ? "\n" + "(See verification log: " + item.evidence.output_path + ")" : "";
    sections.push(`- condition: ${item.condition_id}\n  description: ${descriptions.get(item.condition_id) ?? ""}\n  exit_code: ${item.evidence?.exit_code ?? "unknown"}\n  message: ${item.message}${tail}`);
  }
  return sections.join("\n\n");
}
