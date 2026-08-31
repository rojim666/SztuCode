import { makeChunk, requireSource, validateSplitterOptions, type Chunk, type Chunker, type SplitterOptions } from "./splitter.js";

const HEADING = /^#{1,6}\s+\S/;

export class MarkdownSplitter implements Chunker {
  private readonly options: Required<SplitterOptions>;

  constructor(options: SplitterOptions = {}) {
    this.options = validateSplitterOptions(options);
  }

  split(content: string, metadata: Record<string, string>): Chunk[] {
    requireSource(metadata);
    const lines = content.replace(/\r\n?/g, "\n").split("\n");
    if (!content.trim()) return [];
    const starts = [0];
    let inFence = false;
    lines.forEach((line, index) => {
      if (/^\s*```/.test(line)) inFence = !inFence;
      else if (!inFence && HEADING.test(line) && index > 0) starts.push(index);
    });

    const chunks: Chunk[] = [];
    for (let section = 0; section < starts.length; section += 1) {
      const start = starts[section]!;
      const end = starts[section + 1] ?? lines.length;
      const sectionText = lines.slice(start, end).join("\n").trim();
      if (sectionText.length <= this.options.maxChars) {
        const chunk = makeChunk(lines, start, end, metadata, "markdown", "markdown", chunks.length);
        if (chunk) chunks.push(chunk);
        continue;
      }
      const sectionChunks = this.splitLongSection(lines, start, end, metadata, chunks.length);
      chunks.push(...sectionChunks);
    }
    return chunks;
  }

  private splitLongSection(lines: string[], start: number, end: number, metadata: Record<string, string>, index: number): Chunk[] {
    const chunks: Chunk[] = [];
    let cursor = start;
    while (cursor < end) {
      let next = cursor;
      let length = 0;
      while (next < end && (next === cursor || length + lines[next]!.length + 1 <= this.options.maxChars)) {
        length += lines[next]!.length + 1;
        next += 1;
      }
      if (next < end) {
        let paragraph = next;
        while (paragraph > cursor + 1 && lines[paragraph - 1]!.trim()) paragraph -= 1;
        if (paragraph > cursor + 1) next = paragraph;
      }
      const chunk = makeChunk(lines, cursor, next, metadata, "markdown", "markdown", index + chunks.length);
      if (chunk) chunks.push(chunk);
      if (next >= end) break;
      const overlap = Math.min(this.options.overlapLines, Math.floor(Math.max(0, next - cursor) / 2));
      cursor = Math.max(cursor + 1, next - overlap);
    }
    return chunks;
  }
}

export class TextSplitter implements Chunker {
  private readonly options: Required<SplitterOptions>;

  constructor(options: SplitterOptions = {}) {
    this.options = validateSplitterOptions(options);
  }

  split(content: string, metadata: Record<string, string>): Chunk[] {
    requireSource(metadata);
    const paragraphs = content.replace(/\r\n?/g, "\n").split(/\n\s*\n/).map((item) => item.trim()).filter(Boolean);
    if (paragraphs.length === 0) return [];
    const chunks: Chunk[] = [];
    let current = "";
    for (const paragraph of paragraphs) {
      if (current && current.length + paragraph.length + 2 > this.options.maxChars) {
        chunks.push({ text: current, metadata: { ...metadata, source: requireSource(metadata), type: "text", start_line: undefined, end_line: undefined, chunk_index: chunks.length } });
        current = "";
      }
      current = current ? `${current}\n\n${paragraph}` : paragraph;
    }
    if (current) chunks.push({ text: current, metadata: { ...metadata, source: requireSource(metadata), type: "text", chunk_index: chunks.length } });
    return chunks;
  }
}
