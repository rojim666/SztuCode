import { PDFParse } from "pdf-parse";
import type { DocumentBlock, DocumentParser, ParseOptions, ParsedDocument } from "./types.js";

// pdf-parse v2：自带类型与 ESM 支持，getText 返回逐页文本，getInfo 返回 Info 字典
export class PdfParser implements DocumentParser {
  readonly formats = ["pdf"];

  async parse(buffer: Buffer, options: ParseOptions = {}): Promise<ParsedDocument> {
    const parser = new PDFParse({ data: new Uint8Array(buffer) });
    try {
      const maxPages = Number.isInteger(options.max_pages) && (options.max_pages ?? 0) > 0
        ? (options.max_pages as number)
        : 0;
      const text = await parser.getText(maxPages > 0 ? { first: maxPages } : undefined);

      const blocks: DocumentBlock[] = [];
      let title: string | undefined;
      let author: string | undefined;
      try {
        const info = await parser.getInfo();
        const dict = (info.info ?? {}) as Record<string, unknown>;
        title = typeof dict.Title === "string" && dict.Title.trim() ? dict.Title.trim() : undefined;
        author = typeof dict.Author === "string" && dict.Author.trim() ? dict.Author.trim() : undefined;
        const meta: Record<string, string> = {};
        for (const key of ["Title", "Author", "Subject", "Creator", "Producer"] as const) {
          const value = dict[key];
          if (typeof value === "string" && value.trim()) meta[key] = value.trim();
        }
        if (Object.keys(meta).length > 0) blocks.push({ type: "metadata", metadata: meta });
      } catch {
        // 部分 PDF 的 Info 字典损坏；元数据缺失不影响正文抽取
      }

      for (const page of text.pages) {
        const pageText = page.text.trim();
        if (pageText) blocks.push({ type: "text", content: pageText, page: page.num });
      }
      const parsedPages = text.pages.length;
      const truncated = text.total > parsedPages;
      if (truncated) {
        blocks.push({
          type: "metadata",
          metadata: { note: `only pages 1-${parsedPages} of ${text.total} were parsed (max_pages limit)` },
        });
      }

      return {
        format: "pdf",
        title,
        author,
        page_count: text.total,
        blocks,
        raw_text_length: text.text.length,
        truncated,
      };
    } finally {
      await parser.destroy();
    }
  }
}
