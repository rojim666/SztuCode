<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Check, CheckCircle2, ChevronDown, CircleAlert, Copy, FileDiff, LoaderCircle, Play, TerminalSquare } from "@lucide/vue";
import ActivityDetails from "./ActivityDetails.vue";
import ContextInjectionRow from "./ContextInjectionRow.vue";
import ThinkingPanel from "./ThinkingPanel.vue";
import TokenStream from "./TokenStream.vue";
import ToolCallCard from "./ToolCallCard.vue";
import ToolCallGroup from "./ToolCallGroup.vue";
import PermissionBadge from "./PermissionBadge.vue";
import type { ContextInjectionEntry, PermissionDecision, PermissionState, PlanItem, RunStats, TimelineEvent, TimelineStep, ToolCallEntry } from "./types";
import { formatTokens } from "../../utils/sessionStats";

const props = defineProps<{ steps: TimelineStep[]; workspaceId?: string }>();
// 共享空数组：v-memo 依赖要求引用稳定，避免无注入时每次重算都触发全列表更新
const EMPTY_CONTEXT: ContextInjectionEntry[] = [];
defineEmits<{
  decide: [toolUseId: string, decision: PermissionDecision];
  reverted: [runId: string];
  review: [ctx: { workspaceId: string; runId: string; paths: string[] }];
  continue: [runId?: string];
}>();

type TurnState = "running" | "waiting" | "verified" | "unverified" | "failed" | "interrupted";
type TurnView = {
  key: string | number;
  runId?: string;
  changePaths: string[];
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
  aggregatedStep: TimelineStep;
  steps: TimelineStep[];
  events: Array<TimelineEvent & { tool?: ToolCallEntry }>;
  contextInjections: ContextInjectionEntry[];
  state: TurnState;
  stateLabel: string;
  failureReason?: string;
  passedTests: number;
  failedTests: number;
  completedPlan: number;
  planTotal: number;
};

const now = ref(Date.now());
const expandedTurns = ref(new Set<string | number>());
const copiedTurn = ref<string | number | null>(null);
let copyTimer: number | undefined;
let clockTimer: number | undefined;
onMounted(() => { clockTimer = window.setInterval(() => { now.value = Date.now(); }, 1000); });
onBeforeUnmount(() => { window.clearInterval(clockTimer); window.clearTimeout(copyTimer); });

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

function actionLabel(call: ToolCallEntry): string {
  const name = call.name.toLowerCase();
  if (/read|list_dir/.test(name)) return "正在阅读项目文件";
  if (/grep|glob|search/.test(name)) return "正在项目中定位代码";
  if (/edit|write/.test(name)) return "正在修改工作区文件";
  if (/bash|shell|test/.test(name)) return "正在运行命令并验证结果";
  if (/task|subagent/.test(name)) return "正在协调子任务";
  return "正在执行项目操作";
}

function failureLabel(reason?: string): string {
  if (!reason) return "执行失败，详情见工作记录";
  if (reason === "cancelled") return "任务已取消";
  if (reason === "llm_error") return "模型调用失败";
  if (reason === "permission_denied") return "操作被权限策略拦截";
  return `执行失败：${reason}`;
}

