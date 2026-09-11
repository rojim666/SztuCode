export type DiffPreviewLine = {
  kind: "context" | "add" | "del";
  text: string;
  lineNo: number | null;
};

/**
 * 解析 unified diff，只保留代码行（跳过 diff/index/---/+++/@@ 等头），
 * 并按 @@ 头补齐行号：新增与上下文取新文件行号，删除取旧文件行号。
 */
export function parseDiffPreview(text: string): DiffPreviewLine[] {
  const parts = text.split("\n");
  if (parts.length && parts[parts.length - 1] === "") parts.pop();

  const lines: DiffPreviewLine[] = [];
  let oldNo = 0;
  let newNo = 0;

  for (const raw of parts) {
    if (raw.startsWith("@@")) {
      const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw);
      if (match) {
        oldNo = Number(match[1]);
        newNo = Number(match[2]);
      }
      continue;
    }
    if (
      raw.startsWith("+++") || raw.startsWith("---") ||
      raw.startsWith("diff ") || raw.startsWith("index ") ||
      raw.startsWith("new file") || raw.startsWith("deleted file") ||
      raw.startsWith("similarity index") || raw.startsWith("rename ")
    ) {
      continue;
    }
    if (raw.startsWith("+")) {
      lines.push({ kind: "add", text: raw.slice(1), lineNo: newNo });
      newNo += 1;
      continue;
    }
    if (raw.startsWith("-")) {
      lines.push({ kind: "del", text: raw.slice(1), lineNo: oldNo });
      oldNo += 1;
      continue;
    }
    lines.push({ kind: "context", text: raw.startsWith(" ") ? raw.slice(1) : raw, lineNo: newNo });
    oldNo += 1;
    newNo += 1;
  }

  return lines;
}
