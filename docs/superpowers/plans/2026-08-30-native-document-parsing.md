# 原生文档解析与内容抽取能力 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为SztuCode添加原生文档解析能力，支持PDF、DOCX、XLSX、PPTX等常见格式的文本/表格/图片内容直接抽取，无需依赖外部Python脚本和Skills，让Agent能够像读取代码文件一样直接读取办公文档内容。

**Architecture:** 
- 在`packages/runtime-ts/src/tools.ts`中新增统一的`parse_document`内置工具
- 采用插件式解析器架构：核心定义Document内容模型，各格式解析器作为可选模块
- 第一阶段集成纯JS/TS解析库（pdf-parse、mammoth、xlsx等），零原生依赖
- 第二阶段添加OCR能力（基于tesseract.js或云端API）支持扫描版PDF
- 与现有`read_file`工具集成：对文档类型自动路由到parse_document
- 保持与现有offload/分页机制兼容，大文档自动分页输出

**Tech Stack:** TypeScript, pdf-parse, mammoth (docx), xlsx (SheetJS), tesseract.js (optional OCR), unified, remark (markdown)

---

## 问题背景

当前状态：
- 文档处理完全依赖Skills（pdf/documents/spreadsheets/presentations）
- Agent需要调用Python脚本才能读取文档内容，增加了启动开销和依赖复杂度
- 非代码文档（PDF/Word/Excel）无法通过`read_file`直接读取内容，只能看到二进制标记
- Skills的渲染-检查QA流程面向文档生成场景，不适合简单的内容抽取问答

对标差距：Claude Code和Codex CLI都支持直接读取PDF内容进行问答，无需额外技能调用。

---

### Task 1: 定义统一文档内容模型与解析器接口

**Files:**
- Create: `packages/runtime-ts/src/document-parser/types.ts`
- Create: `packages/runtime-ts/src/document-parser/index.ts`

- [ ] **Step 1: 定义Document内容块类型**

```typescript
// packages/runtime-ts/src/document-parser/types.ts
export type DocumentBlockType =
  | "text"
  | "heading"
  | "paragraph"
  | "table"
  | "list"
  | "image"
  | "page-break"
  | "metadata";

export interface DocumentBlock {
  type: DocumentBlockType;
  content?: string;
  level?: number; // for heading
  rows?: string[][]; // for table
  items?: Array<{ text: string; checked?: boolean }>; // for list
  image?: { mime_type: string; base64: string; alt?: string };
  page?: number;
  bbox?: [number, number, number, number]; // x0,y0,x1,y1
  metadata?: Record<string, string | number | boolean>;
}

export interface ParsedDocument {
  format: "pdf" | "docx" | "xlsx" | "pptx" | "markdown" | "html" | "unknown";
  title?: string;
  author?: string;
  created?: string;
  modified?: string;
  page_count?: number;
  blocks: DocumentBlock[];
  raw_text_length: number;
  truncated: boolean;
}

export interface DocumentParser {
  readonly supportedFormats: string[];
  parse(buffer: Buffer, options?: ParseOptions): Promise<ParsedDocument>;
}

export interface ParseOptions {
  maxPages?: number;
  extractImages?: boolean;
  ocrEnabled?: boolean;
  ocrLanguages?: string[];
}
```

- [ ] **Step 2: 实现解析器注册中心**

```typescript
// packages/runtime-ts/src/document-parser/index.ts
import type { DocumentParser, ParsedDocument, ParseOptions } from "./types.js";

class DocumentParserRegistry {
  private parsers = new Map<string, DocumentParser>();

  register(parser: DocumentParser): void {
    for (const fmt of parser.supportedFormats) {
      this.parsers.set(fmt.toLowerCase(), parser);
    }
  }

  getParser(format: string): DocumentParser | null {
    return this.parsers.get(format.toLowerCase()) ?? null;
  }

  async parse(buffer: Buffer, format: string, options?: ParseOptions): Promise<ParsedDocument> {
    const parser = this.getParser(format);
    if (!parser) {
      return this.createFallbackDocument(format, buffer);
    }
    return parser.parse(buffer, options);
  }

  private createFallbackDocument(format: string, buffer: Buffer): ParsedDocument {
    // 尝试纯文本解码作为降级方案
    const text = buffer.toString("utf8").replace(/\0/g, "");
    return {
      format: "unknown",
      blocks: [{ type: "text", content: text.slice(0, 10000) }],
      raw_text_length: text.length,
      truncated: text.length > 10000,
    };
  }
}

export const documentParsers = new DocumentParserRegistry();
export type { ParsedDocument, DocumentBlock, ParseOptions };
```

- [ ] **Step 3: 编写解析器注册测试**

创建测试验证：
- 未知格式走fallback
- 解析器注册后能正确路由
- ParsedDocument结构符合预期

Run:
```text
npm test -- --grep "document parser"
```

Expected: 基础测试通过，无需外部依赖。

---

### Task 2: 实现PDF解析器

