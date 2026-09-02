<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ArrowLeft, Check, GitBranch, RefreshCw, Search, X } from "@lucide/vue";
import GitGraph from "./GitGraph.vue";
import { changeDiff, commitChanges, discardChanges, gitHistory, listChanges, stageChanges, unstageChanges, workspaceStatus, type ChangeSummary, type GitCommitEntry, type WorkspaceStatus } from "../../services/sztu-runtime";
import { loadCommitDraft, saveCommitDraft } from "../../utils/sourceControlDraft";

const props = defineProps<{ workspaceId: string; workspaceName: string; workspacePath: string }>();
const emit = defineEmits<{ close: []; changed: [] }>();
const status = ref<WorkspaceStatus | null>(null);
const changes = ref<ChangeSummary[]>([]);
const selectedPath = ref("");
const diff = ref("");
const query = ref("");
const loading = ref(false);
const diffLoading = ref(false);
const error = ref("");
const busyPath = ref("");
const commitMessage = ref("");
const committing = ref(false);
const commitNotice = ref("");
const view = ref<"changes" | "graph">("changes");
const commits = ref<GitCommitEntry[]>([]);
const graphLoading = ref(false);
const graphLoadingMore = ref(false);
const graphHasMore = ref(false);
const initialGraphPageSize = 40;
const olderGraphPageSize = 100;
const filteredChanges = computed(() => {
  const value = query.value.trim().toLocaleLowerCase();
  return value ? changes.value.filter((item) => item.path.toLocaleLowerCase().includes(value)) : changes.value;
});
const changeGroups = computed(() => [
  { key: "staged", label: "已暂存的更改", items: filteredChanges.value.filter(isStaged) },
  { key: "unstaged", label: "未暂存的更改", items: filteredChanges.value.filter((item) => !isStaged(item)) },
].filter((group) => group.items.length));
const additions = computed(() => changes.value.reduce((sum, item) => sum + Number(item.additions ?? 0), 0));
const deletions = computed(() => changes.value.reduce((sum, item) => sum + Number(item.deletions ?? 0), 0));
const selected = computed(() => changes.value.find((item) => item.path === selectedPath.value) ?? null);
const diffLines = computed(() => diff.value ? diff.value.split(/\r?\n/) : []);
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : String(reason); }
function fileStatus(item: ChangeSummary) { return item.index_status !== " " && item.index_status !== "?" ? item.index_status : item.worktree_status !== " " ? item.worktree_status : item.index_status || item.worktree_status || "M"; }
function statusLabel(item: ChangeSummary) { const value = fileStatus(item); return value === "A" ? "新增" : value === "D" ? "删除" : value === "R" ? "重命名" : value === "?" ? "未跟踪" : "修改"; }
function isStaged(item: ChangeSummary) { return item.index_status !== " " && item.index_status !== "?"; }
async function select(path: string) { if (!path || diffLoading.value) return; selectedPath.value = path; diffLoading.value = true; error.value = ""; try { diff.value = await changeDiff(props.workspaceId, path); } catch (reason) { diff.value = ""; error.value = messageOf(reason); } finally { diffLoading.value = false; } }
async function refresh() { loading.value = true; error.value = ""; try { const [nextStatus, nextChanges] = await Promise.all([workspaceStatus(props.workspaceId), listChanges(props.workspaceId)]); status.value = nextStatus; changes.value = nextChanges; if (!nextChanges.some((item) => item.path === selectedPath.value)) selectedPath.value = nextChanges[0]?.path ?? ""; if (selectedPath.value) await select(selectedPath.value); } catch (reason) { error.value = messageOf(reason); } finally { loading.value = false; } }
async function stage(path: string) { if (!path || busyPath.value) return; busyPath.value = path; error.value = ""; try { await stageChanges(props.workspaceId, [path]); await refresh(); emit("changed"); } catch (reason) { error.value = `暂存失败：${messageOf(reason)}`; } finally { busyPath.value = ""; } }
async function unstage(path: string) { if (!path || busyPath.value) return; busyPath.value = path; error.value = ""; try { await unstageChanges(props.workspaceId, [path]); await refresh(); emit("changed"); } catch (reason) { error.value = `取消暂存失败：${messageOf(reason)}`; } finally { busyPath.value = ""; } }
async function discard(path: string) { if (!path || busyPath.value || !window.confirm(`放弃 ${path} 的已跟踪改动？`)) return; busyPath.value = path; error.value = ""; try { await discardChanges(props.workspaceId, [path]); await refresh(); emit("changed"); } catch (reason) { error.value = `放弃改动失败：${messageOf(reason)}`; } finally { busyPath.value = ""; } }
async function commit() { const message = commitMessage.value.trim(); if (!message || committing.value) return; committing.value = true; error.value = ""; commitNotice.value = ""; try { const hash = await commitChanges(props.workspaceId, message); commitMessage.value = ""; commitNotice.value = hash ? `已提交 ${hash}` : "提交完成"; await refresh(); emit("changed"); } catch (reason) { error.value = `提交失败：${messageOf(reason)}`; } finally { committing.value = false; } }
async function loadGraph(reset = true) {
  if ((reset && graphLoading.value) || (!reset && (graphLoadingMore.value || !graphHasMore.value))) return;
  if (reset) graphLoading.value = true; else graphLoadingMore.value = true;
  error.value = "";
  try {
    const page = await gitHistory(
      props.workspaceId,
      reset ? initialGraphPageSize : olderGraphPageSize,
      reset ? 0 : commits.value.length,
    );
    if (reset) commits.value = page.commits;
    else {
      const known = new Set(commits.value.map((commit) => commit.hash));
      commits.value = [...commits.value, ...page.commits.filter((commit) => !known.has(commit.hash))];
    }
    graphHasMore.value = page.has_more;
  } catch (reason) {
    if (reset) commits.value = [];
    error.value = `加载提交图谱失败：${messageOf(reason)}`;
  } finally {
    graphLoading.value = false;
    graphLoadingMore.value = false;
  }
}
function loadMoreGraph() { void loadGraph(false); }
function switchView(next: "changes" | "graph") { view.value = next; if (next === "graph") void loadGraph(); }
function refreshCurrentView() { if (view.value === "graph") void loadGraph(); else void refresh(); }
watch(() => props.workspaceId, (workspaceId) => {
  selectedPath.value = "";
  commitMessage.value = loadCommitDraft(workspaceId);
  void refresh();
}, { immediate: true });
watch(commitMessage, (message) => saveCommitDraft(props.workspaceId, message));
</script>

