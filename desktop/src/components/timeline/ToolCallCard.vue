<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import type { ToolCallEntry } from "./types";

const props = withDefaults(defineProps<{ call: ToolCallEntry; expanded?: boolean; compact?: boolean }>(), {
  expanded: false,
  compact: false,
});
const { t } = useI18n({ useScope: "global" });
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
  const running = props.call.status === "running";
  if (kind.value === "edit") return t(running ? "timeline.tool.title.editing" : "timeline.tool.title.edited", { target: detail.value });
  if (kind.value === "search" || kind.value === "glob") return t(running ? "timeline.tool.title.searching" : "timeline.tool.title.searched", { target: detail.value });
  if (kind.value === "file") return t(running ? "timeline.tool.title.reading" : "timeline.tool.title.read", { target: detail.value });
  return t(running ? "timeline.tool.title.running" : "timeline.tool.title.done", { target: detail.value });
});
const isFileTool = computed(() => /read|file|dir/i.test(props.call.name));
const isPathLike = computed(() => /read|file|dir|edit|write/i.test(props.call.name));

// 运行中计时
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

// 输出展示：支持展开查看完整内容
const OUTPUT_MAX_CHARS = props.compact ? 200 : 400;
const OUTPUT_MAX_LINES = props.compact ? 6 : 12;
const showFullOutput = ref(false);
const rawOutput = computed(() => props.call.error || props.call.output || "");
const isOutputTruncated = computed(() => {
  const raw = rawOutput.value;
  if (!raw) return false;
  return raw.length > OUTPUT_MAX_CHARS;
});
const outputToShow = computed(() => {
  const raw = rawOutput.value;
  if (!raw) return "";
  if (showFullOutput.value || raw.length <= OUTPUT_MAX_CHARS) return raw;
  const lines = raw.split("\n");
  return lines.slice(0, OUTPUT_MAX_LINES).join("\n");
});

const hasDetails = computed(() => request.value.length > 2 || rawOutput.value || (props.call.images?.length ?? 0) > 0);

// 工具返回的图片（浏览器截图等）：折叠态显示徽标，展开态内联缩略图，点击切换原图
const imageUrls = computed(() => (props.call.images ?? []).map((image) => `data:${image.mimeType};base64,${image.data}`));
const zoomedImage = ref<number | null>(null);
</script>

<template>
  <section class="tool-call-event" :class="[call.status, { compact }]">
    <button :aria-label="title" :aria-expanded="isOpen" :disabled="!hasDetails" @click="hasDetails && (open = !open)">
      <AppIcon v-if="kind === 'edit'" name="FilePenLine" :size="compact ? 12 : 14" />
      <AppIcon v-else-if="kind === 'search' || kind === 'glob'" name="Search" :size="compact ? 12 : 14" />
      <AppIcon v-else-if="isFileTool" name="FileText" :size="compact ? 12 : 14" />
      <AppIcon v-else name="Terminal" :size="compact ? 12 : 14" />
      <span v-if="!compact" class="tool-call-event__action">{{ actionLabel }}</span>
      <span v-if="!compact" class="timeline-row__separator">·</span>
      <span class="tool-call-event__detail" :class="{ 'is-path': isPathLike }">{{ detail }}</span>
      <span v-if="imageUrls.length" class="tool-call-event__image-badge" :title="t('timeline.tool.screenshotCount', { count: imageUrls.length })"><AppIcon name="ImageIcon" :size="compact ? 11 : 12" />{{ imageUrls.length }}</span>
      <span v-if="elapsed" class="tool-call-event__elapsed"><AppIcon name="Timer" :size="10" />{{ elapsed }}</span>
      <AppIcon v-if="call.status === 'running'" name="LoaderCircle" class="spin" :size="compact ? 12 : 13" />
      <AppIcon v-if="hasDetails" name="ChevronDown" class="timeline-row__chevron" :size="11" />
    </button>
    <transition name="tool-expand">
      <div v-if="isOpen && hasDetails" class="tool-call-event__details">
        <b>{{ call.status === 'running' ? t('timeline.tool.params') : t('timeline.tool.input') }}</b><pre>{{ request }}</pre>
        <template v-if="rawOutput">
          <b>{{ t('timeline.tool.output') }}</b>
          <pre>{{ outputToShow }}</pre>
          <button v-if="isOutputTruncated" class="toggle-output-btn" @click.stop="showFullOutput = !showFullOutput">
            {{ showFullOutput ? t('timeline.tool.collapseOutput') : t('timeline.tool.expandOutput') }}
          </button>
        </template>
        <template v-if="imageUrls.length">
          <b>{{ t('timeline.tool.screenshots') }}</b>
          <div class="tool-call-event__images">
            <img
              v-for="(url, index) in imageUrls"
              :key="index"
              :src="url"
              :class="{ zoomed: zoomedImage === index }"
              :alt="t('timeline.tool.screenshotAlt', { index: index + 1 })"
              @click="zoomedImage = zoomedImage === index ? null : index"
            />
          </div>
        </template>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.tool-call-event {
  font-size: 12px;
}

