<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, Check, FileText, RotateCw, X } from "@lucide/vue";
import { changeDiff, listChanges, revertChanges, stageChanges, type ChangeSummary } from "../../services/sztu-runtime";

const props = defineProps<{ workspaceId: string; runId: string; paths: string[] }>();
const emit = defineEmits<{ close: []; changed: [] }>();

const changes = ref<ChangeSummary[]>([]);
const selected = ref("");
const diff = ref("");
const accepted = ref(new Set<string>());
const rejected = ref(new Set<string>());

// —— 加载 / 错误 / 重试状态 ——
const loadingChanges = ref(false);
const changesError = ref("");
const loadingDiff = ref(false);
const diffError = ref("");
const actionError = ref("");         // accept/reject 操作失败
const busy = ref(new Set<string>()); // 正在执行 accept/reject 的文件
const busyAll = ref(false);          // 正在执行 acceptAll/rejectAll

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// 挂载时拉取该 run 的改动明细并选中第一个文件
async function loadChanges() {
  loadingChanges.value = true;
  changesError.value = "";
  try {
    const all = await listChanges(props.workspaceId, props.runId);
    changes.value = all.filter((change) => props.paths.includes(change.path));
    if (changes.value.length) await select(changes.value[0].path);
  } catch (error) {
    // 请求失败时保留当前已加载内容；首次加载失败则展示错误与重试入口
    changesError.value = messageOf(error);
    if (!changes.value.length) selected.value = "";
  } finally {
    loadingChanges.value = false;
  }
}
onMounted(loadChanges);

const pending = computed(() => changes.value.filter(
  (change) => !accepted.value.has(change.path) && !rejected.value.has(change.path),
));

// 切换选中文件并加载其 diff；失败时保留当前 diff 与选中文件，仅展示内联错误
async function select(path: string) {
  if (accepted.value.has(path) || rejected.value.has(path)) return;
  if (loadingDiff.value) return; // 正在加载时忽略重复切换，避免并发写 diff
  selected.value = path;
  loadingDiff.value = true;
  diffError.value = "";
  try {
    diff.value = await changeDiff(props.workspaceId, path, props.runId);
  } catch (error) {
    diffError.value = messageOf(error);
  } finally {
    loadingDiff.value = false;
  }
}

async function retryDiff() {
  if (!selected.value) return;
  await select(selected.value);
}

// 接受：把文件加入 git 暂存区（保留改动待提交）
async function accept(path: string) {
  if (busy.value.has(path)) return;
  busy.value = new Set([...busy.value, path]);
  actionError.value = "";
  try {
    await stageChanges(props.workspaceId, [path]);
    accepted.value = new Set([...accepted.value, path]);
    if (selected.value === path) { selected.value = ""; diff.value = ""; }
    emit("changed");
  } catch (error) {
    // 失败时不标记为已暂存，展示内联错误供用户重试
    actionError.value = `接受失败：${messageOf(error)}`;
  } finally {
    busy.value = new Set([...busy.value].filter((p) => p !== path));
  }
}

// 拒绝单文件：回滚改动并标记
async function reject(path: string) {
  if (busy.value.has(path)) return;
  if (!window.confirm(`拒绝并回滚该文件改动？\n${path}`)) return;
  busy.value = new Set([...busy.value, path]);
  actionError.value = "";
  try {
    await revertChanges(props.workspaceId, props.runId, [path]);
    rejected.value = new Set([...rejected.value, path]);
    if (selected.value === path) { selected.value = ""; diff.value = ""; }
    emit("changed");
  } catch (error) {
    // 失败时不标记为已拒绝，展示内联错误供用户重试
    actionError.value = `拒绝失败：${messageOf(error)}`;
  } finally {
    busy.value = new Set([...busy.value].filter((p) => p !== path));
  }
}

