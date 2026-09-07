#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import path from "node:path";

type GhResult = { status: number; stdout: string; stderr: string };
type Check = Record<string, unknown>;
type Analysis = Record<string, unknown>;

const failures = new Set(["failure", "error", "cancelled", "timed_out", "action_required"]);
const markers = ["error", "fail", "failed", "traceback", "exception", "assert", "panic", "fatal", "timeout", "segmentation fault"];
const pendingMarkers = ["still in progress", "log will be available when it is complete"];

function run(command: string, args: string[], cwd: string, binary = false): GhResult & { bytes?: Buffer } {
  const result = spawnSync(command, args, { cwd, encoding: binary ? "buffer" : "utf8", windowsHide: true });
  const stdout = binary ? (result.stdout as Buffer | null)?.toString("utf8") ?? "" : String(result.stdout ?? "");
  const stderr = binary ? (result.stderr as Buffer | null)?.toString("utf8") ?? "" : String(result.stderr ?? "");
  return { status: result.status ?? 1, stdout, stderr, bytes: binary ? (result.stdout as Buffer | null) ?? Buffer.alloc(0) : undefined };
}

const gh = (args: string[], cwd: string, binary = false) => run("gh", args, cwd, binary);
const normalize = (value: unknown) => value == null ? "" : String(value).trim().toLowerCase();
const message = (result: GhResult, fallback: string) => (result.stderr || result.stdout).trim() || fallback;
const isPending = (value: string) => pendingMarkers.some((item) => value.toLowerCase().includes(item));
const getString = (value: unknown) => typeof value === "string" ? value : "";

function parseArgs(argv: string[]) {
  const options: { repo: string; pr?: string; maxLines: number; context: number; json: boolean } = { repo: ".", maxLines: 160, context: 30, json: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--json") options.json = true;
    else if (["--repo", "--pr", "--max-lines", "--context"].includes(arg)) {
      const value = argv[++index]; if (!value) throw new Error(`Missing value for ${arg}`);
      if (arg === "--repo") options.repo = value;
      else if (arg === "--pr") options.pr = value;
      else if (arg === "--max-lines") options.maxLines = Math.max(1, Number.parseInt(value, 10));
      else options.context = Math.max(1, Number.parseInt(value, 10));
    } else if (arg === "--help" || arg === "-h") {
      console.log("Usage: inspect_pr_checks.ts [--repo path] [--pr number-or-url] [--max-lines n] [--context n] [--json]"); process.exit(0);
    } else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!Number.isFinite(options.maxLines) || !Number.isFinite(options.context)) throw new Error("Line limits must be integers.");
  return options;
}

function resolveRoot(repo: string): string {
  const start = path.resolve(repo); const result = run("git", ["rev-parse", "--show-toplevel"], start);
  if (result.status !== 0) throw new Error("Not inside a Git repository.");
  return result.stdout.trim();
}

function resolvePr(value: string | undefined, cwd: string): string {
  if (value) return value;
  const result = gh(["pr", "view", "--json", "number"], cwd);
  if (result.status !== 0) throw new Error(message(result, "Unable to resolve PR."));
  const number = (JSON.parse(result.stdout || "{}") as { number?: unknown }).number;
  if (!number) throw new Error("No PR number found.");
  return String(number);
}

