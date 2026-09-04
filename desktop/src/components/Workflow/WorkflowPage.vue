<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import type { WorkflowGraph, WorkflowTaskStatus } from "../../protocol";
import WorkflowGraphCanvas from "./WorkflowGraph.vue";
import { statusMeta } from "./status";
import { onRuntimeEvent, runWorkflow } from "../../services/sztu-runtime";

const props = defineProps<{ connected: boolean }>();

const sampleGraph: WorkflowGraph = {
  workflow_id: "demo-workflow-vis",
  goal: "为 SztuCode 桌面端增加节点式 workflow 可视化原型",
  planner_summary: "按 规划 → 并行编码 → 测试 → 评审 四层拆分；编码任务按包边界并行，测试聚合各编码结果，评审收口。",
  tasks: [
    {
      id: "plan", title: "规划与任务拆分", description: "分析需求，定义任务边界、依赖关系与验收标准。",
      owner: "planner", dependencies: [], completion_criteria: ["任务列表覆盖全部需求", "依赖图无环", "每个任务有明确验收标准"],
      allowed_paths: [], depth: 0, token_budget: 12_000, time_budget_s: 600, max_retries: 1,
    },
    {
      id: "protocol", title: "扩展协议类型", description: "在 packages/protocol 补充节点布局所需类型。",
      owner: "coder", dependencies: ["plan"], completion_criteria: ["类型通过 tsc 检查"],
      allowed_paths: ["packages/protocol"], depth: 1, token_budget: 8_000, time_budget_s: 600, max_retries: 1,
    },
    {
      id: "graph-ui", title: "节点画布组件", description: "实现 DAG 分层布局、SVG 连线与平移缩放画布。",
      owner: "coder", dependencies: ["plan"], completion_criteria: ["桌面端可渲染示例图", "支持滚轮缩放与拖拽平移"],
      allowed_paths: ["desktop/src/components/Workflow"], depth: 1, token_budget: 16_000, time_budget_s: 1_200, max_retries: 2,
    },
    {
      id: "page-embed", title: "接入工作流页面", description: "新增侧边栏入口与页面容器。",
      owner: "coder", dependencies: ["graph-ui"], completion_criteria: ["可从侧边栏打开页面"],
      allowed_paths: ["desktop/src"], depth: 2, token_budget: 8_000, time_budget_s: 600, max_retries: 1,
    },
    {
      id: "runtime-wire", title: "接入守护进程事件", description: "订阅 workflow.* 事件流并驱动画布状态。",
      owner: "coder", dependencies: ["protocol", "graph-ui"], completion_criteria: ["workflow.task_updated 能更新节点状态"],
      allowed_paths: ["desktop/src/services"], depth: 2, token_budget: 10_000, time_budget_s: 900, max_retries: 1,
    },
    {
      id: "e2e", title: "端到端验证", description: "验证模拟运行与真实运行两条路径。",
      owner: "tester", dependencies: ["page-embed", "runtime-wire"], completion_criteria: ["两条路径均通过验证"],
      allowed_paths: ["desktop/tests"], depth: 3, token_budget: 10_000, time_budget_s: 1_200, max_retries: 2,
    },
    {
      id: "review", title: "最终评审", description: "对照完成标准评审全部改动并给出结论。",
      owner: "reviewer", dependencies: ["e2e"], completion_criteria: ["评审结论为接受"],
      allowed_paths: [], depth: 4, token_budget: 8_000, time_budget_s: 600, max_retries: 1,
    },
  ],
};

const graph = ref<WorkflowGraph>(sampleGraph);
const statuses = ref<Record<string, WorkflowTaskStatus>>(Object.fromEntries(sampleGraph.tasks.map((t) => [t.id, "pending"])));
const attempts = ref<Record<string, number>>({});
const errors = ref<Record<string, string>>({});
const selectedId = ref<string | null>(null);
const fitKey = ref(0);

