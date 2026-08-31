import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { zipSync, strToU8 } from "fflate";
import * as XLSX from "xlsx";
import { Workspace } from "../src/workspace.js";
import { createWorkspaceTools } from "../src/tools.js";
import { detectDocumentFormat, documentParsers, formatDocumentMarkdown } from "../src/document-parser/index.js";

// ---- 测试夹具：全部代码生成，不提交二进制 ----------------------------------

// 手工构造带正确 xref 偏移的最小 PDF（每页一行 Helvetica 文本）
function buildPdf(pageTexts: string[]): Buffer {
  const objects: string[] = [];
  objects.push("<< /Type /Catalog /Pages 2 0 R >>");
  const kids = pageTexts.map((_, index) => `${4 + index * 2} 0 R`).join(" ");
  objects.push(`<< /Type /Pages /Kids [${kids}] /Count ${pageTexts.length} >>`);
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  for (const [index, text] of pageTexts.entries()) {
    const contentNumber = 5 + index * 2;
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents ${contentNumber} 0 R >>`);
    const escaped = text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
    const stream = `BT /F1 12 Tf 72 720 Td (${escaped}) Tj ET`;
    objects.push(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`);
  }

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  for (const [index, body] of objects.entries()) {
    offsets.push(Buffer.byteLength(pdf, "latin1"));
    pdf += `${index + 1} 0 obj\n${body}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return Buffer.from(pdf, "latin1");
}

// fflate 拼装最小 DOCX（标题/段落/表格），mammoth 可直接读取
function buildDocx(): Buffer {
  const document = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Quarterly Report</w:t></w:r></w:p>
<w:p><w:r><w:t>Plain paragraph with &amp; entity.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Region</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Sales</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>Shenzhen</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>120</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>`;
  return Buffer.from(zipSync({
    "[Content_Types].xml": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`),
    "_rels/.rels": strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`),
    "word/document.xml": strToU8(document),
  }));
}

function buildXlsx(): Buffer {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([["City", "Pop"], ["Shenzhen", "17"]]), "Cities");
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([["Key", "Value"], ["a", "1"], ["b", "2"]]), "Data");
  return XLSX.write(workbook, { type: "buffer", bookType: "xlsx" }) as Buffer;
}

// ---- 解析器 ------------------------------------------------------------------

test("detectDocumentFormat combines extension and magic bytes", () => {
  assert.equal(detectDocumentFormat("a.pdf", buildPdf(["x"])), "pdf");
  assert.equal(detectDocumentFormat("a.docx", buildDocx()), "docx");
  assert.equal(detectDocumentFormat("a.xlsx", buildXlsx()), "xlsx");
  assert.equal(detectDocumentFormat("a.txt"), null);
  // 扩展名是 .pdf 但内容不是 PDF → 拒绝
  assert.equal(detectDocumentFormat("fake.pdf", Buffer.from("hello")), null);
});

test("pdf parser extracts per-page text and page count", async () => {
  const doc = await documentParsers.parse(buildPdf(["Hello SztuCode", "Second page body"]), "pdf");
  assert.equal(doc.format, "pdf");
  assert.equal(doc.page_count, 2);
  assert.equal(doc.truncated, false);
  const texts = doc.blocks.filter((block) => block.type === "text");
  assert.equal(texts.length, 2);
  assert.match(texts[0]!.content ?? "", /Hello SztuCode/);
  assert.equal(texts[0]!.page, 1);
  assert.match(texts[1]!.content ?? "", /Second page body/);
});

test("pdf parser respects max_pages and reports truncation", async () => {
  const doc = await documentParsers.parse(buildPdf(["Page one", "Page two", "Page three"]), "pdf", { max_pages: 2 });
  assert.equal(doc.page_count, 3);
  assert.equal(doc.truncated, true);
  const texts = doc.blocks.filter((block) => block.type === "text");
  assert.equal(texts.length, 2);
});

