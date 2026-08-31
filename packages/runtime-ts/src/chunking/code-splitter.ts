import { makeChunk, requireSource, splitLineWindow, validateSplitterOptions, type Chunk, type Chunker, type SplitterOptions } from "./splitter.js";

const DECLARATION = /^\s*(?:(?:export|default|public|private|protected|async|static|abstract|final)\s+)*(?:function|class|interface|type|enum|namespace|struct|trait|impl|fn|def)\b/;
const GO_FUNCTION = /^\s*func\s+(?:\([^)]*\)\s*)?[A-Za-z_][\w]*\s*\(/;

export interface CodeSymbol {
  name: string;
  kind: string;
}

const SYMBOL_PATTERNS: Array<{ kind: string; pattern: RegExp }> = [
  { kind: "function", pattern: /^\s*(?:(?:export|default|public|private|protected|async|static)\s+)*(?:function)\s+([A-Za-z_$][\w$]*)/ },
  { kind: "class", pattern: /^\s*(?:(?:export|default|public|private|protected|abstract)\s+)*class\s+([A-Za-z_$][\w$]*)/ },
  { kind: "interface", pattern: /^\s*(?:(?:export|declare)\s+)*interface\s+([A-Za-z_$][\w$]*)/ },
  { kind: "type", pattern: /^\s*(?:(?:export|declare)\s+)*type\s+([A-Za-z_$][\w$]*)/ },
  { kind: "enum", pattern: /^\s*(?:(?:export|declare)\s+)*enum\s+([A-Za-z_$][\w$]*)/ },
  { kind: "namespace", pattern: /^\s*(?:(?:export|declare)\s+)*namespace\s+([A-Za-z_$][\w$]*)/ },
  { kind: "python_function", pattern: /^\s*def\s+([A-Za-z_]\w*)\s*\(/ },
  { kind: "go_function", pattern: /^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(/ },
  { kind: "rust_function", pattern: /^\s*(?:(?:pub|async|unsafe|const)\s+)*fn\s+([A-Za-z_]\w*)\s*[<(]/ },
  { kind: "struct", pattern: /^\s*(?:(?:pub|export)\s+)*(?:struct|trait|impl)\s+([A-Za-z_]\w*)/ },
];

/** 从代码块开头的声明中提取可用于检索的符号名称。 */
export function extractSymbols(content: string): CodeSymbol[] {
  const symbols: CodeSymbol[] = [];
  const seen = new Set<string>();
  for (const line of content.replace(/\r\n?/g, "\n").split("\n")) {
    for (const { kind, pattern } of SYMBOL_PATTERNS) {
      const match = pattern.exec(line);
      const name = match?.[1];
      if (!name) continue;
      const key = `${kind}:${name}`;
      if (!seen.has(key)) {
        seen.add(key);
        symbols.push({ name, kind });
      }
      break;
    }
  }
  return symbols;
}

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
    return splitLineWindow(content, metadata, "code", this.options, this.language, isBoundary).map((chunk) => {
      const symbols = extractSymbols(chunk.text);
      if (symbols.length > 0) {
        chunk.metadata.symbol = symbols.map((symbol) => symbol.name).join(", ");
        chunk.metadata.symbol_kind = symbols[0]!.kind;
      }
      return chunk;
    });
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