type Mode = "idle" | "demo" | "live";
const mode = ref<Mode>("idle");
const overall = ref<"idle" | "running" | WorkflowTaskStatus>("idle");
const runId = ref("");
const realRunning = ref(false);
const liveError = ref("");
const elapsedS = ref(0);

const STATUS_ORDER: WorkflowTaskStatus[] = ["pending", "running", "succeeded", "failed", "blocked", "cancelled", "timed_out", "rejected"];

const runningNow = computed(() => sampleGraph.tasks.filter((t) => statuses.value[t.id] === "running").length);
const doneCount = computed(() => sampleGraph.tasks.filter((t) => ["succeeded", "failed", "blocked", "cancelled", "timed_out", "rejected"].includes(statuses.value[t.id])).length);

const overallLabel = computed(() => {
  if (overall.value === "idle") return "未运行";
  if (overall.value === "running") return "运行中";
  return statusMeta(overall.value).label;
});
const overallColor = computed(() => (overall.value === "idle" ? "#8b8fa3" : statusMeta(overall.value).color));

const modeLabel = computed(() => (mode.value === "demo" ? "模拟" : mode.value === "live" ? "真实运行" : "未运行"));

// ---------- 模拟运行 ----------
let demoTimers: number[] = [];
let demoTick = 0;
function clearDemoTimers() {
  demoTimers.forEach((t) => window.clearTimeout(t));
  demoTimers = [];
  window.clearInterval(demoTick);
  demoTick = 0;
}
function schedule(fn: () => void, ms: number) {
  demoTimers.push(window.setTimeout(fn, ms));
}
function maxRetries(id: string): number {
  return graph.value.tasks.find((t) => t.id === id)?.max_retries ?? 0;
}
function isTerminal(s: WorkflowTaskStatus): boolean {
  return s !== "pending" && s !== "running";
}
function markBlockedFrom(failedId: string) {
  for (const task of graph.value.tasks) {
    if (task.dependencies.includes(failedId) && statuses.value[task.id] === "pending") {
      statuses.value[task.id] = "blocked";
      markBlockedFrom(task.id);
    }
  }
}
function finishTask(id: string, ok: boolean, message: string) {
  const count = attempts.value[id] ?? 1;
  if (!ok && count <= maxRetries(id)) {
    statuses.value[id] = "failed";
    errors.value[id] = message;
    schedule(() => {
      if (statuses.value[id] === "failed") statuses.value[id] = "pending";
    }, 900);
    return;
  }
  statuses.value[id] = ok ? "succeeded" : "failed";
  if (!ok) {
    errors.value[id] = message;
    markBlockedFrom(id);
  }
}
function startTask(id: string) {
  statuses.value[id] = "running";
  attempts.value[id] = (attempts.value[id] ?? 0) + 1;
  const ok = Math.random() > 0.14;
  schedule(
    () => finishTask(id, ok, ok ? "" : "完成标准未满足：单测通过率低于预期，已回退重试"),
    700 + Math.random() * 800,
  );
}
function demoStep() {
  for (const task of graph.value.tasks) {
    if (statuses.value[task.id] !== "pending") continue;
    if (task.dependencies.every((d) => statuses.value[d] === "succeeded")) startTask(task.id);
  }
  const pending = graph.value.tasks.filter((t) => statuses.value[t.id] === "pending").length;
  const running = graph.value.tasks.filter((t) => statuses.value[t.id] === "running").length;
  if (pending === 0 && running === 0) {
    const allOk = graph.value.tasks.every((t) => statuses.value[t.id] === "succeeded");
    overall.value = allOk ? "succeeded" : "failed";
    window.clearInterval(demoTick);
    demoTick = 0;
    return;
  }
  if (running === 0) demoStep(); // 全部被阻塞或等待重试，立即推进下一轮
}
function simulate() {
  clearDemoTimers();
  resetState();
  mode.value = "demo";
  overall.value = "running";
  runId.value = `demo-${Date.now()}`;
  schedule(demoStep, 400);
  demoTick = window.setInterval(demoStep, 250);
}

