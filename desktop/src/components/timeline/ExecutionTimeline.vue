<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Check, CheckCircle2, ChevronDown, CircleAlert, Copy, ExternalLink, LoaderCircle, Play, RotateCw } from "@lucide/vue";
import ActivityDetails from "./ActivityDetails.vue";
import ActivityPhase from "./ActivityPhase.vue";
import ContextInjectionRow from "./ContextInjectionRow.vue";
import TokenStream from "./TokenStream.vue";
import PermissionBadge from "./PermissionBadge.vue";
import AgentLogo from "./AgentLogo.vue";
import FileChangesBadge from "./FileChangesBadge.vue";
import type { ChangeFile, ContextInjectionEntry, PermissionDecision, PermissionState, PlanItem, RunStats, TimelineEvent, TimelineStep, ToolCallEntry } from "./types";
import { formatTokens } from "../../utils/sessionStats";

const props = defineProps<{ steps: TimelineStep[]; workspaceId?: string; workspacePath?: string }>();
const emit = defineEmits<{
  retry: [runId: string, userMessage: string];
  continue: [runId?: string];
  decide: [toolUseId: string, decision: PermissionDecision];
  openFile: [path: string];
  openChanges: [runId: string];
  reverted: [runId: string];
  review: [ctx: { workspaceId: string; runId: string; paths: string[] }];
}>();
// 共享空数组：v-memo 依赖要求引用稳定，避免无注入时每次重算都触发全列表更新
const EMPTY_CONTEXT: ContextInjectionEntry[] = [];

type TurnState = "running" | "waiting" | "failed" | "interrupted" | "done";
type TurnView = {
  key: string | number;
  runId?: string;
  changePaths: string[];
  changeFiles: ChangeFile[];
  userMessage?: string;
  userMessageTime?: string;
  model?: string;
  runStats?: RunStats;
  runStartedAt?: string;
  hasContent: boolean;
  hasActivity: boolean;
  pending?: PermissionState;
  text: string;
  summaryText: string;
  thinkingText: string;
  allToolCalls: ToolCallEntry[];
  completedCalls: ToolCallEntry[];
  liveToolCall?: ToolCallEntry;
  aggregatedStep: TimelineStep;
  steps: TimelineStep[];
  events: Array<TimelineEvent & { tool?: ToolCallEntry }>;
  contextInjections: ContextInjectionEntry[];
  state: TurnState;
  failureReason?: string;
  passedTests: number;
  failedTests: number;
  completedPlan: number;
  planTotal: number;
};

const now = ref(Date.now());
const expandedTurns = ref(new Set<string | number>());
const copiedTurn = ref<string | number | null>(null);
const retryingTurn = ref<string | number | null>(null);
let copyTimer: number | undefined;
let clockTimer: number | undefined;
// 秒表按需启停：仅在有运行/等待中的轮次时走 1s 定时器，空闲时停止以减少无意义重渲染
function startClock() {
  if (clockTimer !== undefined) return;
  now.value = Date.now();
  clockTimer = window.setInterval(() => { now.value = Date.now(); }, 1000);
}
function stopClock() {
  window.clearInterval(clockTimer);
  clockTimer = undefined;
}
onBeforeUnmount(() => { stopClock(); window.clearTimeout(copyTimer); window.clearTimeout(retryTimer); });

function thinkingTextOf(steps: TimelineStep[]): string {
  return [...new Set(steps.map((step) => step.thinking?.trim()).filter(Boolean))].join("\n\n");
}

function toolCallsOf(steps: TimelineStep[]): ToolCallEntry[] {
  return [...new Map(steps.flatMap((step) => step.toolCalls).map((call) => [call.id, call])).values()];
}

function latestPlanOf(steps: TimelineStep[]): PlanItem[] {
  return [...steps].reverse().find((step) => step.plan?.length)?.plan ?? [];
}

