import { readFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { zipSync, strToU8 } from "fflate";
import { ArtifactStore } from "../packages/runtime-ts/src/artifact-store.ts";

const root = path.resolve(process.argv[2] ?? "docs/office-agent/evaluation/samples");
const out = path.resolve(process.argv[3] ?? "tmp/eval/office-baseline");
const csv = await readFile(path.join(root, "sales.csv"), "utf8");
const rows = csv.trim().split(/\r?\n/).slice(1).map(line => line.split(","));
const total = rows.reduce((n, r) => n + Number(r[1]), 0);
if (total !== 450 || rows.length !== 3) throw new Error(`deterministic reconciliation failed: rows=${rows.length} total=${total}`);
const sources = await Promise.all(["source-a.md", "source-b.md", "source-c.md"].map(n => readFile(path.join(root, n), "utf8")));
const body = `<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>销售分析报告</w:t></w:r></w:p><w:p><w:r><w:t>销售额合计：450 万元；数据行数：3。</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>地区</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>销售额</w:t></w:r></w:p></w:tc></w:tr>${rows.map(r=>`<w:tr><w:tc><w:p><w:r><w:t>${r[0]}</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>${r[1]}</w:t></w:r></w:p></w:tc></w:tr>`).join("")}</w:tbl><w:p><w:r><w:t>来源：source-a.md §结论；source-b.md §风险；source-c.md §边界。</w:t></w:r></w:p></w:body></w:document>`;
const files = { "[Content_Types].xml": strToU8(`<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`), "_rels/.rels": strToU8(`<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`), "word/document.xml": strToU8(body) };
await mkdir(out, { recursive: true }); const target = path.join(out, "sales-report.docx"); await writeFile(target, zipSync(files));
const store = new ArtifactStore(path.join(out, "artifacts")); const artifact = await store.register("office-baseline", out, "sales-report.docx", { type: "docx", summary: "确定性销售汇总报告", input_sources: ["source-a.md", "source-b.md", "source-c.md", "sales.csv"].map(p => ({ path: p })) , preview: { mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", text: `销售额合计 450；来源 ${sources.length} 份` } });
const verified = artifact.hash.length === 64 && artifact.version >= 1; await store.updateVerification("office-baseline", artifact.artifact_id, verified ? "passed" : "failed", verified ? "结构写入与哈希检查通过；渲染需独立验证" : "哈希检查失败");
console.log(JSON.stringify({ artifact_id: artifact.artifact_id, path: target, verification_status: verified ? "passed" : "failed", delivery_status: "not_delivered" }, null, 2));
