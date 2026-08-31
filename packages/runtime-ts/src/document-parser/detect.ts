import type { ParsedDocument } from "./types.js";

// 轻量格式检测：只看扩展名 + 魔数，不引入任何解析器依赖，
// 供 read_file 提示与 parse_document 的 auto 格式判断共用
const EXTENSION_FORMATS = new Map<string, ParsedDocument["format"]>([
  [".pdf", "pdf"],
  [".docx", "docx"],
  [".doc", "docx"],
  [".xlsx", "xlsx"],
  [".xlsm", "xlsx"],
  [".xls", "xlsx"],
  [".pptx", "pptx"],
  [".ppt", "pptx"],
]);

export function detectDocumentFormat(fileName: string, buffer?: Buffer): ParsedDocument["format"] | null {
  const extension = fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
  const byExtension = EXTENSION_FORMATS.get(extension) ?? null;
  if (!byExtension) return null;
  if (buffer && buffer.length >= 4) {
    const magic = buffer.subarray(0, 4);
    if (byExtension === "pdf" && magic.toString("latin1") !== "%PDF") return null;
    if (byExtension !== "pdf" && magic.toString("latin1") !== "PK\u0003\u0004") return null;
  }
  return byExtension;
}
