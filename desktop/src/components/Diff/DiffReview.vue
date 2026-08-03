<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, Check, FileText, X } from "@lucide/vue";
import { changeDiff, listChanges, revertChanges, stageChanges, type ChangeSummary } from "../../services/sztu-runtime";

const props = defineProps<{ workspaceId: string; runId: string; paths: string[] }>();
const emit = defineEmits<{ close: []; changed: [] }>();

const changes = ref<ChangeSummary[]>([]);
const selected = ref("");
const diff = ref("");
const accepted = ref(new Set<string>());
const rejected = ref(new Set<string>());

// 挂载时拉取该 run 的改动明细并选中第一个文件
async function loadChanges() {
  const all = await listChanges(props.workspaceId, props.runId);
  changes.value = all.filter((change) => props.paths.includes(change.path));
  if (changes.value.length) select(changes.value[0].path);
}
onMounted(loadChanges);

const pending = computed(() => changes.value.filter(
  (change) => !accepted.value.has(change.path) && !rejected.value.has(change.path),
));

// 切换选中文件并加载其 diff
async function select(path: string) {
  if (accepted.value.has(path) || rejected.value.has(path)) return;
  selected.value = path;
  diff.value = await changeDiff(props.workspaceId, path);
}

// 接受：把文件加入 git 暂存区（保留改动待提交）
async function accept(path: string) {
  try {
    await stageChanges(props.workspaceId, [path]);
  } catch (error) {
    window.alert(error instanceof Error ? error.message : String(error));
    return;
  }
  accepted.value = new Set([...accepted.value, path]);
  if (selected.value === path) { selected.value = ""; diff.value = ""; }
  emit("changed");
}

// 拒绝单文件：回滚改动并标记
async function reject(path: string) {
  if (!window.confirm(`拒绝并回滚该文件改动？\n${path}`)) return;
  await revertChanges(props.workspaceId, props.runId, [path]);
  rejected.value = new Set([...rejected.value, path]);
  if (selected.value === path) { selected.value = ""; diff.value = ""; }
  emit("changed");
}

// 全部接受：把全部待审文件加入 git 暂存区
async function acceptAll() {
  const paths = pending.value.map((change) => change.path);
  if (!paths.length) return;
  try {
    await stageChanges(props.workspaceId, paths);
  } catch (error) {
    window.alert(error instanceof Error ? error.message : String(error));
    return;
  }
  accepted.value = new Set([...accepted.value, ...paths]);
  selected.value = ""; diff.value = "";
  emit("changed");
}

// 全部拒绝：回滚全部待审文件
async function rejectAll() {
  const paths = pending.value.map((change) => change.path);
  if (!paths.length) return;
  if (!window.confirm("拒绝全部待审文件改动并回滚？")) return;
  await revertChanges(props.workspaceId, props.runId, paths);
  rejected.value = new Set([...rejected.value, ...paths]);
  selected.value = ""; diff.value = "";
  emit("changed");
}

// 将统一 diff 文本拆成带样式的行
function diffLines(text: string) {
  return text.split("\n").map((line) => {
    if (line.startsWith("+++") || line.startsWith("---")) return { text: line, cls: "meta" };
    if (line.startsWith("+")) return { text: line, cls: "add" };
    if (line.startsWith("-")) return { text: line, cls: "del" };
    if (line.startsWith("@@")) return { text: line, cls: "hunk" };
    if (line.startsWith("diff ") || line.startsWith("index ")) return { text: line, cls: "meta" };
    return { text: line, cls: "" };
  });
}
</script>

<template>
  <div class="diff-review">
    <header class="diff-review__top">
      <button type="button" class="diff-review__back" @click="emit('close')"><ArrowLeft :size="16" />返回</button>
      <h1>代码变更审核</h1>
      <span class="diff-review__run">run {{ runId.slice(0, 8) }}</span>
      <button type="button" class="diff-review__accept-all" @click="acceptAll">全部接受</button>
      <button type="button" class="diff-review__reject-all" @click="rejectAll">全部拒绝</button>
    </header>
    <div class="diff-review__body">
      <aside class="diff-review__files">
        <div v-for="change in changes" :key="change.path" class="diff-review__file"
             :class="{ active: selected === change.path, accepted: accepted.has(change.path), rejected: rejected.has(change.path) }">
          <button type="button" class="diff-review__file-path" @click="select(change.path)">
            <FileText :size="14" /><span>{{ change.path }}</span>
          </button>
          <span class="diff-review__file-nums"><em class="add">+{{ change.additions ?? 0 }}</em><em class="del">−{{ change.deletions ?? 0 }}</em></span>
          <span v-if="accepted.has(change.path)" class="diff-review__badge accepted">已暂存</span>
          <span v-else-if="rejected.has(change.path)" class="diff-review__badge rejected">已拒绝</span>
          <template v-else>
            <button type="button" class="diff-review__file-accept" title="接受并暂存" @click="accept(change.path)"><Check :size="13" /></button>
            <button type="button" class="diff-review__file-reject" title="拒绝并回滚" @click="reject(change.path)"><X :size="13" /></button>
          </template>
        </div>
        <p v-if="!changes.length" class="diff-review__empty">暂无待审文件</p>
      </aside>
      <div class="diff-review__view">
        <p v-if="!selected" class="diff-review__empty">选择左侧文件查看差异</p>
        <pre v-else class="diff-review__pre"><code v-for="(line, index) in diffLines(diff)" :key="index" :class="line.cls">{{ line.text }}{{ '\n' }}</code></pre>
      </div>
    </div>
  </div>
</template>
