<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import {
  readFile,
  workspaceTree,
  type WorkspaceNode,
  listExternalApps,
  openPathWithApp,
  type ExternalAppInfo,
} from "../../services/sztu-runtime";
import RichFilePreview from "./RichFilePreview.vue";
import FileTreeNode from "./FileTreeNode.vue";

const props = defineProps<{
  workspaceId: string;
  workspaceName?: string;
  workspacePath?: string;
}>();

function basename(p: string): string {
  const normalized = p.replace(/[\\/]+$/, "");
  const idx = Math.max(normalized.lastIndexOf("/"), normalized.lastIndexOf("\\"));
  return idx >= 0 ? normalized.slice(idx + 1) : normalized;
}

function resolveToRelative(rawPath: string): string {
  let p = rawPath.trim();
  // 去掉行号后缀，如 foo.ts:25
  p = p.replace(/:\d+(?:-\d+)?$/, "");
  // 统一路径分隔符为正斜杠
  const normalizedP = p.replace(/\\/g, "/");
  // 标准化工作区路径：去掉尾部分隔符，统一为正斜杠
  const wsRaw = props.workspacePath ?? "";
  const wsPath = wsRaw.replace(/[\\/]+$/, "").replace(/\\/g, "/");
  
  // 处理 Windows 绝对路径（如 C:/path/to/file）
  if (/^[A-Za-z]:[\\/]/.test(p)) {
    if (wsPath) {
      const wsLower = wsPath.toLowerCase();
      const pLower = normalizedP.toLowerCase();
      // 检查是否在工作区内
      if (pLower.startsWith(wsLower + "/")) {
        return normalizedP.slice(wsPath.length + 1);
      }
      if (pLower === wsLower) {
        return "";
      }
    }
    // 绝对路径不在工作区内，尝试提取最后一部分作为回退
    // 这种情况不应该发生，但作为防御性处理
    const parts = normalizedP.split("/").filter(Boolean);
    return parts[parts.length - 1] ?? "";
  }
  
  // 处理 Unix 绝对路径（/开头）
  if (normalizedP.startsWith("/")) {
    if (wsPath) {
      if (normalizedP.startsWith(wsPath + "/")) {
        return normalizedP.slice(wsPath.length + 1);
      }
      if (normalizedP === wsPath) {
        return "";
      }
    }
    // 不在工作区内，去掉开头的/
    return normalizedP.slice(1);
  }
  
  // 相对路径：只去掉开头的 ./ 前缀（../ 保留，交给后端判定边界）
  return normalizedP.replace(/^\.\//, "");
}

function friendlyError(err: unknown, filePath: string): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (/ENOENT|no such file|not found/i.test(msg)) return `文件不存在：${filePath}`;
  if (/EACCES|permission|denied/i.test(msg)) return `无权限读取文件：${filePath}`;
  if (/EISDIR|directory/i.test(msg)) return `路径是目录而非文件：${filePath}`;
  return msg || `无法读取文件：${filePath}`;
}

// ========== 状态 ==========
export type TreeNode = WorkspaceNode & { children?: TreeNode[]; loading?: boolean };

interface OpenFileTab {
  path: string;
  name: string;
  content: string;
  encoding: string;
  binary: boolean;
  truncated: boolean;
  mediaBase64: string | null;
  mimeType: string | null;
  error: string;
}

const root = ref<TreeNode[]>([]);
const loading = ref(false);
const treeError = ref("");
const treeWidth = ref(Number(localStorage.getItem("sztu.treeWidth")) || 200);
const treeCollapsed = ref(localStorage.getItem("sztu.treeCollapsed") === "1");
const tabs = ref<OpenFileTab[]>([]);
const activeTabPath = ref("");
const activeTab = computed(() => tabs.value.find((t) => t.path === activeTabPath.value) ?? null);

const selectedPath = computed(() => activeTabPath.value);
const selectedName = computed(() => activeTab.value?.name ?? "");
const preview = computed(() => activeTab.value?.content ?? "");
const previewEncoding = computed(() => activeTab.value?.encoding ?? "UTF-8");
const previewBinary = computed(() => activeTab.value?.binary ?? false);
const previewTruncated = computed(() => activeTab.value?.truncated ?? false);
const previewMediaBase64 = computed(() => activeTab.value?.mediaBase64 ?? null);
const previewMimeType = computed(() => activeTab.value?.mimeType ?? null);
const previewError = computed(() => activeTab.value?.error ?? "");

