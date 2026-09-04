<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import type { WorkflowTask, WorkflowTaskStatus } from "../../protocol";
import { layoutWorkflow, fitTransform, NODE_WIDTH, NODE_HEIGHT, type PlacedTask } from "./layout";
import { edgeColor, roleLabel, statusMeta } from "./status";

const props = withDefaults(
  defineProps<{
    graph: { tasks: WorkflowTask[] };
    statuses: Record<string, WorkflowTaskStatus>;
    attempts?: Record<string, number>;
    errors?: Record<string, string>;
    selectedId?: string | null;
    /** 外部通过 key 变化强制重新适配视图。 */
    fitKey?: number;
  }>(),
  { attempts: () => ({}), errors: () => ({}), selectedId: null, fitKey: 0 },
);

const emit = defineEmits<{ select: [id: string] }>();

const layout = computed(() => layoutWorkflow(props.graph.tasks));
const byId = computed(() => new Map(layout.value.placed.map((p) => [p.task.id, p])));

const container = ref<HTMLElement | null>(null);
const viewport = ref({ width: 800, height: 480 });
const view = ref({ x: 0, y: 0, k: 1 });
const dragging = ref(false);
let dragStart = { x: 0, y: 0, ox: 0, oy: 0 };
let pointerId = -1;

const MIN_K = 0.2;
const MAX_K = 2;

function resizeObserver() {
  if (!container.value) return;
  const rect = container.value.getBoundingClientRect();
  viewport.value = { width: rect.width, height: rect.height };
}
let observer: ResizeObserver | null = null;
let fitQueued = false;
function scheduleFit() {
  if (fitQueued) return;
  fitQueued = true;
  void nextTick(() => {
    fitQueued = false;
    applyFit();
  });
}
onMounted(() => {
  resizeObserver();
  observer = new ResizeObserver(resizeObserver);
  if (container.value) observer.observe(container.value);
  scheduleFit();
});
onBeforeUnmount(() => observer?.disconnect());

// 画布尺寸或图本身变化时自动重新适配；拖动/缩放后不再自动跟随。
watch([() => viewport.value.width, () => viewport.value.height, () => layout.value.width, () => layout.value.height], () => {
  if (!dragging.value) scheduleFit();
});
watch(
  () => props.fitKey,
  () => applyFit(),
);

function applyFit() {
  const { x, y, k } = fitTransform(layout.value, viewport.value);
  view.value = { x, y, k };
}

function zoomAt(px: number, py: number, factor: number) {
  const k = Math.min(MAX_K, Math.max(MIN_K, view.value.k * factor));
  const ratio = k / view.value.k;
  view.value = {
    k,
    x: px - (px - view.value.x) * ratio,
    y: py - (py - view.value.y) * ratio,
  };
}

function onWheel(event: WheelEvent) {
  event.preventDefault();
  const rect = container.value?.getBoundingClientRect();
  if (!rect) return;
  const factor = Math.exp(-event.deltaY * 0.0016);
  zoomAt(event.clientX - rect.left, event.clientY - rect.top, factor);
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return;
  dragging.value = true;
  pointerId = event.pointerId;
  dragStart = { x: event.clientX, y: event.clientY, ox: view.value.x, oy: view.value.y };
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value || event.pointerId !== pointerId) return;
  view.value.x = dragStart.ox + (event.clientX - dragStart.x);
  view.value.y = dragStart.oy + (event.clientY - dragStart.y);
}

function onPointerUp(event: PointerEvent) {
  if (event.pointerId !== pointerId) return;
  dragging.value = false;
  pointerId = -1;
}

const transformStyle = computed(
  () => `translate(${view.value.x}px, ${view.value.y}px) scale(${view.value.k})`,
);

function nodeStyle(p: PlacedTask) {
  return { width: `${NODE_WIDTH}px`, height: `${NODE_HEIGHT}px`, transform: `translate(${p.x}px, ${p.y}px)` };
}

function taskStatus(id: string): WorkflowTaskStatus {
  return props.statuses[id] ?? "pending";
}

const selected = computed(() => (props.selectedId ? byId.value.get(props.selectedId) ?? null : null));
</script>

