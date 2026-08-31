import { makeChunk, requireSource, splitLineWindow, validateSplitterOptions, type Chunk, type Chunker, type SplitterOptions } from "./splitter.js";

const DECLARATION = /^\s*(?:(?:export|default|public|private|protected|async|static|abstract|final)\s+)*(?:function|class|interface|type|enum|namespace|struct|trait|impl|fn|def)\b/;
const GO_FUNCTION = /^\s*func\s+(?:\([^)]*\)\s*)?[A-Za-z_][\w]*\s*\(/;

function isBoundary(line: string, index: number): boolean {
  return index > 0 && (DECLARATION.test(line) || GO_FUNCTION.test(line));
}

export class CodeSplitter implements Chunker {
  private readonly options: Required<SplitterOptions>;
  private readonly language?: string;

  constructor(options: SplitterOptions = {}, language?: string) {
    this.options = validateSplitterOptions(options);
    this.language = language;
  }

  split(content: string, metadata: Record<string, string>): Chunk[] {
    requireSource(metadata);
    if (!content.trim()) return [];
    return splitLineWindow(content, metadata, "code", this.options, this.language, isBoundary);
  }
}

/** 只在需要保留单个声明整体时使用的简单声明分块辅助函数。 */
export function splitDeclarations(content: string, metadata: Record<string, string>, language?: string): Chunk[] {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const starts = [0];
  lines.forEach((line, index) => { if (isBoundary(line, index)) starts.push(index); });
  const chunks: Chunk[] = [];
  for (let index = 0; index < starts.length; index += 1) {
    const chunk = makeChunk(lines, starts[index]!, starts[index + 1] ?? lines.length, metadata, "code", language, index);
    if (chunk) chunks.push(chunk);
  }
  return chunks;
}
