<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, nextTick } from "vue";
import { Brain, Check, ChevronDown, Code2, Edit3, FolderOpen, LoaderCircle, Search, Terminal } from "@lucide/vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";
import { reasoningSummary } from "../../utils/reasoningSummary";

const props = defineProps<{
  thinking?: string;
  calls: ToolCallEntry[];
  running?: boolean;
  completed?: boolean;
}>();

const open = ref(false);
const hasContent = computed(() => (props.thinking && props.thinking.trim().length > 0) || props.calls.length > 0);

watch(() => props.running, (isRunning) => {
  if (isRunning) {
    open.value = true;
  } else if (props.completed) {
    open.value = false;
  }
}, { immediate: true });

// 思考过程快速播放：大块文本到达时单帧最多加入若干字符，追赶输出
const initialThinking = props.thinking ?? "";
const displayedThinking = ref(props.completed ? initialThinking : "");
let thinkingChars = Array.from(initialThinking);
let displayedCount = Array.from(displayedThinking.value).length;
let playbackFrame: number | null = null;

function revealCount(remaining: number): number {
  return Math.min(12, Math.max(1, Math.ceil(remaining / 18)));
}

function advancePlayback() {
  playbackFrame = null;
  const remaining = thinkingChars.length - displayedCount;
  if (remaining <= 0) return;
  displayedCount += revealCount(remaining);
  displayedThinking.value = thinkingChars.slice(0, displayedCount).join("");
  if (displayedCount < thinkingChars.length) playbackFrame = requestAnimationFrame(advancePlayback);
}

function schedulePlayback() {
  if (playbackFrame !== null || displayedCount >= thinkingChars.length) return;
  playbackFrame = requestAnimationFrame(advancePlayback);
}

watch(() => props.thinking ?? "", (value) => {
  thinkingChars = Array.from(value);
  if (!value.startsWith(displayedThinking.value)) {
    displayedCount = 0;
    displayedThinking.value = "";
  }
  schedulePlayback();
});

watch(() => props.completed, () => schedulePlayback());
onBeforeUnmount(() => {
  if (playbackFrame !== null) cancelAnimationFrame(playbackFrame);
});
if (!props.completed && thinkingChars.length) schedulePlayback();

const catchingUp = computed(() => displayedThinking.value !== (props.thinking ?? ""));
const thinkingRunning = computed(() => props.running || catchingUp.value);

// 按类型分组统计工具调用
const groups = computed(() => {
  const buckets: Record<string, { label: string; icon: typeof Terminal; count: number }> = {};
  for (const call of props.calls) {
    const name = call.name.toLowerCase();
    let key: string;
    let label: string;
    let icon: typeof Terminal;
    if (/read|file|dir|ls/i.test(name)) {
      key = "file"; label = "读取"; icon = FolderOpen;
    } else if (/glob|search|grep|find/i.test(name)) {
      key = "search"; label = "搜索"; icon = Search;
    } else if (/edit|write|patch|create/i.test(name)) {
      key = "edit"; label = "编辑"; icon = Edit3;
    } else if (/bash|shell|terminal|command|powershell|pwsh|exec|run/i.test(name)) {
      key = "exec"; label = "执行"; icon = Terminal;
    } else {
      key = "other"; label = "调用"; icon = Code2;
    }
    if (!buckets[key]) buckets[key] = { label, icon, count: 0 };
    buckets[key].count++;
  }
  return Object.values(buckets);
});

// 摘要标签：优先显示思考状态
const summaryLabel = computed(() => {
  if (props.thinking && props.running && !props.calls.length) {
    return "思考中";
  }
  if (props.running) {
    return props.thinking ? "思考中" : "执行中";
  }
  if (!props.calls.length && props.thinking) {
    return "思考完成";
  }
  const total = props.calls.length;
  if (total === 0) return "已完成";
  const parts = groups.value.map(g => `${g.label} ${g.count}`);
  if (props.thinking && !props.completed) parts.unshift("思考");
  return parts.join(" · ");
});

// 第一个工具的细节路径作为提示
const detailHint = computed(() => {
  if (props.thinking) return "";
  const first = props.calls[0];
  if (!first) return "";
  const value = first.params.command ?? first.params.cmd ?? first.params.path ?? first.params.query ?? first.params.description;
  if (typeof value === "string") {
    const parts = value.split(/[\\/]/);
    return parts[parts.length - 1] || value.slice(0, 40);
  }
  return "";
});

// 思考预览行：流式时跟随最后一行，完成后显示首行
const thinkingPreview = computed(() => reasoningSummary(displayedThinking.value, thinkingRunning.value));

// 预览行自动滚到末尾（流式跟随）
const previewRef = ref<HTMLElement | null>(null);
watch([thinkingPreview, thinkingRunning], () => {
  const el = previewRef.value;
  if (!el) return;
  el.scrollLeft = thinkingRunning.value ? el.scrollWidth - el.clientWidth : 0;
}, { flush: "post" });
</script>

