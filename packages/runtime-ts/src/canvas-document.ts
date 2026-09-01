// CanvasDocument - 文档画布：让 AI 产出高质量富文本交付物（Markdown：文字/表格/图片）
// 与 TaskCanvas（任务步骤流程图）互补：TaskCanvas 记录"做过什么"，CanvasDocument 承载"交付什么"。
// 工具通过 EventBus 发布 canvas.document 事件，客户端（桌面端面板）实时渲染文档。

import type { CanvasDocumentPayload } from "@sztucode/protocol";
import type { EventBus } from "./event-bus.js";
import type { Tool, ToolResult } from "./tools.js";

const ok = (output: string): ToolResult => ({ ok: true, output });
const fail = (error: string, errorType: ToolResult["errorType"] = "runtime_error"): ToolResult => ({ ok: false, output: "", error, errorType });

export interface CanvasDocument {
  id: string;
  title: string;
  kind: "markdown";
  content: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

const MAX_DOCS_PER_SCOPE = 20;
const MAX_DOC_CHARS = 200_000;
const MAX_TITLE_CHARS = 120;

function _now(): string {
  return new Date().toISOString();
}

function _sanitizeId(raw: string): string {
  return raw.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
}

function toPayload(doc: CanvasDocument): CanvasDocumentPayload {
  return { id: doc.id, title: doc.title, kind: doc.kind, content: doc.content, version: doc.version, created_at: doc.createdAt, updated_at: doc.updatedAt };
}

// 单一会话（或匿名 run）范围内的文档集合
export class CanvasDocumentStore {
  private readonly _docs = new Map<string, CanvasDocument>();
  private _counter = 0;

  get size(): number {
    return this._docs.size;
  }

  create(params: { title: string; content: string; id?: string }): CanvasDocument {
    const title = params.title.trim().slice(0, MAX_TITLE_CHARS) || "未命名文档";
    const content = params.content.slice(0, MAX_DOC_CHARS);
    let id = params.id ? _sanitizeId(params.id) : "";
    if (!id) {
      this._counter++;
      id = `doc-${String(this._counter).padStart(2, "0")}`;
    }
    // 显式 id 冲突时自动加后缀，避免误覆盖既有文档
    if (this._docs.has(id)) {
      let suffix = 2;
      while (this._docs.has(`${id}-${suffix}`)) suffix++;
      id = `${id}-${suffix}`;
    }
    // 超出容量时淘汰最旧文档
    if (this._docs.size >= MAX_DOCS_PER_SCOPE) {
      const oldest = this._docs.keys().next().value;
      if (oldest !== undefined) this._docs.delete(oldest);
    }
    const doc: CanvasDocument = { id, title, kind: "markdown", content, version: 1, createdAt: _now(), updatedAt: _now() };
    this._docs.set(id, doc);
    return doc;
  }

  update(id: string, params: { title?: string; content?: string; append?: boolean }): CanvasDocument | null {
    const doc = this._docs.get(id);
    if (!doc) return null;
    if (typeof params.title === "string" && params.title.trim()) {
      doc.title = params.title.trim().slice(0, MAX_TITLE_CHARS);
    }
    if (typeof params.content === "string") {
      doc.content = params.append ? (doc.content + "\n\n" + params.content).slice(0, MAX_DOC_CHARS) : params.content.slice(0, MAX_DOC_CHARS);
    }
    doc.version++;
    doc.updatedAt = _now();
    return doc;
  }

  get(id: string): CanvasDocument | undefined {
    return this._docs.get(id);
  }

