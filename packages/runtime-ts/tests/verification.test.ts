import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { buildCompletionContract, RepairCircuitBreaker, VerificationExecutor } from "../src/verification.js";

test("discovers user checks with stable priority ordering", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-verification-"));
  await writeFile(path.join(root, "package.json"), JSON.stringify({ scripts: { test: "node" } }));
  await mkdir(path.join(root, ".sztu"));
  await writeFile(path.join(root, ".sztu", "checks.toml"), '[[check]]\nid = "unit"\ncommand = ["node", "-e", "process.exit(0)"]\npriority = 10\n');
  const contract = await buildCompletionContract("run-1", root);
  assert.equal(contract?.conditions[0]?.id, "unit");
  assert.equal(contract?.conditions[0]?.source, "user");
});

test("executes argv checks and persists output evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-verification-"));
  const runRoot = path.join(root, ".sztu", "runs", "run-1");
  const contract = { run_id: "run-1", created_at: new Date().toISOString(), conditions: [{ id: "ok", description: "ok", source: "user" as const, check_command: [process.execPath, "-e", "console.log('verified')"], required: true, priority: 1 }] };
  const result = await new VerificationExecutor(root, runRoot).verify(contract);
  assert.equal(result.overall, "verified");
  assert.match(result.results[0]?.evidence?.output_path ?? "", /ok\.log$/);
});

test("circuit breaker stops identical verification failures", () => {
  const breaker = new RepairCircuitBreaker(3);
  const signature = [["unit", "failed", 1] as [string, "failed", number]];
  breaker.record(signature); breaker.record(signature);
  assert.match(breaker.stopReason() ?? "", /identical/);
});
