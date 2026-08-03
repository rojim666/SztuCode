<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { FileText, RotateCcw, Search } from "@lucide/vue";
import { listChanges, revertChanges, type ChangeSummary } from "../../services/sztu-runtime";

const props = defineProps<{ workspaceId: string; runId: string; paths: string[] }>();
const emit = defineEmits<{
  reverted: [runId: string];
  review: [ctx: { workspaceId: string; runId: string; paths: string[] }];
}>();

const changes = ref<ChangeSummary[]>([]);
const loading = ref(false);
const reverting = ref(false);

// 挂载时拉取该 run 的 agent 改动及其增减行统计
async function load() {
  loading.value = true;
  try {
    const all = await listChanges(props.workspaceId, props.runId);
    changes.value = all.filter((change) => props.paths.includes(change.path));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const totalAdd = computed(() => changes.value.reduce((sum, change) => sum + (change.additions ?? 0), 0));
const totalDel = computed(() => changes.value.reduce((sum, change) => sum + (change.deletions ?? 0), 0));

// 一键回滚该 run 的全部文件改动并通知上层销毁卡片
async function revertAll() {
  if (reverting.value || !changes.value.length) return;
  if (!window.confirm("撤销本次 AI 的全部文件改动？")) return;
  reverting.value = true;
  try {
    await revertChanges(props.workspaceId, props.runId, props.paths);
    emit("reverted", props.runId);
  } finally {
    reverting.value = false;
  }
}

function openReview() {
  emit("review", { workspaceId: props.workspaceId, runId: props.runId, paths: props.paths });
}
</script>

<template>
  <section class="change-review-card">
    <header class="change-review-card__head">
      <div class="change-review-card__title">
        <span class="change-review-card__icon"><FileText :size="16" /></span>
        <b>已编辑 {{ changes.length }} 个文件</b>
        <span v-if="loading" class="change-review-card__loading">加载中…</span>
        <span v-else class="change-review-card__totals">
          <em class="add">+{{ totalAdd }}</em>
          <em class="del">−{{ totalDel }}</em>
        </span>
      </div>
      <div class="change-review-card__actions">
        <button type="button" class="change-review-card__revert" :disabled="reverting || !changes.length" @click="revertAll">
          <RotateCcw :size="13" />撤销
        </button>
        <button type="button" class="change-review-card__review" :disabled="!changes.length" @click="openReview">
          <Search :size="13" />审核
        </button>
      </div>
    </header>
    <ul v-if="changes.length" class="change-review-card__files">
      <li v-for="change in changes" :key="change.path" :title="change.path">
        <span class="change-review-card__path">{{ change.path }}</span>
        <span class="change-review-card__nums">
          <em v-if="(change.additions ?? 0) > 0" class="add">+{{ change.additions }}</em>
          <em v-if="(change.deletions ?? 0) > 0" class="del">−{{ change.deletions }}</em>
        </span>
      </li>
    </ul>
  </section>
</template>
