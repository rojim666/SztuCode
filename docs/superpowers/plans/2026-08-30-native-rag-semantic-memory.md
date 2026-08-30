# 原生代码语义搜索与会话记忆增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为SztuCode添加轻量级原生**代码语义搜索**和**会话记忆语义检索**能力。新增`semantic_search`工具让Agent基于概念/语义搜索代码（"认证中间件在哪"、"错误处理逻辑"），不再仅依赖grep关键词匹配；同时升级记忆系统支持语义查询历史notes。

**与Issue #15的边界：**
- 本Issue：**代码库语义检索** + **会话记忆语义查询** - 解决"找代码"和"回忆之前聊过什么"的问题
- Issue #15：**项目/行业规范知识库RAG** - 解决"编码规范是什么"、"安全规则有哪些"的问题
- 两者**共享底层嵌入层和向量存储基础设施**，但索引内容和检索目标完全不同，不重叠

**Architecture:**
- 分层设计：嵌入层 → 向量存储层 → 检索层 → 记忆增强层
- 默认使用纯JS实现，零原生依赖：`@xenova/transformers`做本地嵌入，内存+JSONL做持久化向量存储
- 支持切换云端嵌入API（OpenAI/Cohere等）
- 向量索引按workspace隔离，存储在`.sztu/vector/`目录
- 新增`semantic_search`工具，与现有grep_search互补
- 扩展memory系统：会话notes自动向量化，支持语义查询历史对话
- 懒索引：首次使用时自动构建索引，文件变更增量更新

**Tech Stack:** TypeScript, @xenova/transformers (local embeddings), 现有tools/memory/context架构

---

## 问题背景

当前状态：
- 只有基于关键词的grep_search/glob_search，无法进行语义搜索（不知道确切函数名就搜不到）
- 记忆系统是纯Markdown文件+关键词子串匹配，无法查询"我们之前讨论过的那个架构问题"
- 大代码库中，Agent经常搜不到需要的内容（因为功能描述和代码命名不完全匹配）
- 跨会话记忆查找困难，只有笔记标题和关键词匹配

对标差距：
- Cursor有@Codebase索引，支持语义搜索代码
- Claude Code有项目记忆和语义检索能力

本计划采用渐进式RAG，先做轻量级本地代码语义搜索和记忆语义化，不做重型规范知识库（由#15负责）。

---

### Task 1: 定义嵌入层接口与本地嵌入实现

**Files:**
- Create: `packages/runtime-ts/src/embedding/types.ts`
- Create: `packages/runtime-ts/src/embedding/local-embedder.ts`
- Create: `packages/runtime-ts/src/embedding/openai-embedder.ts`
- Create: `packages/runtime-ts/src/embedding/index.ts`
- Modify: `packages/runtime-ts/package.json`

- [ ] **Step 1: 定义Embedder接口**

```typescript
// embedding/types.ts
export interface Embedder {
  readonly name: string;
  readonly dimensions: number;
  readonly maxTokens: number;

  /**
   * Generate embeddings for one or more text chunks.
   * Returns array of number arrays with same length as input.
   */
  embed(texts: string[]): Promise<number[][]>;

  /**
   * Embed a single text (convenience wrapper)
   */
  embedQuery(text: string): Promise<number[]>;
}

export interface EmbedderConfig {
  provider: "local" | "openai" | "cohere";
  model?: string;
  apiKey?: string;
  dimensions?: number;
  batchSize?: number;
}
```

- [ ] **Step 2: 添加@xenova/transformers依赖**

```bash
cd packages/runtime-ts
npm install @xenova/transformers
```

这是一个纯JS的transformers实现，可以在Node.js中运行，支持all-MiniLM-L6-v2等轻量级嵌入模型（首次运行自动下载模型，约23MB）。

- [ ] **Step 3: 实现本地Embedder**