**Files:**
- Create: `packages/runtime-ts/src/document-parser/pdf.ts`
- Modify: `packages/runtime-ts/src/document-parser/index.ts` (注册PDF解析器)
- Modify: `packages/runtime-ts/package.json` (添加pdf-parse依赖)

- [ ] **Step 1: 添加pdf-parse依赖**

```bash
cd packages/runtime-ts
npm install pdf-parse
npm install --save-dev @types/pdf-parse
```

- [ ] **Step 2: 实现PDF解析器**

基于pdf-parse实现，支持：
- 文本内容按页抽取
- 基础元数据（标题、作者、创建时间、页数）
- 可选的简单表格检测（基于文本位置启发式）
- 图片占位提示（第一阶段不抽取图片二进制）

```typescript
// pdf.ts
import pdf from "pdf-parse";
import type { DocumentParser, ParsedDocument, DocumentBlock, ParseOptions } from "./types.js";

export class PdfParser implements DocumentParser {
  readonly supportedFormats = ["pdf"];

  async parse(buffer: Buffer, options: ParseOptions = {}): Promise<ParsedDocument> {
    const data = await pdf(buffer, {
      max: options.maxPages ?? 0,
    });

    const blocks: DocumentBlock[] = [];

    // 元数据
    if (data.info) {
      blocks.push({
        type: "metadata",
        metadata: {
          Title: data.info.Title ?? "",
          Author: data.info.Author ?? "",
          Creator: data.info.Creator ?? "",
          Producer: data.info.Producer ?? "",
          CreationDate: data.info.CreationDate ?? "",
          ModDate: data.info.ModDate ?? "",
        },
      });
    }

    // 按页分割文本（pdf-parse返回的text带form feed字符分隔页面）
    const pages = data.text.split(/\f/);
    for (let i = 0; i < pages.length; i++) {
      const pageText = pages[i]!.trim();
      if (!pageText) continue;
      blocks.push({
        type: "text",
        content: pageText,
        page: i + 1,
      });
      if (i < pages.length - 1) {
        blocks.push({ type: "page-break", page: i + 1 });
      }
    }

    return {
      format: "pdf",
      title: data.info?.Title,
      author: data.info?.Author,
      page_count: data.numpages,
      blocks,
      raw_text_length: data.text.length,
      truncated: false,
    };
  }
}
```

- [ ] **Step 3: 注册PDF解析器并测试**

在index.ts中注册：
```typescript
import { PdfParser } from "./pdf.js";
documentParsers.register(new PdfParser());
```

创建简单PDF测试用例（使用一个小的测试PDF文件或内嵌PDF数据）验证解析结果。

---

### Task 3: 实现DOCX解析器

**Files:**
- Create: `packages/runtime-ts/src/document-parser/docx.ts`
- Modify: `packages/runtime-ts/src/document-parser/index.ts`
- Modify: `packages/runtime-ts/package.json` (添加mammoth依赖)

- [ ] **Step 1: 添加mammoth依赖**

```bash
npm install mammoth
npm install --save-dev @types/mammoth
```

- [ ] **Step 2: 实现DOCX解析器**

使用mammoth转换为Markdown或HTML后解析为文档块：
- 支持标题层级（h1-h6）
- 支持段落、列表（有序/无序）
- 支持表格转换
- 支持图片提取（可选，base64内嵌）
- 保留基础格式（粗体/斜体）

- [ ] **Step 3: 测试DOCX解析**

创建测试DOCX文件验证：标题、段落、列表、表格都能正确识别。

---

### Task 4: 实现XLSX/电子表格解析器

**Files:**
- Create: `packages/runtime-ts/src/document-parser/xlsx.ts`
- Modify: `packages/runtime-ts/src/document-parser/index.ts`
- Modify: `packages/runtime-ts/package.json` (添加xlsx依赖)

- [ ] **Step 1: 添加SheetJS依赖**

```bash
npm install xlsx
```

- [ ] **Step 2: 实现XLSX解析器**

- 遍历所有sheet
- 每个sheet作为一个表格块输出
- 保留sheet名称作为元数据
- 支持大表格截断提示
- 提供CSV格式降级选项

- [ ] **Step 3: 测试XLSX解析**

验证多sheet、公式单元格（取缓存值）、合并单元格处理。

---

### Task 5: 将文档解析集成到read_file工具

**Files:**
- Modify: `packages/runtime-ts/src/tools.ts`
- Modify: `packages/runtime-ts/src/server-service.ts`

- [ ] **Step 1: 在tools.ts中添加parse_document工具**

```typescript
registry.register({
  name: "parse_document",
  description: "Parse and extract text content from PDF, DOCX, XLSX, PPTX and other document formats. Returns structured content with pages, tables, and metadata.",
  permission: "read_only",
  schema: {
    type: "object",
    properties: {
      path: { type: "string", description: "Path to the document file, relative to workspace root" },
      max_pages: { type: "integer", minimum: 1, maximum: 100, default: 20 },
      extract_tables: { type: "boolean", default: true },
      format: { type: "string", enum: ["pdf", "docx", "xlsx", "pptx", "auto"], default: "auto" },
    },
    required: ["path"],
  },
  async invoke(params, context) {
    // 实现：读取文件 -> 检测格式 -> 调用解析器 -> 格式化输出
  },
});
```