<template>
  <div v-if="hasContent" class="activity-phase" :class="{ open, running: running, done: completed && !running, thinking: !!thinking }">
    <button
      type="button"
      class="activity-phase__trigger"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="activity-phase__status">
        <LoaderCircle v-if="running" class="spin" :size="13" />
        <Check v-else-if="completed" :size="13" />
        <Brain v-else :size="13" />
      </span>

      <span class="activity-phase__label">{{ summaryLabel }}</span>

      <!-- 思考过程一行预览（流式快速输出，类似ThinkingPanel） -->
      <span v-if="thinking" ref="previewRef" class="activity-phase__preview" :data-follow-end="thinkingRunning || undefined">
        {{ thinkingPreview }}
      </span>

      <!-- 工具提示（没有思考时才显示） -->
      <span v-else-if="!open && detailHint" class="activity-phase__hint">{{ detailHint }}</span>

      <ChevronDown v-if="hasContent" class="activity-phase__chevron" :size="11" />
    </button>

    <transition name="phase-expand">
      <div v-if="open" class="activity-phase__body">
        <!-- 思考过程（展开后显示完整内容） -->
        <div v-if="thinking" class="activity-phase__thinking">
          <pre class="activity-phase__thinking-text">{{ displayedThinking }}</pre>
        </div>
        <!-- 工具调用列表 -->
        <div v-if="calls.length" class="activity-phase__tools">
          <div v-if="thinking" class="activity-phase__section-label">
            <Terminal :size="11" /> 工具调用
          </div>
          <ToolCallCard v-for="call in calls" :key="call.id" :call="call" :compact="true" />
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.activity-phase {
  margin: 1px 0 4px;
  font-size: 12px;
}

.activity-phase__trigger {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 7px;
  min-height: 28px;
  padding: 4px 6px;
  margin: 0 -6px;
  color: #6d737c;
  background: transparent;
  border: 0;
  border-radius: 4px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}

.activity-phase__trigger:hover {
  background: rgba(0, 0, 0, 0.04);
}

.activity-phase__status {
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 4px;
  color: #727983;
}

.activity-phase.running .activity-phase__status {
  color: #2563eb;
}

.activity-phase.done .activity-phase__status {
  color: #16a34a;
}

.activity-phase__label {
  flex: 0 0 auto;
  color: #59616b;
  font-weight: 500;
  letter-spacing: -0.01em;
}

.activity-phase.running .activity-phase__label {
  color: #2563eb;
}

/* 分隔符 */
.activity-phase__trigger .activity-phase__label::after {
  content: "·";
  margin-left: 7px;
  color: #b2b7bd;
  font-weight: 400;
}

/* 思考预览一行（核心：单行省略，流式时跟随末尾） */
.activity-phase__preview {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #747b84;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.activity-phase__preview[data-follow-end] {
  text-overflow: clip;
}

.activity-phase__hint {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #9ca3af;
  font-family: "SF Mono", Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-phase__chevron {
  flex: 0 0 auto;
  margin-left: auto;
  color: #8c9299;
  transition: opacity 0.15s ease, transform 0.18s ease;
  opacity: 0;
}

.activity-phase__trigger:hover .activity-phase__chevron,
.activity-phase.open .activity-phase__chevron {
  opacity: 1;
}

.activity-phase.open .activity-phase__chevron {
  transform: rotate(180deg);
}

/* 思考中扫光效果 */
.activity-phase.running.thinking .activity-phase__trigger {
  position: relative;
  overflow: hidden;
}
.activity-phase.running.thinking .activity-phase__trigger::after {
  content: "";
  position: absolute;
  inset-block: 0;
  left: 0;
  width: 200px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(37, 99, 235, 0.04) 50%,
    transparent 100%
  );
  animation: thinkingSweep 1.8s ease-out infinite;
  pointer-events: none;
}
@keyframes thinkingSweep {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(500%); }
}

.activity-phase__body {
  margin: 2px 0 6px 0;
  padding-left: 26px;
  border-left: 1px solid rgb(118 126 136 / 22%);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.activity-phase__section-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 4px 0 2px;
  color: #9ca3af;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.activity-phase__thinking {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.activity-phase__thinking-text {
  margin: 0;
  padding: 6px 10px;
  color: #6b7280;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  border-radius: 6px;
  font: 12px/1.7 var(--font-ui, "Microsoft YaHei UI"), "SF Mono", Consolas, sans-serif;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 240px;
  overflow: auto;
}

.activity-phase__tools {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.phase-expand-enter-active,
.phase-expand-leave-active {
  transition: all 0.18s ease;
  overflow: hidden;
}

.phase-expand-enter-from,
.phase-expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
  margin-bottom: 0;
}

.phase-expand-enter-to,
.phase-expand-leave-from {
  opacity: 1;
  max-height: 1000px;
}

/* 暗色主题 */
:global(.dark) .activity-phase__trigger:hover {
  background: rgba(255, 255, 255, 0.06);
}
:global(.dark) .activity-phase__status {
  color: #6b7280;
}
:global(.dark) .activity-phase.running .activity-phase__status {
  color: #60a5fa;
}
:global(.dark) .activity-phase.done .activity-phase__status {
  color: #4ade80;
}
:global(.dark) .activity-phase__label {
  color: #d1d5db;
}
:global(.dark) .activity-phase.running .activity-phase__label {
  color: #60a5fa;
}
:global(.dark) .activity-phase__trigger .activity-phase__label::after {
  color: #4b5563;
}
:global(.dark) .activity-phase__preview {
  color: #9ca3af;
}
:global(.dark) .activity-phase__hint {
  color: #6b7280;
}
:global(.dark) .activity-phase__chevron {
  color: #6b7280;
}
:global(.dark) .activity-phase__body {
  border-left-color: #374151;
}
:global(.dark) .activity-phase__section-label {
  color: #6b7280;
}
:global(.dark) .activity-phase__thinking-text {
  color: #9ca3af;
  background: #1f2937;
  border-color: #374151;
}
:global(.dark) .activity-phase.running.thinking .activity-phase__trigger::after {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(96, 165, 250, 0.06) 50%,
    transparent 100%
  );
}

@media (prefers-reduced-motion: reduce) {
  .phase-expand-enter-active,
  .phase-expand-leave-active {
    transition: none;
  }
  .activity-phase.running.thinking .activity-phase__trigger::after {
    animation: none;
  }
}
</style>