.tool-call-event > button {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: 24px;
  padding: 3px 4px;
  color: #6b7280;
  background: transparent;
  border: 0;
  border-radius: 3px;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s ease;
}

.tool-call-event > button:disabled {
  cursor: default;
}

.tool-call-event > button:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.04);
}

.tool-call-event > button > svg:first-child {
  flex: 0 0 auto;
  color: #9ca3af;
}

.tool-call-event.running > button > svg:first-child,
.tool-call-event.running .spin {
  color: #2563eb;
}

.tool-call-event.done > button > svg:first-child {
  color: #16a34a;
}

/* 失败使用橙色 warning 语义（项目约定：不用红色表达操作失败） */
.tool-call-event.failed > button {
  color: #b45309;
}

.tool-call-event.failed > button > svg:first-child {
  color: #d97706;
}

.tool-call-event__action {
  flex: 0 0 auto;
  color: #4b5563;
  font-weight: 500;
}

.timeline-row__separator {
  flex: 0 0 auto;
  color: #d1d5db;
}

.tool-call-event__detail {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #6b7280;
  font-family: "SF Mono", Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-event__detail.is-path {
  color: #4b5563;
}

.tool-call-event__elapsed {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: 0 0 auto;
  color: #9ca3af;
  font: 10px Consolas, monospace;
}

.tool-call-event__image-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: 0 0 auto;
  padding: 1px 5px;
  color: #6b7280;
  background: #f3f4f6;
  border-radius: 3px;
  font: 10px Consolas, monospace;
}

.tool-call-event__images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tool-call-event__images img {
  max-width: 240px;
  max-height: 160px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  cursor: zoom-in;
  object-fit: contain;
}

.tool-call-event__images img.zoomed {
  max-width: 100%;
  max-height: none;
  cursor: zoom-out;
}

.timeline-row__chevron {
  flex: 0 0 auto;
  margin-left: auto;
  color: #d1d5db;
  transition: transform 0.15s ease, opacity 0.15s ease;
  opacity: 0;
}

.tool-call-event > button:hover:not(:disabled) .timeline-row__chevron,
.tool-call-event.open .timeline-row__chevron {
  opacity: 1;
}

.tool-call-event.open .timeline-row__chevron {
  transform: rotate(180deg);
}

.tool-call-event__details {
  margin: 2px 0 4px 20px;
  padding-left: 8px;
  border-left: 1px solid #e5e7eb;
}

.tool-call-event__details > b {
  display: block;
  margin: 6px 0 3px;
  color: #9ca3af;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.tool-call-event__details > b:first-child {
  margin-top: 2px;
}

