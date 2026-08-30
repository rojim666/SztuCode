<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, nextTick } from "vue";
import { Brain, Check, ChevronDown, Code2, Edit3, FolderOpen, LoaderCircle, Search, Terminal, XCircle } from "@lucide/vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";
import { reasoningSummary, firstLine } from "../../utils/reasoningSummary";

const props = defineProps<{
  thinking?: string;
  calls: ToolCallEntry[];
  running?: boolean;
  completed?: boolean;
  stepIndex?: number;
  stepTitle?: string;
}>();

const open = ref(false);
const hasContent = computed(() => (props.thinking && props.thinking.trim().length > 0) || props.calls.length > 0);

// 始终保持紧凑折叠，用户点击才展开；失败的工具自动展开提示
const hasFailedCalls = computed(() => props.calls.some(c => c.status === "failed"));

watch(() => [props.running, props.completed, hasFailedCalls.value], () => {
  // 只有失败时自动展开，其他情况（包括运行中）都保持折叠，界面更清爽
  if (hasFailedCalls.value) {
    open.value = true;
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

// 从思考文本中提取行为目的：清理前缀，保留简洁的目的描述
function extractPurpose(thinking: string): string {
  if (!thinking?.trim()) return "";
  const first = firstLine(thinking).trim();
  // 去掉常见的思考前缀/自语，保留核心动作
  let cleaned = first
    .replace(/^(好的|我来|让我|现在|接下来|首先|先|好，|好的，|嗯，|哦，|I need to|Let me|Now|First|Okay,?|Alright,?|So,?|I will|I should)\s*/i, "")
    .replace(/[。！？\.\!\?]+.*$/, "") // 去掉句号后面的内容，只留第一句
    .trim();
  // 太长则截断
  if (cleaned.length > 40) cleaned = cleaned.slice(0, 38) + "…";
  return cleaned;
}

// 行为目的摘要：从思考中提取，或基于工具推断
const purposeSummary = computed(() => {
  // 优先从思考内容提取目的
  const fromThinking = extractPurpose(props.thinking || displayedThinking.value);
  if (fromThinking) return fromThinking;
  // 没有思考时，根据工具推断目的
  const first = props.calls[0];
  if (!first) return "";
  const name = first.name.toLowerCase();
  if (/read|file|dir|ls/i.test(name)) {
    const path = first.params.path as string | undefined;
    if (path) {
      const parts = path.split(/[\\/]/);
      return `查看 ${parts[parts.length - 1]}`;
    }
    return "读取文件";
  }
  if (/glob|search|grep|find/i.test(name)) {
    const q = first.params.query ?? first.params.pattern ?? "";
    if (typeof q === "string" && q) return `搜索 "${q.slice(0, 20)}"`;
    return "搜索相关代码";
  }
  if (/edit|write|patch|create/i.test(name)) {
    const path = first.params.path as string | undefined;
    if (path) {
      const parts = path.split(/[\\/]/);
      return `修改 ${parts[parts.length - 1]}`;
    }
    return "编辑文件";
  }
  if (/bash|shell|terminal|command/i.test(name)) {
    return "执行命令";
  }
  return "";
});

// 工具结果摘要：完成后显示操作统计
const toolResultSummary = computed(() => {
  const total = props.calls.length;
  if (total === 0) return "";
  const toolParts = groups.value.map(g => g.count > 1 ? `${g.label}${g.count}` : g.label);
  return toolParts.join(" · ");
});

// 有效的目的描述：优先使用传入的stepTitle（来自plan），否则从思考/工具推断
const effectivePurpose = computed(() => {
  if (props.stepTitle?.trim()) return props.stepTitle.trim();
  return purposeSummary.value;
});

// 思考预览行：流式时跟随最后一行，完成后显示首行（不做额外处理，由purposeSummary显示目的）
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
  <div v-if="hasContent" class="activity-phase" :class="{ open, running: running, done: completed && !running, failed: hasFailedCalls, thinking: !!thinking }">
    <button
      type="button"
      class="activity-phase__trigger"
      :aria-expanded="open"
      @click="open = !open"
    >
      <!-- 步骤序号圆 -->
      <span class="activity-phase__status">
        <!-- 运行中：蓝色旋转圆圈 -->
        <template v-if="running">
          <span v-if="stepIndex !== undefined" class="step-badge step-badge--running">{{ stepIndex }}</span>
          <LoaderCircle v-else class="spin" :size="14" />
        </template>
        <!-- 失败：红色圆形叉号 -->
        <template v-else-if="hasFailedCalls">
          <XCircle :size="14" />
        </template>
        <!-- 完成：绿色圆形对勾 -->
        <template v-else-if="completed">
          <span v-if="stepIndex !== undefined" class="step-badge step-badge--done">{{ stepIndex }}</span>
          <Check v-else :size="14" />
        </template>
        <!-- 默认/仅有思考：灰色脑图标 -->
        <Brain v-else :size="13" />
      </span>

      <!-- 行为目的描述 -->
      <span v-if="effectivePurpose" class="activity-phase__purpose">
        {{ effectivePurpose }}
      </span>

      <!-- 思考流式预览：运行中跟随最后一行思考内容 -->
      <span v-if="running && thinking && !effectivePurpose" ref="previewRef" class="activity-phase__preview" :data-follow-end="thinkingRunning || undefined">
        {{ thinkingPreview }}
      </span>

      <!-- 完成后显示操作结果统计（绿色对勾旁边） -->
      <span v-if="completed && !running && toolResultSummary && !hasFailedCalls" class="activity-phase__result">
        {{ toolResultSummary }}
      </span>

      <!-- 失败显示提示 -->
      <span v-if="hasFailedCalls" class="activity-phase__fail-hint">
        操作失败，点击查看
      </span>

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
  width: 20px;
  height: 20px;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 50%;
  color: #727983;
}

/* 步骤序号徽章 */
.step-badge {
  display: grid;
  width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.step-badge--running {
  color: #fff;
  background: #2563eb;
  animation: pulse-blue 1.5s ease-in-out infinite;
}

.step-badge--done {
  color: #fff;
  background: #16a34a;
}

@keyframes pulse-blue {
  0%, 100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(37, 99, 235, 0); }
}

/* 运行中：蓝色旋转 */
.activity-phase.running .activity-phase__status {
  color: #2563eb;
  background: rgba(37, 99, 235, 0.1);
}

/* 完成：绿色圆形背景对勾 */
.activity-phase.done .activity-phase__status {
  color: #fff;
  background: #16a34a;
}

/* 失败：红色圆形背景叉号 */
.activity-phase.failed .activity-phase__status {
  color: #fff;
  background: #dc2626;
}

/* 行为目的描述 */
.activity-phase__purpose {
  min-width: 0;
  flex: 0 1 auto;
  overflow: hidden;
  color: #374151;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.activity-phase.running .activity-phase__purpose {
  color: #1f2937;
}

.activity-phase.done .activity-phase__purpose {
  color: #16a34a;
}

/* 分隔符 - 目的描述后面的点 */
.activity-phase__purpose::after {
  content: "·";
  margin-left: 7px;
  color: #b2b7bd;
  font-weight: 400;
}

/* 完成结果统计 */
.activity-phase__result {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #16a34a;
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 失败提示 */
.activity-phase__fail-hint {
  min-width: 0;
  flex: 1 1 auto;
  color: #dc2626;
  font-size: 12px;
  font-weight: 500;
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

.activity-phase__chevron {
  flex: 0 0 auto;
  margin-left: auto;
  color: #8c9299;
  transition: opacity 0.15s ease, transform 0.18s ease;
  opacity: 0.6;
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
  padding-left: 27px;
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
  background: transparent;
}
:global(.dark) .step-badge--running {
  color: #fff;
  background: #3b82f6;
}
:global(.dark) .step-badge--done {
  color: #fff;
  background: #22c55e;
}
:global(.dark) .activity-phase.running .activity-phase__status {
  color: #60a5fa;
  background: rgba(96, 165, 250, 0.15);
}
:global(.dark) .activity-phase.done .activity-phase__status {
  color: #fff;
  background: #22c55e;
}
:global(.dark) .activity-phase.failed .activity-phase__status {
  color: #fff;
  background: #ef4444;
}
:global(.dark) .activity-phase__purpose {
  color: #d1d5db;
}
:global(.dark) .activity-phase.running .activity-phase__purpose {
  color: #e5e7eb;
}
:global(.dark) .activity-phase.done .activity-phase__purpose {
  color: #4ade80;
}
:global(.dark) .activity-phase__purpose::after {
  color: #4b5563;
}
:global(.dark) .activity-phase__result {
  color: #4ade80;
}
:global(.dark) .activity-phase__fail-hint {
  color: #f87171;
}
:global(.dark) .activity-phase__preview {
  color: #9ca3af;
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