<template>
  <div class="wf-graph" :class="{ dragging }" ref="container">
    <svg class="wf-graph__svg" :width="viewport.width" :height="viewport.height" aria-hidden="true">
      <g :transform="transformStyle">
        <path
          v-for="edge in layout.edges"
          :key="`${edge.from}-${edge.to}`"
          :d="edge.d"
          fill="none"
          :stroke="edgeColor(taskStatus(edge.from), taskStatus(edge.to)).edge"
          :stroke-width="1.6 / view.k"
          stroke-linecap="round"
          class="wf-edge"
          :class="{ 'wf-edge--pulse': edgeColor(taskStatus(edge.from), taskStatus(edge.to)).pulse }"
        />
      </g>
    </svg>

    <div class="wf-graph__nodes" :style="transformStyle">      <button
        v-for="p in layout.placed"
        :key="p.task.id"
        type="button"
        class="wf-node"
        :class="[`wf-node--${taskStatus(p.task.id)}`, { 'wf-node--selected': p.task.id === selectedId }]"
        :style="nodeStyle(p)"
        :title="p.task.title"
        @click.stop="emit('select', p.task.id)"
      >
        <span class="wf-node__head">
          <i class="wf-node__dot" :style="{ background: statusMeta(taskStatus(p.task.id)).color }" />
          <b>{{ p.task.title }}</b>
        </span>
        <span class="wf-node__meta">
          <em :class="`wf-role wf-role--${p.task.owner}`">{{ roleLabel(p.task.owner) }}</em>
          <em class="wf-node__status" :style="{ color: statusMeta(taskStatus(p.task.id)).color }">
            <template v-if="taskStatus(p.task.id) === 'running'"><AppIcon name="Loader2" :size="11" class="wf-spin" />{{ statusMeta(taskStatus(p.task.id)).label }}</template>
            <template v-else-if="taskStatus(p.task.id) === 'succeeded'"><AppIcon name="Check" :size="11" />{{ statusMeta(taskStatus(p.task.id)).label }}</template>
            <template v-else-if="taskStatus(p.task.id) === 'pending'"><AppIcon name="Circle" :size="11" />{{ statusMeta(taskStatus(p.task.id)).label }}</template>
            <template v-else>{{ statusMeta(taskStatus(p.task.id)).label }}</template>
          </em>
        </span>
        <span class="wf-node__foot">
          <small>{{ p.task.completion_criteria.length }} 条完成标准</small>
          <small v-if="(attempts[p.task.id] ?? 0) > 1">第 {{ attempts[p.task.id] }} 次尝试</small>
        </span>
        <span v-if="errors[p.task.id]" class="wf-node__error" :title="errors[p.task.id]">{{ errors[p.task.id] }}</span>
      </button>
    </div>

    <div class="wf-graph__controls" @pointerdown.stop>
      <button type="button" title="放大" aria-label="放大" @click="zoomAt(viewport.width / 2, viewport.height / 2, 1.2)"><AppIcon name="ZoomIn" :size="15" /></button>
      <button type="button" title="缩小" aria-label="缩小" @click="zoomAt(viewport.width / 2, viewport.height / 2, 1 / 1.2)"><AppIcon name="ZoomOut" :size="15" /></button>
      <button type="button" title="适配视图" aria-label="适配视图" @click="applyFit"><AppIcon name="Maximize2" :size="15" /></button>
      <button type="button" title="重置" aria-label="重置" @click="view = { x: 0, y: 0, k: 1 }"><AppIcon name="RotateCcw" :size="15" /></button>
      <span class="wf-graph__scale">{{ Math.round(view.k * 100) }}%</span>
    </div>

    <div v-if="selected" class="wf-node-detail">
      <header>
        <b>{{ selected.task.title }}</b>
        <span :style="{ color: statusMeta(taskStatus(selected.task.id)).color }">{{ statusMeta(taskStatus(selected.task.id)).label }}</span>
      </header>
      <p>{{ selected.task.description }}</p>
      <dl>
        <dt>角色</dt><dd>{{ roleLabel(selected.task.owner) }}</dd>
        <dt>Token 预算</dt><dd>{{ selected.task.token_budget.toLocaleString() }}</dd>
        <dt>时限</dt><dd>{{ selected.task.time_budget_s }} 秒</dd>
        <dt>依赖</dt><dd>{{ selected.task.dependencies.length ? selected.task.dependencies.join(", ") : "无" }}</dd>
        <dt>允许路径</dt><dd>{{ selected.task.allowed_paths.length ? selected.task.allowed_paths.join(", ") : "无限制" }}</dd>
      </dl>
      <ul>
        <li v-for="c in selected.task.completion_criteria" :key="c">{{ c }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.wf-graph {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 1px 1px, rgb(255 255 255 / 0.05) 1px, transparent 0) 0 0 / 22px 22px,
    var(--wf-canvas, #12141c);
  touch-action: none;
  user-select: none;
  cursor: grab;
  border-radius: 10px;
  border: 1px solid rgb(255 255 255 / 0.07);
}
.wf-graph.dragging,
.wf-graph:active { cursor: grabbing; }
.wf-graph__svg { position: absolute; inset: 0; }
.wf-graph__nodes { position: absolute; inset: 0; transform-origin: 0 0; }

.wf-edge { transition: stroke 0.25s ease; }
.wf-edge--pulse {
  stroke-dasharray: 6 6;
  animation: wf-dash 0.9s linear infinite;
}
@keyframes wf-dash { to { stroke-dashoffset: -12; } }

.wf-node {
  position: absolute;
  transform-origin: 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #1a1d27;
  border: 1px solid rgb(255 255 255 / 0.09);
  color: inherit;
  text-align: left;
  font: inherit;
  cursor: pointer;
  box-shadow: 0 4px 14px rgb(0 0 0 / 0.28);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  overflow: hidden;
}
.wf-node:hover { border-color: rgb(255 255 255 / 0.28); transform: translateY(-1px); }
.wf-node--selected { border-color: var(--wf-accent, #4f8cff); box-shadow: 0 0 0 2px rgb(79 140 255 / 0.35); }
.wf-node--running { box-shadow: 0 4px 18px rgb(59 130 246 / 0.35); }
.wf-node--succeeded { border-color: rgb(34 197 94 / 0.45); }
.wf-node--failed,
.wf-node--rejected,
.wf-node--timed_out { border-color: rgb(239 68 68 / 0.5); }
.wf-node--blocked { border-color: rgb(245 158 11 / 0.5); }

.wf-node__head { display: flex; align-items: center; gap: 6px; min-width: 0; }
.wf-node__head b {
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wf-node__dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.wf-node__meta { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.wf-role {
  font-style: normal;
  font-size: 10.5px;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.07);
  color: #b6bace;
}
.wf-role--planner { background: rgb(168 85 247 / 0.16); color: #c4a3f2; }
.wf-role--coder { background: rgb(79 140 255 / 0.16); color: #9cc2ff; }
.wf-role--tester { background: rgb(34 197 94 / 0.14); color: #86efac; }
.wf-role--reviewer { background: rgb(245 158 11 / 0.16); color: #fcd34d; }
.wf-node__status { display: inline-flex; align-items: center; gap: 4px; font-style: normal; font-size: 11px; font-weight: 600; }
.wf-spin { animation: wf-spin 1s linear infinite; }
@keyframes wf-spin { to { transform: rotate(360deg); } }
.wf-node__foot { display: flex; justify-content: space-between; gap: 6px; }
.wf-node__foot small { font-size: 10.5px; color: #8b8fa3; }
.wf-node__error {
  position: absolute;
  top: 8px;
  right: 8px;
  max-width: 60%;
  font-size: 10px;
  color: #fca5a5;
  background: rgb(239 68 68 / 0.16);
  border-radius: 6px;
  padding: 1px 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wf-graph__controls {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px;
  border-radius: 9px;
  background: rgb(18 20 28 / 0.85);
  border: 1px solid rgb(255 255 255 / 0.09);
  backdrop-filter: blur(6px);
}
.wf-graph__controls button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  color: #b6bace;
  border-radius: 6px;
  cursor: pointer;
}
.wf-graph__controls button:hover { background: rgb(255 255 255 / 0.1); color: #fff; }
.wf-graph__scale { font-size: 10.5px; color: #8b8fa3; padding: 0 6px; min-width: 42px; text-align: center; }

.wf-node-detail {
  position: absolute;
  left: 12px;
  bottom: 12px;
  width: min(320px, calc(100% - 24px));
  max-height: 46%;
  overflow: auto;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgb(18 20 28 / 0.92);
  border: 1px solid rgb(255 255 255 / 0.1);
  backdrop-filter: blur(8px);
}
.wf-node-detail header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.wf-node-detail header b { font-size: 13px; }
.wf-node-detail header span { font-size: 11px; font-weight: 600; }
.wf-node-detail p { font-size: 11.5px; line-height: 1.5; color: #b6bace; margin: 6px 0 8px; }
.wf-node-detail dl { display: grid; grid-template-columns: 72px 1fr; gap: 3px 8px; margin: 0 0 8px; font-size: 11px; }
.wf-node-detail dt { color: #8b8fa3; }
.wf-node-detail dd { margin: 0; color: #d7dae4; word-break: break-all; }
.wf-node-detail ul { margin: 0; padding-left: 16px; }
.wf-node-detail li { font-size: 11px; color: #b6bace; line-height: 1.5; }
</style>
