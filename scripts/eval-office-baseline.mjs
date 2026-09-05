import { readFile, readdir, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const sampleDir = path.join(root, "docs/office-agent/evaluation/samples");
const outDir = path.join(root, "tmp/eval/office-baseline");
const checks = [];
const check = (id, status, detail) => checks.push({ id, status, detail });

const names = (await readdir(sampleDir)).sort();
for (const required of ["source-a.md", "source-b.md", "source-c.md", "sales.csv"]) check(`fixture:${required}`, names.includes(required) ? "passed" : "failed", names.includes(required) ? "present" : "missing");
const read = async (name) => readFile(path.join(sampleDir, name), "utf8");
const [a,b,c,csv] = await Promise.all([read("source-a.md"), read("source-b.md"), read("source-c.md"), read("sales.csv")]);
check("research:chinese", /华东|退货率/.test(a+b) ? "passed" : "failed", "Chinese source text present");
check("research:source-coverage", /## 结论/.test(a) && /## 风险/.test(b) && /## 边界/.test(c) ? "passed" : "failed", "three sections available for citation");
check("table:row-count", csv.trim().split(/\r?\n/).length - 1 === 3 ? "passed" : "failed", "3 data rows");
const rows = csv.trim().split(/\r?\n/).slice(1).map(line => line.split(","));
const total = rows.reduce((sum, row) => sum + Number(row[1]), 0);
check("table:sum", total === 450 ? "passed" : "failed", `sales total=${total}, expected=450`);
check("table:missing-value", rows.filter(row => row[2] === "").length === 1 ? "passed" : "failed", "one missing order count");
check("artifacts:docx", "unimplemented", "No verified DOCX generation adapter in current runtime");
check("artifacts:pptx", "unimplemented", "No verified PPTX generation adapter in current runtime");

await mkdir(outDir, { recursive: true });
const report = { schema_version: "office-eval-report-1", generated_at: new Date().toISOString(), runner: "offline-fixture", external_model: false, checks, summary: { passed: checks.filter(x=>x.status === "passed").length, failed: checks.filter(x=>x.status === "failed").length, unimplemented: checks.filter(x=>x.status === "unimplemented").length } };
await writeFile(path.join(outDir, "report.json"), JSON.stringify(report, null, 2) + "\n");
const lines = ["# Office baseline report", "", `Runner: ${report.runner}; external model: ${report.external_model}`, "", "| Check | Status | Detail |", "|---|---|---|", ...checks.map(x => `| ${x.id} | ${x.status} | ${x.detail} |`), "", `Passed ${report.summary.passed}; failed ${report.summary.failed}; unimplemented ${report.summary.unimplemented}.`];
await writeFile(path.join(outDir, "summary.md"), lines.join("\n") + "\n");
console.log(lines.slice(-1)[0]);
if (report.summary.failed) process.exitCode = 1;