function availableFields(value: string): string[] {
  const marker = value.indexOf("Available fields:");
  return marker < 0 ? [] : value.slice(marker + "Available fields:".length).split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function fetchChecks(pr: string, cwd: string): Check[] {
  let fields = ["name", "state", "conclusion", "detailsUrl", "startedAt", "completedAt"];
  let result = gh(["pr", "checks", pr, "--json", fields.join(",")], cwd);
  if (result.status !== 0) {
    const offered = availableFields(`${result.stderr}\n${result.stdout}`);
    fields = ["name", "state", "bucket", "link", "startedAt", "completedAt", "workflow"].filter((field) => offered.includes(field));
    if (!fields.length) throw new Error(message(result, "gh pr checks failed."));
    result = gh(["pr", "checks", pr, "--json", fields.join(",")], cwd);
    if (result.status !== 0) throw new Error(message(result, "gh pr checks failed."));
  }
  const payload: unknown = JSON.parse(result.stdout || "[]");
  if (!Array.isArray(payload)) throw new Error("Unexpected checks JSON shape.");
  return payload as Check[];
}

function runId(url: string) { return /\/actions\/runs\/(\d+)/.exec(url)?.[1] ?? /\/runs\/(\d+)/.exec(url)?.[1] ?? null; }
function jobId(url: string) { return /\/actions\/runs\/\d+\/job\/(\d+)/.exec(url)?.[1] ?? /\/job\/(\d+)/.exec(url)?.[1] ?? null; }
function failureSnippet(log: string, maxLines: number, context: number): string {
  const lines = log.split(/\r?\n/); let found = -1;
  for (let index = lines.length - 1; index >= 0; index -= 1) if (markers.some((item) => lines[index].toLowerCase().includes(item))) { found = index; break; }
  if (found < 0) return lines.slice(-maxLines).join("\n");
  return lines.slice(Math.max(0, found - context), Math.min(lines.length, found + context)).slice(-maxLines).join("\n");
}

function runMetadata(id: string, cwd: string): Record<string, unknown> | null {
  const fields = "conclusion,status,workflowName,name,event,headBranch,headSha,url";
  const result = gh(["run", "view", id, "--json", fields], cwd);
  if (result.status !== 0) return null;
  try { const value: unknown = JSON.parse(result.stdout || "{}"); return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null; } catch { return null; }
}

function fetchLog(id: string, job: string | null, cwd: string): { log?: string; error?: string; pending?: boolean } {
  const result = gh(["run", "view", id, "--log"], cwd);
  if (result.status === 0) return { log: result.stdout };
  const error = message(result, "gh run view failed");
  if (!isPending(error)) return { error };
  if (!job) return { error, pending: true };
  const repo = gh(["repo", "view", "--json", "nameWithOwner"], cwd);
  if (repo.status !== 0) return { error: "Unable to resolve repository name for job logs." };
  const slug = (JSON.parse(repo.stdout || "{}") as { nameWithOwner?: string }).nameWithOwner;
  if (!slug) return { error: "Unable to resolve repository name for job logs." };
  const jobLog = gh(["api", `/repos/${slug}/actions/jobs/${job}/logs`], cwd, true);
  if (jobLog.status !== 0) { const value = message(jobLog, "gh api job logs failed"); return { error: value, pending: isPending(value) }; }
  if (jobLog.bytes?.subarray(0, 2).equals(Buffer.from("PK"))) return { error: "Job logs returned a zip archive; unable to parse." };
  return { log: jobLog.stdout };
}

function analyze(check: Check, cwd: string, maxLines: number, context: number): Analysis {
  const url = getString(check.detailsUrl) || getString(check.link); const run = runId(url); const job = jobId(url);
  const output: Analysis = { name: check.name ?? "", detailsUrl: url, runId: run, jobId: job };
  if (!run) return { ...output, status: "external", note: "No GitHub Actions run id detected in detailsUrl." };
  const metadata = runMetadata(run, cwd); const fetched = fetchLog(run, job, cwd);
  if (fetched.pending) return { ...output, status: "log_pending", note: fetched.error ?? "Logs are not available yet.", ...(metadata ? { run: metadata } : {}) };
  if (fetched.error) return { ...output, status: "log_unavailable", error: fetched.error, ...(metadata ? { run: metadata } : {}) };
  const log = fetched.log ?? "";
  return { ...output, status: "ok", run: metadata ?? {}, logSnippet: failureSnippet(log, maxLines, context), logTail: log.split(/\r?\n/).slice(-maxLines).join("\n") };
}

function render(pr: string, results: Analysis[]) {
  console.log(`PR #${pr}: ${results.length} failing checks analyzed.`);
  for (const result of results) {
    console.log("-".repeat(60)); console.log(`Check: ${result.name ?? ""}`);
    if (result.detailsUrl) console.log(`Details: ${result.detailsUrl}`); if (result.runId) console.log(`Run ID: ${result.runId}`); if (result.jobId) console.log(`Job ID: ${result.jobId}`);
    console.log(`Status: ${result.status ?? "unknown"}`); if (result.note) console.log(`Note: ${result.note}`);
    if (result.error) { console.log(`Error fetching logs: ${result.error}`); continue; }
    if (result.logSnippet) console.log(`Failure snippet:\n${String(result.logSnippet).split("\n").map((line) => `  ${line}`).join("\n")}`); else console.log("No snippet available.");
  }
  console.log("-".repeat(60));
}

async function main() {
  const options = parseArgs(process.argv.slice(2)); const cwd = resolveRoot(options.repo);
  const auth = gh(["auth", "status"], cwd); if (auth.status !== 0) throw new Error(message(auth, "gh not authenticated."));
  const pr = resolvePr(options.pr, cwd); const checks = fetchChecks(pr, cwd);
  const failing = checks.filter((check) => failures.has(normalize(check.conclusion)) || failures.has(normalize(check.state ?? check.status)) || normalize(check.bucket) === "fail");
  if (!failing.length) { console.log(`PR #${pr}: no failing checks detected.`); return; }
  const results = failing.map((check) => analyze(check, cwd, options.maxLines, options.context));
  if (options.json) console.log(JSON.stringify({ pr, results }, null, 2)); else render(pr, results);
  process.exitCode = 1;
}

main().catch((error) => { console.error(`Error: ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