// 中断（预算/上限耗尽）状态文案：区别于失败，明确告知可续跑
function interruptedLabel(reason?: string): string {
  if (reason === "max_tokens_exceeded") return "Token 预算用尽，可继续";
  if (reason === "max_wall_clock_exceeded") return "墙钟预算用尽，可继续";
  return "步数预算用尽，可继续";
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

function liveStatsLabel(turn: TurnView): string {
  const startedAt = turn.runStartedAt ? new Date(turn.runStartedAt).getTime() : Number.NaN;
  const elapsed = turn.state === "running" || turn.state === "waiting"
    ? (Number.isNaN(startedAt) ? turn.runStats?.elapsedSeconds ?? 0 : Math.max(0, (now.value - startedAt) / 1000))
    : turn.runStats?.elapsedSeconds ?? 0;
  const totalTokens = (turn.runStats?.inputTokens ?? 0) + (turn.runStats?.outputTokens ?? 0);
  return `${formatDuration(elapsed)} · ${formatTokens(totalTokens)} tokens`;
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

function liveCallSummary(turn: TurnView): string {
  const failed = turn.allToolCalls.filter((call) => call.status === "failed").length;
  if (failed) return `运行失败 ${failed} 项操作`;
  return `已运行 ${turn.allToolCalls.length} 项操作`;
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

function latestTextOf(events: Array<TimelineEvent & { tool?: ToolCallEntry }>, steps: TimelineStep[]): string {
  return [...events].reverse().find((event) => event.kind === "text" && event.text?.trim())?.text?.trim()
    ?? [...steps].reverse().map(stepText).find(Boolean)
    ?? "";
}

function stateOf(steps: TimelineStep[], pending: PermissionState | undefined, calls: ToolCallEntry[], text: string) {
  if (pending) return { state: "waiting" as const, label: "等待授权" };
  const interruptedOutcome = [...steps].reverse().find((step) => step.outcome?.status === "interrupted")?.outcome;
  if (interruptedOutcome) return { state: "interrupted" as const, label: interruptedLabel(interruptedOutcome.reason), reason: interruptedOutcome.reason };
  const failedOutcome = [...steps].reverse().find((step) => step.outcome?.status === "failed")?.outcome;
  if (failedOutcome) return { state: "failed" as const, label: failureLabel(failedOutcome.reason), reason: failedOutcome.reason };
  const runningCall = [...calls].reverse().find((call) => call.status === "running" || call.status === "awaiting_permission");
  if (runningCall) return { state: "running" as const, label: actionLabel(runningCall) };
  const last = steps[steps.length - 1];
  if (last && last.status !== "done") {
    if (last.status === "observing") return { state: "running" as const, label: "正在检查" };
    if ((last.streamText || last.tokens.length) && !last.finalText) return { state: "running" as const, label: "整理中" };
    return { state: "running" as const, label: calls.length ? "规划中" : "正在思考" };
  }
  const tests = steps.flatMap((step) => step.tests ?? []);
  if (tests.some((test) => test.status === "failed")) return { state: "failed" as const, label: "已完成，待验证" };
  if (text && tests.some((test) => test.status === "passed")) return { state: "verified" as const, label: "已完成并验证" };
  return { state: "unverified" as const, label: text ? "已完成，尚未验证" : "工作记录" };
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
    const thinkingText = thinkingTextOf(steps);
    const aggregatedStep = aggregateStep(steps);
    const events = orderedEvents(steps);
    const summaryText = latestTextOf(events, steps);
    const pending = steps.find((step) => step.permission?.status === "pending")?.permission;
    const status = stateOf(steps, pending, allToolCalls, text);
    const tests = aggregatedStep.tests ?? [];
    const plan = aggregatedStep.plan ?? [];
    const changePaths = [...new Set(aggregatedStep.changes?.flatMap((entry) => entry.paths) ?? [])];
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
      aggregatedStep,
      steps,
      events,
      contextInjections: aggregatedStep.contextInjections?.filter((entry) => entry.source !== "canvas") ?? EMPTY_CONTEXT,
      state: status.state,
      stateLabel: status.label,
      failureReason: status.reason,
      passedTests: tests.filter((test) => test.status === "passed").length,
      failedTests: tests.filter((test) => test.status === "failed").length,
      completedPlan: plan.filter((item) => item.status === "completed").length,
      planTotal: plan.length,
      hasContent: Boolean(text || hasActivity || pending || steps.length),
    };
  });
});
</script>

