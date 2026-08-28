import type { TimelineStep, ToolCallEntry } from "../types";

/**
 * 流水线阶段。粒度刻意做得粗——每完成一类动作才推进一次，
 * 避免逐步跳变让用户看不出"现在在干嘛"。
 */
export type PipelinePhase = "understanding" | "executing" | "verifying" | "delivering";

export const PHASE_ORDER: readonly PipelinePhase[] = ["understanding", "executing", "verifying", "delivering"];

export const PHASE_META: Record<PipelinePhase, { label: string; hint: string }> = {
  understanding: { label: "理解", hint: "读取上下文、定位改动点" },
  executing: { label: "执行", hint: "写入与修改文件" },
  verifying: { label: "验证", hint: "跑测试、构建与静态检查" },
  delivering: { label: "交付", hint: "汇总本轮结果" },
};

export type ToolCategory = "read" | "write" | "verify" | "other";

// runtime-ts 注册的工具名（packages/runtime-ts/src/tools.ts）
const WRITE_TOOLS = new Set(["write_file", "edit_file", "task_create", "task_update"]);
const READ_TOOLS = new Set(["read_file", "list_dir", "glob_search", "grep_search", "task_list", "task_get", "ask_user_question"]);

// 未登记工具的兜底关键词，按 _ - 与驼峰切词后逐个比对
const VERIFY_KEYWORDS = new Set(["test", "tests", "typecheck", "lint", "check", "checks", "build", "verify", "compile", "validate", "audit", "bench"]);
const WRITE_KEYWORDS = new Set(["write", "edit", "create", "update", "delete", "remove", "move", "rename", "patch", "apply", "insert", "append", "save", "mkdir", "touch"]);
const READ_KEYWORDS = new Set(["read", "view", "list", "glob", "grep", "search", "find", "get", "fetch", "inspect", "show", "stat", "cat", "head", "tail", "open", "load", "query", "describe"]);

// bash 是最难归类的工具：命令本身才决定它是验证还是普通执行。
const VERIFY_COMMAND = /\b(pytest|jest|vitest|mocha|ruff|mypy|flake8|eslint|tsc|go\s+test|cargo\s+(?:test|check|clippy)|dotnet\s+test|mvn\s+test|gradle\s+test|npm\s+test|pnpm\s+test|yarn\s+test|npm\s+run\s+[\w:-]*(?:test|lint|build|check|typecheck)[\w:-]*|pnpm\s+run\s+[\w:-]*(?:test|lint|build|check|typecheck)[\w:-]*|yarn\s+[\w:-]*(?:test|lint|build)[\w:-]*|make\s+(?:test|lint|check)|uv\s+run\s+(?:pytest|ruff|mypy))\b/i;

export function classifyTool(name: string, params: Record<string, unknown>): ToolCategory {
  const key = name.toLowerCase();
  if (WRITE_TOOLS.has(key)) return "write";
  if (READ_TOOLS.has(key)) return "read";
  if (key === "bash" || key === "shell" || key === "terminal" || key === "run_command") {
    const raw = params.command ?? params.cmd;
    const command = typeof raw === "string" ? raw : "";
    return VERIFY_COMMAND.test(command) ? "verify" : "other";
  }
  // 未登记的工具按名字兜底。这里必须按「词」匹配而不是子串匹配——
  // 子串写法会把 frobnicate 里的 cat 误判成只读工具（测试里真实踩到过）。
  const tokens = key.split(/[^a-z0-9]+/).filter(Boolean);
  if (tokens.some((token) => VERIFY_KEYWORDS.has(token))) return "verify";
  if (tokens.some((token) => WRITE_KEYWORDS.has(token))) return "write";
  if (tokens.some((token) => READ_KEYWORDS.has(token))) return "read";
  return "other";
}

export type PipelineSegment = {
  id: string;
  step: number;
  phase: PipelinePhase;
} & (
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string; completed: boolean }
  | { kind: "tools"; calls: ToolCallEntry[]; category: ToolCategory }
);

type RawItem = { step: number } & (
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string; completed: boolean }
  | { kind: "tool"; call: ToolCallEntry }
);

function stepText(step: TimelineStep): string {
  return step.finalText || step.streamText || step.tokens.join("");
}

