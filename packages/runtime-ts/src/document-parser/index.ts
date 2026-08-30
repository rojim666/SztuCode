import type { DocumentBlock, DocumentParser, ParseOptions, ParsedDocument } from "./types.js";
import { PdfParser } from "./pdf.js";
import { DocxParser } from "./docx.js";
import { XlsxParser } from "./xlsx.js";

export { detectDocumentFormat } from "./detect.js";

class DocumentParserRegistry {
  private readonly parsers = new Map<string, DocumentParser>();

  register(parser: DocumentParser): void {
    for (const format of parser.formats) {
      this.parsers.set(format.toLowerCase(), parser);
    }
  }

  hasParser(format: string): boolean {
    return this.parsers.has(format.toLowerCase());
  }

  getParser(format: string): DocumentParser | null {
    return this.parsers.get(format.toLowerCase()) ?? null;
  }

  async parse(buffer: Buffer, format: string, options?: ParseOptions): Promise<ParsedDocument> {
    const parser = this.getParser(format);
    if (!parser) return fallbackDocument(buffer);
    return parser.parse(buffer, options);
  }
}

// 未知格式：尽力按纯文本解码作为降级方案
function fallbackDocument(buffer: Buffer): ParsedDocument {
  const text = buffer.toString("utf8").replace(/\0/g, "");
  const limited = text.slice(0, 10_000);
  return {
    format: "unknown",
    blocks: [{ type: "text", content: limited }],
    raw_text_length: text.length,
    truncated: text.length > limited.length,
  };
}

// ParsedDocument → Agent 可读的 Markdown；超过 maxChars 截断并给出续读提示
export function formatDocumentMarkdown(doc: ParsedDocument, maxChars = 16_000): string {
  const header: string[] = [`# Document: ${doc.title ?? "(untitled)"}`];
  const facts: string[] = [`format: ${doc.format}`];
  if (doc.page_count !== undefined) facts.push(`pages: ${doc.page_count}`);
  if (doc.sheet_count !== undefined) facts.push(`sheets: ${doc.sheet_count}`);
  if (doc.author) facts.push(`author: ${doc.author}`);
  header.push(facts.join(" | "), "");
  if (doc.truncated) header.push("> [注意] 文档较大，本次输出有截断，可用 max_pages/max_rows 参数分批读取。", "");

  let output = header.join("\n");
  for (const block of doc.blocks) {
    const rendered = renderBlock(block);
    if (!rendered) continue;
    if (output.length + rendered.length > maxChars) {
      output += `\n\n[...已截断：输出超过 ${maxChars} 字符。可用 max_pages / max_rows 参数分批解析...]`;
      return output;
    }
    output += rendered;
  }
  return output.trimEnd();
}

function renderBlock(block: DocumentBlock): string {
  switch (block.type) {
    case "heading":
      return `\n\n${"#".repeat(Math.min(6, Math.max(1, block.level ?? 1)))} ${block.content ?? ""}\n\n`;
    case "text":
      return `${block.content ?? ""}\n\n`;
    case "list":
      return (block.items ?? []).map((item) => `- ${item}`).join("\n") + "\n\n";
    case "table":
      return renderTable(block.rows ?? []);
    case "page-break":
      return `\n\n---\n*Page ${block.page ?? ""}*\n\n`;
    case "metadata": {
      const entries = Object.entries(block.metadata ?? {});
      if (entries.length === 0) return "";
      return entries.map(([key, value]) => `- **${key}**: ${value}`).join("\n") + "\n\n";
    }
    default:
      return "";
  }
}

function renderTable(rows: string[][]): string {
  if (rows.length === 0) return "";
  const width = Math.max(...rows.map((row) => row.length));
  const cells = (row: string[]) => Array.from({ length: width }, (_, index) => (row[index] ?? "").replace(/\|/g, "\\|").replace(/\n/g, " "));
  const [head, ...body] = rows;
  const lines = [
    `| ${cells(head ?? []).join(" | ")} |`,
    `| ${Array.from({ length: width }, () => "---").join(" | ")} |`,
    ...body.map((row) => `| ${cells(row).join(" | ")} |`),
  ];
  return lines.join("\n") + "\n\n";
}

export const documentParsers = new DocumentParserRegistry();
documentParsers.register(new PdfParser());
documentParsers.register(new DocxParser());
documentParsers.register(new XlsxParser());

export type { DocumentBlock, DocumentBlockType, DocumentParser, ParseOptions, ParsedDocument } from "./types.js";
