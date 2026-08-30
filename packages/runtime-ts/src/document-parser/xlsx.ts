import * as XLSX from "xlsx";
import type { DocumentBlock, DocumentParser, ParseOptions, ParsedDocument } from "./types.js";

const DEFAULT_MAX_ROWS = 500;

// SheetJS（xlsx）：遍历所有 sheet，每个 sheet 输出为一个表格块；
// 公式单元格取缓存值（raw:false），空行过滤，超出 max_rows 截断
export class XlsxParser implements DocumentParser {
  readonly formats = ["xlsx", "xls"];

  async parse(buffer: Buffer, options: ParseOptions = {}): Promise<ParsedDocument> {
    const workbook = XLSX.read(buffer, { type: "buffer" });
    const maxRows = Number.isInteger(options.max_rows) && (options.max_rows ?? 0) > 0
      ? (options.max_rows as number)
      : DEFAULT_MAX_ROWS;
    const blocks: DocumentBlock[] = [];
    let rawLength = 0;
    let truncated = false;

    for (const name of workbook.SheetNames) {
      const sheet = workbook.Sheets[name];
      if (!sheet) continue;
      const rows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, raw: false, defval: "" })
        .map((row) => (row as unknown[]).map((cell) => String(cell ?? "")))
        .filter((row) => row.some((cell) => cell.trim() !== ""));
      rawLength += rows.reduce((total, row) => total + row.join("\t").length, 0);

      if (rows.length === 0) continue;
      const limited = rows.slice(0, maxRows);
      if (rows.length > maxRows) {
        truncated = true;
        limited.push([`[sheet "${name}": showing first ${maxRows} of ${rows.length} rows]`]);
      }
      blocks.push({ type: "table", rows: limited, metadata: { sheet: name } });
    }

    return {
      format: "xlsx",
      sheet_count: workbook.SheetNames.length,
      blocks,
      raw_text_length: rawLength,
      truncated,
    };
  }
}
