<script setup lang="ts">
import { ref, watch } from "vue";

import { listChanges, type ChangeSummary } from "../../services/sztu-runtime";

const props = defineProps<{
  workspaceId: string | null;
  runId: string | null;
  paths: string[];
}>();

const changes = ref<ChangeSummary[]>([]);

async function load() {
  if (!props.workspaceId || !props.runId) {
    changes.value = [];
    return;
  }
  try {
    const all = await listChanges(props.workspaceId, props.runId);
    changes.value = props.paths.length
      ? all.filter((change) => props.paths.includes(change.path))
      : all;
  } catch {
    changes.value = [];
  }
}

watch(
  () => `${props.workspaceId ?? ""}|${props.runId ?? ""}|${props.paths.join("\u0000")}`,
  () => void load(),
  { immediate: true },
);
</script>

<template>
  <section v-if="changes.length" class="change-summary-rail" aria-label="本轮文件修改数量" aria-live="polite">
    <span class="change-summary-rail__line"><span>修改了</span><strong>{{ changes.length }}</strong><span>个文件</span></span>
  </section>
</template>