```typescript
// embedding/local-embedder.ts
import type { Embedder } from "./types.js";

export class LocalEmbedder implements Embedder {
  readonly name = "local";
  readonly dimensions = 384; // all-MiniLM-L6-v2
  readonly maxTokens = 512;
  private pipeline: any = null;
  private modelLoading: Promise<any> | null = null;

  async embed(texts: string[]): Promise<number[][]> {
    const pipe = await this.getPipeline();
    const results = [];
    // Process in batches to avoid memory issues
    const batchSize = 8;
    for (let i = 0; i < texts.length; i += batchSize) {
      const batch = texts.slice(i, i + batchSize);
      const output = await pipe(batch, { pooling: "mean", normalize: true });
      // output.data is Float32Array
      for (let j = 0; j < batch.length; j++) {
        const start = j * this.dimensions;
        const end = start + this.dimensions;
        results.push(Array.from(output.data.slice(start, end)));
      }
    }
    return results;
  }

  async embedQuery(text: string): Promise<number[]> {
    const [result] = await this.embed([text]);
    return result;
  }

  private async getPipeline() {
    if (this.pipeline) return this.pipeline;
    if (this.modelLoading) return this.modelLoading;
    this.modelLoading = (async () => {
      const { pipeline } = await import("@xenova/transformers");
      this.pipeline = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2");
      return this.pipeline;
    })();
    return this.modelLoading;
  }
}
```

设计考虑：
- 懒加载模型：第一次调用embed时才下载/加载，不影响启动速度
- 模型缓存：@xenova/transformers自动缓存到`./models/`
- 归一化向量：余弦相似度计算更快

- [ ] **Step 4: 实现OpenAI API Embedder（可选）**

支持text-embedding-3-small/large：
- 从settings读取API key
- 批处理支持
- 自动重试

- [ ] **Step 5: Embedder工厂与配置**

在index.ts中：
- 根据settings创建对应Embedder
- 默认fallback到local
- 支持运行时切换embedder

- [ ] **Step 6: 编写嵌入测试**

测试：
- Local embedder可以生成正确维度的向量
- 相似文本向量余弦相似度高
- 不相关文本相似度低
- 批处理返回正确数量的结果

注意：测试中mock掉模型下载，使用固定向量避免测试依赖网络。

---

### Task 2: 实现轻量级向量存储

**Files:**
- Create: `packages/runtime-ts/src/vector-store/types.ts`
- Create: `packages/runtime-ts/src/vector-store/memory-store.ts`
- Create: `packages/runtime-ts/src/vector-store/jsonl-store.ts` (持久化)
- Create: `packages/runtime-ts/src/vector-store/index.ts`

- [ ] **Step 1: 定义向量存储接口**

```typescript
// vector-store/types.ts
export interface VectorRecord {
  id: string;
  vector: number[];
  text: string;
  metadata: Record<string, string | number | boolean>;
  // Required metadata fields:
  // - source: file path or "memory" or "doc:xxx"
  // - chunk_index: number
  // - workspace_id: string
  // - timestamp: number
}

export interface SearchResult {
  record: VectorRecord;
  score: number; // 0-1 cosine similarity
}

export interface VectorStore {
  readonly name: string;
  readonly dimensions: number;

  add(records: Omit<VectorRecord, "id">[]): Promise<string[]>;
  delete(filter: Partial<VectorRecord["metadata"]>): Promise<number>;
  search(query: number[], topK: number, filter?: Partial<VectorRecord["metadata"]>): Promise<SearchResult[]>;
  count(filter?: Partial<VectorRecord["metadata"]>): Promise<number>;
  clear(): Promise<void>;
}
```

- [ ] **Step 2: 实现内存向量存储（用于测试和小数据）**

```typescript
// vector-store/memory-store.ts
// 纯JS余弦相似度搜索
// 对于<10,000 chunks，线性扫描完全够用（毫秒级）
function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) throw new Error("Dimension mismatch");
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

export class MemoryVectorStore implements VectorStore {
  private records: VectorRecord[] = [];
  readonly name = "memory";

  constructor(readonly dimensions: number) {}

  async add(records: Omit<VectorRecord, "id">[]): Promise<string[]> {
    const ids = records.map(() => crypto.randomUUID());
    records.forEach((r, i) => {
      this.records.push({ ...r, id: ids[i]! });
    });
    return ids;
  }

  async search(query: number[], topK: number, filter?: Partial<VectorRecord["metadata"]>): Promise<SearchResult[]> {
    const candidates = filter
      ? this.records.filter(r => Object.entries(filter).every(([k, v]) => r.metadata[k] === v))
      : this.records;

    const results: SearchResult[] = candidates.map(record => ({
      record,
      score: cosineSimilarity(query, record.vector),
    }));

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, topK);
  }

  // ... delete, count, clear implementations
}
```

- [ ] **Step 3: 实现持久化JSONL向量存储**

