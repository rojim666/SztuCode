export * from "./splitter.js";
export * from "./code-splitter.js";
export * from "./markdown-splitter.js";

import { CodeSplitter } from "./code-splitter.js";
import { MarkdownSplitter, TextSplitter } from "./markdown-splitter.js";
import type { Chunker, SplitterOptions } from "./splitter.js";

const CODE_EXTENSIONS = new Map([
  [".ts", "typescript"], [".tsx", "typescript"], [".js", "javascript"], [".jsx", "javascript"],
  [".py", "python"], [".go", "go"], [".rs", "rust"], [".java", "java"], [".c", "c"],
  [".cc", "cpp"], [".cpp", "cpp"], [".h", "c"], [".hpp", "cpp"],
]);

export function createChunker(fileName: string, options: SplitterOptions = {}): Chunker {
  const extension = fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
  if (CODE_EXTENSIONS.has(extension)) return new CodeSplitter(options, CODE_EXTENSIONS.get(extension));
  if (extension === ".md" || extension === ".markdown") return new MarkdownSplitter(options);
  return new TextSplitter(options);
}
