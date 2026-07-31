<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ChevronRight, File, FileDiff, Folder, RefreshCw, RotateCcw, Search, SlidersHorizontal, X,
} from "@lucide/vue";
import {
  changeDiff, listChanges, readFile, revertChanges, searchFiles, workspaceTree,
  type ChangeSummary, type FileSearchMatch, type WorkspaceNode,
} from "../../services/sztu-runtime";

const props = defineProps<{ workspaceId: string; runId?: string | null }>();
type FlatNode = WorkspaceNode & { depth: number };
type SortMode = "name" | "type";
const tab = ref<"files" | "search" | "changes">("files");
const nodes = ref<WorkspaceNode[]>([]);
const matches = ref<FileSearchMatch[]>([]);
const changes = ref<ChangeSummary[]>([]);
const treeQuery = ref("");
const searchQuery = ref("");
const sortMode = ref<SortMode>("name");
const collapsedPaths = ref(new Set<string>());
const selectedPath = ref("");
const preview = ref("");
const loading = ref(false);
const notice = ref("");

function sortNodes(items: WorkspaceNode[]): WorkspaceNode[] {
  return [...items].sort((left, right) => {
    if (sortMode.value === "type" && left.kind !== right.kind) return left.kind === "directory" ? -1 : 1;
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base", numeric: true });
  });
}

function matchesTree(node: WorkspaceNode): boolean {
  const query = treeQuery.value.trim().toLowerCase();
  return !query || node.name.toLowerCase().includes(query) || Boolean(node.children?.some(matchesTree));
}

function flatten(items: WorkspaceNode[], depth = 0): FlatNode[] {
  return sortNodes(items).flatMap((node) => {
    const visible: FlatNode[] = [{ ...node, depth }];
    const shouldExpand = Boolean(treeQuery.value.trim()) || !collapsedPaths.value.has(node.path);
    if (node.children?.length && shouldExpand) visible.push(...flatten(node.children, depth + 1));
    return visible;
  });
}

const flatNodes = computed(() => flatten(nodes.value.filter(matchesTree)));
const selectedName = computed(() => selectedPath.value.split(/[\\/]/).filter(Boolean).pop() ?? selectedPath.value);

function toggleDirectory(path: string) {
  const next = new Set(collapsedPaths.value);
  if (next.has(path)) next.delete(path);
  else next.add(path);
  collapsedPaths.value = next;
}

function isCollapsed(path: string) { return collapsedPaths.value.has(path); }

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

async function selectFile(path: string) {
  selectedPath.value = path;
  preview.value = await readFile(props.workspaceId, path);
}

async function search() {
  if (!searchQuery.value.trim()) {
    matches.value = [];
    return;
  }
  loading.value = true;
  try { matches.value = await searchFiles(props.workspaceId, searchQuery.value.trim()); }
  finally { loading.value = false; }
}

async function showDiff(change: ChangeSummary) {
  selectedPath.value = change.path;
  preview.value = await changeDiff(props.workspaceId, change.path);
}

async function revert(change: ChangeSummary) {
  const runId = change.run_id ?? props.runId;
  if (!runId || !change.revertible) return;
  if (!window.confirm("回滚 " + change.path + " 到本次 Agent 运行前的状态？")) return;
  const result = await revertChanges(props.workspaceId, runId, [change.path]);
  notice.value = result.reverted_paths.length ? "已回滚 " + result.reverted_paths.join(", ") : Object.values(result.blocked_paths).join("\n");
  await refresh();
}

watch(() => [props.workspaceId, props.runId], () => {
  collapsedPaths.value = new Set();
  treeQuery.value = "";
  void refresh();
}, { immediate: true });
</script>

