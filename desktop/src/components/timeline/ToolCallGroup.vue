<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Check, ChevronDown, Code2, Edit3, FileSearch, FolderOpen, LoaderCircle, Search, Terminal } from "@lucide/vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";

const props = defineProps<{ calls: ToolCallEntry[] }>();
const open = ref(false);

const running = computed(() => props.calls.some((call) => call.status === "running"));
const allDone = computed(() => props.calls.every((call) => call.status === "done" || call.status === "failed"));

// Codex 风格：按工具类型分组统计
const groups = computed(() => {
  const buckets: Record<string, { label: string; icon: typeof Terminal; count: number; calls: ToolCallEntry[] }> = {};

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
      key = "other"; label = "操作"; icon = Code2;
    }

    if (!buckets[key]) {
      buckets[key] = { label, icon, count: 0, calls: [] };
    }
    buckets[key].count++;
    buckets[key].calls.push(call);
  }

  return Object.values(buckets);
});

// 有工具在运行时自动展开，完成后自动折叠保持紧凑（Codex风格：运行中展开看详情，完成后折叠成一行）
watch(running, (isRunning) => {
  if (isRunning) {
    open.value = true;
  } else if (allDone.value) {
    open.value = false;
  }
}, { immediate: true });

// 提取一个代表性的细节路径
const detailPath = computed(() => {
  const first = props.calls[0];
  if (!first) return "";
  const value = first.params.command ?? first.params.cmd ?? first.params.path ?? first.params.query ?? first.params.description;
  if (typeof value === "string") {
    // 只取文件名部分
    const parts = value.split(/[\\/]/);
    return parts[parts.length - 1] || value;
  }
  return "";
});
</script>

<template>
  <div v-if="calls.length" class="tool-call-group" :class="{ open, running }">
    <button
      type="button"
      class="tool-call-group__trigger"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="tool-call-group__status">
        <LoaderCircle v-if="running" class="spin" :size="13" />
        <Check v-else-if="allDone" :size="13" />
        <FolderOpen v-else :size="13" />
      </span>

      <div class="tool-call-group__summary">
        <template v-for="(group, idx) in groups" :key="group.label">
          <span class="tool-call-group__item">
            <component :is="group.icon" :size="11" />
            {{ group.label }} <b>{{ group.count }}</b>
          </span>
          <span v-if="idx < groups.length - 1" class="tool-call-group__sep">·</span>
        </template>
      </div>

      <span v-if="!open && detailPath" class="tool-call-group__detail">{{ detailPath }}</span>

      <ChevronDown class="tool-call-group__chevron" :size="12" />
    </button>

    <transition name="tool-group-expand">
      <div v-if="open" class="tool-call-group__body">
        <ToolCallCard v-for="call in calls" :key="call.id" :call="call" :compact="true" />
      </div>
    </transition>
  </div>
</template>

<style scoped>
.tool-call-group {
  margin: 6px 0;
  font-size: 12px;
}

.tool-call-group__trigger {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 4px 6px;
  color: #6b7280;
  background: transparent;
  border: 0;
  border-radius: 4px;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}

.tool-call-group__trigger:hover {
  background: rgba(0, 0, 0, 0.04);
}

.tool-call-group__status {
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 4px;
}

.tool-call-group.running .tool-call-group__status {
  color: #2563eb;
}

.tool-call-group:not(.running) .tool-call-group__status {
  color: #16a34a;
}

.tool-call-group__summary {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  font-weight: 500;
}

.tool-call-group__item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.tool-call-group__item b {
  font-weight: 600;
  color: #374151;
}

.tool-call-group__sep {
  color: #d1d5db;
}

.tool-call-group__detail {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #9ca3af;
  font-family: "SF Mono", Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-group__chevron {
  flex: 0 0 auto;
  margin-left: auto;
  color: #9ca3af;
  transition: transform 0.18s ease;
}

.tool-call-group.open .tool-call-group__chevron {
  transform: rotate(180deg);
}

.tool-call-group__body {
  margin: 4px 0 2px 24px;
  padding-left: 10px;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.tool-group-expand-enter-active,
.tool-group-expand-leave-active {
  transition: all 0.15s ease;
  overflow: hidden;
}

.tool-group-expand-enter-from,
.tool-group-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.tool-group-expand-enter-to,
.tool-group-expand-leave-from {
  opacity: 1;
  max-height: 600px;
}

:global(.dark) .tool-call-group__trigger:hover {
  background: rgba(255, 255, 255, 0.06);
}

:global(.dark) .tool-call-group__status {
  color: #60a5fa;
}

:global(.dark) .tool-call-group:not(.running) .tool-call-group__status {
  color: #4ade80;
}

:global(.dark) .tool-call-group__item b {
  color: #e5e7eb;
}

:global(.dark) .tool-call-group__sep {
  color: #4b5563;
}

:global(.dark) .tool-call-group__detail {
  color: #6b7280;
}

:global(.dark) .tool-call-group__chevron {
  color: #6b7280;
}

:global(.dark) .tool-call-group__body {
  border-left-color: #374151;
}

@media (prefers-reduced-motion: reduce) {
  .tool-group-expand-enter-active,
  .tool-group-expand-leave-active {
    transition: none;
  }
}
</style>
