import assert from "node:assert/strict";
import test from "node:test";
import type { TimelineStep } from "../src/components/timeline/types";
import { cacheHitPercent, deriveSessionStats, formatContextPercent, formatDuration, formatTokens, formatTokensPerSecond } from "../src/utils/sessionStats";

function step(overrides: Partial<TimelineStep>): TimelineStep {
  return { step: 1, status: "done", tokens: [], toolCalls: [], ...overrides };
}

// 功能：高缓存命中时命中率不超过 100%（分母 = 未缓存输入 + 缓存读）
// 设计：cacheRead 远大于 inputTokens 的极端场景（input 是不含命中的净输入），
//       验证分子分母同口径，避免旧公式算出的 1789% 类超范围值
test("cacheHitPercent stays within 0-100 even when cacheRead exceeds inputTokens", () => {
  const stats = deriveSessionStats([
    step({
      runId: "run-a",
      runStats: { inputTokens: 18, outputTokens: 5, cacheReadInputTokens: 90, elapsedSeconds: 1 },
    }),
  ]);
  assert.equal(cacheHitPercent(stats), 83.3); // 90 / (18 + 90)
});

// 功能：无命中时显示 0%
test("cacheHitPercent returns 0 when nothing was cached", () => {
  const stats = deriveSessionStats([
    step({
      runId: "run-a",
      runStats: { inputTokens: 100, outputTokens: 5, cacheReadInputTokens: 0, elapsedSeconds: 1 },
    }),
  ]);
  assert.equal(cacheHitPercent(stats), 0);
});

// 功能：无计费活动时返回 null（统计条不渲染缓存命中组）
test("cacheHitPercent returns null with no billed input", () => {
  const stats = deriveSessionStats([]);
  assert.equal(cacheHitPercent(stats), null);
});

// 功能：历史数据缺缓存字段（undefined 累加成 NaN）时兜底为 0，不显示「缓存命中 NaN%」
test("cacheHitPercent falls back to 0 when cache fields are missing", () => {
  const stats = deriveSessionStats([
    step({
      runId: "run-a",
      // 旧会话历史没有 cache_read_input_tokens，映射时缺字段 → 累加出 NaN
      runStats: { inputTokens: 100, outputTokens: 5, elapsedSeconds: 1 } as unknown as TimelineStep["runStats"],
    }),
  ]);
  assert.equal(cacheHitPercent(stats), 0);
});

test("deriveSessionStats returns all-zero stats for an empty timeline", () => {
  const stats = deriveSessionStats([]);
  assert.deepEqual(stats, {
    turns: 0, steps: 0, llmMs: 0, toolMs: 0, ttftSteps: 0, ttftMsTotal: 0,
    inputTokens: 0, outputTokens: 0, cacheReadTokens: 0,
    contextPct: undefined, contextBreakdown: undefined,
  });
});

test("deriveSessionStats picks the latest usage sample for context occupancy", () => {
  const steps = [
    step({
      runId: "run-1",
      usage: {
        inputTokens: 1, outputTokens: 1, contextPct: .4, model: "m",
        contextWindow: 100, availableTokens: 60, reservedOutputTokens: 10,
        systemTokens: 10, summaryTokens: 5, conversationTokens: 20, toolTokens: 5,
      },
    }),
    step({
      runId: "run-1",
      usage: {
        inputTokens: 1, outputTokens: 1, contextPct: .72, model: "m",
        contextWindow: 100, availableTokens: 28, reservedOutputTokens: 10,
        systemTokens: 12, summaryTokens: 8, conversationTokens: 40, toolTokens: 12,
      },
    }),
  ];

  const stats = deriveSessionStats(steps);

  assert.equal(stats.contextPct, .72);
  assert.deepEqual(stats.contextBreakdown, { system: 12, summary: 8, conversation: 40, tool: 12 });
});

test("deriveSessionStats counts one run's runStats once even across many steps", () => {
  const runStats = {
    inputTokens: 100, outputTokens: 50, cacheReadInputTokens: 40, elapsedSeconds: 3.2, ttftMs: 800,
  };
  const steps = [
    step({ step: 1, runId: "run-1", runStats }),
    step({ step: 2, runId: "run-1", runStats }),
    step({ step: 3, runId: "run-1", runStats }),
  ];

  const stats = deriveSessionStats(steps);

  assert.equal(stats.turns, 1);
  assert.equal(stats.steps, 3);
  assert.equal(stats.inputTokens, 100);
  assert.equal(stats.outputTokens, 50);
  assert.equal(stats.cacheReadTokens, 40);
  assert.equal(stats.llmMs, 3200);
  assert.equal(stats.ttftSteps, 1);
  assert.equal(stats.ttftMsTotal, 800);
});

test("deriveSessionStats aggregates multiple runs", () => {
  const steps = [
    step({ step: 1, runId: "run-a", runStats: { inputTokens: 200, outputTokens: 60, cacheReadInputTokens: 150, elapsedSeconds: 2, ttftMs: 500 } }),
    step({ step: 2, runId: "run-b", runStats: { inputTokens: 300, outputTokens: 90, cacheReadInputTokens: 100, elapsedSeconds: 4, ttftMs: 1100 } }),
  ];

  const stats = deriveSessionStats(steps);

  assert.equal(stats.turns, 2);
  assert.equal(stats.inputTokens, 500);
  assert.equal(stats.outputTokens, 150);
  assert.equal(stats.cacheReadTokens, 250);
  assert.equal(stats.llmMs, 6000);
  assert.equal(stats.ttftSteps, 2);
  assert.equal(stats.ttftMsTotal, 1600);
});

test("deriveSessionStats sums only settled tool call durations", () => {
  const steps = [
    step({
      runId: "run-a",
      toolCalls: [
        { id: "t1", name: "read", params: {}, status: "done", elapsedMs: 1200 },
        { id: "t2", name: "write", params: {}, status: "failed", elapsedMs: 800 },
        { id: "t3", name: "bash", params: {}, status: "running", elapsedMs: 900 },
      ],
    }),
  ];

  assert.equal(deriveSessionStats(steps).toolMs, 2000);
});

test("formatTokens uses compact K/M notation", () => {
  assert.equal(formatTokens(0), "0");
  assert.equal(formatTokens(517), "517");
  assert.equal(formatTokens(12_200), "12.2K");
  assert.equal(formatTokens(100_000), "100K");
  assert.equal(formatTokens(100_001), "0.1M");
  assert.equal(formatTokens(120_000), "0.12M");
  assert.equal(formatTokens(517_000), "0.52M");
  assert.equal(formatTokens(1_200_000), "1.2M");
});

test("formatDuration renders seconds and minutes", () => {
  assert.equal(formatDuration(0.3), "300ms");
  assert.equal(formatDuration(45.2), "45.2s");
  assert.equal(formatDuration(162), "2m42s");
  assert.equal(formatDuration(120), "2m");
});

test("formatTokensPerSecond keeps one decimal below ten", () => {
  assert.equal(formatTokensPerSecond(4.56), "4.6");
  assert.equal(formatTokensPerSecond(45.6), "46");
});

test("formatContextPercent converts ratios to a two-decimal percentage", () => {
  assert.equal(formatContextPercent(.37654), "37.65");
  assert.equal(formatContextPercent(0), "0.00");
  assert.equal(formatContextPercent(1.2), "100.00");
});