// 全部接受：把全部待审文件加入 git 暂存区
async function acceptAll() {
  const paths = pending.value.map((change) => change.path);
  if (!paths.length || busyAll.value) return;
  busyAll.value = true;
  actionError.value = "";
  try {
    await stageChanges(props.workspaceId, paths);
    accepted.value = new Set([...accepted.value, ...paths]);
    selected.value = ""; diff.value = "";
    emit("changed");
  } catch (error) {
    actionError.value = `全部接受失败：${messageOf(error)}`;
  } finally {
    busyAll.value = false;
  }
}

// 全部拒绝：回滚全部待审文件
async function rejectAll() {
  const paths = pending.value.map((change) => change.path);
  if (!paths.length || busyAll.value) return;
  if (!window.confirm("拒绝全部待审文件改动并回滚？")) return;
  busyAll.value = true;
  actionError.value = "";
  try {
    await revertChanges(props.workspaceId, props.runId, paths);
    rejected.value = new Set([...rejected.value, ...paths]);
    selected.value = ""; diff.value = "";
    emit("changed");
  } catch (error) {
    actionError.value = `全部拒绝失败：${messageOf(error)}`;
  } finally {
    busyAll.value = false;
  }
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
      <div class="diff-review__identity">
        <h1>代码变更审核</h1>
        <span class="diff-review__run">run {{ runId.slice(0, 8) }}</span>
      </div>
      <div class="diff-review__bulk-actions">
        <button type="button" class="diff-review__accept-all" :disabled="busyAll || !pending.length" @click="acceptAll">全部接受</button>
        <button type="button" class="diff-review__reject-all" :disabled="busyAll || !pending.length" @click="rejectAll">全部拒绝</button>
      </div>
    </header>
    <div class="diff-review__body">
      <aside class="diff-review__files">
        <div v-if="loadingChanges && !changes.length" class="diff-review__status">正在加载改动列表…</div>
        <div v-else-if="changesError && !changes.length" class="diff-review__status diff-review__error">
          <span>加载失败：{{ changesError }}</span>
          <button type="button" class="diff-review__retry" @click="loadChanges"><RotateCw :size="12" />重试</button>
        </div>
        <template v-else>
          <div v-for="change in changes" :key="change.path" class="diff-review__file"
               :class="{ active: selected === change.path, accepted: accepted.has(change.path), rejected: rejected.has(change.path), busy: busy.has(change.path) }">
            <button type="button" class="diff-review__file-path" :disabled="busy.has(change.path) || loadingDiff" @click="select(change.path)">
              <FileText :size="14" /><span>{{ change.path }}</span>
            </button>
            <span class="diff-review__file-nums"><em class="add">+{{ change.additions ?? 0 }}</em><em class="del">−{{ change.deletions ?? 0 }}</em></span>
            <span v-if="accepted.has(change.path)" class="diff-review__badge accepted">已暂存</span>
            <span v-else-if="rejected.has(change.path)" class="diff-review__badge rejected">已拒绝</span>
            <template v-else>
              <button type="button" class="diff-review__file-accept" :disabled="busy.has(change.path) || busyAll" title="接受并暂存" @click="accept(change.path)"><Check :size="13" /></button>
              <button type="button" class="diff-review__file-reject" :disabled="busy.has(change.path) || busyAll" title="拒绝并回滚" @click="reject(change.path)"><X :size="13" /></button>
            </template>
          </div>
          <p v-if="!changes.length" class="diff-review__empty">暂无待审文件</p>
        </template>
      </aside>
      <div class="diff-review__view">
        <div v-if="actionError" class="diff-review__inline-error">操作失败：{{ actionError }}</div>
        <p v-if="!selected" class="diff-review__empty">选择左侧文件查看差异</p>
        <template v-else>
          <div v-if="loadingDiff" class="diff-review__status">正在加载差异…</div>
          <div v-else-if="diffError && !diff" class="diff-review__status diff-review__error">
            <span>差异加载失败：{{ diffError }}</span>
            <button type="button" class="diff-review__retry" @click="retryDiff"><RotateCw :size="12" />重试</button>
          </div>
          <template v-else>
            <pre class="diff-review__pre"><code v-for="(line, index) in diffLines(diff)" :key="index" :class="line.cls">{{ line.text }}{{ '\n' }}</code></pre>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>
