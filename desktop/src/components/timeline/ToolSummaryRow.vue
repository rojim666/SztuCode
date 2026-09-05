<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";

const props = defineProps<{
  calls: ToolCallEntry[];
  running?: boolean;
  defaultOpen?: boolean;
}>();
const { t } = useI18n({ useScope: "global" });

const open = ref(!!props.defaultOpen);

// 父组件切换历史展开/折叠时，同步默认打开状态（用户手动点击过的优先级更高，通过 initialized 标志追踪）
const userToggled = ref(false);
watch(() => props.defaultOpen, (val) => {
  if (!userToggled.value) open.value = !!val;
});

type CallKind = "read" | "search" | "edit" | "exec" | "other";

function classifyCall(name: string): CallKind {
  const n = name.toLowerCase();
  if (/read(file)?|getfile|dir|ls|cat|view|show|open/i.test(n)) return "read";
  if (/glob|search|grep|find|fzf|ripgrep|scan/i.test(n)) return "search";
  if (/edit|write|patch|create|mkdir|rename|delete|rm/i.test(n)) return "edit";
  if (/bash|shell|terminal|command|powershell|pwsh|exec|run/i.test(n)) return "exec";
  return "other";
}

type GroupInfo = {
  kind: CallKind;
  icon: string;
  count: number;
  failed: number;
  isRunning: boolean;
  chipText: string;
};

const groups = computed<GroupInfo[]>(() => {
  const order: CallKind[] = ["read", "search", "edit", "exec", "other"];
  const iconMap: Record<CallKind, string> = {
    read: "FolderOpen",
    search: "FileSearch",
    edit: "Edit3",
    exec: "Terminal",
    other: "Code2",
  };

  const counts: Record<CallKind, { count: number; failed: number; running: boolean }> = {
    read:   { count: 0, failed: 0, running: false },
    search: { count: 0, failed: 0, running: false },
    edit:   { count: 0, failed: 0, running: false },
    exec:   { count: 0, failed: 0, running: false },
    other:  { count: 0, failed: 0, running: false },
  };

  for (const call of props.calls) {
    const k = classifyCall(call.name);
    counts[k].count++;
    if (call.status === "failed") counts[k].failed++;
    if (call.status === "running") counts[k].running = true;
  }

  return order
    .filter((k) => counts[k].count > 0)
    .map((k) => {
      const c = counts[k];
      // chip 文案取自语言包（timeline.toolSummary.<kind>.<running|counting|done>），computed 内调用 t 保证切换语言时重建
      const text = props.running && c.running
        ? t(`timeline.toolSummary.${k}.running`)
        : t(`timeline.toolSummary.${k}.${props.running ? "counting" : "done"}`, { count: c.count });
      return {
        kind: k,
        icon: iconMap[k],
        count: c.count,
        failed: c.failed,
        isRunning: props.running && c.running,
        chipText: text,
      };
    });
});

// 是否有失败项
const hasFailures = computed(() => groups.value.some((g) => g.failed > 0));

// 是否可展开（至少有一个调用有输出/错误/等待权限）
const expandable = computed(() =>
  props.calls.some((c) => c.output || c.error || c.status === "failed" || c.status === "awaiting_permission"),
);
</script>

<template>
  <div class="tool-summary" :class="{ open, running: running && !hasFailures, failed: hasFailures }">
    <button
      v-if="expandable"
      type="button"
      class="tool-summary__trigger"
      :aria-expanded="open"
      @click="userToggled = true; open = !open"
    >
      <span class="tool-summary__chips">
        <span v-for="g in groups" :key="g.kind" class="tool-chip" :class="`tool-chip--${g.kind}`">
          <AppIcon v-if="g.isRunning" name="LoaderCircle" class="spin" :size="13" />
          <AppIcon v-else-if="g.failed" name="AlertCircle" :size="13" />
          <AppIcon v-else :name="g.icon" :size="13" />
          <span>{{ g.chipText }}</span>
        </span>
      </span>
      <AppIcon name="ChevronRight" class="tool-summary__chevron" :size="12" />
    </button>
    <div v-else class="tool-summary__static">
      <span class="tool-summary__chips">
        <span v-for="g in groups" :key="g.kind" class="tool-chip" :class="`tool-chip--${g.kind}`">
          <AppIcon v-if="g.isRunning" name="LoaderCircle" class="spin" :size="13" />
          <AppIcon v-else-if="g.failed" name="AlertCircle" :size="13" />
          <AppIcon v-else :name="g.icon" :size="13" />
          <span>{{ g.chipText }}</span>
        </span>
      </span>
    </div>

    <transition name="tool-expand">
      <div v-if="open && expandable" class="tool-summary__body">
        <ToolCallCard v-for="call in calls" :key="call.id" :call="call" :compact="true" />
      </div>
    </transition>
  </div>
</template>

<style scoped>
.tool-summary {
  margin: 2px 0;
  font-size: 13px;
}

.tool-summary__trigger,
.tool-summary__static {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 2px 4px;
  margin: 0 -4px;
}

.tool-summary__trigger {
  background: transparent;
  border: 0;
  border-radius: 4px;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s ease;
}

.tool-summary__trigger:hover {
  background: rgba(0, 0, 0, 0.03);
}

.tool-summary__chips {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: #8c9299;
  font-size: 13px;
}

.tool-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  line-height: 1.4;
  color: #7b828c;
}

.tool-chip .spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.tool-summary.failed .tool-chip {
  color: #b45309;
}

.tool-summary.failed .tool-chip .alert-circle {
  color: #d97706;
}

.tool-summary__chevron {
  flex: 0 0 auto;
  margin-left: 2px;
  color: #b0b5bc;
  transition: transform 0.15s ease;
}

.tool-summary.open .tool-summary__chevron {
  transform: rotate(90deg);
}

.tool-summary__body {
  margin: 4px 0 4px 0;
  padding-left: 20px;
  border-left: 1px solid rgb(118 126 136 / 18%);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tool-expand-enter-active,
.tool-expand-leave-active {
  transition: all 0.15s ease;
  overflow: hidden;
}

.tool-expand-enter-from,
.tool-expand-leave-to {
  opacity: 0;
  max-height: 0;
  transform: translateY(-3px);
}

.tool-expand-enter-to,
.tool-expand-leave-from {
  opacity: 1;
  max-height: 600px;
  transform: translateY(0);
}

/* 暗色主题 */
:global([data-app-theme="dark"] .tool-summary__trigger:hover){
  background: rgba(255, 255, 255, 0.04);
}
:global([data-app-theme="dark"] .tool-summary__chips){
  color: #6b7280;
}
:global([data-app-theme="dark"] .tool-chip){
  color: #6b7280;
}
:global([data-app-theme="dark"] .tool-summary.running .tool-chip){
  color: #9ca3af;
}
:global([data-app-theme="dark"] .tool-summary.failed .tool-chip){
  color: #fbbf24;
}
:global([data-app-theme="dark"] .tool-summary__body){
  border-left-color: #374151;
}
:global([data-app-theme="dark"] .tool-summary__chevron){
  color: #4b5563;
}

@media (prefers-reduced-motion: reduce) {
  .tool-expand-enter-active,
  .tool-expand-leave-active {
    transition: none;
  }
  .tool-chip .spin {
    animation: none;
  }
}
</style>