function aggregateStep(steps: TimelineStep[]): TimelineStep {
  return {
    step: steps[0]?.step ?? 0,
    status: steps.some((step) => step.status === "failed") ? "failed" : "done",
    tokens: [],
    toolCalls: [],
    thinking: "",
    plan: latestPlanOf(steps),
    tests: steps.flatMap((step) => step.tests ?? []),
    changes: steps.flatMap((step) => step.changes ?? []),
    subagents: steps.flatMap((step) => step.subagents ?? []),
    skills: steps.flatMap((step) => step.skills ?? []),
    logs: steps.flatMap((step) => step.logs ?? []),
    contextInjections: steps.flatMap((step) => step.contextInjections ?? []),
    workflowTasks: [...steps].reverse().find((step) => step.workflowTasks?.length)?.workflowTasks ?? [],
    workflowHandoffs: steps.flatMap((step) => step.workflowHandoffs ?? []),
    workflowReviews: steps.flatMap((step) => step.workflowReviews ?? []),
    workflowOutcome: [...steps].reverse().find((step) => step.workflowOutcome)?.workflowOutcome,
  };
}

function hasAssistantContent(step: TimelineStep): boolean {
  return Boolean(
    step.finalText || step.streamText || step.tokens.length || step.thinking || step.toolCalls.length ||
    step.plan?.length || step.tests?.length || step.changes?.length ||
    step.logs?.length || step.subagents?.length || step.skills?.length ||
    step.runStartedAt || step.runStats || step.workflowTasks?.length ||
    step.workflowHandoffs?.length || step.workflowReviews?.length,
  );
}