<template>
  <section class="source-control-page">
    <header class="source-control-header"><button type="button" class="source-control-back" aria-label="返回会话" title="返回会话" @click="emit('close')"><ArrowLeft :size="17" /></button><div class="source-control-title"><GitBranch :size="18" /><div><h1>源代码管理</h1><p>{{ workspaceName }}<span>{{ workspacePath }}</span></p></div></div><button type="button" class="source-control-refresh" aria-label="刷新源代码管理" title="刷新" :disabled="loading || graphLoading" @click="refreshCurrentView"><RefreshCw :size="16" :class="{ spin: loading || graphLoading }" /></button></header>
    <div class="source-control-branch"><GitBranch :size="14" /><b>{{ status?.branch || "未检测到分支" }}</b><small>{{ status?.is_git_repository ? "Git 仓库" : "非 Git 仓库" }}</small></div>
    <div v-if="error" class="source-control-error" role="alert">{{ error }}</div>
    <nav class="source-control-tabs" aria-label="源代码管理视图"><button type="button" :class="{ active: view === 'changes' }" @click="switchView('changes')">更改</button><button type="button" :class="{ active: view === 'graph' }" @click="switchView('graph')">提交图谱</button></nav>
    <template v-if="view === 'changes'">
    <div class="source-control-summary"><span><b>{{ changes.length }}</b> 项更改</span><span class="source-control-add">+{{ additions }}</span><span class="source-control-del">-{{ deletions }}</span><span v-if="commitNotice" class="source-control-commit-notice">{{ commitNotice }}</span></div>
    <label class="source-control-search"><Search :size="14" /><input v-model="query" placeholder="筛选更改" aria-label="筛选更改" /></label>
    <form class="source-control-commit" @submit.prevent="commit"><input v-model="commitMessage" aria-label="提交信息" placeholder="提交信息" :disabled="committing" /><button type="submit" :disabled="committing || !commitMessage.trim() || !changes.some((item) => isStaged(item))">{{ committing ? "提交中…" : "提交" }}</button></form>
    <div class="source-control-body"><div class="source-control-files"><p v-if="!filteredChanges.length" class="source-control-empty"><Check :size="24" /><b>工作区干净</b><span>没有待处理的源代码更改</span></p><section v-for="group in changeGroups" :key="group.key" class="source-control-group"><header class="source-control-group-header"><b>{{ group.label }}</b><span>{{ group.items.length }}</span></header><div v-for="item in group.items" :key="item.path" class="source-control-file" :class="{ active: selectedPath === item.path }" role="button" tabindex="0" @click="select(item.path)" @keydown.enter="select(item.path)" @keydown.space.prevent="select(item.path)"><span class="source-control-file-status" :class="`status-${fileStatus(item).toLowerCase()}`" :title="statusLabel(item)">{{ fileStatus(item) }}</span><span class="source-control-file-name"><b>{{ item.path.split(/[\\/]/).pop() }}</b><small>{{ item.path }}</small></span><span class="source-control-file-stats"><span class="stat-add">+{{ item.additions ?? 0 }}</span><span class="stat-del">-{{ item.deletions ?? 0 }}</span></span><span class="source-control-file-actions"><button type="button" :aria-label="isStaged(item) ? `取消暂存 ${item.path}` : `暂存 ${item.path}`" :title="isStaged(item) ? '取消暂存' : '暂存文件'" :disabled="busyPath === item.path" @click.stop="isStaged(item) ? unstage(item.path) : stage(item.path)"><Check :size="14" /></button><button type="button" class="source-control-discard" :aria-label="`放弃 ${item.path} 的改动`" title="放弃文件改动" :disabled="busyPath === item.path || isStaged(item)" @click.stop="discard(item.path)"><X :size="14" /></button></span></div></section></div><article class="source-control-diff"><header><span>{{ selected?.path || "选择文件查看差异" }}</span><button v-if="selectedPath" type="button" aria-label="清除选择" title="清除选择" @click="selectedPath = ''; diff = ''"><X :size="14" /></button></header><div v-if="diffLoading" class="source-control-diff-empty"><RefreshCw :size="17" class="spin" />加载差异…</div><div v-else-if="error" class="source-control-diff-empty">{{ error }}</div><pre v-else-if="diff" class="source-control-diff-code"><code v-for="(line, index) in diffLines" :key="index" :class="{ add: line.startsWith('+') && !line.startsWith('+++'), del: line.startsWith('-') && !line.startsWith('---'), hunk: line.startsWith('@@') }">{{ line || " " }}</code></pre><div v-else class="source-control-diff-empty">{{ selectedPath ? "此文件没有可显示的差异。" : "从左侧选择一个文件。" }}</div></article></div>
    </template>
    <GitGraph v-else :commits="commits" :branch="status?.branch ?? null" :loading="graphLoading" :loading-more="graphLoadingMore" :has-more="graphHasMore" @refresh="loadGraph" @load-more="loadMoreGraph" />
  </section>
</template>