.tool-call-event__details pre {
  max-height: 180px;
  margin: 0;
  padding: 6px 8px;
  overflow: auto;
  color: #374151;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  border-radius: 4px;
  font: 11px/1.5 "SF Mono", Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.toggle-output-btn {
  display: inline-block;
  margin: 4px 0 0;
  padding: 2px 8px;
  color: #6b7280;
  background: transparent;
  border: 1px solid #e5e7eb;
  border-radius: 3px;
  font-size: 10px;
  cursor: pointer;
  transition: all 0.1s ease;
}

.toggle-output-btn:hover {
  color: #2563eb;
  border-color: #2563eb;
  background: rgba(37, 99, 235, 0.05);
}

/* Compact 模式（在分组内展开时） */
.tool-call-event.compact > button {
  min-height: 22px;
  gap: 5px;
  padding: 2px 4px;
}

.tool-call-event.compact .tool-call-event__detail {
  font-size: 11px;
}

/* 暗色主题 */
:global([data-app-theme="dark"]) .tool-call-event > button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.06);
}

:global([data-app-theme="dark"]) .tool-call-event.running > button > svg:first-child,
:global([data-app-theme="dark"]) .tool-call-event.running .spin {
  color: #60a5fa;
}

:global([data-app-theme="dark"]) .tool-call-event.done > button > svg:first-child {
  color: #4ade80;
}

:global([data-app-theme="dark"]) .tool-call-event.failed > button {
  color: #fd9851;
}

:global([data-app-theme="dark"]) .tool-call-event.failed > button > svg:first-child {
  color: #fd9851;
}

:global([data-app-theme="dark"]) .tool-call-event__action {
  color: #d1d5db;
}

:global([data-app-theme="dark"]) .timeline-row__separator {
  color: #4b5563;
}

:global([data-app-theme="dark"]) .tool-call-event__detail {
  color: #9ca3af;
}

:global([data-app-theme="dark"]) .tool-call-event__detail.is-path {
  color: #d1d5db;
}

:global([data-app-theme="dark"]) .tool-call-event__elapsed {
  color: #6b7280;
}

:global([data-app-theme="dark"]) .tool-call-event__image-badge {
  color: #9ca3af;
  background: #1f2937;
}

:global([data-app-theme="dark"]) .tool-call-event__images img {
  background: #111827;
  border-color: #374151;
}

:global([data-app-theme="dark"]) .timeline-row__chevron {
  color: #6b7280;
}

:global([data-app-theme="dark"]) .tool-call-event__details {
  border-left-color: #374151;
}

:global([data-app-theme="dark"]) .tool-call-event__details > b {
  color: #6b7280;
}

:global([data-app-theme="dark"]) .tool-call-event__details pre {
  color: #d1d5db;
  background: #1f2937;
  border-color: #374151;
}

:global([data-app-theme="dark"]) .toggle-output-btn {
  color: #9ca3af;
  border-color: #374151;
}

:global([data-app-theme="dark"]) .toggle-output-btn:hover {
  color: #60a5fa;
  border-color: #60a5fa;
  background: rgba(96, 165, 250, 0.1);
}

/* 展开/折叠动画 */
.tool-expand-enter-active,
.tool-expand-leave-active {
  transition: all 0.12s ease;
  overflow: hidden;
}

.tool-expand-enter-from,
.tool-expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
  margin-bottom: 0;
}

.tool-expand-enter-to,
.tool-expand-leave-from {
  opacity: 1;
  max-height: 300px;
}

/* 运行中光带效果（仅非compact模式显示） */
.tool-call-event.running:not(.compact) {
  position: relative;
  overflow: hidden;
}

.tool-call-event.running:not(.compact)::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 200px;
  pointer-events: none;
  background: linear-gradient(90deg, transparent 0%, rgb(255 255 255 / 40%) 50%, transparent 100%);
  animation: tool-sweep 2s ease-out infinite;
}

@keyframes tool-sweep {
  0% { left: -200px; }
  90%, 100% { left: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .tool-expand-enter-active,
  .tool-expand-leave-active {
    transition: none;
  }

  .tool-call-event.running:not(.compact)::after {
    animation: none;
  }
}
</style>
