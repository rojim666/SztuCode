import type { IpcEvent } from "../lib/ipc";

// ── 会话与工作区 ──────────────────────────────────────────

export type Session = {
  session_id: string;
  title: string;
  status: string;
  updated_at: string;
  archived: boolean;
  pinned?: boolean;
  workspace_id?: string | null;
  latest_run_id?: string | null;
};

export type Workspace = {
  workspace_id: string;
  path: string;
  name: string;
};

// ── 时间线与变更 ──────────────────────────────────────────

export type TimelineItem = {
  id: string;
  kind: "user" | "agent" | "tool" | "system";
  title?: string;
  body: string;
  state?: string;
};

export type Change = {
  path: string;
  index_status: string;
  worktree_status: string;
  run_id?: string | null;
  agent_owned?: boolean;
  revertible?: boolean;
};

export type DiffView = "unified" | "split";

export type DiffRow = {
  old: string;
  next: string;
  kind: "context" | "added" | "removed" | "meta";
};

// ── 计划与验证 ────────────────────────────────────────────

export type PlanItem = {
  id: number;
  subject: string;
  status: "pending" | "in_progress" | "completed";
  blocked_by: number[];
};

export type TestResult = {
  tool_use_id: string;
  status: "passed" | "failed";
  summary: string;
};

// ── 权限与运行时 ──────────────────────────────────────────

export type Permission = {
  tool_use_id: string;
  tool_name: string;
  params: unknown;
  run_id?: string;
};

export type RuntimeSettings = {
  provider: "anthropic" | "openai";
  model: string;
  router: string;
  permission_mode: string;
  applies_at: "next_run";
  persistent: boolean;
};

export type ProviderStatus = {
  provider: "anthropic" | "openai";
  model: string;
  api_key_configured: boolean;
  custom_endpoint_configured: boolean;
  ready_for_next_run: boolean;
  mcp_servers: {
    name: string;
    transport: string;
    status: "connected" | "unavailable";
    tool_count: number;
  }[];
  skills: { name: string; description: string }[];
};

// ── 命令面板 ──────────────────────────────────────────────

export type PaletteCommand = {
  id: string;
  title: string;
  detail: string;
  key: string;
  disabled?: boolean;
  action: () => void;
};

// ── 诊断与文件 ────────────────────────────────────────────

export type Diagnostics = {
  version: string;
  uptime: string;
  branch: string;
  changes: number;
  repository: boolean;
};

export type FileNode = {
  path: string;
  name: string;
  kind: "file" | "directory";
  children?: FileNode[];
};

export type DaemonStartResult = {
  status: "started" | "starting" | "already_running";
  detail: string;
};

// ── 连接状态 ──────────────────────────────────────────────

export type ConnectionState = "connecting" | "ready" | "offline";

// ── 工具函数 ──────────────────────────────────────────────

/** 截断过长的字符串用于 UI 展示 */
export function short(value: string, length = 44): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

/** 会话运行状态的中文文本 */
export function sessionState(session: Session): string {
  return session.status === "active" ? "运行中" : "就绪";
}

/** 格式化错误消息 */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** 执行模式的中文标签 */
export function modeLabel(mode: string): string {
  return (
    {
      normal: "标准审批",
      plan: "计划模式",
      accept_edits: "允许编辑",
      auto: "自动执行",
    } as Record<string, string>
  )[mode] ?? mode;
}

/** 执行模式的中文描述 */
export function modeDescription(mode: string): string {
  return (
    {
      normal: "每项有影响的操作都由你确认。",
      plan: "默认只允许只读分析与计划拆分。",
      accept_edits: "允许工作区文件编辑，其余操作仍审批。",
      auto: "低风险步骤自动执行，高风险动作仍可见。",
    } as Record<string, string>
  )[mode] ?? "使用本地安全策略执行。";
}

/** 从消息内容中提取文本 */
export function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((block) => {
      if (!block || typeof block !== "object") return "";
      const value = block as Record<string, unknown>;
      if (value.type === "text") return String(value.text ?? "");
      if (value.type === "tool_use") return `调用工具：${String(value.name ?? "unknown")}`;
      if (value.type === "tool_result") return String(value.content ?? "工具已完成");
      return "";
    })
    .filter(Boolean)
    .join("\n\n");
}

/** 将对话历史转换为时间线条目 */
export function historyToTimeline(messages: unknown[]): TimelineItem[] {
  return messages.flatMap((message, index) => {
    if (!message || typeof message !== "object") return [];
    const value = message as Record<string, unknown>;
    const body = messageText(value.content);
    if (!body) return [];
    return [
      {
        id: `history-${index}`,
        kind: (value.role === "user" ? "user" : "agent") as TimelineItem["kind"],
        body,
      },
    ];
  });
}

/** 解析 unified diff 为对照视图行 */
export function splitDiff(diff: string): DiffRow[] {
  const rows: DiffRow[] = [];
  for (const line of diff.split("\n")) {
    if (
      line.startsWith("+++ ") ||
      line.startsWith("--- ") ||
      line.startsWith("@@") ||
      line.startsWith("diff --git") ||
      line.startsWith("index ")
    ) {
      rows.push({ old: line, next: line, kind: "meta" });
    } else if (line.startsWith("-")) {
      rows.push({ old: line.slice(1), next: "", kind: "removed" });
    } else if (line.startsWith("+")) {
      rows.push({ old: "", next: line.slice(1), kind: "added" });
    } else {
      const value = line.startsWith(" ") ? line.slice(1) : line;
      rows.push({ old: value, next: value, kind: "context" });
    }
  }
  return rows;
}

// Re-export IpcEvent for convenience
export type { IpcEvent };