```typescript
// vector-store/jsonl-store.ts
// 存储在 .sztu/vector/index.jsonl
// 每行一个VectorRecord
// 启动时加载到内存，修改时append写入，后台compact
export class JsonlVectorStore extends MemoryVectorStore {
  constructor(readonly dimensions: number, private readonly storePath: string) {
    super(dimensions);
  }

  async load(): Promise<void> { /* 读取JSONL到内存 */ }
  async save(): Promise<void> { /* 全量写入（小数据量） */ }

  // 增量append + 定期compact避免无限增长
  private async appendRecord(record: VectorRecord): Promise<void>;
}
```

设计决策：
- 第一版不引入FAISS/hnswlib等原生依赖向量库
- 1万chunks以下线性扫描完全够用（代码库/文档库通常<5万chunks）
- 后续性能瓶颈时再替换为近似最近邻索引
- JSONL持久化简单可靠，Git友好（可选加入.gitignore）

---

### Task 3: 文档分块(Chunking)管线

**Files:**
- Create: `packages/runtime-ts/src/chunking/splitter.ts`
- Create: `packages/runtime-ts/src/chunking/code-splitter.ts`
- Create: `packages/runtime-ts/src/chunking/markdown-splitter.ts`
- Create: `packages/runtime-ts/src/chunking/index.ts`

- [ ] **Step 1: 定义Chunker接口**

```typescript
// chunking/splitter.ts
export interface Chunk {
  text: string;
  metadata: {
    source: string;
    start_line?: number;
    end_line?: number;
    type: "code" | "markdown" | "text" | "document";
    language?: string;
    [key: string]: string | number | boolean | undefined;
  };
}

export interface Chunker {
  split(content: string, metadata: Record<string, string>): Chunk[];
}
```

- [ ] **Step 2: 实现代码分块器**

代码分块策略：
- 按AST语法结构分割（函数、类、接口）
- 如果没有AST解析器，按行+缩进启发式分割
- 重叠(overlap)：块之间重叠20-50行，避免断裂上下文
- 目标块大小：~500-1000 tokens（约2000-4000字符）
- 支持语言：TS/JS/Python/Go/Rust/Java等常见语言（基于简单启发式）

- [ ] **Step 3: 实现Markdown/文本分块器**

Markdown分块策略：
- 按标题层级分割（#、##、###）
- 段落边界保持完整
- 列表项不拆分
- 代码块作为整体保留
- 同样支持overlap

纯文本分块：
- 按段落（空行分割）
- 超过目标大小时按句子拆分

- [ ] **Step 4: 分块器测试**

测试：
- 代码文件正确按函数分块
- Markdown按标题分块
- 块大小在目标范围内
- overlap正确工作
- 短文档不被过度拆分

---

### Task 4: 实现semantic_search工具

**Files:**
- Modify: `packages/runtime-ts/src/tools.ts`
- Create: `packages/runtime-ts/src/indexing/workspace-indexer.ts`
- Modify: `packages/runtime-ts/src/workspace-manager.ts`

- [ ] **Step 1: 工作区索引管理器**

```typescript
// indexing/workspace-indexer.ts
export class WorkspaceIndexer {
  constructor(
    private readonly workspaceRoot: string,
    private readonly embedder: Embedder,
    private readonly vectorStore: VectorStore,
  ) {}

  /**
   * Index a single file
   */
  async indexFile(relativePath: string): Promise<number> {
    // 1. Read file
    // 2. Detect language/type
    // 3. Chunk with appropriate chunker
    // 4. Embed chunks
    // 5. Delete old chunks for this file (if reindexing)
    // 6. Add new chunks to vector store
    // 7. Save
  }

  /**
   * Index all files in workspace (respecting .gitignore)
   */
  async indexAll(options?: {
    extensions?: string[];
    maxFiles?: number;
    onProgress?: (indexed: number, total: number) => void;
  }): Promise<{ files_indexed: number; chunks_indexed: number }>;

  /**
   * Update index for changed files (incremental)
   */
  async updateIndex(changedFiles: string[]): Promise<void>;

  /**
   * Check if a file should be indexed
   */
  shouldIndex(relativePath: string): boolean {
    // Respect .gitignore
    // Skip node_modules, dist, build, binary files, large files (>1MB)
    // Only index code and text files
  }
}
```

默认索引的文件类型：
- 代码：.ts, .tsx, .js, .jsx, .py, .go, .rs, .java, .c, .cpp, .h, .cs, .rb, .php
- 文档：.md, .txt, .rst, .adoc
- 配置：.json, .yaml, .yml, .toml（小文件）

- [ ] **Step 2: 在tools.ts注册semantic_search工具**

