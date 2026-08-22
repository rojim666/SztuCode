<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { FileText, Folder, Folders, LoaderCircle } from "@lucide/vue";
import { readFile, workspaceTree, type WorkspaceNode } from "../../services/sztu-runtime";
import CodePreview from "./CodePreview.vue";
import FileTreeNode from "./FileTreeNode.vue";

const props = defineProps<{
  workspaceId: string;
  workspaceName?: string;
  workspacePath?: string;
}>();

export type TreeNode = WorkspaceNode & { children?: TreeNode[]; loading?: boolean };

const root = ref<TreeNode[]>([]);
const loading = ref(false);
const error = ref("");
const treeWidth = ref(Number(localStorage.getItem("sztu.treeWidth")) || 200);
const selectedPath = ref("");
const selectedName = ref("");
const preview = ref("");
const previewEncoding = ref("UTF-8");
const previewBinary = ref(false);
const previewTruncated = ref(false);
const previewMediaBase64 = ref<string | null>(null);
const previewMimeType = ref<string | null>(null);

// 加载某目录的下一层节点：path 为空表示工作区根目录
async function loadDir(node: TreeNode | null) {
  if (node) node.loading = true;
  else loading.value = true;
  error.value = "";
  try {
    // maxDepth=0：只取该目录的直接子项（不含孙级），目录点击时才懒加载下一层
    const nodes = await workspaceTree(props.workspaceId, node?.path ?? "", 0);
    const mapped: TreeNode[] = nodes.map((n) => ({ ...n }));
    if (node) {
      node.children = mapped;
      node.loading = false;
    } else {
      root.value = mapped;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    if (node) node.loading = false;
  } finally {
    if (!node) loading.value = false;
  }
}

// 目录行：已展开则折叠，否则懒加载子节点
function toggleDir(node: TreeNode) {
  if (node.children) {
    node.children = undefined;
    return;
  }
  void loadDir(node);
}

// 拖拽分隔线调整文件树宽度（向右拖变宽），持久化到 localStorage
let dragCleanup: (() => void) | null = null;
function startTreeDrag(event: MouseEvent) {
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = treeWidth.value;
  const onMove = (moveEvent: MouseEvent) => {
    // 树在分隔线右侧：分隔线右移（delta 正）→ 树变窄；左移 → 树变宽
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

// 文件行：读取内容并预览
async function openFile(node: TreeNode) {
  selectedPath.value = node.path;
  selectedName.value = node.name;
  preview.value = "";
  previewEncoding.value = "UTF-8";
  previewBinary.value = false;
  previewTruncated.value = false;
  previewMediaBase64.value = null;
  previewMimeType.value = null;
  try {
    const result = await readFile(props.workspaceId, node.path);
    preview.value = result.content;
    previewEncoding.value = result.encoding;
    previewBinary.value = result.binary;
    previewTruncated.value = result.truncated;
    previewMediaBase64.value = result.media_base64 ?? null;
    previewMimeType.value = result.mime_type ?? null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

watch(() => props.workspaceId, () => {
  root.value = [];
  selectedPath.value = "";
  preview.value = "";
  void loadDir(null);
});
onMounted(() => void loadDir(null));
</script>

<template>
  <div class="file-tree-view" :style="{ gridTemplateColumns: `minmax(0, 1fr) 6px ${treeWidth}px` }">
    <!-- 左：预览栏（未选文件时空白占位） -->
    <section class="file-preview file-preview--files" :class="{ empty: !selectedPath }">
      <header v-if="selectedPath"><span class="preview-tab"><Folder :size="14" /><b>{{ selectedName }}</b><i /></span><small>{{ selectedPath }}</small></header>
      <CodePreview
        v-if="selectedPath"
        :content="preview"
        :path="selectedPath"
        :encoding="previewEncoding"
        :binary="previewBinary"
        :truncated="previewTruncated"
        :media-base64="previewMediaBase64"
        :mime-type="previewMimeType"
      />
      <div v-else class="files-empty files-preview-placeholder">
        <Folders :size="28" :stroke-width="1.7" />
        <b>打开文件</b>
        <p>从工作区目录树中选择文件</p>
      </div>
    </section>

    <!-- 中：可拖拽分隔线，调整预览与文件树的宽度比 -->
    <div class="file-tree-divider" role="separator" aria-orientation="vertical" title="拖拽调整文件树宽度" @mousedown="startTreeDrag" />

    <!-- 右：文件树 -->
    <div class="files-body">
      <div v-if="loading" class="files-loading"><LoaderCircle :size="18" class="spin" /><span>加载中…</span></div>
      <p v-else-if="error" class="files-error">{{ error }}</p>
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
      <p v-if="!loading && !error && !root.length" class="files-empty">目录为空</p>
    </div>
  </div>
</template>
