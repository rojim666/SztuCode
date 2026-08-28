import type { AgentPhase } from "@sztucode/protocol";

/**
 * 执行阶段编排：由 daemon 在 agent-loop 里判定并推送 phase.changed 事件。
 *
 * 注意：desktop/src/components/timeline/pipeline/phase.ts 里有一份同名的前端兜底推断
 * （桌面端连不上阶段事件时用工具名自行猜测）。两处规则必须保持一致，
 * 改这里记得同步改那边，否则「daemon 有阶段 / 无阶段」两种情况下界面会跳。
 */

export type ToolCategory = "read" | "write" | "verify" | "other";

// tools.ts 里注册的工具
const WRITE_TOOLS = new Set(["write_file", "edit_file", "task_create", "task_update"]);
const READ_TOOLS = new Set(["read_file", "list_dir", "glob_search", "grep_search", "task_list", "task_get", "ask_user_question"]);

// 未登记工具的兜底关键词，按 _ - 切词后逐个比对
const VERIFY_KEYWORDS = new Set(["test", "tests", "typecheck", "lint", "check", "checks", "build", "verify", "compile", "validate", "audit", "bench"]);
const WRITE_KEYWORDS = new Set(["write", "edit", "create", "update", "delete", "remove", "move", "rename", "patch", "apply", "insert", "append", "save", "mkdir", "touch"]);
const READ_KEYWORDS = new Set(["read", "view", "list", "glob", "grep", "search", "find", "get", "fetch", "inspect", "show", "stat", "cat", "head", "tail", "open", "load", "query", "describe"]);

// bash 的归类取决于命令本身，而不是工具名
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
  // 按「词」匹配而不是子串匹配，否则 frobnicate 里的 cat 会被当成只读工具
  const tokens = key.split(/[^a-z0-9]+/).filter(Boolean);
  if (tokens.some((token) => VERIFY_KEYWORDS.has(token))) return "verify";
  if (tokens.some((token) => WRITE_KEYWORDS.has(token))) return "write";
  if (tokens.some((token) => READ_KEYWORDS.has(token))) return "read";
  return "other";
}

export type PhaseChange = { from: AgentPhase; to: AgentPhase; reason: string };

export type PhaseTracker = {
  current(): AgentPhase;
  /** 观察到一次工具调用；仅当阶段发生变化时返回变更，否则返回 null */
  observeTool(name: string, params: Record<string, unknown>): PhaseChange | null;
  /** 本轮没有待执行工具、即将收尾 */
  finish(): PhaseChange | null;
};

export function createPhaseTracker(): PhaseTracker {
  let current: AgentPhase = "understanding";
  return {
    current: () => current,
    observeTool(name, params) {
      const category = classifyTool(name, params);
      // 只读探查不改变阶段：它既可能发生在最开始的理解，也可能发生在执行中的回查
      const next: AgentPhase | null = category === "write" ? "executing" : category === "verify" ? "verifying" : null;
      if (!next || next === current) return null;
      const from = current;
      current = next;
      return { from, to: next, reason: `${name} 属于${category === "write" ? "写入" : "验证"}类操作` };
    },
    finish() {
      if (current === "delivering") return null;
      const from = current;
      current = "delivering";
      return { from, to: "delivering", reason: "本轮无待执行工具，进入收尾" };
    },
  };
}
