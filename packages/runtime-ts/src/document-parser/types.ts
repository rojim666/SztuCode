// 统一文档内容模型：parse_document 的类型系统与解析器接口（issue #143）
export type DocumentBlockType =
  | "text"
  | "heading"
  | "table"
  | "list"
  | "page-break"
  | "metadata";

export interface DocumentBlock {
  type: DocumentBlockType;
  /** text/heading 的正文内容 */
  content?: string;
  /** heading 层级（h1-h6 → 1-6） */
  level?: number;
  /** table 的行（首行通常为表头） */
  rows?: string[][];
  /** list 的条目文本 */
  items?: string[];
  /** 所属页码（PDF） */
  page?: number;
  /** metadata 块的键值对（标题/作者等） */
  metadata?: Record<string, string>;
}

export interface ParsedDocument {
  format: "pdf" | "docx" | "xlsx" | "pptx" | "unknown";
  title?: string;
  author?: string;
  page_count?: number;
  /** xlsx 的 sheet 数量 */
  sheet_count?: number;
  blocks: DocumentBlock[];
  raw_text_length: number;
  truncated: boolean;
}

export interface ParseOptions {
  /** PDF 只解析前 N 页（0 或缺省 = 全部） */
  max_pages?: number;
  /** xlsx 每个 sheet 最多输出的行数（0 = 不限制） */
  max_rows?: number;
}

export interface DocumentParser {
  readonly formats: readonly string[];
  parse(buffer: Buffer, options?: ParseOptions): Promise<ParsedDocument>;
}
