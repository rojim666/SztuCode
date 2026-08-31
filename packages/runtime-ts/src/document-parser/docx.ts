import mammoth from "mammoth";
import type { DocumentBlock, DocumentParser, ParseOptions, ParsedDocument } from "./types.js";

const ENTITIES: Record<string, string> = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&apos;": "'" };
const decodeEntities = (text: string): string => text.replace(/&(amp|lt|gt|quot|#39|apos);/g, (match) => ENTITIES[match] ?? match);
const stripTags = (html: string): string => decodeEntities(html.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "")).trim();

// mammoth 输出干净的语义 HTML（h1-h6/p/ul/ol/table），这里按块级标签顺序切开，
// 不引入完整 HTML 解析器
const BLOCK_RE = /<(h[1-6]|p|table|ul|ol)\b[^>]*>([\s\S]*?)<\/\1>/g;

export class DocxParser implements DocumentParser {
  readonly formats = ["docx"];

  async parse(buffer: Buffer, _options: ParseOptions = {}): Promise<ParsedDocument> {
    const { value: html } = await mammoth.convertToHtml({ buffer });
    const blocks: DocumentBlock[] = [];
    let match: RegExpExecArray | null;
    BLOCK_RE.lastIndex = 0;
    while ((match = BLOCK_RE.exec(html)) !== null) {
      const tag = match[1]!;
      const inner = match[2]!;
      if (tag === "table") {
        const rows: string[][] = [];
        const rowRe = /<tr\b[^>]*>([\s\S]*?)<\/tr>/g;
        let row: RegExpExecArray | null;
        while ((row = rowRe.exec(inner)) !== null) {
          const cells: string[] = [];
          const cellRe = /<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g;
          let cell: RegExpExecArray | null;
          while ((cell = cellRe.exec(row[1]!)) !== null) {
            cells.push(stripTags(cell[1]!).replace(/\n+/g, " "));
          }
          if (cells.some((value) => value !== "")) rows.push(cells);
        }
        if (rows.length > 0) blocks.push({ type: "table", rows });
        continue;
      }
      if (tag === "ul" || tag === "ol") {
        const items: string[] = [];
        const liRe = /<li\b[^>]*>([\s\S]*?)<\/li>/g;
        let li: RegExpExecArray | null;
        while ((li = liRe.exec(inner)) !== null) {
          const text = stripTags(li[1]!).replace(/\s+/g, " ");
          if (text) items.push(text);
        }
        if (items.length > 0) blocks.push({ type: "list", items });
        continue;
      }
      const content = stripTags(inner);
      if (!content) continue;
      if (tag === "p") blocks.push({ type: "text", content });
      else blocks.push({ type: "heading", content, level: Number(tag[1]) });
    }

    const rawText = html
      .replace(/<(h[1-6]|p|li|tr|table)\b[^>]*>/gi, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/&amp;/g, "&");
    return { format: "docx", blocks, raw_text_length: rawText.length, truncated: false };
  }
}