```typescript
registry.register({
  name: "semantic_search",
  description: "Search workspace code and documents using semantic/meaning-based search (not just keywords). Use this when you need to find code or content related to a concept but don't know the exact keywords. Complements grep_search (which does exact regex matching).",
  permission: "read_only",
  schema: {
    type: "object",
    properties: {
      query: {
        type: "string",
        description: "Natural language query describing what you're looking for (can be a question, description, or concept)",
      },
      top_k: {
        type: "integer",
        minimum: 1,
        maximum: 20,
        default: 5,
        description: "Number of results to return",
      },
      path: {
        type: "string",
        description: "Optional subdirectory to search within (relative to workspace root)",
      },
      file_type: {
        type: "string",
        enum: ["code", "markdown", "document", "any"],
        default: "any",
      },
      min_score: {
        type: "number",
        minimum: 0,
        maximum: 1,
        default: 0.5,
        description: "Minimum similarity score threshold (0-1)",
      },
      auto_index: {
        type: "boolean",
        default: true,
        description: "Automatically index files if index is empty or stale",
      },
    },
    required: ["query"],
  },
  async invoke(params, context) {
    // 实现：
    // 1. 检查索引是否存在，不存在或stale则自动索引（on first use）
    // 2. embed查询文本
    // 3. 向量搜索
    // 4. 格式化结果：返回文件路径、行号范围、匹配代码块、相似度分数
    // 5. 结果格式类似grep，方便Agent阅读
  },
});
```

结果输出格式（示例）：
```
Semantic search results for: "how does authentication work"
Score | File:Line Range | Preview
------|-----------------|--------
0.82  | src/auth/middleware.ts:45-78
  | export function authMiddleware(...) {
  |   // Validates JWT tokens and attaches user to request
  |   ...
0.78  | src/lib/token.ts:12-34
  | function verifyToken(token: string): User | null {
  ...
```

- [ ] **Step 3: 首次使用自动索引（懒索引）**

关键体验设计：
- 不强制用户主动触发索引
- 第一次调用semantic_search时，如果索引不存在：
  - 显示提示"Building semantic index, this may take a moment for large workspaces..."
  - 后台索引文件
  - 索引进度通过事件推送给UI
  - 索引完成后执行搜索返回结果
- 文件监听（可选）：workspace打开后监听文件变化，增量更新索引

---

### Task 5: 记忆系统语义增强

**Files:**
- Modify: `packages/runtime-ts/src/memory.ts`
- Modify: `packages/runtime-ts/src/session-store.ts`
- Create: `packages/runtime-ts/src/memory/semantic-memory.ts`

- [ ] **Step 1: Session Notes向量化**

当前note_save/note_update只保存文本，需要：
- 保存note时同时生成embedding存入向量库
- note的metadata包含：session_id, run_id, timestamp
- 修改memory_read支持语义查询

- [ ] **Step 2: 升级memory_read工具**

扩展memory_read工具：
```typescript
// 新增参数
query_mode: "keyword" | "semantic" | "hybrid" (default: "hybrid")
```

混合搜索策略：
- 同时执行关键词搜索和语义搜索
- 结果融合排序（Reciprocal Rank Fusion）
- 关键词匹配优先保证精确查找，语义补全相关记忆

- [ ] **Step 3: 自动记忆巩固（Memory Consolidation）**

会话结束或上下文压缩时：
- 提取关键决策、事实、未解决问题
- 生成结构化笔记
- 自动去重相似笔记
- 重要信息提升到project或global memory
- （第一版可以手动触发，后续自动化）

新增工具：
- `memory_consolidate`: 分析当前会话，提取值得持久化的信息

---

### Task 6: 向量索引生命周期管理

**Files:**
- Create: `packages/runtime-ts/src/indexing/index-manager.ts`
- Modify: `packages/runtime-ts/src/workspace-manager.ts`
- Modify: `packages/runtime-ts/src/server-service.ts` (添加RPC接口)
- Modify: `desktop/src/` (UI状态显示)

- [ ] **Step 1: 索引管理器单例**

```typescript
class IndexManager {
  // per-workspace index storage: Map<workspace_id, WorkspaceIndexer>
  // Embedder初始化（懒加载）
  // 索引状态：not_started | indexing | ready | failed | stale
  // 索引进度事件
}
```

- [ ] **Step 2: 添加RPC管理接口**