// ========== 文件树加载 ==========
async function loadDir(node: TreeNode | null) {
  if (node) node.loading = true;
  else loading.value = true;
  treeError.value = "";
  try {
    const nodes = await workspaceTree(props.workspaceId, node?.path ?? "", 0);
    const mapped: TreeNode[] = nodes.map((n) => ({ ...n }));
    if (node) {
      node.children = mapped;
      node.loading = false;
    } else {
      root.value = mapped;
    }
  } catch (e) {
    treeError.value = e instanceof Error ? e.message : String(e);
    if (node) node.loading = false;
  } finally {
    if (!node) loading.value = false;
  }
}

function toggleDir(node: TreeNode) {
  if (node.children) {
    node.children = undefined;
    return;
  }
  void loadDir(node);
}

// ========== 拖拽调整宽度 ==========
let dragCleanup: (() => void) | null = null;
function startTreeDrag(event: MouseEvent) {
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = treeWidth.value;
  const onMove = (moveEvent: MouseEvent) => {
    const next = Math.min(Math.max(startWidth - (moveEvent.clientX - startX), 140), 360);
    treeWidth.value = next;
    localStorage.setItem("sztu.treeWidth", String(next));
  };
  const onUp = () => {
    dragCleanup?.();
    dragCleanup = null;
  };
  dragCleanup = () => {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}
onBeforeUnmount(() => dragCleanup?.());

// ========== 折叠/展开文件树 ==========
function toggleTreeCollapse() {
  treeCollapsed.value = !treeCollapsed.value;
  localStorage.setItem("sztu.treeCollapsed", treeCollapsed.value ? "1" : "0");
}

// ========== Tab 管理 ==========
function openTabFor(path: string, name: string, content: string, encoding: string, binary: boolean, truncated: boolean, mediaBase64: string | null, mimeType: string | null) {
  const existing = tabs.value.find((t) => t.path === path);
  if (existing) {
    existing.content = content;
    existing.encoding = encoding;
    existing.binary = binary;
    existing.truncated = truncated;
    existing.mediaBase64 = mediaBase64;
    existing.mimeType = mimeType;
    existing.error = "";
    existing.name = name;
    activeTabPath.value = path;
    return;
  }
  tabs.value.push({ path, name, content, encoding, binary, truncated, mediaBase64, mimeType, error: "" });
  activeTabPath.value = path;
}

function setTabError(path: string, errMsg: string) {
  const t = tabs.value.find((x) => x.path === path);
  if (t) t.error = errMsg;
}

function switchTab(path: string) {
  activeTabPath.value = path;
  nextTick(() => {
    const el = tabsScrollRef.value;
    if (!el) return;
    const active = el.querySelector<HTMLElement>(".file-tab.active");
    if (active) active.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  });
}

function closeTab(path: string, event?: MouseEvent) {
  event?.stopPropagation();
  const idx = tabs.value.findIndex((t) => t.path === path);
  if (idx === -1) return;
  tabs.value.splice(idx, 1);
  if (activeTabPath.value === path) {
    if (tabs.value.length) {
      activeTabPath.value = tabs.value[Math.min(idx, tabs.value.length - 1)].path;
    } else {
      activeTabPath.value = "";
    }
  }
}

// ========== 文件打开 ==========
async function openFile(node: TreeNode) {
  const relPath = node.path;
  const name = node.name;
  // 先打开一个空 tab 占位，再异步加载
  if (!tabs.value.some((t) => t.path === relPath)) {
    tabs.value.push({
      path: relPath, name, content: "", encoding: "UTF-8",
      binary: false, truncated: false, mediaBase64: null, mimeType: null, error: "",
    });
  }
  activeTabPath.value = relPath;
  try {
    const result = await readFile(props.workspaceId, relPath);
    openTabFor(relPath, name, result.content, result.encoding, result.binary, result.truncated, result.media_base64 ?? null, result.mime_type ?? null);
  } catch (e) {
    setTabError(relPath, friendlyError(e, relPath));
  }
}

async function previewFileAtPath(rawPath: string) {
  const relPath = resolveToRelative(rawPath);
  if (!relPath) return;
  const name = basename(relPath);
  if (!tabs.value.some((t) => t.path === relPath)) {
    tabs.value.push({
      path: relPath, name, content: "", encoding: "UTF-8",
      binary: false, truncated: false, mediaBase64: null, mimeType: null, error: "",
    });
  }
  activeTabPath.value = relPath;
  try {
    const result = await readFile(props.workspaceId, relPath);
    openTabFor(relPath, name, result.content, result.encoding, result.binary, result.truncated, result.media_base64 ?? null, result.mime_type ?? null);
  } catch (e) {
    // 精确路径失败：AI 可能只给短文件名或相对其工作目录的路径，按文件名在工作区内定位
    const resolved = await locateByBasename(relPath);
    if (resolved && resolved !== relPath) {
      const staleIdx = tabs.value.findIndex((t) => t.path === relPath);
      if (staleIdx >= 0) tabs.value.splice(staleIdx, 1);
      if (!tabs.value.some((t) => t.path === resolved)) {
        tabs.value.push({
          path: resolved, name: basename(resolved), content: "", encoding: "UTF-8",
          binary: false, truncated: false, mediaBase64: null, mimeType: null, error: "",
        });
      }
      activeTabPath.value = resolved;
      try {
        const result = await readFile(props.workspaceId, resolved);
        openTabFor(resolved, basename(resolved), result.content, result.encoding, result.binary, result.truncated, result.media_base64 ?? null, result.mime_type ?? null);
        return;
      } catch (e2) {
        setTabError(resolved, friendlyError(e2, resolved));
        return;
      }
    }
    setTabError(relPath, friendlyError(e, relPath));
  }
}

// 工作区全量文件路径索引（懒加载 + 短缓存），供按文件名回退定位
let fileIndexCache: { wsId: string; at: number; files: string[] } | null = null;
async function indexedFiles(): Promise<string[]> {
  if (fileIndexCache && fileIndexCache.wsId === props.workspaceId && Date.now() - fileIndexCache.at < 15_000) {
    return fileIndexCache.files;
  }
  try {
    const nodes = await workspaceTree(props.workspaceId, "", 32);
    const files: string[] = [];
    const walk = (list: WorkspaceNode[]) => {
      for (const node of list) {
        if (node.kind === "file") files.push(node.path);
        if (node.children?.length) walk(node.children);
      }
    };
    walk(nodes);
    fileIndexCache = { wsId: props.workspaceId, at: Date.now(), files };
    return files;
  } catch {
    fileIndexCache = null;
    return [];
  }
}

// 按文件名在工作区全量索引中定位，优先选择父目录名一致的匹配（减少同名误判）
async function locateByBasename(relPath: string): Promise<string | null> {
  const fileName = basename(relPath);
  if (!fileName) return null;
  const files = await indexedFiles();
  if (!files.length) return null;
  const matches = files.filter((p) => basename(p) === fileName);
  if (!matches.length) return null;
  const parentParts = relPath.split("/").slice(0, -1).filter(Boolean);
  const parentName = parentParts[parentParts.length - 1] ?? "";
  if (parentName) {
    const byParent = matches.find((p) => p.split("/").slice(0, -1).includes(parentName));
    if (byParent) return byParent;
  }
  return matches[0];
}

defineExpose({ previewFileAtPath });

// ========== Open 下拉菜单 ==========
const openMenuOpen = ref(false);
const externalApps = ref<ExternalAppInfo[]>([]);
let openMenuCleanup: (() => void) | null = null;
const openBtnRef = ref<HTMLElement | null>(null);
const tabsScrollRef = ref<HTMLElement | null>(null);
const openMenuStyle = ref({ top: "0px", right: "0px" });

async function loadExternalApps() {
  try {
    externalApps.value = await listExternalApps();
  } catch {
    externalApps.value = [];
  }
}

function updateMenuPosition() {
  if (!openBtnRef.value) return;
  const rect = openBtnRef.value.getBoundingClientRect();
  openMenuStyle.value = {
    top: `${rect.bottom + 8}px`,
    right: `${window.innerWidth - rect.right}px`,
  };
}

function toggleOpenMenu() {
  openMenuOpen.value = !openMenuOpen.value;
  if (openMenuOpen.value) {
    if (!externalApps.value.length) void loadExternalApps();
    // 立即计算 + 多次重试，防止首次打开时布局尚未稳定
    updateMenuPosition();
    nextTick(updateMenuPosition);
    setTimeout(updateMenuPosition, 0);
    setTimeout(updateMenuPosition, 100);
    setTimeout(() => {
      const onDocClick = (e: MouseEvent) => {
        const menuEl = document.getElementById("file-open-menu-teleport");
        if (
          !openBtnRef.value?.contains(e.target as Node) &&
          !menuEl?.contains(e.target as Node)
        ) {
          closeOpenMenu();
        }
      };
      // 捕获阶段监听所有滚动容器的滚动事件，实时更新菜单位置
      const onScroll = () => updateMenuPosition();
      document.addEventListener("mousedown", onDocClick);
      window.addEventListener("resize", updateMenuPosition);
      window.addEventListener("scroll", onScroll, true);
      openMenuCleanup = () => {
        document.removeEventListener("mousedown", onDocClick);
        window.removeEventListener("resize", updateMenuPosition);
        window.removeEventListener("scroll", onScroll, true);
      };
    }, 0);
  } else {
    closeOpenMenu();
  }
}

function closeOpenMenu() {
  openMenuOpen.value = false;
  openMenuCleanup?.();
  openMenuCleanup = null;
}

onBeforeUnmount(() => {
  openMenuCleanup?.();
  openMenuCleanup = null;
});

// 标签栏鼠标滚轮横向滚动（监听在整个标签栏上，Open 按钮区域也能滚）
function handleTabsWheel(e: WheelEvent) {
  const el = tabsScrollRef.value;
  if (!el) return;
  // 如果内容没有溢出，无需处理
  if (el.scrollWidth <= el.clientWidth + 1) return;
  // 优先使用垂直滚轮来横向滚动（Shift+滚轮已经原生支持横向）
  const delta = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
  if (delta === 0) return;
  el.scrollLeft += delta;
  e.preventDefault();
}

function appIconSvg(icon: string): string {
  switch (icon) {
    case "trae":
      return "trae";
    case "vscode":
      return "vscode";
    case "cursor":
      return "cursor";
    case "webstorm":
      return "webstorm";
    case "folder":
      return "folder";
    case "default":
      return "default";
    default:
      return "app";
  }
}

async function openWith(appId: string) {
  openMenuOpen.value = false;
  openMenuCleanup?.();
  openMenuCleanup = null;
  if (!activeTab.value || !props.workspacePath) return;
  const sep = props.workspacePath.includes("\\") ? "\\" : "/";
  const base = props.workspacePath.replace(/[\\/]+$/, "");
  const absPath = `${base}${sep}${activeTab.value.path.replace(/\//g, sep)}`;
  try {
    await openPathWithApp(absPath, appId);
  } catch (e) {
    // ignore errors silently (app not found etc.)
    console.warn("openWith failed:", e);
  }
}

watch(() => props.workspaceId, () => {
  root.value = [];
  tabs.value = [];
  activeTabPath.value = "";
  void loadDir(null);
});
onMounted(() => void loadDir(null));
</script>

<template>
  <div
    class="file-tree-view"
    :style="treeCollapsed ? 'grid-template-columns: minmax(0, 1fr) 0 0;' : `grid-template-columns: minmax(0, 1fr) 6px ${treeWidth}px;`"
  >
    <!-- 左：预览区 -->
    <section class="file-preview file-preview--files" :class="{ empty: !selectedPath, error: !!previewError }">
      <!-- 顶部操作栏：标签 + Open + 折叠按钮 -->
      <div class="file-tabs-bar" v-if="tabs.length" @wheel="handleTabsWheel">
        <div ref="tabsScrollRef" class="file-tabs-scroll">
          <div
            v-for="tab in tabs"
            :key="tab.path"
            class="file-tab"
            :class="{ active: tab.path === activeTabPath, 'has-error': !!tab.error }"
            role="button"
            tabindex="0"
            @click="switchTab(tab.path)"
            @keydown.enter.self.prevent="switchTab(tab.path)"
            @keydown.space.self.prevent="switchTab(tab.path)"
          >
            <AppIcon name="Folder" :size="13" :filled="tab.path === activeTabPath" />
            <span class="file-tab-name" :title="tab.path">{{ tab.name }}</span>
            <button class="file-tab-close" @click="closeTab(tab.path, $event)" title="关闭">
              <AppIcon name="X" :size="12" />
            </button>
          </div>
        </div>
        <div class="file-tabs-actions">
          <!-- Open 按钮 -->
          <div v-if="activeTab" class="file-open-wrap">
            <button ref="openBtnRef" class="file-open-btn" @click="toggleOpenMenu" title="使用外部应用打开">
              <AppIcon name="ExternalLink" :size="14" />
              <span>Open</span>
              <AppIcon name="ChevronDown" :size="13" :class="{ rotated: openMenuOpen }" />
            </button>
          </div>
          <!-- 折叠/展开文件树按钮 -->
          <button
            class="tree-toggle-btn"
            :title="treeCollapsed ? '展开文件树' : '折叠文件树'"
            @click="toggleTreeCollapse"
          >
            <AppIcon name="PanelLeftOpen" v-if="treeCollapsed" :size="15" />
            <AppIcon name="PanelLeftClose" v-else :size="15" />
          </button>
        </div>
      </div>
      <!-- 无 tab 时也显示折叠按钮（右上角小按钮） -->
      <div v-else class="file-tabs-bar file-tabs-bar--empty">
        <button
          class="tree-toggle-btn tree-toggle-btn--solo"
          :title="treeCollapsed ? '展开文件树' : '折叠文件树'"
          @click="toggleTreeCollapse"
        >
          <AppIcon name="PanelLeftOpen" v-if="treeCollapsed" :size="15" />
          <AppIcon name="PanelLeftClose" v-else :size="15" />
        </button>
      </div>

      <!-- 预览内容 -->
      <template v-if="selectedPath">
        <div v-if="previewError" class="preview-error">
          <AppIcon name="FileX2" :size="20" />
          <b>无法预览文件</b>
          <p>{{ previewError }}</p>
        </div>
        <RichFilePreview
          v-else
          :content="preview"
          :path="selectedPath"
          :encoding="previewEncoding"
          :binary="previewBinary"
          :truncated="previewTruncated"
          :media-base64="previewMediaBase64"
          :mime-type="previewMimeType"
          :workspace-id="workspaceId"
          :hide-chrome="true"
        />
      </template>
      <div v-else class="files-empty files-preview-placeholder">
        <AppIcon name="Folders" :size="28" />
        <b>打开文件</b>
        <p>从工作区目录树中选择文件</p>
      </div>
    </section>

    <!-- 分隔线 -->
    <div
      v-show="!treeCollapsed"
      class="file-tree-divider"
      role="separator"
      aria-orientation="vertical"
      title="拖拽调整文件树宽度"
      @mousedown="startTreeDrag"
    />

    <!-- 右：文件树 -->
    <div v-show="!treeCollapsed" class="files-body">
      <div v-if="loading" class="files-loading"><AppIcon name="LoaderCircle" :size="18" class="spin" /><span>加载中…</span></div>
      <p v-else-if="treeError" class="files-error">{{ treeError }}</p>
      <ul v-else class="file-tree" role="tree">
        <li v-for="node in root" :key="node.path">
          <FileTreeNode
            :node="node"
            :depth="0"
            :selected-path="selectedPath"
            @toggle="toggleDir"
            @open="openFile"
          />
        </li>
      </ul>
      <p v-if="!loading && !treeError && !root.length" class="files-empty">目录为空</p>
    </div>

    <!-- Open 下拉菜单（通过 Teleport 渲染到 body，避免被 overflow 裁剪） -->
    <Teleport to="body">
      <div
        v-if="openMenuOpen"
        id="file-open-menu-teleport"
        class="file-open-menu file-open-menu--teleport"
        :style="openMenuStyle"
      >
        <button
          v-for="app in externalApps"
          :key="app.id"
          class="file-open-item"
          :class="{ disabled: !app.available }"
          :disabled="!app.available"
          @click="app.available && openWith(app.id)"
        >
          <span class="file-open-icon" :data-icon="appIconSvg(app.icon)">
            <template v-if="app.icon === 'folder'"><AppIcon name="FolderOpen" :size="20" /></template>
            <template v-else-if="app.icon === 'default'"><AppIcon name="Monitor" :size="20" /></template>
            <template v-else-if="app.icon === 'vscode'">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M17 3L7 12L17 21L21 19V5L17 3Z" fill="#007ACC"/><path d="M3 7L7 12L3 17L5.5 18.5L12 12L5.5 5.5L3 7Z" fill="#007ACC"/></svg>
            </template>
            <template v-else-if="app.icon === 'trae'">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="2" y="3" width="20" height="18" rx="4" fill="#1a1a1a"/><rect x="5" y="9" width="5" height="3" rx="1" fill="#22c55e"/><rect x="11" y="9" width="8" height="3" rx="1" fill="#22c55e"/><rect x="5" y="14" width="14" height="2" rx="1" fill="#22c55e"/></svg>
            </template>
            <template v-else-if="app.icon === 'cursor'">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="20" height="20" rx="4" fill="#1a1a1a"/><path d="M7 7l10 10-4 1-2-5-5-2 1-4z" fill="#fff"/><path d="M10 14l2-2" stroke="#fff" stroke-width="1.5"/></svg>
            </template>
            <template v-else-if="app.icon === 'webstorm'">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="20" height="20" rx="3" fill="#000"/><path d="M7 8h4v1.5H9v1.5h2V12H9v3H7V8z" fill="#fff"/><path d="M12 15l3-7h-1.5l-2 5-1-2H9l2 4z" fill="#ff318c"/></svg>
            </template>
            <template v-else>
              <AppIcon name="ExternalLink" :size="20" />
            </template>
          </span>
          <span class="file-open-label">{{ app.name }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>
