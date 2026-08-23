// 全局会话统计投影（借鉴 dsh sessionStats/tokenUsage 投影）：
// 从时间线 steps 折叠出会话级统计——轮数/步数、LLM/工具用时、首 token 平均、
// 吞吐、缓存命中率、输入/输出 token；按 runId 去重记账，翻页与压缩不改变数字
import type { TimelineStep } from "../components/timeline/types";

export type SessionStats = {
  turns: number;          // 轮数（distinct runId）
  steps: number;          // 步数
  llmMs: number;          // LLM 墙钟合计（Σ 每 run 的 elapsedSeconds）
  toolMs: number;         // 工具调用用时合计（Σ 已完成调用的 elapsedMs）
  ttftSteps: number;      // 有首 token 读数的 run 数
  ttftMsTotal: number;    // 首 token 延迟合计
  inputTokens: number;    // 输入 token 合计（未缓存部分，不含命中）
  outputTokens: number;   // 输出 token 合计
  cacheReadTokens: number; // 缓存命中读 token 合计
  contextPct?: number;    // 上下文占用比例 0～1（最新样本，借鉴 dsh contextPressure）
  contextBreakdown?: { system: number; summary: number; conversation: number; tool: number };
};

// 从时间线 steps 聚合会话级统计（借鉴 dsh 8.2/8.3 事件折叠语义）
export function deriveSessionStats(steps: readonly TimelineStep[]): SessionStats {
  // 每 run 一份 runStats：同 run 的多个 step 共享同一记账（历史导入时重复挂载），
  // 按 runId 去重避免重复累加；最后见到的记账胜出（与「高 seq 胜出」一致）
  const runStatsByRun = new Map<string, NonNullable<TimelineStep["runStats"]>>();
  const runIds = new Set<string>();
  const toolCalls = new Map<string, NonNullable<TimelineStep["toolCalls"]>[number]>();
  // 上下文占用取最新样本（借鉴 dsh ContextMeter：projectedTokens 取最新样本）
  let latestUsage: NonNullable<TimelineStep["usage"]> | undefined;

  for (const step of steps) {
    if (step.runId) {
      runIds.add(step.runId);
      if (step.runStats) runStatsByRun.set(step.runId, step.runStats);
    }
    if (step.usage) {
      latestUsage = step.usage;
    } else if (step.runStats?.contextPct) {
      // 历史恢复路径：usage 未持久化，从 runStats 补 contextPct（breakdown 样本不可得，置 0）
      latestUsage = {
        inputTokens: 0, outputTokens: 0, contextPct: step.runStats.contextPct, model: "",
        contextWindow: 0, availableTokens: 0, reservedOutputTokens: 0,
        systemTokens: 0, summaryTokens: 0, conversationTokens: 0, toolTokens: 0,
      };
    }
    for (const call of step.toolCalls ?? []) toolCalls.set(call.id, call);
  }

  let llmMs = 0;
  let ttftSteps = 0;
  let ttftMsTotal = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  let cacheReadTokens = 0;
  for (const stats of runStatsByRun.values()) {
    llmMs += stats.elapsedSeconds * 1000;
    if (stats.ttftMs !== undefined) {
      ttftSteps += 1;
      ttftMsTotal += stats.ttftMs;
    }
    inputTokens += stats.inputTokens;
    outputTokens += stats.outputTokens;
    cacheReadTokens += stats.cacheReadInputTokens;
  }

  let toolMs = 0;
  for (const call of toolCalls.values()) {
    if (call.status === "done" || call.status === "failed") toolMs += call.elapsedMs ?? 0;
  }

  return {
    turns: runIds.size,
    steps: steps.length,
    llmMs,
    toolMs,
    ttftSteps,
    ttftMsTotal,
    inputTokens,
    outputTokens,
    cacheReadTokens,
    contextPct: latestUsage?.contextPct,
    contextBreakdown: latestUsage ? {
      system: latestUsage.systemTokens,
      summary: latestUsage.summaryTokens,
      conversation: latestUsage.conversationTokens,
      tool: latestUsage.toolTokens,
    } : undefined,
  };
}

// 缓存命中率（借鉴 dsh 8.3 公式）：计费输入 = 未缓存输入 + 缓存读（+ 缓存写），
// 命中率 = 缓存读 / 计费输入。input_tokens 是未缓存部分，分母必须与分子同口径
// （高命中时会远大于 input_tokens，不能只用它做分母——否则命中率会超过 100%）
export function cacheHitPercent(stats: SessionStats): number | null {
  // Number() 归一化兜底：历史数据缺字段时 undefined/NaN 会被归零，
  // 否则 0 + undefined = NaN 会一路传染成「缓存命中 NaN%」
  const input = Number(stats.inputTokens) || 0;
  const cacheRead = Number(stats.cacheReadTokens) || 0;
  const billedInput = input + cacheRead;
  if (billedInput <= 0) return null;
  return Math.round((cacheRead / billedInput) * 1000) / 10;
}

// 将后端 0～1 的上下文占用比例格式化为固定两位小数的百分比。
export function formatContextPercent(contextRatio: number): string {
  const ratio = Number(contextRatio);
  const percent = Number.isFinite(ratio) ? Math.min(100, Math.max(0, ratio * 100)) : 0;
  return percent.toFixed(2);
}

// 紧凑 token 格式：超过 100K 后切换为 M，百万以下最多保留两位小数。
export function formatTokens(tokens: number): string {
  if (tokens > 100_000) {
    const precision = tokens < 1_000_000 ? 2 : 1;
    return `${trimDecimalZeros((tokens / 1_000_000).toFixed(precision))}M`;
  }
  if (tokens >= 1000) return `${trimDecimalZeros((tokens / 1000).toFixed(1))}K`;
  return String(tokens);
}

// 去掉小数部分的尾零（0.50 → 0.5、1.00 → 1），保持紧凑格式。
function trimDecimalZeros(value: string): string {
  return value.replace(/0+$/, "").replace(/\.$/, "");
}

// 时长格式（45.2s / 2m42s / 300ms）
export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return remainder ? `${minutes}m${String(remainder).padStart(2, "0")}s` : `${minutes}m`;
}

// 吞吐格式（<10 一位小数，其余取整）
export function formatTokensPerSecond(tokensPerSecond: number): string {
  return tokensPerSecond < 10 ? tokensPerSecond.toFixed(1) : String(Math.round(tokensPerSecond));
}