// ---------- 真实运行（守护进程） ----------
let unsubscribe: (() => void) | null = null;
function handleRuntimeEvent(event: Record<string, unknown>) {
  if (event.type === "workflow.started") {
    const id = String(event.run_id ?? "");
    if (mode.value !== "live" || runId.value !== id) {
      resetState();
      mode.value = "live";
      runId.value = id;
      overall.value = "running";
      const snap = event.tasks as Array<{ id: string; status: WorkflowTaskStatus; attempt: number; error: string }>;
      for (const t of snap ?? []) {
        statuses.value[t.id] = t.status;
        if (t.attempt > 0) attempts.value[t.id] = t.attempt;
        if (t.error) errors.value[t.id] = t.error;
      }
    }
    return;
  }
  if (event.type === "workflow.task_updated" && runId.value === event.run_id) {
    const t = event.task as { id: string; status: WorkflowTaskStatus; attempt: number; error: string };
    if (!t) return;
    statuses.value[t.id] = t.status;
    attempts.value[t.id] = t.attempt ?? 0;
    if (t.error) errors.value[t.id] = t.error;
    return;
  }
  if (event.type === "workflow.finished" && runId.value === event.run_id) {
    overall.value = (event.status as WorkflowTaskStatus) === "cancelled" ? "cancelled" : (event.status as WorkflowTaskStatus) === "failed" ? "failed" : "succeeded";
  }
}
async function runReal() {
  if (!props.connected || realRunning.value) return;
  liveError.value = "";
  clearDemoTimers();
  resetState();
  mode.value = "live";
  overall.value = "running";
  realRunning.value = true;
  try {
    const result = await runWorkflow(graph.value);
    const finalByStatus = Object.fromEntries((result.tasks ?? []).map((t: { task: { id: string }; status: WorkflowTaskStatus }) => [t.task.id, t.status]));
    for (const [id, s] of Object.entries(finalByStatus)) statuses.value[id] = s;
    overall.value = result.status;
  } catch (error) {
    liveError.value = error instanceof Error ? error.message : String(error);
    overall.value = "failed";
  } finally {
    realRunning.value = false;
  }
}

function resetState() {
  clearDemoTimers();
  statuses.value = Object.fromEntries(graph.value.tasks.map((t) => [t.id, "pending"]));
  attempts.value = {};
  errors.value = {};
  overall.value = "idle";
  mode.value = "idle";
  runId.value = "";
  liveError.value = "";
}

let elapsedTick = 0;
onMounted(() => {
  unsubscribe = onRuntimeEvent(handleRuntimeEvent);
  const start = Date.now();
  elapsedTick = window.setInterval(() => {
    if (overall.value === "running") elapsedS.value = Math.round((Date.now() - start) / 1000);
  }, 1000);
});
onBeforeUnmount(() => {
  unsubscribe?.();
  clearDemoTimers();
  window.clearInterval(elapsedTick);
});
</script>