<template>
  <section class="execution-timeline" aria-live="polite">
    <article
      v-for="turn in turns"
      :key="turn.key"
      v-memo="[turn.key, turn.state, turn.summaryText, turn.thinkingText, turn.runStats, turn.pending, turn.hasContent, turn.contextInjections, isTurnExpanded(turn), copiedTurn, turn.state === 'running' ? now : null]"
      class="timeline-step"
    >
      <div v-if="turn.userMessage" class="timeline-user-message">
        {{ turn.userMessage }}
        <span v-if="turn.model || turn.userMessageTime" class="timeline-user-message__meta">{{ turn.model || "未记录模型" }} · {{ formatTime(turn.userMessageTime) }}</span>
      </div>
      <div v-if="turn.hasContent" class="timeline-assistant">
        <div class="timeline-step__content">
          <!-- 上下文注入行：压缩/干预/系统注入；任务进度画布不进入会话区。 -->
          <ContextInjectionRow v-for="entry in turn.contextInjections" :key="entry.id" :entry="entry" />
          <button
            v-if="turn.hasActivity || turn.runStats"
            type="button"
            class="turn-history-toggle"
            :class="{ expanded: isTurnExpanded(turn) }"
            :aria-expanded="isTurnExpanded(turn)"
            :disabled="turn.state === 'running' || turn.state === 'waiting'"
            @click="toggleTurn(turn)"
          >
            <span>{{ elapsedLabel(turn) }}</span>
            <ChevronDown :size="15" />
          </button>

          <div v-if="turn.state === 'running' || turn.state === 'waiting'" class="turn-status" :class="turn.state">
            <b>{{ turn.stateLabel }}</b>
          </div>

          <div
            v-if="(turn.state === 'running' || turn.state === 'waiting') && turn.allToolCalls.length"
            class="turn-call-summary"
            :class="{ failed: turn.allToolCalls.some((call) => call.status === 'failed') }"
            role="status"
          >
            <TerminalSquare :size="12" />
            <span>{{ liveCallSummary(turn) }}</span>
            <LoaderCircle v-if="turn.state === 'running'" class="spin" :size="12" />
          </div>

          <!-- 折叠态思考行：运行中跟随增量输出；结算后继续保留到历史区展开，
               让一次到达的大块 thinking 也能按顺序播放完，不会在 run.finished 时被直接卸载。 -->
          <ThinkingPanel
            v-if="turn.thinkingText && !isTurnExpanded(turn)"
            :text="turn.thinkingText"
            :completed="turn.state !== 'running'"
          />

          <PermissionBadge v-if="turn.pending" :permission="turn.pending" @decide="$emit('decide', turn.pending?.toolUseId ?? '', $event)" />

          <section v-if="isTurnExpanded(turn)" class="turn-history" aria-label="历史输出与调用">
            <template v-for="event in turn.events" :key="event.id">
              <div v-if="event.kind === 'text' && event.text && event.text !== turn.summaryText" class="turn-history-text"><TokenStream :tokens="[]" :final-text="event.text" /></div>
              <ThinkingPanel v-else-if="event.kind === 'thinking' && event.text" :text="event.text" :completed="turn.state !== 'running'" />
              <div
                v-else-if="event.kind === 'tool' && event.tool && (turn.allToolCalls.length <= 2 || isFirstToolEvent(turn, event))"
                class="turn-history-actions"
              >
                <ToolCallGroup v-if="turn.allToolCalls.length > 2" :calls="turn.allToolCalls" />
                <ToolCallCard v-else :call="event.tool" />
              </div>
            </template>
          </section>

          <section v-if="turn.summaryText" class="turn-result" aria-label="任务结果">
            <TokenStream :tokens="[]" :final-text="turn.summaryText" />
            <button v-if="turn.text || turn.summaryText" type="button" class="turn-copy" :title="copiedTurn === turn.key ? '已复制' : '复制整段总结'" :aria-label="copiedTurn === turn.key ? '已复制总结' : '复制整段总结'" @click="copyTurnSummary(turn)">
              <Check v-if="copiedTurn === turn.key" :size="15" :stroke-width="1.8" />
              <Copy v-else :size="15" :stroke-width="1.8" />
            </button>
          </section>

          <div v-if="isTurnExpanded(turn) && turn.state !== 'running' && turn.state !== 'waiting' && turn.stateLabel !== '工作记录'" class="turn-status turn-status--result" :class="turn.state">
            <b>{{ turn.stateLabel }}</b>
          </div>

          <!-- 每轮 Token 消耗与缓存命中：展开历史时展示，运行中轮次不渲染 -->
          <div v-if="turn.runStats && isTurnExpanded(turn)" class="turn-usage" aria-label="本轮 Token 消耗与缓存命中">
            <span>命中缓存 {{ formatTokens(turn.runStats.cacheReadInputTokens) }}</span>
            <span>输入 {{ formatTokens(turn.runStats.inputTokens) }}</span>
            <span>输出 {{ formatTokens(turn.runStats.outputTokens) }}</span>
            <b>总计 {{ formatTokens(turn.runStats.inputTokens + turn.runStats.outputTokens) }} tokens</b>
          </div>

          <section v-if="isTurnExpanded(turn) && (turn.passedTests || turn.failedTests || turn.changePaths.length || (turn.state === 'failed' && turn.failureReason))" class="evidence-strip" aria-label="验证与变更">
            <div v-if="turn.passedTests" class="evidence-item passed"><CheckCircle2 :size="15" /><span><b>{{ turn.passedTests }}</b> 项验证通过</span></div>
            <div v-if="turn.failedTests" class="evidence-item failed"><CircleAlert :size="15" /><span><b>{{ turn.failedTests }}</b> 项验证失败</span></div>
            <div v-if="turn.changePaths.length" class="evidence-item changed"><FileDiff :size="15" /><span><b>{{ turn.changePaths.length }}</b> 个文件有变更</span></div>
            <div v-if="turn.state === 'failed' && turn.failureReason" class="evidence-item failed"><CircleAlert :size="15" /><span>{{ turn.failureReason }}</span></div>
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
