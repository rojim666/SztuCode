<script setup lang="ts">
import { computed, ref } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import type { TimelineStep } from "../timeline/types";

const props = defineProps<{
  steps: TimelineStep[];
  attachments: string[];
  workspaceName?: string;
  workspacePath?: string;
}>();

const expanded = ref(false);
const plan = computed(() => [...props.steps].reverse().find((step) => step.plan?.length)?.plan ?? []);
const completed = computed(() => plan.value.filter((item) => item.status === "completed").length);
const progress = computed(() => plan.value.length ? Math.round((completed.value / plan.value.length) * 100) : 0);

type ContextItem = { path: string; source: "attachment" | "change" | "tool" | "workspace" };

function basename(path: string) {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

const contextItems = computed<ContextItem[]>(() => {
  const items: ContextItem[] = props.attachments.map((path) => ({ path, source: "attachment" }));
  for (const step of props.steps) {
    for (const change of step.changes ?? []) {
      for (const path of change.paths) items.push({ path, source: "change" });
    }
    for (const call of step.toolCalls) {
      for (const key of ["path", "file_path", "target_path"]) {
        const value = call.params[key];
        if (typeof value === "string" && value.trim()) {
          const path = value.trim();
          if ((path === "." || path === "./") && props.workspacePath) items.push({ path: props.workspacePath, source: "workspace" });
          else items.push({ path, source: "tool" });
        }
      }
    }
  }
  if (!items.length && props.workspacePath) items.push({ path: props.workspacePath, source: "workspace" });
  return [...new Map(items.map((item) => [item.path, item])).values()];
});

const visibleContext = computed(() => expanded.value ? contextItems.value : contextItems.value.slice(0, 5));
</script>

<template>
  <aside class="work-context-panel" aria-label="任务进度与上下文">
    <section class="work-context-card progress-card">
      <header><AppIcon name="ListChecks" :size="16" /><h2>进度</h2><span v-if="plan.length">{{ completed }}/{{ plan.length }}</span></header>
      <div v-if="plan.length" class="progress-meter" :style="{ '--progress': progress + '%' }">
        <i /><span>{{ progress }}%</span>
      </div>
      <ol v-if="plan.length" class="progress-list">
        <li v-for="item in plan" :key="item.id" :class="item.status">
          <span class="progress-state"><AppIcon name="Check" v-if="item.status === 'completed'" :size="11" /><AppIcon name="Circle" v-else :size="9" /></span>
          <span>{{ item.subject }}</span>
        </li>
      </ol>
      <div v-else class="context-empty progress-empty"><span><i /><i /></span><p>任务计划会显示在这里</p></div>
    </section>

    <section class="work-context-card context-card">
      <header><AppIcon name="FolderOpen" :size="16" /><h2>上下文</h2><span>{{ contextItems.length }}</span></header>
      <div v-if="contextItems.length" class="context-list">
        <div v-for="item in visibleContext" :key="item.path" class="context-file" :title="item.path">
          <AppIcon name="Paperclip" v-if="item.source === 'attachment'" :size="15" />
          <AppIcon name="FolderOpen" v-else-if="item.source === 'workspace'" :size="15" />
          <AppIcon name="FileText" v-else :size="15" />
          <span><b>{{ item.source === 'workspace' ? (workspaceName || basename(item.path)) : basename(item.path) }}</b><small>{{ item.path }}</small></span>
        </div>
        <button v-if="contextItems.length > 5" class="context-expand" type="button" @click="expanded = !expanded">
          <AppIcon name="ChevronDown" :size="14" :class="{ expanded }" />{{ expanded ? '收起' : '展开 ' + (contextItems.length - 5) + ' 个' }}
        </button>
      </div>
      <div v-else class="context-empty"><AppIcon name="FileText" :size="22" /><p>相关文件会显示在这里</p></div>
    </section>
  </aside>
</template>