<template>
  <aside class="project-inspector">
    <header class="inspector-header">
      <nav aria-label="项目检查器">
        <button :class="{ active: tab === 'files' }" title="文件" @click="tab = 'files'"><Folder :size="16" /><span class="sr-only">文件</span></button>
        <button :class="{ active: tab === 'search' }" title="搜索" @click="tab = 'search'"><Search :size="16" /><span class="sr-only">搜索</span></button>
        <button :class="{ active: tab === 'changes' }" title="变更" @click="tab = 'changes'"><FileDiff :size="16" /><span v-if="changes.length" class="inspector-badge">{{ changes.length }}</span><span class="sr-only">变更</span></button>
      </nav>
      <button class="refresh-inspector" :disabled="loading" title="刷新文件树" @click="refresh"><RefreshCw :size="14" :class="{ spin: loading }" /><span>刷新</span></button>
    </header>

    <div v-if="tab === 'files'" class="file-browser">
      <form class="file-toolbar" @submit.prevent>
        <Search :size="15" />
        <input v-model="treeQuery" aria-label="筛选文件" placeholder="筛选文件..." />
        <select v-model="sortMode" aria-label="排序方式" title="排序方式">
          <option value="name">名称</option>
          <option value="type">类型</option>
        </select>
        <SlidersHorizontal :size="14" class="sort-icon" />
      </form>
      <div class="file-tree">
        <button
          v-for="node in flatNodes"
          :key="node.path"
          class="file-tree-row"
          :class="{ directory: node.kind === 'directory', selected: node.path === selectedPath }"
          :style="{ paddingLeft: (8 + node.depth * 15) + 'px' }"
          :aria-expanded="node.kind === 'directory' ? !isCollapsed(node.path) : undefined"
          :disabled="loading"
          @click="node.kind === 'directory' ? toggleDirectory(node.path) : selectFile(node.path)"
        >
          <ChevronRight v-if="node.kind === 'directory'" :size="13" :class="{ expanded: !isCollapsed(node.path) }" />
          <span v-else class="file-leading"><File :size="14" /></span>
          <Folder v-if="node.kind === 'directory'" :size="14" class="folder-icon" />
          <File v-else :size="14" class="file-icon" />
          <span class="file-tree-name">{{ node.name }}</span>
        </button>
        <div v-if="loading" class="file-tree-skeleton" aria-label="正在加载文件">
          <i v-for="index in 7" :key="index" :style="{ width: (58 + (index % 3) * 12) + '%' }" />
        </div>
        <p v-if="!flatNodes.length && !loading" class="inspector-empty">{{ treeQuery ? '没有匹配的文件' : '项目中没有可显示的文件' }}</p>
      </div>
    </div>

    <div v-else-if="tab === 'search'" class="inspector-search">
      <form class="global-search-form" @submit.prevent="search">
        <Search :size="15" />
        <input v-model="searchQuery" aria-label="搜索项目文件" placeholder="搜索项目文件..." />
        <button title="搜索" :disabled="loading"><Search :size="15" /></button>
      </form>
      <button v-for="match in matches" :key="match.path + ':' + match.line" class="search-match" @click="selectFile(match.path)">
        <b>{{ match.path }}:{{ match.line }}</b><span>{{ match.preview }}</span>
      </button>
      <p v-if="searchQuery && !matches.length && !loading" class="inspector-empty">没有匹配结果</p>
    </div>

    <div v-else class="change-list">
      <div class="changes-toolbar"><span>本次运行的变更</span><button type="button" title="刷新变更" :disabled="loading" @click="refresh"><RefreshCw :size="13" :class="{ spin: loading }" /></button></div>
      <article v-for="change in changes" :key="change.path">
        <button class="change-path" @click="showDiff(change)"><FileDiff :size="14" /><span>{{ change.path }}</span><code>{{ change.index_status }}{{ change.worktree_status }}</code></button>
        <button v-if="change.revertible" class="revert-change" title="回滚此变更" @click="revert(change)"><RotateCcw :size="14" /></button>
      </article>
      <p v-if="!changes.length && !loading" class="inspector-empty">没有待处理变更</p>
    </div>

    <section v-if="selectedPath" class="file-preview">
      <header><span class="preview-kind">文件预览</span><b :title="selectedPath">{{ selectedName }}</b><button title="关闭预览" @click="selectedPath = ''; preview = ''"><X :size="16" /></button></header>
      <div class="preview-path">{{ selectedPath }}</div>
      <pre><code>{{ preview }}</code></pre>
    </section>
    <p v-if="notice" class="inspector-notice">{{ notice }}</p>
  </aside>
</template>