<template>
  <div class="wfp">
    <header class="wfp__header">
      <div class="wfp__title">
        <h1>工作流可视化</h1>
        <p>{{ graph.goal }}</p>
        <small>{{ graph.planner_summary }}</small>
      </div>
      <div class="wfp__actions">
        <span class="wfp__mode" :style="{ color: overallColor }">
          <AppIcon v-if="overall === 'running'" name="Radio" :size="13" class="wfp__pulse" />
          <template v-else-if="overall === 'succeeded'">✓</template>
          <template v-else-if="overall === 'failed'">✕</template>
          {{ modeLabel }} · {{ overallLabel }}<template v-if="runId"> · {{ runId.slice(0, 8) }}</template>
        </span>
        <button type="button" class="wfp__btn wfp__btn--primary" :disabled="overall === 'running'" @click="simulate">
          <AppIcon name="Play" :size="14" />模拟运行
        </button>
        <button type="button" class="wfp__btn" :disabled="!connected || overall === 'running'" :title="connected ? '通过 daemon 提交 workflow.run' : '本地服务未连接'" @click="runReal">
          <AppIcon name="TerminalSquare" :size="14" />真实运行
        </button>
        <button type="button" class="wfp__btn" :disabled="overall === 'idle' && !Object.values(statuses).some((s) => s !== 'pending')" @click="resetState">
          <AppIcon name="RotateCcw" :size="14" />重置
        </button>
        <button type="button" class="wfp__btn" @click="fitKey++"><AppIcon name="CirclePlay" :size="14" />适配视图</button>
      </div>
    </header>

    <p v-if="liveError" class="wfp__error"><AppIcon name="Square" :size="13" />{{ liveError }}</p>

    <div class="wfp__body">
      <WorkflowGraphCanvas
        :graph="graph"
        :statuses="statuses"
        :attempts="attempts"
        :errors="errors"
        :selected-id="selectedId"
        :fit-key="fitKey"
        @select="selectedId = $event"
      />
      <aside class="wfp__legend">
        <h2>状态图例</h2>
        <ul>
          <li v-for="s in STATUS_ORDER" :key="s">
            <i :style="{ background: statusMeta(s).color }" />
            {{ statusMeta(s).label }}
          </li>
        </ul>
        <h2>进度</h2>
        <p class="wfp__progress">{{ doneCount }} / {{ graph.tasks.length }} 完成 · {{ runningNow }} 运行中</p>
        <div class="wfp__bar"><i :style="{ width: `${(doneCount / graph.tasks.length) * 100}%`, background: overallColor }" /></div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.wfp {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 20px 24px;
  box-sizing: border-box;
}
.wfp__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.wfp__title h1 { margin: 0; font-size: 19px; font-weight: 600; }
.wfp__title p { margin: 6px 0 0; font-size: 13px; color: var(--text-muted, #777b82); }
.wfp__title small { display: block; margin-top: 4px; font-size: 12px; color: var(--text-faint, #9aa0ab); max-width: 640px; line-height: 1.5; }
.wfp__actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.wfp__mode {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text, #000) 6%, transparent);
}
.wfp__pulse { animation: wfp-blink 1s ease-in-out infinite; }
@keyframes wfp-blink { 50% { opacity: 0.25; } }
.wfp__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  padding: 7px 12px;
  border-radius: 8px;
  border: 1px solid var(--border, rgb(0 0 0 / 0.12));
  background: var(--surface-raised, rgb(255 255 255 / 0.6));
  color: var(--text, #202426);
  cursor: pointer;
}
.wfp__btn--primary { background: var(--accent, #2f6bff); border-color: var(--accent, #2f6bff); color: var(--accent-contrast, #fff); }
.wfp__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.wfp__error {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12.5px;
  color: #b45309;
  background: rgb(217 119 6 / 0.1);
  padding: 8px 12px;
  border-radius: 8px;
}
[data-app-theme="dark"] .wfp__error { color: #fd9851; background: rgb(217 119 6 / 0.16); }
.wfp__body { flex: 1; min-height: 0; display: flex; gap: 12px; }
.wfp__legend {
  width: 168px;
  flex: none;
  border: 1px solid var(--border, rgb(0 0 0 / 0.08));
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 12px;
  overflow: auto;
}
.wfp__legend h2 { margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--text-muted, #55585f); }
.wfp__legend h2 + ul { list-style: none; margin: 0 0 14px; padding: 0; display: grid; gap: 6px; }
.wfp__legend li { display: flex; align-items: center; gap: 8px; color: var(--text-muted, #55585f); }
.wfp__legend li i { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.wfp__progress { margin: 0 0 8px; color: var(--text-muted, #777b82); }
.wfp__bar { height: 6px; border-radius: 999px; background: color-mix(in srgb, var(--text, #000) 10%, transparent); overflow: hidden; }
.wfp__bar i { display: block; height: 100%; transition: width 0.3s ease; }
</style>