新增server RPC方法：
- `index.status` - 查询当前workspace索引状态
- `index.build` - 手动触发全量索引
- `index.update` - 增量更新指定文件
- `index.clear` - 清除索引
- `index.stats` - 返回统计：chunks数、文件数、最后索引时间

- [ ] **Step 3: 设置项**

在Settings中添加：
- 启用/禁用语义搜索（默认启用）
- 嵌入模型选择（local vs OpenAI）
- 索引文件大小限制
- 忽略的目录/文件模式
- OpenAI API key（如果使用云端嵌入）

- [ ] **Step 4: 桌面端UI状态**

- 索引中时显示进度条
- 状态栏显示"语义索引就绪"或"需要重建索引"
- 设置页面提供索引管理按钮
- .gitignore默认添加`.sztu/vector/`

---

### Task 7: 检索增强集成到Agent主循环

**Files:**
- Modify: `packages/runtime-ts/src/agent-loop.ts`
- Modify: `packages/runtime-ts/src/prompt-harness.ts`

- [ ] **Step 1: 查询重写与自动检索（可选）**

高级特性（可选，第一版可以只做工具，不做自动检索）：
- Agent判断用户问题是否需要代码库/文档检索
- 自动生成检索query并调用semantic_search
- 将检索结果注入上下文
- 第一版：依赖Agent主动调用工具，不做自动检索（更可控）

- [ ] **Step 2: 系统提示词引导**

在系统提示中告知Agent：
```
You have access to semantic_search for concept-based code search.
- Use grep_search when you know exact function names, variable names, or patterns.
- Use semantic_search when you describe functionality or concepts ("authentication middleware", "error handling logic", "how are events processed").
- Start with semantic_search for broad understanding, then narrow down with grep_search and read_file.
```

---

### Task 8: 测试、性能与验证

**Files:**
- Create: `packages/runtime-ts/tests/embedding.test.ts`
- Create: `packages/runtime-ts/tests/vector-store.test.ts`
- Create: `packages/runtime-ts/tests/chunking.test.ts`
- Create: `packages/runtime-ts/tests/semantic-search.test.ts`

- [ ] **Step 1: 单元测试覆盖**

- 嵌入层：向量维度、相似度计算正确
- 向量存储：add/search/delete/count正确
- 分块器：各种语言/文档正确分块
- 工具：semantic_search端到端返回合理结果
- 记忆：memory_read semantic模式工作

- [ ] **Step 2: 性能基准测试**

- 索引1000/10000/50000文件的时间和内存
- 查询延迟（P50/P95）
- 内存占用
- 在SztuCode自身代码库上测试检索质量

- [ ] **Step 3: 集成测试**

Run:
```text
cd packages/runtime-ts
npm test
npx tsc --noEmit
```

Expected:
- 所有现有测试通过
- 新增测试通过
- TypeScript零错误
- 首次索引在1000文件代码库上<30秒（本地模型）
- 单次查询<100ms（内存向量扫描）

- [ ] **Step 4: 手动场景验证**

在SztuCode自身仓库验证：
1. "如何处理上下文压缩？" → 找到context.ts相关代码
2. "权限检查在哪里做的？" → 找到permission-policy.ts和bash-permission.ts
3. "工具调用是怎么执行的？" → 找到agent-loop.ts和tools.ts
4. 跨session记忆：session A保存note"使用JSONL存储事件"，session B语义搜索"事件持久化"能找到该note

---

## 验收标准

- [ ] `semantic_search`工具可基于语义查询代码和文档
- [ ] 本地嵌入模型工作正常，无需云端API key即可使用
- [ ] 首次使用自动懒索引，无需手动配置
- [ ] 记忆系统支持语义搜索notes
- [ ] 向量索引按workspace隔离，持久化到磁盘
- [ ] 增量更新，文件变更时索引不失效
- [ ] 与现有grep_search互补，不替换
- [ ] 所有现有功能不受影响
- [ ] 测试覆盖核心路径，TypeScript编译零错误
- [ ] 默认配置下开箱即用，无需原生依赖编译

## 非目标（本阶段不做）

- Reranker/交叉编码器重排（后续可加）
- 多模态向量（图片/图表检索，与multimodal plan配合）
- 云端托管向量数据库（Pinecone/Weaviate集成）
- GraphRAG/知识图谱
- 实时文件系统watcher自动更新索引（可以用轮询或手动刷新）
- 问答对/对话历史向量化（memory系统做会话记忆即可）
- Hybrid search with BM25（第一版只做向量+关键词，后续可加BM25融合）