  list(): CanvasDocument[] {
    return [...this._docs.values()];
  }
}

// 进程级共享：同一会话跨多轮 run 复用同一文档集合（createPlanTools 每 run 重建工具，但画布内容要保留）
const sharedStores = new Map<string, CanvasDocumentStore>();

export function canvasStoreFor(scope: string): CanvasDocumentStore {
  const key = scope || "default";
  let store = sharedStores.get(key);
  if (!store) {
    store = new CanvasDocumentStore();
    sharedStores.set(key, store);
    // 防止长驻进程无限积累：最多保留 200 个作用域，超出时清理最旧
    if (sharedStores.size > 200) {
      const oldest = sharedStores.keys().next().value;
      if (oldest !== undefined) sharedStores.delete(oldest);
    }
  }
  return store;
}

/** 仅测试用：清空共享存储。 */
export function resetCanvasStores(): void {
  sharedStores.clear();
}

/**
 * 创建文档画布工具集：canvas_create / canvas_update / canvas_get / canvas_list。
 * 与 createPlanTools 同构——每 run 调用一次，事件经 EventBus 直达客户端。
 */
export function createCanvasTools(events: EventBus, runId: string, sessionId = ""): Tool[] {
  const store = canvasStoreFor(sessionId || `run:${runId}`);
  const publish = (action: "create" | "update", doc: CanvasDocument) => {
    events.publish({ type: "canvas.document", run_id: runId, ...(sessionId ? { session_id: sessionId } : {}), action, document: toPayload(doc), ts: _now() });
  };
  const summary = (doc: CanvasDocument) => JSON.stringify({ document_id: doc.id, title: doc.title, version: doc.version, chars: doc.content.length });

  return [
    {
      name: "canvas_create",
      description: "在客户端画布面板创建一份高质量 Markdown 交付文档，支持标题/表格/列表/代码块/图片引用（相对工作区路径）。用于报告、方案、对比分析、总结等富文本成果，用户会实时看到渲染后的文档。Create a rich Markdown deliverable on the client canvas panel.",
      permission: "workspace_write",
      schema: {
        type: "object",
        properties: {
          title: { type: "string", minLength: 1, description: "文档标题" },
          content: { type: "string", minLength: 1, description: "完整 Markdown 内容（表格用 GFM 语法，图片用 ![alt](相对路径) 引用工作区文件）" },
          document_id: { type: "string", description: "可选自定义 ID（小写字母/数字/连字符），便于后续 canvas_update 引用" },
        },
        required: ["title", "content"],
      },
      async invoke(params) {
        const title = typeof params.title === "string" ? params.title : "";
        const content = typeof params.content === "string" ? params.content : "";
        if (!title.trim() || !content.trim()) return fail("title and content are required", "schema_error");
        const doc = store.create({ title, content, ...(typeof params.document_id === "string" ? { id: params.document_id } : {}) });
        publish("create", doc);
        return ok(summary(doc));
      },
    },
    {
      name: "canvas_update",
      description: "更新画布面板中已有的 Markdown 文档（整体替换或追加内容、改标题），客户端实时刷新。Update an existing canvas document.",
      permission: "workspace_write",
      schema: {
        type: "object",
        properties: {
          document_id: { type: "string", minLength: 1 },
          title: { type: "string", description: "可选新标题" },
          content: { type: "string", description: "新内容（mode=replace 时为完整文档，mode=append 时为追加片段）" },
          mode: { type: "string", enum: ["replace", "append"], default: "replace" },
        },
        required: ["document_id"],
      },
      async invoke(params) {
        const id = typeof params.document_id === "string" ? params.document_id.trim() : "";
        if (!id) return fail("document_id is required", "schema_error");
        const doc = store.update(id, {
          ...(typeof params.title === "string" ? { title: params.title } : {}),
          ...(typeof params.content === "string" ? { content: params.content } : {}),
          append: params.mode === "append",
        });
        if (!doc) return fail(`canvas document not found: ${id}`, "schema_error");
        publish("update", doc);
        return ok(summary(doc));
      },
    },
    {
      name: "canvas_get",
      description: "读取画布文档的完整 Markdown 内容。Read a canvas document by ID.",
      permission: "read_only",
      schema: { type: "object", properties: { document_id: { type: "string", minLength: 1 } }, required: ["document_id"] },
      async invoke(params) {
        const id = typeof params.document_id === "string" ? params.document_id.trim() : "";
        const doc = id ? store.get(id) : undefined;
        if (!doc) return fail(`canvas document not found: ${id || "(missing)"}`, "schema_error");
        return ok(JSON.stringify(toPayload(doc)));
      },
    },
    {
      name: "canvas_list",
      description: "列出当前会话的所有画布文档（ID/标题/版本/字数）。List canvas documents in this session.",
      permission: "read_only",
      schema: { type: "object", properties: {} },
      async invoke() {
        return ok(JSON.stringify(store.list().map((doc) => ({ document_id: doc.id, title: doc.title, version: doc.version, chars: doc.content.length, updated_at: doc.updatedAt }))));
      },
    },
  ];
}
