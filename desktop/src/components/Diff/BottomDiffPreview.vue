<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { ChevronDown, ChevronUp, FileDiff, RotateCcw, Search } from "@lucide/vue";
import { changeDiff, listChanges, revertChanges, type ChangeSummary } from "../../services/sztu-runtime";

// 会话区底部常驻的迷你 diff 预览条：展示最近一个已完成 run 的改动汇总，可展开查看文件级 diff
const props = defineProps<{
  workspaceId: string | null;
  runId: string | null;
  paths: string[];
}>();

const emit = defineEmits<{
  reverted: [runId: string];
  review: [ctx: { workspaceId: string; runId: string; paths: string[] }];
}>();

const changes = ref<ChangeSummary[]>([]);
const loading = ref(false);
const reverting = ref(false);
const open = ref(false);
const selected = ref("");
const diff = ref("");
const loadingDiff = ref(false);
const diffError = ref("");

// 拉取该 run 的改动明细与增减行统计（runId 变化时自动刷新并收起）
async function load() {
  if (!props.workspaceId || !props.runId) {
    changes.value = [];
    return;
  }
  loading.value = true;
  try {
    const all = await listChanges(props.workspaceId, props.runId);
    changes.value = props.paths.length
      ? all.filter((change) => props.paths.includes(change.path))
      : all;
  } catch {
    changes.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.workspaceId, props.runId, props.paths] as const,
  () => {
    open.value = false;
    selected.value = "";
    diff.value = "";
    diffError.value = "";
    void load();
  },
  { immediate: true },
);

const totalAdd = computed(() => changes.value.reduce((sum, change) => sum + (change.additions ?? 0), 0));
const totalDel = computed(() => changes.value.reduce((sum, change) => sum + (change.deletions ?? 0), 0));
const resolvedPaths = computed(() => changes.value.map((change) => change.path));

// 展开/收起抽屉，首次展开时默认选中第一个文件
async function toggleOpen() {
  open.value = !open.value;
  if (open.value && !selected.value && changes.value.length) await select(changes.value[0].path);
}

// 选中文件并加载其 diff，按行拆分以便着色
async function select(path: string) {
  if (loadingDiff.value || !props.workspaceId || path === selected.value) return;
  selected.value = path;
  loadingDiff.value = true;
  diffError.value = "";
  try {
    diff.value = await changeDiff(props.workspaceId, path, props.runId);
  } catch (error) {
    diffError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loadingDiff.value = false;
  }
}

const diffLines = computed(() =>
  diff.value.split("\n").map((line) => ({
    text: line,
    kind: line.startsWith("+++") || line.startsWith("---")
      ? "meta"
      : line.startsWith("@@")
        ? "hunk"
        : line.startsWith("+")
          ? "add"
          : line.startsWith("-")
            ? "del"
            : "ctx",
  })),
);

// 一键回滚该 run 的全部文件改动并通知上层刷新
async function revertAll() {
  if (reverting.value || !props.workspaceId || !props.runId || !resolvedPaths.value.length) return;
  if (!window.confirm("撤销本次 AI 的全部文件改动？")) return;
  reverting.value = true;
  try {
    await revertChanges(props.workspaceId, props.runId, resolvedPaths.value);
    emit("reverted", props.runId);
  } finally {
    reverting.value = false;
  }
}

// 进入统一的 Git 源代码管理页
function openReview() {
  if (!props.workspaceId || !props.runId || !resolvedPaths.value.length) return;
  emit("review", { workspaceId: props.workspaceId, runId: props.runId, paths: resolvedPaths.value });
}
</script>

<template>
  <section v-if="changes.length || loading" class="bottom-diff-preview" :class="{ open }">
    <button type="button" class="bottom-diff-preview__bar" :aria-expanded="open" @click="toggleOpen">
      <span class="bottom-diff-preview__icon"><FileDiff :size="14" /></span>
      <b>本轮修改 {{ changes.length }} 个文件</b>
      <span v-if="loading" class="bottom-diff-preview__loading">加载中…</span>
      <span v-else class="bottom-diff-preview__totals">
        <em class="add">+{{ totalAdd }}</em>
        <em class="del">−{{ totalDel }}</em>
      </span>
      <span class="bottom-diff-preview__actions">
        <button
          type="button"
          class="bottom-diff-preview__action"
          :disabled="reverting || !changes.length"
          @click.stop="revertAll"
        >
          <RotateCcw :size="12" />回滚
        </button>
        <button
          type="button"
          class="bottom-diff-preview__action"
          :disabled="!changes.length"
          @click.stop="openReview"
        >
          <Search :size="12" />查看变更
        </button>
      </span>
      <ChevronUp v-if="open" class="bottom-diff-preview__chevron" :size="14" />
      <ChevronDown v-else class="bottom-diff-preview__chevron" :size="14" />
    </button>

    <div v-if="open" class="bottom-diff-preview__drawer">
      <div class="bottom-diff-preview__files">
        <button
          v-for="change in changes"
          :key="change.path"
          type="button"
          class="bottom-diff-preview__file"
          :class="{ selected: selected === change.path }"
          :title="change.path"
          @click="select(change.path)"
        >
          <span class="bottom-diff-preview__path">{{ change.path }}</span>
          <span class="bottom-diff-preview__nums">
            <em v-if="(change.additions ?? 0) > 0" class="add">+{{ change.additions }}</em>
            <em v-if="(change.deletions ?? 0) > 0" class="del">−{{ change.deletions }}</em>
          </span>
        </button>
      </div>
      <div class="bottom-diff-preview__diff">
        <span v-if="loadingDiff" class="bottom-diff-preview__hint">加载 diff…</span>
        <span v-else-if="diffError" class="bottom-diff-preview__hint error">{{ diffError }}</span>
        <span v-else-if="!diff" class="bottom-diff-preview__hint">选择文件查看 diff</span>
        <div v-else class="bottom-diff-preview__code">
          <span
            v-for="(line, i) in diffLines"
            :key="i"
            :class="'bottom-diff-preview__' + line.kind"
          >{{ line.text || " " }}</span>
        </div>
      </div>
    </div>
  </section>
</template>
