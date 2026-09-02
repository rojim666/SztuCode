// TaskCanvas - 任务画布：将 Agent 执行过程组织为结构化的步骤记录
// 参考 Python 版 py-runtime/src/sztu_code/core/compact/canvas.py
// 不额外调用 LLM — 由 AgentLoop 在每步结束时自动维护。

export type CanvasNodeStatus = "pending" | "running" | "done" | "failed";
export type VerifiedStatus = "verified" | "failed" | "unverified";

export interface CanvasNode {
  nodeId: string;
  label: string;
  status: CanvasNodeStatus;
  toolNames: string[];
  summary: string;
  refs: string[];
  tsStart: string;
  tsEnd: string;
  // Recuris 五元组结构化轨迹（失败定位的证据基础）：
  state: string;
  skill: string;
  action: string;
  observation: string;
  verified: VerifiedStatus;
}

function _now(): string {
  return new Date().toISOString();
}

// 清理文本使其可作为 Mermaid 节点标签：去除换行、转义特殊字符
function _sanitizeMermaidLabel(text: string, maxLen = 80): string {
  let cleaned = text.trim().split("\n")[0]!.trim();
  if (cleaned.length > maxLen) {
    cleaned = cleaned.slice(0, maxLen - 3) + "...";
  }
  // 移除或替换会破坏 Mermaid 语法的字符
  cleaned = cleaned.replace(/"/g, "'");
  cleaned = cleaned.replace(/\(/g, "（").replace(/\)/g, "）");
  cleaned = cleaned.replace(/\[/g, "【").replace(/\]/g, "】");
  cleaned = cleaned.replace(/\{/g, "｛").replace(/\}/g, "｝");
  cleaned = cleaned.replace(/</g, "＜").replace(/>/g, "＞");
  cleaned = cleaned.replace(/&/g, "＆");
  cleaned = cleaned.replace(/#/g, "＃");
  if (cleaned.startsWith("＃")) {
    cleaned = "_" + cleaned.slice(1);
  }
  return cleaned;
}

const STATUS_ICONS: Record<CanvasNodeStatus, string> = {
  pending: "⏳",
  running: "🔵",
  done: "✅",
  failed: "❌",
};

export class TaskCanvas {
  private _nodes: CanvasNode[] = [];
  private _stepCounter = 0;
  private readonly _maxVisible: number;

  constructor(maxVisibleNodes = 20) {
    this._maxVisible = maxVisibleNodes;
  }

  get nodes(): CanvasNode[] {
    return [...this._nodes];
  }

  get nodeCount(): number {
    return this._nodes.length;
  }

  // 注册一个新的步骤节点（AgentLoop 每步结束后调用）
  recordStep(params: {
    label?: string;
    toolNames?: string[];
    summary?: string;
    refs?: string[];
    status?: CanvasNodeStatus;
    state?: string;
    skill?: string;
    action?: string;
    observation?: string;
    verified?: VerifiedStatus;
  }): CanvasNode {
    this._stepCounter++;
    const nodeId = `step_${String(this._stepCounter).padStart(2, "0")}`;
    const now = _now();
    const status = params.status ?? "done";
    const node: CanvasNode = {
      nodeId,
      label: _sanitizeMermaidLabel(params.label || `Step ${this._stepCounter}`),
      status,
      toolNames: [...(params.toolNames ?? [])],
      summary: (params.summary ?? "").slice(0, 200),
      refs: [...(params.refs ?? [])],
      tsStart: now,
      tsEnd: status === "done" || status === "failed" ? now : "",
      state: params.state ?? "",
      skill: params.skill ?? "",
      action: params.action ?? "",
      observation: params.observation ?? "",
      verified: params.verified ?? "unverified",
    };
    this._nodes.push(node);
    return node;
  }

  // 将最近的 tool_use → tool_result 整理为一个画布节点
  recordToolCalls(
    toolNames: string[],
    summaries: string[],
    refPaths: string[],
    status: CanvasNodeStatus = "done"
  ): CanvasNode {
    let label = toolNames.slice(0, 3).join("; ");
    if (toolNames.length > 3) {
      label += ` +${toolNames.length - 3} more`;
    }
    const combinedSummary = summaries.length > 0 ? summaries.slice(0, 3).join("; ").slice(0, 200) : "";
    return this.recordStep({
      label,
      toolNames: [...toolNames],
      summary: combinedSummary,
      refs: [...refPaths],
      status,
    });
  }

  // 渲染为 Mermaid flowchart 文本
  renderMermaid(): string {
    if (this._nodes.length === 0) {
      return "(任务画布为空 — 尚无执行步骤)";
    }

    const visible = this._nodes.slice(-this._maxVisible);
    const lines = ["```mermaid", "graph TD"];

    // 绘制节点
    for (const node of visible) {
      lines.push(this._toMermaidNode(node));
    }

    // 绘制边（顺序依赖）
    for (let i = 0; i < visible.length - 1; i++) {
      lines.push(`    ${visible[i]!.nodeId} --> ${visible[i + 1]!.nodeId}`);
    }

    // 折叠旧节点标记
    if (this._nodes.length > this._maxVisible) {
      const hiddenCount = this._nodes.length - this._maxVisible;
      lines.push(`    %% ${hiddenCount} 个更早的步骤已折叠`);
    }

    lines.push("```");
    return lines.join("\n");
  }

  private _toMermaidNode(node: CanvasNode): string {
    const icon = STATUS_ICONS[node.status] ?? STATUS_ICONS.pending;
    return `    ${node.nodeId}["${icon} ${node.label}"]`;
  }

  // 渲染最近完成节点的文本摘要
  recentSummary(n = 5): string {
    if (this._nodes.length === 0) return "";
    const recent = this._nodes.slice(-n).filter(node => node.status === "done");
    if (recent.length === 0) return "";
    return recent.map(node => this._toSummaryLine(node)).join("\n");
  }

  private _toSummaryLine(node: CanvasNode): string {
    const icon = STATUS_ICONS[node.status] ?? STATUS_ICONS.pending;
    const tools = node.toolNames.length > 0 ? node.toolNames.join(", ") : "—";
    const detail = node.summary.slice(0, 120) || "进行中...";
    return `- ${node.nodeId}: ${icon} ${detail} (工具: ${tools})`;
  }

  // 当前进行中的节点
  get activeNodes(): CanvasNode[] {
    return this._nodes.filter(n => n.status === "running");
  }

  // 按状态分组统计
  stats(): Record<string, number> {
    const counts: Record<string, number> = {};
    for (const node of this._nodes) {
      counts[node.status] = (counts[node.status] ?? 0) + 1;
    }
    return counts;
  }

  // 更新最后一个节点的完成信息（工具执行完毕后调用）
  finalizeLast(params: {
    label?: string;
    status?: CanvasNodeStatus;
    summary?: string;
    refs?: string[];
    state?: string;
    skill?: string;
    action?: string;
    observation?: string;
    verified?: VerifiedStatus;
  }): void {
    if (this._nodes.length === 0) return;
    const node = this._nodes[this._nodes.length - 1]!;
    if (params.label && params.label.trim()) {
      node.label = _sanitizeMermaidLabel(params.label);
    }
    if (params.status) {
      node.status = params.status;
    }
    if (params.summary) {
      node.summary = params.summary.slice(0, 200);
    }
    if (params.refs) {
      node.refs = [...params.refs];
    }
    if (params.state !== undefined) {
      node.state = params.state;
    }
    if (params.skill !== undefined) {
      node.skill = params.skill;
    }
    if (params.action !== undefined) {
      node.action = params.action;
    }
    if (params.observation !== undefined) {
      node.observation = params.observation;
    }
    if (params.verified !== undefined) {
      node.verified = params.verified;
    }
    if (node.status === "done" || node.status === "failed") {
      node.tsEnd = _now();
    }
  }

  // 标记最后一个节点开始运行
  markLastRunning(): void {
    if (this._nodes.length === 0) return;
    const node = this._nodes[this._nodes.length - 1]!;
    node.status = "running";
    node.tsStart = _now();
    node.tsEnd = "";
  }

  // 导出所有节点数据（用于事件流持久化）
  export(): Array<Record<string, unknown>> {
    return this._nodes.map(n => ({
      node_id: n.nodeId,
      label: n.label,
      status: n.status,
      tool_names: n.toolNames,
      summary: n.summary,
      refs: n.refs,
      ts_start: n.tsStart,
      ts_end: n.tsEnd,
      state: n.state,
      skill: n.skill,
      action: n.action,
      observation: n.observation,
      verified: n.verified,
    }));
  }

  // 清空画布
  clear(): void {
    this._nodes = [];
    this._stepCounter = 0;
  }
}
