export type TimelineStatus = "thinking" | "acting" | "observing" | "done" | "failed";

export type ToolCallEntry = {
  id: string;
  name: string;
  params: Record<string, unknown>;
  status: "running" | "done" | "failed" | "awaiting_permission";
  output?: string;
  error?: string;
  elapsedMs?: number;
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

export interface TimelineStep {
  step: number;
  status: TimelineStatus;
  thinking?: string;
  tokens: string[];
  toolCalls: ToolCallEntry[];
  permission?: PermissionState;
  usage?: LlmUsage;
  userMessage?: string;
  finalText?: string;
  plan?: PlanItem[];
  tests?: TestEntry[];
  changes?: ChangeEntry[];
  logs?: LogEntry[];
  subagents?: SubagentEntry[];
  skills?: SkillEntry[];
}

export function toolSummary(params: Record<string, unknown>): string {
  const command = params.command ?? params.cmd ?? params.path ?? params.query;
  return typeof command === "string" ? command : JSON.stringify(params);
}