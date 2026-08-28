export type TimelineStatus = "thinking" | "acting" | "observing" | "done" | "failed";
export type RunOutcome = { status: "success" | "failed" | "interrupted"; reason?: string };
export type RunStats = { inputTokens: number; outputTokens: number; cacheReadInputTokens: number; elapsedSeconds: number; ttftMs?: number; contextPct?: number };

export type ToolCallEntry = {
  id: string;
  name: string;
  params: Record<string, unknown>;
  status: "running" | "done" | "failed" | "awaiting_permission";
  output?: string;
  error?: string;
  elapsedMs?: number;
  startedAt?: string;  // 工具开始执行的 UTC 时间戳，用于 running 计时
};

// 上下文注入行：展示模型实际收到的完整 system 上下文及内部干预。
export type ContextInjectionEntry = {
  id: string;
  source: "compaction" | "canvas" | "intervention" | "steering" | "system";
  label: string;    // 展示名（如 "上下文注入"、"会话压缩"）
  chars: number;    // 注入内容字符数
  preview: string;  // 折叠时摘要（首行/前 100 字符）
  text?: string;    // 展开时完整正文（缺省用 preview）
};

export type TimelineEvent = {
  id: string;
  kind: "text" | "thinking" | "tool";
  text?: string;
  toolCallId?: string;
};

export type PermissionDecision = "allow_once" | "always_allow" | "deny_once" | "always_deny";

export type PermissionState = {
  toolUseId: string;
  toolName: string;
  preview: string;
  status: "pending" | "granted" | "denied";
};

export type LlmUsage = {
  inputTokens: number;
  outputTokens: number;
  contextPct: number;
  model: string;
  contextWindow: number;
  availableTokens: number;
  reservedOutputTokens: number;
  systemTokens: number;
  summaryTokens: number;
  conversationTokens: number;
  toolTokens: number;
  compacting?: boolean;
  compactedTokens?: number;
};

export type PlanItem = {
  id: number;
  subject: string;
  status: "pending" | "in_progress" | "completed";
  blocked_by: number[];
};

export type TestEntry = { status: "passed" | "failed"; summary: string };
export type ChangeEntry = { paths: string[]; workspacePath: string };
export type LogEntry = { level: string; source: string; message: string };
export type SubagentEntry = { runId: string; description: string; status: "running" | "success" | "failed" };
export type SkillEntry = { name: string; arguments: string };
export type WorkflowTaskEntry = {
  id: string;
  title: string;
  owner: "planner" | "coder" | "tester" | "reviewer";
  status: "pending" | "running" | "succeeded" | "failed" | "blocked" | "cancelled" | "timed_out" | "rejected";
  dependencies: string[];
  completionCriteria: string[];
  allowedPaths: string[];
  attempt: number;
  error?: string;
};
export type WorkflowHandoffEntry = {
  taskId: string;
  role: WorkflowTaskEntry["owner"];
  status: "succeeded" | "failed";
  summary: string;
  changedPaths: string[];
  scopeEscalations: string[];
  commands: string[];
  output: string;
  conclusion: string;
  childRunId: string;
};
export type WorkflowReviewEntry = {
  taskId: string;
  decision: "accept" | "return";
  diffSummary: string;
  testSummary: string;
  securitySummary: string;
  conclusion: string;
};
export type WorkflowOutcome = {
  status: "succeeded" | "failed" | "cancelled" | "timed_out";
  reason: string;
  totalTokens: number;
  elapsedS: number;
};

export interface TimelineStep {
  step: number;
  runId?: string;  // 所属 run 的全局唯一 ID，标识一轮思考生命周期
  // daemon 通过 phase.changed 下发的权威阶段。缺省时前端按工具类型自行推断。
  // 取值需与 packages/protocol 的 AgentPhase 保持一致（桌面端不依赖 protocol 包，故内联）。
  daemonPhase?: "understanding" | "executing" | "verifying" | "delivering";
  status: TimelineStatus;
  thinking?: string;
  tokens: string[];
  streamText?: string;
  toolCalls: ToolCallEntry[];
  events?: TimelineEvent[];
  permission?: PermissionState;
  usage?: LlmUsage;
  userMessage?: string;
  userMessageTime?: string;
  finalText?: string;
  outcome?: RunOutcome;
  runStats?: RunStats;
  runStartedAt?: string;
  plan?: PlanItem[];
  tests?: TestEntry[];
  changes?: ChangeEntry[];
  logs?: LogEntry[];
  subagents?: SubagentEntry[];
  skills?: SkillEntry[];
  workflowTasks?: WorkflowTaskEntry[];
  workflowHandoffs?: WorkflowHandoffEntry[];
  workflowReviews?: WorkflowReviewEntry[];
  workflowOutcome?: WorkflowOutcome;
  contextInjections?: ContextInjectionEntry[];
}

export function toolSummary(params: Record<string, unknown>): string {
  const command = params.command ?? params.cmd ?? params.path ?? params.query;
  return typeof command === "string" ? command : JSON.stringify(params);
}
