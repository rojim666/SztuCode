<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  ArrowDownAZ, Braces, Check, ChevronDown, ChevronLeft, ChevronRight, File, FileCode2,
  FileDiff, FileText, ListFilter, RefreshCw, RotateCcw, Search, X,
} from "@lucide/vue";
import {
  changeDiff, listChanges, readFile, revertChanges, searchFiles, workspaceTree,
  type ChangeSummary, type FileSearchMatch, type WorkspaceNode,
} from "../../services/sztu-runtime";
import CodePreview from "./CodePreview.vue";

const props = defineProps<{ workspaceId: string; runId?: string | null }>();
type FlatNode = WorkspaceNode & { depth: number };
type SortMode = "name" | "type";
type InspectorView = "files" | "search" | "changes";

const view = ref<InspectorView>("files");
const nodes = ref<WorkspaceNode[]>([]);
const matches = ref<FileSearchMatch[]>([]);
const changes = ref<ChangeSummary[]>([]);
const filterQuery = ref("");
const searchQuery = ref("");
const sortMode = ref<SortMode>("type");
const collapsedPaths = ref(new Set<string>());
const selectedPath = ref("");
const preview = ref("");
const previewEncoding = ref("UTF-8");
const previewBinary = ref(false);
const previewTruncated = ref(false);
const previewMediaBase64 = ref<string | null>(null);
const previewMimeType = ref<string | null>(null);
const previewLanguage = ref("");
const loading = ref(false);
const notice = ref("");
const menuOpen = ref(false);
const treeInitialized = ref(false);
const directoryLoading = ref(new Set<string>());
const toolbar = ref<HTMLElement | null>(null);

const fileNameCollator = new Intl.Collator("zh-CN", {
  sensitivity: "base",
  numeric: true,
});

function sortNodes(items: WorkspaceNode[]): WorkspaceNode[] {
  return [...items].sort((left, right) => {
    if (sortMode.value === "type" && left.kind !== right.kind) return left.kind === "directory" ? -1 : 1;
    return fileNameCollator.compare(left.name, right.name);
  });
}

function matchesFilter(node: WorkspaceNode): boolean {
  const query = filterQuery.value.trim().toLowerCase();
  return !query || node.name.toLowerCase().includes(query) || Boolean(node.children?.some(matchesFilter));
}

function flatten(items: WorkspaceNode[], depth = 0): FlatNode[] {
  return sortNodes(items).flatMap((node) => {
    const result: FlatNode[] = [{ ...node, depth }];
    const expandedForFilter = Boolean(filterQuery.value.trim());
    if (node.children?.length && (expandedForFilter || !collapsedPaths.value.has(node.path))) {
      result.push(...flatten(node.children.filter(matchesFilter), depth + 1));
    }
    return result;
  });
}

function collectDirectoryPaths(items: WorkspaceNode[]): string[] {
  return items.flatMap((node) => node.kind === "directory"
    ? [node.path, ...collectDirectoryPaths(node.children ?? [])]
    : []);
}

function collectInitiallyCollapsedPaths(items: WorkspaceNode[], depth = 0): string[] {
  return items.flatMap((node) => node.kind === "directory"
    ? [(depth > 0 ? node.path : ""), ...collectInitiallyCollapsedPaths(node.children ?? [], depth + 1)].filter(Boolean)
    : []);
}

const flatNodes = computed(() => flatten(nodes.value.filter(matchesFilter)));
const selectedName = computed(() => selectedPath.value.split(/[\\/]/).filter(Boolean).pop() ?? selectedPath.value);

function replaceDirectoryChildren(items: WorkspaceNode[], path: string, children: WorkspaceNode[]): WorkspaceNode[] {
  return items.map((node) => {
    if (node.path === path) return { ...node, children };
    if (!node.children) return node;
    return { ...node, children: replaceDirectoryChildren(node.children, path, children) };
  });
}

async function toggleDirectory(node: WorkspaceNode) {
  if (node.children === undefined) {
    directoryLoading.value = new Set(directoryLoading.value).add(node.path);
    notice.value = "";
    try {
      const children = await workspaceTree(props.workspaceId, node.path);
      nodes.value = replaceDirectoryChildren(nodes.value, node.path, children);
      const next = new Set(collapsedPaths.value);
      next.delete(node.path);
      collapsedPaths.value = next;
    } catch (error) {
      notice.value = error instanceof Error ? error.message : String(error);
    } finally {
      const nextLoading = new Set(directoryLoading.value);
      nextLoading.delete(node.path);
      directoryLoading.value = nextLoading;
    }
    return;
  }
  const next = new Set(collapsedPaths.value);
  if (next.has(node.path)) next.delete(node.path);
  else next.add(node.path);
  collapsedPaths.value = next;
}

