<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ChevronRight, File, FileDiff, Folder, RotateCcw, Search } from "@lucide/vue";
import {
  changeDiff, listChanges, readFile, revertChanges, searchFiles, workspaceTree,
  type ChangeSummary, type FileSearchMatch, type WorkspaceNode,
} from "../../services/sztu-runtime";

const props = defineProps<{ workspaceId: string; runId?: string | null }>();
type FlatNode = WorkspaceNode & { depth: number };
const tab = ref<"files" | "search" | "changes">("files");
const nodes = ref<WorkspaceNode[]>([]);
const matches = ref<FileSearchMatch[]>([]);
const changes = ref<ChangeSummary[]>([]);
const query = ref("");
const selectedPath = ref("");
const preview = ref("");
const loading = ref(false);
const notice = ref("");

function flatten(items: WorkspaceNode[], depth = 0): FlatNode[] {
  return items.flatMap((node) => [{ ...node, depth }, ...(node.children ? flatten(node.children, depth + 1) : [])]);
}
const flatNodes = computed(() => flatten(nodes.value));

async function refresh() {
  loading.value = true;
  notice.value = "";
  try {
    [nodes.value, changes.value] = await Promise.all([workspaceTree(props.workspaceId), listChanges(props.workspaceId, props.runId)]);
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}
async function selectFile(path: string) { selectedPath.value = path; preview.value = await readFile(props.workspaceId, path); }
async function search() {
  if (!query.value.trim()) return;
  loading.value = true;
  try { matches.value = await searchFiles(props.workspaceId, query.value.trim()); }
  finally { loading.value = false; }
}
async function showDiff(change: ChangeSummary) { selectedPath.value = change.path; preview.value = await changeDiff(props.workspaceId, change.path); }
async function revert(change: ChangeSummary) {
  const runId = change.run_id ?? props.runId;
  if (!runId || !change.revertible) return;
  if (!window.confirm("回滚 " + change.path + " 到本次 Agent 运行前的状态？")) return;
  const result = await revertChanges(props.workspaceId, runId, [change.path]);
  notice.value = result.reverted_paths.length ? "已回滚 " + result.reverted_paths.join(", ") : Object.values(result.blocked_paths).join("\n");
  await refresh();
}
watch(() => [props.workspaceId, props.runId], refresh, { immediate: true });
</script>

<template>
  <aside class="project-inspector">
    <header>
      <nav aria-label="项目检查器">
        <button :class="{ active: tab === 'files' }" title="文件" @click="tab = 'files'"><Folder :size="16" /></button>
        <button :class="{ active: tab === 'search' }" title="搜索" @click="tab = 'search'"><Search :size="16" /></button>
        <button :class="{ active: tab === 'changes' }" title="变更" @click="tab = 'changes'"><FileDiff :size="16" /><span v-if="changes.length">{{ changes.length }}</span></button>
      </nav>
      <button class="refresh-inspector" :disabled="loading" @click="refresh">刷新</button>
    </header>
    <div v-if="tab === 'search'" class="inspector-search">
      <form @submit.prevent="search"><input v-model="query" aria-label="搜索项目文件" placeholder="搜索文件内容" /><button title="搜索"><Search :size="15" /></button></form>
      <button v-for="match in matches" :key="match.path + ':' + match.line" class="search-match" @click="selectFile(match.path)"><b>{{ match.path }}:{{ match.line }}</b><span>{{ match.preview }}</span></button>
      <p v-if="query && !matches.length && !loading" class="inspector-empty">没有匹配结果</p>
    </div>
    <div v-else-if="tab === 'changes'" class="change-list">
      <article v-for="change in changes" :key="change.path">
        <button class="change-path" @click="showDiff(change)"><FileDiff :size="14" /><span>{{ change.path }}</span><code>{{ change.index_status }}{{ change.worktree_status }}</code></button>
        <button v-if="change.revertible" class="revert-change" title="回滚此变更" @click="revert(change)"><RotateCcw :size="14" /></button>
      </article>
      <p v-if="!changes.length && !loading" class="inspector-empty">没有待处理变更</p>
    </div>
    <div v-else class="file-tree">
      <button v-for="node in flatNodes" :key="node.path" :style="{ paddingLeft: (10 + node.depth * 15) + 'px' }" :disabled="node.kind === 'directory'" @click="selectFile(node.path)">
        <ChevronRight v-if="node.kind === 'directory'" :size="13" /><Folder v-if="node.kind === 'directory'" :size="14" /><File v-else :size="14" /><span>{{ node.name }}</span>
      </button>
      <p v-if="!flatNodes.length && !loading" class="inspector-empty">项目中没有可显示的文件</p>
    </div>
    <section v-if="selectedPath" class="file-preview"><header><b>{{ selectedPath }}</b><button title="关闭预览" @click="selectedPath = ''; preview = ''">×</button></header><pre><code>{{ preview }}</code></pre></section>
    <p v-if="notice" class="inspector-notice">{{ notice }}</p>
  </aside>
</template>