// 将 ISO 时间戳格式化为可读的本地时间，空值返回空串
function formatTime(iso?: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`;
}

function formatTokensPerSecond(tokensPerSecond: number): string {
  return tokensPerSecond < 10 ? tokensPerSecond.toFixed(1) : String(Math.round(tokensPerSecond));
}

// 每轮时序指标（借鉴 dsh 8.6 turn-tail）：首 token 延迟 + 吞吐；
// 吞吐 = Σ输出 token / decode 墙钟（LLM 用时扣除首 token 前的等待，只计双有步）
function turnTailMetrics(turn: TurnView): { ttft?: string; throughput?: string } | null {
  const stats = turn.runStats;
  if (!stats) return null;
  const out: { ttft?: string; throughput?: string } = {};
  if (stats.ttftMs !== undefined) out.ttft = formatDuration(stats.ttftMs / 1000);
  if (stats.outputTokens > 0 && stats.elapsedSeconds > 0) {
    const decodeSeconds = Math.max(0.001, stats.elapsedSeconds - (stats.ttftMs ?? 0) / 1000);
    out.throughput = `${formatTokensPerSecond(stats.outputTokens / decodeSeconds)} tok/s`;
  }
  return out.ttft || out.throughput ? out : null;
}

function elapsedLabel(turn: TurnView): string {
  const startedAt = turn.runStartedAt ? new Date(turn.runStartedAt).getTime() : Number.NaN;
  const elapsed = turn.state === "running" || turn.state === "waiting"
    ? (Number.isNaN(startedAt) ? turn.runStats?.elapsedSeconds ?? 0 : Math.max(0, (now.value - startedAt) / 1000))
    : turn.runStats?.elapsedSeconds ?? 0;
  return `耗时 ${formatDuration(elapsed)}`;
}

function isTurnExpanded(turn: TurnView): boolean {
  // Full work history is intentionally available only after the run is over.
  // During execution the conversation stays compact and shows one call summary.
  return turn.state !== "running" && turn.state !== "waiting" && expandedTurns.value.has(turn.key);
}

function isTurnRunning(turn: TurnView): boolean {
  return turn.state === "running" || turn.state === "waiting";
}

function liveToolCallOf(calls: ToolCallEntry[]): ToolCallEntry | undefined {
  return [...calls].reverse().find((call) => call.status === "running" || call.status === "awaiting_permission");
}

function completedToolCalls(calls: ToolCallEntry[]): ToolCallEntry[] {
  return calls.filter((call) => call.status === "done" || call.status === "failed");
}

function toggleTurn(turn: TurnView) {
  const next = new Set(expandedTurns.value);
  if (next.has(turn.key)) next.delete(turn.key);
  else next.add(turn.key);
  expandedTurns.value = next;
}

async function copyTurnSummary(turn: TurnView) {
  await navigator.clipboard.writeText(turn.text || turn.summaryText);
  copiedTurn.value = turn.key;
  window.clearTimeout(copyTimer);
  copyTimer = window.setTimeout(() => { copiedTurn.value = null; }, 1600);
}

let retryTimer: number | undefined;

function retryTurn(turn: TurnView) {
  if (!turn.runId || !turn.userMessage) return;
  retryingTurn.value = turn.key;
  emit("retry", turn.runId, turn.userMessage);
  // 兜底复位：父级重试失败时已弹错误提示，这里避免按钮永久停留在转圈态
  window.clearTimeout(retryTimer);
  retryTimer = window.setTimeout(() => { retryingTurn.value = null; }, 20_000);
}

function stepText(step: TimelineStep): string {
  return step.finalText || step.streamText || step.tokens.join("");
}

function stepHasDetails(step: TimelineStep): boolean {
  return Boolean(
    stepText(step) || step.thinking || step.toolCalls.length || step.plan?.length ||
    step.tests?.length || step.changes?.length || step.logs?.length ||
    step.subagents?.length || step.skills?.length || step.workflowTasks?.length ||
    step.workflowHandoffs?.length || step.workflowReviews?.length,
  );
}

function orderedEvents(steps: TimelineStep[]): Array<TimelineEvent & { tool?: ToolCallEntry }> {
  const calls = new Map(toolCallsOf(steps).map((call) => [call.id, call]));
  const events = steps.flatMap((step) => {
    if (step.events?.length) return step.events;
    const fallback: TimelineEvent[] = [];
    if (step.thinking) fallback.push({ id: `thinking-fallback-${step.step}`, kind: "thinking", text: step.thinking });
    const text = stepText(step);
    if (text) fallback.push({ id: `text-fallback-${step.step}`, kind: "text", text });
    for (const call of step.toolCalls) fallback.push({ id: `tool-fallback-${call.id}`, kind: "tool", toolCallId: call.id });
    return fallback;
  });
  return events.map((event) => ({ ...event, tool: event.toolCallId ? calls.get(event.toolCallId) : undefined }));
}

function isFirstToolEvent(turn: TurnView, event: TimelineEvent): boolean {
  return turn.events.find((item) => item.kind === "tool" && item.tool)?.id === event.id;
}

type InlineSegment =
  | { type: "text"; text: string; isFinal?: boolean }
  | { type: "activity"; thinking: string; calls: ToolCallEntry[]; isRunning: boolean; stepIndex?: number; stepTitle?: string };

function inlineSegments(turn: TurnView): InlineSegment[] {
  const segments: InlineSegment[] = [];
  const isRunning = turn.state === "running" || turn.state === "waiting";
  const visibleCalls = new Map<string, ToolCallEntry>();
  for (const c of turn.completedCalls) visibleCalls.set(c.id, c);
  if (turn.liveToolCall) visibleCalls.set(turn.liveToolCall.id, turn.liveToolCall);

  // 将连续的思考+工具调用合并为一个activity块，只在遇到文本时分割
  let pendingCalls: ToolCallEntry[] = [];
  let pendingThinking = "";
  let pendingText = "";
  let activityIndex = 0;

  // 获取计划项，按顺序分配给activity块
  const planItems = turn.aggregatedStep.plan ?? [];

  const flushActivity = () => {
    if (pendingThinking.trim() || pendingCalls.length) {
      // 尝试匹配对应的plan项
      const matchedPlan = planItems[activityIndex];
      segments.push({
        type: "activity",
        thinking: pendingThinking.trim(),
        calls: [...pendingCalls],
        isRunning,
        stepIndex: planItems.length > 0 ? activityIndex + 1 : undefined,
        stepTitle: matchedPlan?.subject,
      });
      activityIndex++;
      pendingCalls = [];
      pendingThinking = "";
    }
  };
  const flushText = () => {
    if (pendingText.trim()) {
      segments.push({ type: "text", text: pendingText.trim() });
      pendingText = "";
    }
  };

  for (const event of turn.events) {
    if (event.kind === "thinking") {
      flushText();
      if (event.text) pendingThinking += (pendingThinking ? "\n\n" : "") + event.text;
    } else if (event.kind === "text") {
      flushActivity();
      if (event.text) pendingText += (pendingText ? "\n\n" : "") + event.text;
    } else if (event.kind === "tool" && event.tool && visibleCalls.has(event.tool.id)) {
      flushText();
      pendingCalls.push(event.tool);
      visibleCalls.delete(event.tool.id);
    }
  }
  // 追加剩余未在events中出现的调用（通常是liveToolCall）
  for (const c of visibleCalls.values()) pendingCalls.push(c);

  flushText();
  flushActivity();

  return segments;
}

// 计划进度：计算完成进度
function getPlanProgress(turn: TurnView) {
  const plan = turn.aggregatedStep.plan ?? [];
  if (plan.length === 0) return null;
  const completed = plan.filter(p => p.status === "completed").length;
  const inProgress = plan.some(p => p.status === "in_progress");
  return { total: plan.length, completed, inProgress, percent: Math.round((completed / plan.length) * 100) };
}

// 判断是否应该显示"正在规划下一步"（运行中且当前没有文本输出、没有活跃工具调用时）
function shouldShowPlanningHint(turn: TurnView): boolean {
  if (turn.state !== "running" && turn.state !== "waiting") return false;
  // 有 liveToolCall 说明正在执行工具，显示"正在执行..."由工具摘要行自己处理
  if (turn.liveToolCall) return false;
  // 如果最后一个segment是文本且有streaming内容，说明LLM正在输出文字，不显示规划提示
  const segs = inlineSegments(turn);
  const lastSeg = segs[segs.length - 1];
  if (lastSeg?.type === "text") return false;
  return true;
}

function latestTextOf(events: Array<TimelineEvent & { tool?: ToolCallEntry }>, steps: TimelineStep[]): string {
  return [...events].reverse().find((event) => event.kind === "text" && event.text?.trim())?.text?.trim()
    ?? [...steps].reverse().map(stepText).find(Boolean)
    ?? "";
}

function stateOf(steps: TimelineStep[], pending: PermissionState | undefined, calls: ToolCallEntry[]) {
  if (pending) return { state: "waiting" as const };
  const interruptedOutcome = [...steps].reverse().find((step) => step.outcome?.status === "interrupted")?.outcome;
  if (interruptedOutcome) return { state: "interrupted" as const, reason: interruptedOutcome.reason };
  const failedOutcome = [...steps].reverse().find((step) => step.outcome?.status === "failed")?.outcome;
  if (failedOutcome) return { state: "failed" as const, reason: failedOutcome.reason };
  const runningCall = [...calls].reverse().find((call) => call.status === "running" || call.status === "awaiting_permission");
  if (runningCall) return { state: "running" as const };
  const last = steps[steps.length - 1];
  if (last && last.status !== "done") return { state: "running" as const };
  return { state: "done" as const };
}

const turns = computed<TurnView[]>(() => {
  const groups: { userMessage?: string; userMessageTime?: string; steps: TimelineStep[] }[] = [];
  for (const item of props.steps) {
    if (item.userMessage) {
      const group = { userMessage: item.userMessage, userMessageTime: item.userMessageTime, steps: [] as TimelineStep[] };
      groups.push(group);
      if (hasAssistantContent(item)) group.steps.push(item);
    } else {
      if (!groups.length) groups.push({ steps: [] });
      groups[groups.length - 1].steps.push(item);
    }
  }
  return groups.map((group, index) => {
    const steps = group.steps;
    const model = steps.find((step) => step.usage?.model)?.usage?.model ?? "";
    const runStats = [...steps].reverse().find((step) => step.runStats)?.runStats;
    const runStartedAt = steps.find((step) => step.runStartedAt)?.runStartedAt ?? group.userMessageTime;
    const text = steps.map((step) => step.finalText || step.streamText || step.tokens.join("")).filter(Boolean).join("\n\n");
    const allToolCalls = toolCallsOf(steps);
    const completedCalls = completedToolCalls(allToolCalls);
    const liveToolCall = liveToolCallOf(allToolCalls);
    const thinkingText = thinkingTextOf(steps);
    const aggregatedStep = aggregateStep(steps);
    const events = orderedEvents(steps);
    const summaryText = latestTextOf(events, steps);
    const pending = steps.find((step) => step.permission?.status === "pending")?.permission;
    const status = stateOf(steps, pending, allToolCalls);
    const tests = aggregatedStep.tests ?? [];
    const plan = aggregatedStep.plan ?? [];
    const changePaths = [...new Set(aggregatedStep.changes?.flatMap((entry) => entry.paths) ?? [])];
    // 优先使用files字段（带additions/deletions统计），否则从paths构建
    const changeFiles: ChangeFile[] = aggregatedStep.changes?.length
      ? (() => {
          const allFiles = aggregatedStep.changes!.flatMap((entry) => entry.files ?? entry.paths.map((p) => ({ path: p })));
          const map = new Map<string, ChangeFile>();
          for (const f of allFiles) {
            const existing = map.get(f.path);
            if (existing) {
              existing.additions = (existing.additions ?? 0) + (f.additions ?? 0);
              existing.deletions = (existing.deletions ?? 0) + (f.deletions ?? 0);
            } else {
              map.set(f.path, { ...f });
            }
          }
          return [...map.values()];
        })()
      : changePaths.map((p) => ({ path: p }));
    const hasActivity = Boolean(
      allToolCalls.length || thinkingText || plan.length || aggregatedStep.subagents?.length ||
      aggregatedStep.skills?.length || aggregatedStep.logs?.length ||
      aggregatedStep.workflowTasks?.length || aggregatedStep.workflowHandoffs?.length ||
      aggregatedStep.workflowReviews?.length,
    );
    return {
      key: steps.find((step) => step.runId)?.runId ?? `turn-${index}`,
      runId: steps.find((step) => step.runId)?.runId,
      changePaths,
      changeFiles,
      userMessage: group.userMessage,
      userMessageTime: group.userMessageTime,
      model,
      runStats,
      runStartedAt,
      hasActivity,
      pending,
      text,
      summaryText,
      thinkingText,
      allToolCalls,
      completedCalls,
      liveToolCall,
      aggregatedStep,
      steps,
      events,
      contextInjections: aggregatedStep.contextInjections?.filter((entry) => entry.source !== "canvas") ?? EMPTY_CONTEXT,
      state: status.state,
      failureReason: status.reason,
      passedTests: tests.filter((test) => test.status === "passed").length,
      failedTests: tests.filter((test) => test.status === "failed").length,
      completedPlan: plan.filter((item) => item.status === "completed").length,
      planTotal: plan.length,
      hasContent: Boolean(text || hasActivity || pending || steps.length),
    };
  });
});

// 存在运行/等待中的轮次时启动秒表，全部结束后停止
watch(
  () => turns.value.some((turn) => turn.state === "running" || turn.state === "waiting"),
  (active) => { if (active) startClock(); else stopClock(); },
  { immediate: true },
);

// 重试生效（该轮重新进入运行/等待态）后立即结束按钮 loading
watch(
  () => turns.value.find((turn) => turn.key === retryingTurn.value)?.state,
  (state) => {
    if (state === "running" || state === "waiting") {
      window.clearTimeout(retryTimer);
      retryingTurn.value = null;
    }
  },
);
</script>

<template>
  <!-- 不使用 aria-live：流式输出期间每个 token 批次都会触发读屏通告，造成噪音 -->
  <section class="execution-timeline">
    <article
      v-for="turn in turns"
      :key="turn.key"
      v-memo="[turn.key, turn.state, turn.summaryText, turn.thinkingText, turn.runStats, turn.pending, turn.hasContent, turn.contextInjections, turn.liveToolCall, turn.completedCalls.length, isTurnExpanded(turn), copiedTurn, retryingTurn, turn.state === 'running' ? now : null]"
      class="timeline-step"
    >
      <div v-if="turn.userMessage" class="timeline-user-message">
        {{ turn.userMessage }}
        <span v-if="turn.model || turn.userMessageTime" class="timeline-user-message__meta">{{ turn.model || "未记录模型" }} · {{ formatTime(turn.userMessageTime) }}</span>
      </div>
      <div v-if="turn.hasContent" class="timeline-assistant">
        <AgentLogo :active="turn.state === 'running' || turn.state === 'waiting'" />
        <div class="timeline-step__content">
          <!-- 上下文注入行：压缩/干预/系统注入；任务进度画布不进入会话区。 -->
          <ContextInjectionRow v-for="entry in turn.contextInjections" :key="entry.id" :entry="entry" />
          <button
            v-if="(turn.hasActivity || turn.runStats) && turn.state !== 'running' && turn.state !== 'waiting'"
            type="button"
            class="turn-history-toggle"
            :class="{ expanded: isTurnExpanded(turn), 'turn-history-toggle--failed': turn.state === 'failed' || turn.state === 'interrupted' }"
            :aria-expanded="isTurnExpanded(turn)"
            @click="toggleTurn(turn)"
          >
            <!-- 失败/中断的轮次在折叠态给出可见标记，避免用户不展开就发现不了异常 -->
            <em v-if="turn.state === 'failed'" class="turn-state-chip"><CircleAlert :size="13" :stroke-width="1.9" />失败</em>
            <em v-else-if="turn.state === 'interrupted'" class="turn-state-chip"><CircleAlert :size="13" :stroke-width="1.9" />已中断</em>
            <span>{{ isTurnExpanded(turn) ? '收起过程' : `查看过程 · ${elapsedLabel(turn)}` }}</span>
            <ChevronDown :size="15" />
          </button>

          <!-- 折叠态（已完成且未展开）：只展示最终输出文字 -->
          <div v-if="!isTurnRunning(turn) && !isTurnExpanded(turn)" class="turn-event-stream turn-event-stream--collapsed">
            <div v-if="turn.text || turn.summaryText" class="turn-inline-text">
              <TokenStream :tokens="[]" :final-text="turn.text || turn.summaryText" />
            </div>
          </div>

          <!-- 展开态 / 运行中：事件流内联渲染，活动过程(思考+工具)折叠为单一摘要行，文本直接展示 -->
          <div v-else class="turn-event-stream">
            <!-- 长程任务进度条：有plan时显示 -->
            <div v-if="getPlanProgress(turn)" class="task-progress-bar">
              <div class="task-progress-bar__track">
                <div
                  class="task-progress-bar__fill"
                  :class="{ 'task-progress-bar__fill--active': getPlanProgress(turn)?.inProgress }"
                  :style="{ width: getPlanProgress(turn)?.percent + '%' }"
                />
              </div>
              <span class="task-progress-bar__label">
                <template v-if="turn.state === 'running' || turn.state === 'waiting'">
                  <LoaderCircle class="spin" :size="11" />
                  步骤 {{ Math.min((getPlanProgress(turn)?.completed ?? 0) + 1, getPlanProgress(turn)?.total ?? 1) }} / {{ getPlanProgress(turn)?.total }}
                </template>
                <template v-else>
                  <Check :size="11" />
                  完成 {{ getPlanProgress(turn)?.completed }} / {{ getPlanProgress(turn)?.total }} 个步骤
                </template>
              </span>
            </div>

            <template v-for="(segment, segIdx) in inlineSegments(turn)" :key="segIdx">
              <!-- 活动块：思考+工具调用合并为一个可折叠行，默认只显示一行摘要 -->
              <ActivityPhase
                v-if="segment.type === 'activity'"
                :thinking="segment.thinking"
                :calls="segment.calls"
                :running="segment.isRunning && (turn.state === 'running' || turn.state === 'waiting')"
                :completed="turn.state === 'done' || turn.state === 'failed' || turn.state === 'interrupted'"
                :step-index="segment.stepIndex"
                :step-title="segment.stepTitle"
              />
              <!-- 文本块：Agent输出的文字内容，始终直接显示 -->
              <div v-else-if="segment.type === 'text'" class="turn-inline-text">
                <TokenStream :tokens="[]" :final-text="segment.text" />
              </div>
            </template>
            <!-- 进行中提示："正在规划下一步" -->
            <div v-if="shouldShowPlanningHint(turn)" class="turn-planning-hint">
              <LoaderCircle class="spin" :size="14" />
              <span>正在规划下一步</span>
            </div>
          </div>

          <!-- 文字下方操作栏：复制 + 重试，hover/focus 时显现 -->
          <div v-if="turn.text || turn.summaryText || (turn.runId && turn.userMessage && turn.state !== 'running' && turn.state !== 'waiting')" class="turn-actions" :class="{ 'turn-actions--busy': retryingTurn === turn.key }">
            <button
              v-if="turn.text || turn.summaryText"
              type="button"
              class="turn-action-btn"
              :title="copiedTurn === turn.key ? '已复制' : '复制整段总结'"
              :aria-label="copiedTurn === turn.key ? '已复制总结' : '复制整段总结'"
              @click="copyTurnSummary(turn)"
            >
              <Check v-if="copiedTurn === turn.key" :size="14" :stroke-width="1.8" />
              <Copy v-else :size="14" :stroke-width="1.8" />
            </button>
            <button
              v-if="turn.runId && turn.userMessage && turn.state !== 'running' && turn.state !== 'waiting'"
              type="button"
              class="turn-action-btn"
              title="回退本次修改并重新执行"
              aria-label="回退本次修改并重新执行"
              :disabled="retryingTurn === turn.key"
              @click="retryTurn(turn)"
            >
              <LoaderCircle v-if="retryingTurn === turn.key" class="spin" :size="14" :stroke-width="1.8" />
              <RotateCw v-else :size="14" :stroke-width="1.8" />
            </button>
          </div>

          <PermissionBadge v-if="turn.pending" :permission="turn.pending" @decide="$emit('decide', turn.pending?.toolUseId ?? '', $event)" />

          <!-- 每轮 Token 消耗与缓存命中：展开历史时展示，运行中轮次不渲染 -->
          <div v-if="turn.runStats && isTurnExpanded(turn)" class="turn-usage" aria-label="本轮 Token 消耗与缓存命中">
            <span><small>缓存</small>{{ formatTokens(turn.runStats.cacheReadInputTokens) }}</span>
            <i />
            <span><small>输入</small>{{ formatTokens(turn.runStats.inputTokens) }}</span>
            <i />
            <span><small>输出</small>{{ formatTokens(turn.runStats.outputTokens) }}</span>
            <strong>{{ formatTokens(turn.runStats.inputTokens + turn.runStats.outputTokens) }} tokens</strong>
          </div>

          <section v-if="isTurnExpanded(turn) && (turn.passedTests || turn.failedTests || turn.changeFiles.length || (turn.state === 'failed' && turn.failureReason))" class="evidence-strip" aria-label="验证与变更">
            <div v-if="turn.passedTests" class="evidence-item passed"><CheckCircle2 :size="14" /><span><b>{{ turn.passedTests }}</b> 项验证通过</span></div>
            <div v-if="turn.failedTests" class="evidence-item failed"><CircleAlert :size="14" /><span><b>{{ turn.failedTests }}</b> 项验证失败</span></div>
            <FileChangesBadge
              v-if="turn.changeFiles.length"
              :files="turn.changeFiles"
              :workspace-path="workspacePath ?? ''"
              @open-file="(path) => emit('openFile', path)"
              @open-all="turn.runId && emit('openChanges', turn.runId)"
            />
            <div v-if="turn.state === 'failed' && turn.failureReason" class="evidence-item failed"><CircleAlert :size="14" /><span>{{ turn.failureReason }}</span></div>
          </section>

          <button v-if="isTurnExpanded(turn) && turn.state === 'interrupted'" class="continue-button" type="button" title="从中断处继续执行" @click="$emit('continue', turn.runId)">
            <Play :size="14" />继续执行
          </button>

          <!-- turn 页脚时序指标（借鉴 dsh 8.6 turn-tail）：每轮首字延迟与吞吐，无读数不渲染 -->
          <div v-if="isTurnExpanded(turn) && turnTailMetrics(turn)" class="turn-tail-metrics" aria-label="本轮时序指标">
            <span v-if="turnTailMetrics(turn)?.ttft"><b>首字</b> {{ turnTailMetrics(turn)?.ttft }}</span>
            <span v-if="turnTailMetrics(turn)?.throughput"><b>吞吐</b> {{ turnTailMetrics(turn)?.throughput }}</span>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>
