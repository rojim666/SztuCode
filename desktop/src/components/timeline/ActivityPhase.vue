<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Brain, Check, ChevronDown, Code2, Edit3, FolderOpen, LoaderCircle, Search, Terminal } from "@lucide/vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";

const props = defineProps<{
  thinking?: string;
  calls: ToolCallEntry[];
  running?: boolean;
  completed?: boolean;
}>();

const open = ref(false);
const hasContent = computed(() => (props.thinking && props.thinking.trim().length > 0) || props.calls.length > 0);

// 运行时自动展开，完成后自动折叠（Codex风格：运行中看过程，完成后只留最终答案）
watch(() => props.running, (isRunning) => {
  if (isRunning) {
    open.value = true;
  } else if (props.completed) {
    open.value = false;
  }
}, { immediate: true });

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

    if (!buckets[key]) {
      buckets[key] = { label, icon, count: 0 };
    }
    buckets[key].count++;
  }

  return Object.values(buckets);
});

// 摘要标签
const summaryLabel = computed(() => {
  if (props.running) {
    return props.thinking ? "思考中" : "执行中";
  }
  if (!props.calls.length && props.thinking) {
    return "思考完成";
  }
  const total = props.calls.length;
  if (total === 0) return "已完成";
  const parts = groups.value.map(g => `${g.label} ${g.count}`);
  if (props.thinking) parts.unshift("思考");
  return parts.join(" · ");
});

// 第一个工具的细节路径作为提示
const detailHint = computed(() => {
  const first = props.calls[0];
  if (!first) return "";
  const value = first.params.command ?? first.params.cmd ?? first.params.path ?? first.params.query ?? first.params.description;
  if (typeof value === "string") {
    const parts = value.split(/[\\/]/);
    return parts[parts.length - 1] || value.slice(0, 40);
  }
  return "";
});
</script>

<template>
  <div v-if="hasContent" class="activity-phase" :class="{ open, running: running, done: completed && !running }">
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

      <span v-if="!open && detailHint" class="activity-phase__hint">{{ detailHint }}</span>

      <ChevronDown v-if="hasContent" class="activity-phase__chevron" :size="11" />
    </button>

    <transition name="phase-expand">
      <div v-if="open" class="activity-phase__body">
        <!-- 思考过程（直接显示，不嵌套折叠） -->
        <div v-if="thinking" class="activity-phase__thinking">
          <div class="activity-phase__section-label">
            <Brain :size="11" /> 思考过程
          </div>
          <pre class="activity-phase__thinking-text">{{ thinking }}</pre>
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
  margin: 4px 0;
  font-size: 12px;
}

.activity-phase__trigger {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  min-height: 26px;
  padding: 3px 6px;
  margin: 0 -6px;
  color: #6b7280;
  background: transparent;
  border: 0;
  border-radius: 4px;
  font-size: 12px;
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
}

.activity-phase.running .activity-phase__status {
  color: #2563eb;
}

.activity-phase.done .activity-phase__status {
  color: #16a34a;
}

.activity-phase__label {
  flex: 0 0 auto;
  color: #4b5563;
  font-weight: 500;
}

.activity-phase.running .activity-phase__label {
  color: #2563eb;
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
  color: #9ca3af;
  transition: transform 0.18s ease;
  opacity: 0;
}

.activity-phase__trigger:hover .activity-phase__chevron,
.activity-phase.open .activity-phase__chevron {
  opacity: 1;
}

.activity-phase.open .activity-phase__chevron {
  transform: rotate(180deg);
}

.activity-phase__body {
  margin: 4px 0 6px 0;
  padding-left: 26px;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 6px;
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
  padding: 8px 10px;
  color: #6b7280;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  border-radius: 4px;
  font: 11px/1.6 "SF Mono", Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 200px;
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

@media (prefers-reduced-motion: reduce) {
  .phase-expand-enter-active,
  .phase-expand-leave-active {
    transition: none;
  }
}
</style>

