<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ChevronDown, FilePenLine, FileText, LoaderCircle, Search, Terminal, Timer } from "@lucide/vue";
import type { ToolCallEntry } from "./types";

const props = withDefaults(defineProps<{ call: ToolCallEntry; expanded?: boolean }>(), { expanded: false });
const open = ref(false);
const isOpen = computed(() => props.expanded || open.value);
const request = computed(() => JSON.stringify(props.call.params, null, 2));
const detail = computed(() => {
  const value = props.call.params.command ?? props.call.params.cmd ?? props.call.params.path ?? props.call.params.query ?? props.call.params.description;
  return typeof value === "string" ? value : props.call.name;
});
const kind = computed(() => {
  const name = props.call.name.toLowerCase();
  if (/edit|write/.test(name)) return "edit";
  if (/glob/.test(name)) return "glob";
  if (/grep|search/.test(name)) return "search";
  if (/read|file|dir/.test(name)) return "file";
  return "command";
});
const actionLabel = computed(() => {
  const name = props.call.name.toLowerCase();
  if (/powershell|pwsh/.test(name)) return "Pwsh";
  if (/bash|shell|terminal|command/.test(name)) return "Shell";
  if (/glob/.test(name)) return "Glob";
  if (/grep/.test(name)) return "Grep";
  if (/search/.test(name)) return "Search";
  if (/edit|patch/.test(name)) return "Edit";
  if (/write/.test(name)) return "Write";
  if (/read|file|dir/.test(name)) return "Read";
  return props.call.name;
});
const title = computed(() => {
  const prefix = props.call.status === "running" ? "正在" : "已运行";
  if (kind.value === "edit") return `${props.call.status === "running" ? "正在编辑" : "已编辑"} ${detail.value}`;
  if (kind.value === "search" || kind.value === "glob") return `${props.call.status === "running" ? "正在搜索" : "已搜索"} ${detail.value}`;
  if (kind.value === "file") return `${props.call.status === "running" ? "正在读取" : "已读取"} ${detail.value}`;
  return `${prefix} ${detail.value}`;
});
const isFileTool = computed(() => /read|file|dir/i.test(props.call.name));
const isPathLike = computed(() => /read|file|dir|edit|write/i.test(props.call.name));

// 运行中计时：以 started_at 为起点每秒刷新（借鉴 dsh web GUI 终端卡 running 态）
const now = ref(Date.now());
let timer: number | undefined;
watch(
  () => props.call.status,
  (status) => {
    if (timer !== undefined) { window.clearInterval(timer); timer = undefined; }
    if (status === "running") timer = window.setInterval(() => { now.value = Date.now(); }, 1000);
  },
  { immediate: true },
);
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer); });
const elapsed = computed(() => {
  if (props.call.status !== "running" || !props.call.startedAt) return null;
  const start = new Date(props.call.startedAt).getTime();
  if (Number.isNaN(start)) return null;
  const seconds = Math.max(0, (now.value - start) / 1000);
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
});

// 输出摘要：超过 400 字符/12 行时保留头部并标记省略量（借鉴 dsh ToolRow 折叠摘要）
const OUTPUT_MAX_CHARS = 400;
const OUTPUT_MAX_LINES = 12;
const outputSummary = computed(() => {
  const raw = props.call.error || props.call.output || "";
  if (!raw) return "";
  if (raw.length <= OUTPUT_MAX_CHARS) return raw;
  const lines = raw.split("\n");
  const head = lines.slice(0, OUTPUT_MAX_LINES).join("\n");
  const omittedChars = raw.length - head.length;
  const omittedLines = Math.max(0, lines.length - OUTPUT_MAX_LINES);
  return `${head}\n\n[... 已省略 ${omittedLines} 行 / ${omittedChars} 字符 ...]`;
});
</script>

<template>
  <section class="tool-call-event" :class="call.status">
    <button :aria-label="title" :aria-expanded="isOpen" @click="open = !open">
      <FilePenLine v-if="kind === 'edit'" :size="16" />
      <Search v-else-if="kind === 'search' || kind === 'glob'" :size="16" />
      <FileText v-else-if="isFileTool" :size="16" />
      <Terminal v-else :size="16" />
      <span class="tool-call-event__action">{{ actionLabel }}</span>
      <span class="timeline-row__separator">·</span>
      <span class="tool-call-event__detail" :class="{ 'is-path': isPathLike }">{{ detail }}</span>
      <span v-if="elapsed" class="tool-call-event__elapsed"><Timer :size="11" />{{ elapsed }}</span>
      <LoaderCircle v-if="call.status === 'running'" class="spin" :size="14" />
      <ChevronDown class="timeline-row__chevron" :size="13" />
    </button>
    <div v-if="isOpen" class="tool-call-event__details">
      <b>{{ call.status === 'running' ? '本次参数' : '输入参数' }}</b><pre>{{ request }}</pre>
      <template v-if="outputSummary"><b>执行返回</b><pre>{{ outputSummary }}</pre></template>
    </div>
  </section>
</template>

<style scoped>
.tool-call-event__elapsed {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex: 0 0 auto;
  color: #8a6a4a;
  font: 10px Consolas, monospace;
}
/* 运行扫光（借鉴 dsh ToolRow sweep）：300px 固定宽光带滑过运行中的卡片，
   ease-out + 尾部 10% 停驻给每次扫过留一拍 */
.tool-call-event.running {
  position: relative;
  overflow: hidden;
}
.tool-call-event.running::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 300px;
  pointer-events: none;
  background: linear-gradient(90deg, transparent 0%, rgb(255 255 255 / 60%) 55%, transparent 100%);
  animation: sz-tool-row-sweep 2.6s ease-out infinite;
}
@keyframes sz-tool-row-sweep {
  0% { left: -300px; }
  90%, 100% { left: 100%; }
}
/* 减弱动效（借鉴 dsh：prefers-reduced-motion 关闭全部状态动画） */
@media (prefers-reduced-motion: reduce) {
  .tool-call-event.running::after { animation: none; }
}
</style>