test("docx parser extracts heading, paragraph and table", async () => {
  const doc = await documentParsers.parse(buildDocx(), "docx");
  assert.equal(doc.format, "docx");
  const headings = doc.blocks.filter((block) => block.type === "heading");
  assert.deepEqual(headings.map((block) => block.content), ["Quarterly Report"]);
  assert.equal(headings[0]!.level, 1);
  const paragraphs = doc.blocks.filter((block) => block.type === "text");
  assert.match(paragraphs[0]!.content ?? "", /Plain paragraph with & entity\./);
  const table = doc.blocks.find((block) => block.type === "table");
  assert.deepEqual(table?.rows, [["Region", "Sales"], ["Shenzhen", "120"]]);
});

test("xlsx parser reads every sheet and honors max_rows", async () => {
  const doc = await documentParsers.parse(buildXlsx(), "xlsx");
  assert.equal(doc.format, "xlsx");
  assert.equal(doc.sheet_count, 2);
  const tables = doc.blocks.filter((block) => block.type === "table");
  assert.equal(tables.length, 2);
  assert.equal(tables[0]!.metadata?.sheet, "Cities");
  assert.deepEqual(tables[0]!.rows, [["City", "Pop"], ["Shenzhen", "17"]]);

  const limited = await documentParsers.parse(buildXlsx(), "xlsx", { max_rows: 1 });
  const limitedTables = limited.blocks.filter((block) => block.type === "table");
  assert.equal(limited.truncated, true);
  assert.match(limitedTables[1]!.rows!.at(-1)![0]!, /showing first 1 of 3 rows/);
});

test("unknown format falls back to plain text decoding", async () => {
  const doc = await documentParsers.parse(Buffer.from("hello \0 world"), "bin");
  assert.equal(doc.format, "unknown");
  assert.equal(doc.blocks[0]!.type, "text");
});

test("formatDocumentMarkdown renders tables as Markdown and truncates", () => {
  const markdown = formatDocumentMarkdown({
    format: "docx", title: "Report", blocks: [
      { type: "heading", content: "Summary", level: 2 },
      { type: "table", rows: [["A|B", "C"], ["x", "y"]] },
    ], raw_text_length: 10, truncated: false,
  });
  assert.match(markdown, /# Document: Report/);
  assert.match(markdown, /## Summary/);
  assert.match(markdown, /\| A\\|B \| C \|/);
  assert.match(markdown, /\| --- \| --- \|/);

  const truncated = formatDocumentMarkdown({
    format: "pdf", blocks: [{ type: "text", content: "x".repeat(100) }], raw_text_length: 100, truncated: false,
  }, 60);
  assert.match(truncated, /已截断/);
});

// ---- 工具集成 ----------------------------------------------------------------

test("parse_document tool parses a document inside the workspace", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-doc-parser-"));
  await writeFile(path.join(root, "sample.pdf"), buildPdf(["Integration body text"]));
  const tools = createWorkspaceTools();
  const result = await tools.get("parse_document")!.invoke({ path: "sample.pdf" }, { workspace: new Workspace(root) });
  assert.equal(result.ok, true);
  assert.match(result.output, /format: pdf/);
  assert.match(result.output, /Integration body text/);
});

test("parse_document rejects unsupported types and read_file hints at documents", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-doc-parser-"));
  await writeFile(path.join(root, "slides.pptx"), Buffer.from("PK\u0003\u0004fake"));
  await writeFile(path.join(root, "report.pdf"), buildPdf(["hint target"]));
  await writeFile(path.join(root, "notes.txt"), "plain text");
  const tools = createWorkspaceTools();
  const context = { workspace: new Workspace(root) };

  const unsupported = await tools.get("parse_document")!.invoke({ path: "slides.pptx" }, context);
  assert.equal(unsupported.ok, false);
  assert.match(unsupported.error ?? "", /not supported/);

  const hint = await tools.get("read_file")!.invoke({ path: "report.pdf" }, context);
  assert.equal(hint.ok, true);
  assert.match(hint.output, /parse_document/);

  const normal = await tools.get("read_file")!.invoke({ path: "notes.txt" }, context);
  assert.equal(normal.ok, true);
  assert.match(normal.output, /plain text/);
});