function isCollapsed(node: WorkspaceNode) { return node.children === undefined || collapsedPaths.value.has(node.path); }
function collapseAll() { collapsedPaths.value = new Set(collectDirectoryPaths(nodes.value)); menuOpen.value = false; }
async function expandAll() {
  menuOpen.value = false;
  loading.value = true;
  try {
    nodes.value = await workspaceTree(props.workspaceId, "", 3);
    collapsedPaths.value = new Set();
  } finally {
    loading.value = false;
  }
}
function setSort(mode: SortMode) { sortMode.value = mode; menuOpen.value = false; }
function openView(next: InspectorView) { view.value = next; menuOpen.value = false; }

function fileKind(name: string) {
  const extension = name.split(".").pop()?.toLowerCase() ?? "";
  if (["ts", "tsx", "js", "jsx", "vue", "py", "rs", "go", "java", "c", "cpp", "h", "sh", "ps1"].includes(extension)) return "code";
  if (["json", "toml", "yaml", "yml", "env", "lock"].includes(extension) || name.startsWith(".")) return "config";
  if (["md", "txt", "rst", "pdf"].includes(extension)) return "document";
  return "file";
}

async function refresh() {
  loading.value = true;
  notice.value = "";
  try {
    const [nextNodes, nextChanges] = await Promise.all([workspaceTree(props.workspaceId), listChanges(props.workspaceId, props.runId)]);
    nodes.value = nextNodes;
    changes.value = nextChanges;
    if (!treeInitialized.value) {
      collapsedPaths.value = new Set(collectInitiallyCollapsedPaths(nextNodes));
      treeInitialized.value = true;
    }
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function selectFile(path: string) {
  selectedPath.value = path;
  preview.value = "";
  notice.value = "";
  previewLanguage.value = "";
  previewBinary.value = false;
  previewTruncated.value = false;
  previewMediaBase64.value = null;
  previewMimeType.value = null;
  try {
    const result = await readFile(props.workspaceId, path);
    preview.value = result.content;
    previewEncoding.value = result.encoding;
    previewBinary.value = result.binary;
    previewTruncated.value = result.truncated;
    previewMediaBase64.value = result.media_base64 ?? null;
    previewMimeType.value = result.mime_type ?? null;
  }
  catch (error) { notice.value = error instanceof Error ? error.message : String(error); }
}

async function search() {
  if (!searchQuery.value.trim()) { matches.value = []; return; }
  loading.value = true;
  try { matches.value = await searchFiles(props.workspaceId, searchQuery.value.trim()); }
  finally { loading.value = false; }
}

async function showDiff(change: ChangeSummary) {
  selectedPath.value = change.path;
  previewLanguage.value = "diff";
  previewEncoding.value = "UTF-8";
  previewBinary.value = false;
  previewTruncated.value = false;
  previewMediaBase64.value = null;
  previewMimeType.value = null;
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

function handleOutside(event: PointerEvent) {
  if (menuOpen.value && !toolbar.value?.contains(event.target as Node)) menuOpen.value = false;
}

watch(() => [props.workspaceId, props.runId], () => {
  treeInitialized.value = false;
  directoryLoading.value = new Set();
  selectedPath.value = "";
  preview.value = "";
  filterQuery.value = "";
  view.value = "files";
  void refresh();
}, { immediate: true });

onMounted(() => document.addEventListener("pointerdown", handleOutside));
onBeforeUnmount(() => document.removeEventListener("pointerdown", handleOutside));
</script>

<template>
  <aside class="project-inspector file-rail">
    <header ref="toolbar" class="file-rail-toolbar">
      <label class="file-filter">
        <Search :size="15" />
        <input v-model="filterQuery" aria-label="筛选文件" placeholder="筛选文件..." @focus="view = 'files'" />
        <button v-if="filterQuery" type="button" title="清除筛选" @click="filterQuery = ''"><X :size="13" /></button>
      </label>
      <button class="file-rail-menu-trigger" type="button" title="文件栏选项" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
        <ListFilter :size="15" /><ChevronDown :size="12" />
      </button>
      <div v-if="menuOpen" class="file-rail-menu">
        <span>排序</span>
        <button @click="setSort('name')"><ArrowDownAZ :size="14" />按名称<Check v-if="sortMode === 'name'" :size="13" /></button>
        <button @click="setSort('type')"><File :size="14" />文件夹优先<Check v-if="sortMode === 'type'" :size="13" /></button>
        <i />
        <button @click="refresh"><RefreshCw :size="14" :class="{ spin: loading }" />刷新</button>
        <button @click="expandAll"><ChevronRight :size="14" class="expanded" />全部展开</button>
        <button @click="collapseAll"><ChevronRight :size="14" />全部收起</button>
        <i />
        <button @click="openView('search')"><Search :size="14" />搜索文件内容</button>
        <button @click="openView('changes')"><FileDiff :size="14" />查看变更<span v-if="changes.length" class="file-rail-count">{{ changes.length }}</span></button>
      </div>
    </header>

    <div v-if="view === 'files'" class="file-rail-browser">
      <div class="file-tree" role="tree" aria-label="项目文件">
        <button
          v-for="node in flatNodes"
          :key="node.path"
          class="file-tree-row"
          :class="[{ directory: node.kind === 'directory', selected: node.path === selectedPath }, node.kind === 'file' ? 'kind-' + fileKind(node.name) : '']"
          :style="{ paddingLeft: (10 + node.depth * 16) + 'px' }"
          :aria-expanded="node.kind === 'directory' ? !isCollapsed(node) : undefined"
          :disabled="loading || directoryLoading.has(node.path)"
          role="treeitem"
          @click="node.kind === 'directory' ? toggleDirectory(node) : selectFile(node.path)"
        >
          <RefreshCw v-if="node.kind === 'directory' && directoryLoading.has(node.path)" :size="13" class="spin" />
          <ChevronRight v-else-if="node.kind === 'directory'" :size="14" :class="{ expanded: !isCollapsed(node) }" />
          <FileCode2 v-else-if="fileKind(node.name) === 'code'" :size="15" />
          <Braces v-else-if="fileKind(node.name) === 'config'" :size="15" />
          <FileText v-else-if="fileKind(node.name) === 'document'" :size="15" />
          <File v-else :size="15" />
          <span>{{ node.name }}</span>
        </button>
        <div v-if="loading" class="file-tree-skeleton" aria-label="正在加载文件"><i v-for="index in 9" :key="index" :style="{ width: (58 + (index % 3) * 12) + '%' }" /></div>
        <p v-if="!flatNodes.length && !loading" class="inspector-empty">{{ filterQuery ? '没有匹配的文件' : '项目中没有可显示的文件' }}</p>
      </div>
    </div>

    <section v-else-if="view === 'search'" class="file-rail-view">
      <header><button title="返回文件树" @click="openView('files')"><ChevronLeft :size="16" /></button><b>搜索文件内容</b></header>
      <form class="file-content-search" @submit.prevent="search"><Search :size="15" /><input v-model="searchQuery" aria-label="搜索项目文件" placeholder="输入关键词..." /><button :disabled="loading">搜索</button></form>
      <div class="file-rail-results">
        <button v-for="match in matches" :key="match.path + ':' + match.line" class="search-match" @click="selectFile(match.path)"><b>{{ match.path }}:{{ match.line }}</b><span>{{ match.preview }}</span></button>
        <p v-if="searchQuery && !matches.length && !loading" class="inspector-empty">没有匹配结果</p>
      </div>
    </section>

    <section v-else class="file-rail-view">
      <header><button title="返回文件树" @click="openView('files')"><ChevronLeft :size="16" /></button><b>本次运行的变更</b><button title="刷新变更" :disabled="loading" @click="refresh"><RefreshCw :size="14" :class="{ spin: loading }" /></button></header>
      <div class="change-list file-rail-results">
        <article v-for="change in changes" :key="change.path"><button class="change-path" @click="showDiff(change)"><FileDiff :size="14" /><span>{{ change.path }}</span><code>{{ change.index_status }}{{ change.worktree_status }}</code></button><button v-if="change.revertible" class="revert-change" title="回滚此变更" @click="revert(change)"><RotateCcw :size="14" /></button></article>
        <p v-if="!changes.length && !loading" class="inspector-empty">没有待处理变更</p>
      </div>
    </section>

    <section v-if="selectedPath" class="file-preview file-preview--flyout">
      <header><FileText :size="16" /><b>{{ selectedName }}</b><button title="关闭预览" @click="selectedPath = ''; preview = ''"><X :size="17" /></button></header>
      <CodePreview
        :content="preview"
        :path="selectedPath"
        :encoding="previewEncoding"
        :binary="previewBinary"
        :truncated="previewTruncated"
        :force-language="previewLanguage"
        :media-base64="previewMediaBase64"
        :mime-type="previewMimeType"
      />
    </section>
    <p v-if="notice" class="inspector-notice">{{ notice }}</p>
  </aside>
</template>