function hasAssistantContent(step: TimelineStep): boolean {
  return Boolean(
    stepText(step).trim() ||
    step.thinking?.trim() ||
    step.toolCalls.length ||
    step.permission ||
    step.plan?.length ||
    step.tests?.length ||
    step.changes?.length ||
    step.logs?.length ||
    step.subagents?.length ||
    step.skills?.length ||
    step.workflowTasks?.length ||
    step.workflowHandoffs?.length ||
    step.workflowReviews?.length ||
    step.contextInjections?.length,
  );
}

/** 把若干个 step 摊平成一条按时间顺序排列的流水：文本段、思考段、工具段交错。 */
export function buildPipelineSegments(steps: TimelineStep[]): PipelineSegment[] {
  const raw: RawItem[] = [];

  for (const step of steps) {
    if (step.userMessage && !hasAssistantContent(step)) continue;
    const calls = new Map(step.toolCalls.map((call) => [call.id, call]));

    if (step.events?.length) {
      for (const event of step.events) {
        if (event.kind === "text") {
          const text = event.text ?? "";
          if (!text.trim()) continue;
          const last = raw[raw.length - 1];
          // 相邻的 token 事件合并成一段正文，否则每段正文会被拆成上百张卡片
          if (last && last.kind === "text") last.text += text;
          else raw.push({ step: step.step, kind: "text", text });
        } else if (event.kind === "thinking") {
          const text = event.text ?? "";
          if (!text.trim()) continue;
          const last = raw[raw.length - 1];
          if (last && last.kind === "thinking") last.text += text;
          else raw.push({ step: step.step, kind: "thinking", text, completed: step.status === "done" });
        } else if (event.toolCallId) {
          const call = calls.get(event.toolCallId);
          if (call) raw.push({ step: step.step, kind: "tool", call });
        }
      }
    } else {
      // 兜底路径与 ExecutionTimeline.orderedEvents 保持一致
      if (step.thinking?.trim()) raw.push({ step: step.step, kind: "thinking", text: step.thinking, completed: step.status === "done" });
      const text = stepText(step);
      if (text.trim()) raw.push({ step: step.step, kind: "text", text });
      for (const call of step.toolCalls) raw.push({ step: step.step, kind: "tool", call });
    }
  }

  const segments: PipelineSegment[] = [];
  let phase: PipelinePhase = "understanding";

  for (const item of raw) {
    if (item.kind === "tool") {
      const category = classifyTool(item.call.name, item.call.params);
      if (category === "write") phase = "executing";
      else if (category === "verify") phase = "verifying";
      const last = segments[segments.length - 1];
      // 连续同类工具收成一组："读取了 5 个文件" 而不是 5 张卡片
      if (last && last.kind === "tools" && last.category === category) {
        last.calls.push(item.call);
        continue;
      }
      segments.push({ id: `tools-${item.call.id}`, step: item.step, phase, kind: "tools", calls: [item.call], category });
      continue;
    }
    segments.push({ ...item, id: `${item.kind}-${item.step}-${segments.length}`, phase });
  }

  // 收尾：没有工具在跑、且最后是正文，才算进入交付阶段
  const running = steps.some((step) => step.toolCalls.some((call) => call.status === "running" || call.status === "awaiting_permission"));
  const last = segments[segments.length - 1];
  if (!running && last && last.kind === "text") last.phase = "delivering";

  return segments;
}

export type PhaseState = {
  phase: PipelinePhase;
  reached: boolean;
  active: boolean;
  count: number;
};

/** 阶段轴数据：哪些阶段已发生、当前处在哪个阶段。 */
export function phaseStates(segments: PipelineSegment[], running: boolean): PhaseState[] {
  const counts = new Map<PipelinePhase, number>();
  for (const segment of segments) counts.set(segment.phase, (counts.get(segment.phase) ?? 0) + 1);
  const current = segments[segments.length - 1]?.phase ?? "understanding";
  return PHASE_ORDER.map((phase) => ({
    phase,
    reached: (counts.get(phase) ?? 0) > 0,
    active: running && phase === current,
    count: counts.get(phase) ?? 0,
  }));
}