- [ ] **Step 2: 修改read_file自动检测文档类型**

当读取的文件扩展名是.pdf/.docx/.xlsx/.pptx时：
1. 提示用户"这是一个二进制文档，是否使用parse_document解析内容？"
2. 或者根据Agent自动判断直接解析（添加auto_parse选项）
3. 在输出中保留文档类型提示

- [ ] **Step 3: 与server-service.ts的file.read对接**

更新`workspace.file` RPC返回：
- 文档类型返回`parsed_content`字段（结构化文本）
- 同时保留`media_base64`用于图片类型
- 添加`document_format`字段标识格式

---

### Task 6: 文档输出格式化与分页

**Files:**
- Modify: `packages/runtime-ts/src/document-parser/index.ts`
- Modify: `packages/runtime-ts/src/offload.ts`

- [ ] **Step 1: 实现ParsedDocument到可读文本的格式化**

```typescript
function formatDocumentMarkdown(doc: ParsedDocument, maxChars = 16000): string {
  let output = "";
  // 添加元数据头部
  output += `# Document: ${doc.title ?? "Untitled"}\n`;
  output += `Format: ${doc.format} | Pages: ${doc.page_count ?? "?"}\n\n`;

  for (const block of doc.blocks) {
    switch (block.type) {
      case "heading":
        output += `${"#".repeat(block.level ?? 1)} ${block.content}\n\n`;
        break;
      case "paragraph":
      case "text":
        output += `${block.content}\n\n`;
        break;
      case "table":
        if (block.rows) {
          // 简单markdown表格
          const [header, ...rows] = block.rows;
          output += `| ${header?.join(" | ") ?? ""} |\n`;
          output += `| ${header?.map(() => "---").join(" | ")} |\n`;
          for (const row of rows) {
            output += `| ${row.join(" | ")} |\n`;
          }
          output += "\n";
        }
        break;
      case "page-break":
        output += `\n---\n*Page ${block.page}*\n\n`;
        break;
    }
    if (output.length > maxChars) {
      output += `\n\n[...Document truncated at ${maxChars} characters. Use parse_document with offset/limit or page ranges to read more...]`;
      break;
    }
  }
  return output;
}
```

- [ ] **Step 2: 大文档自动offload**

当格式化输出超过offload阈值时，自动卸载到refs，与grep/bash输出一致。

---

### Task 7: 测试与验证

**Files:**
- Create: `packages/runtime-ts/tests/document-parser.test.ts`
- Create: `packages/runtime-ts/tests/fixtures/` (test documents)

- [ ] **Step 1: 创建测试夹具**

添加几个小的测试文档：
- `sample.pdf` - 1-2页带简单文本和表格
- `sample.docx` - 带标题、列表、表格的Word文档
- `sample.xlsx` - 多sheet的Excel文件

- [ ] **Step 2: 编写解析器测试**

测试覆盖：
- PDF文本提取正确性
- DOCX标题/列表/表格识别
- XLSX多sheet读取
- 未知格式fallback
- 截断行为正确
- 权限检查（read_only正确执行）

- [ ] **Step 3: 集成测试与类型检查**

Run:
```text
cd packages/runtime-ts
npm test
npx tsc --noEmit
```

Expected: 所有现有测试继续通过，新增文档解析测试全部通过，TypeScript无错误。

---

### Task 8: 可选增强（OCR与PPTX支持）

**Files:**
- Create: `packages/runtime-ts/src/document-parser/ocr.ts`
- Create: `packages/runtime-ts/src/document-parser/pptx.ts`

- [ ] **Step 1: OCR支持（可选）**

集成tesseract.js：
- 纯JS OCR引擎，无需原生依赖
- 默认禁用，通过`ocr_enabled: true`选项开启
- 支持中英文语言包
- 扫描版PDF自动检测（基于文本层为空判断）

- [ ] **Step 2: PPTX演示文稿解析**

添加PPTX解析器：
- 提取每页幻灯片文本
- 保留演讲者备注
- 识别幻灯片标题和内容层级

---

## 验收标准

- [ ] `parse_document`工具可直接读取PDF/DOCX/XLSX并返回可读文本
- [ ] 文档表格转换为Markdown表格格式
- [ ] 大文档自动分页和offload，不破坏上下文窗口
- [ ] `read_file`对文档类型给出友好提示
- [ ] 所有新增代码有测试覆盖
- [ ] TypeScript编译零错误
- [ ] 不引入大型原生依赖，保持跨平台兼容性

## 非目标（本阶段不做）

- 文档生成/编辑（保留现有Skills工作流）
- 高级OCR（手写识别、表格结构重建）
- 文档渲染为图片预览
- PDF批注/签名功能
