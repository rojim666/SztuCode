export type ChunkType = "code" | "markdown" | "text" | "document";

export interface ChunkMetadata {
  source: string;
  start_line?: number;
  end_line?: number;
  type: ChunkType;
  language?: string;
  [key: string]: string | number | boolean | undefined;
}

export interface Chunk {
  text: string;
  metadata: ChunkMetadata;
}

export interface Chunker {
  split(content: string, metadata: Record<string, string>): Chunk[];
}

export interface SplitterOptions {
  maxChars?: number;
  overlapLines?: number;
}

export function validateSplitterOptions(options: SplitterOptions): Required<SplitterOptions> {
  const maxChars = options.maxChars ?? 3_500;
  const overlapLines = options.overlapLines ?? 20;
  if (!Number.isInteger(maxChars) || maxChars < 1) throw new Error("分块 maxChars 必须是正整数");
  if (!Number.isInteger(overlapLines) || overlapLines < 0) throw new Error("分块 overlapLines 必须是非负整数");
  return { maxChars, overlapLines };
}

export function requireSource(metadata: Record<string, string>): string {
  const source = metadata.source?.trim();
  if (!source) throw new Error("分块 metadata.source 不能为空");
  return source;
}

export function makeChunk(
  lines: readonly string[],
  start: number,
  end: number,
  metadata: Record<string, string>,
  type: ChunkType,
  language?: string,
  chunkIndex = 0,
): Chunk | null {
  const text = lines.slice(start, end).join("\n").trim();
  if (!text) return null;
  return {
    text,
    metadata: {
      ...metadata,
      source: requireSource(metadata),
      type,
      ...(language ? { language } : {}),
      start_line: start + 1,
      end_line: end,
      chunk_index: chunkIndex,
    },
  };
}

export function splitLineWindow(
  content: string,
  metadata: Record<string, string>,
  type: ChunkType,
  options: SplitterOptions,
  language?: string,
  boundary?: (line: string, index: number) => boolean,
): Chunk[] {
  requireSource(metadata);
  const { maxChars, overlapLines } = validateSplitterOptions(options);
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  if (lines.length === 1 && !lines[0]!.trim()) return [];
  const chunks: Chunk[] = [];
  let start = 0;
  while (start < lines.length) {
    let end = start;
    let length = 0;
    while (end < lines.length && (end === start || length + lines[end]!.length + 1 <= maxChars)) {
      length += lines[end]!.length + 1;
      end += 1;
    }
    if (end <= start) end = start + 1;
    if (end < lines.length && boundary) {
      let candidate = end;
      const minimumBoundaryDistance = Math.min(20, Math.max(2, Math.floor((end - start) / 3)));
      while (candidate > start + minimumBoundaryDistance && !boundary(lines[candidate - 1]!, candidate - 1)) candidate -= 1;
      if (candidate > start + minimumBoundaryDistance) end = candidate;
    }
    const chunk = makeChunk(lines, start, end, metadata, type, language, chunks.length);
    if (chunk) chunks.push(chunk);
    if (end >= lines.length) break;
    const overlap = Math.min(overlapLines, Math.floor(Math.max(0, end - start) / 2));
    start = Math.max(start + 1, end - overlap);
  }
  return chunks;
}
