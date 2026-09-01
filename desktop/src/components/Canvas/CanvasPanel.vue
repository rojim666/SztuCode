<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import DOMPurify from "dompurify";
import { marked, Renderer } from "marked";
import { Check, Copy, Download, FileText, X } from "@lucide/vue";
import { readFile } from "../../services/sztu-runtime";

export type CanvasDoc = {
  id: string;
  title: string;
  content: string;
  version: number;
  updatedAt: string;
};

const props = defineProps<{
  docs: CanvasDoc[];
  activeId: string | null;
  workspaceId?: string;
}>();
const emit = defineEmits<{ close: []; select: [id: string] }>();

// 当前展示的文档：优先选中项，否则最新一篇
const activeDoc = computed<CanvasDoc | null>(() => {
  if (!props.docs.length) return null;
  return props.docs.find((doc) => doc.id === props.activeId) ?? props.docs[props.docs.length - 1]!;
});

// —— Markdown 渲染：工作区相对路径的图片先渲染为占位，再异步解析为 data URL ——
const imageUrlCache = new Map<string, string>();
const failedImages = new Set<string>();

class CanvasRenderer extends Renderer {
  override image({ href, title, text }: { href: string; title: string | null | undefined; text: string }): string {
    const alt = text.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    if (/^(?:https?:|data:|blob:)/i.test(href)) {
      const titleAttr = title ? ` title="${title.replace(/"/g, "&quot;")}"` : "";
      return `<img src="${href}" alt="${alt}"${titleAttr} loading="lazy">`;
    }
    // 工作区相对路径（或绝对路径）：占位，渲染后由 resolveImages 注入 data URL
    const escaped = href.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    return `<img class="canvas-img-pending" data-canvas-img="${escaped}" alt="${alt}">`;
  }
}
const canvasRenderer = new CanvasRenderer();

const html = computed(() => {
  if (!activeDoc.value) return "";
  const parsed = marked.parse(activeDoc.value.content, { async: false, renderer: canvasRenderer }) as string;
  return DOMPurify.sanitize(parsed, { ADD_ATTR: ["data-canvas-img", "loading"] });
});

const bodyEl = ref<HTMLElement | null>(null);
let resolveToken = 0;

async function resolveImages() {
  const root = bodyEl.value;
  const workspaceId = props.workspaceId;
  if (!root) return;
  const token = ++resolveToken;
  const pendings = [...root.querySelectorAll<HTMLImageElement>("img[data-canvas-img]")];
  for (const img of pendings) {
    const path = img.dataset.canvasImg ?? "";
    if (!path) continue;
    const cached = imageUrlCache.get(path);
    if (cached) {
      img.src = cached;
      img.classList.remove("canvas-img-pending");
      continue;
    }
    if (failedImages.has(path) || !workspaceId) {
      markImageFailed(img, path);
      continue;
    }
    try {
      const result = await readFile(workspaceId, path);
      if (token !== resolveToken) return; // 文档已切换，放弃本次注入
      if (result.media_base64 && result.mime_type) {
        const dataUrl = `data:${result.mime_type};base64,${result.media_base64}`;
        imageUrlCache.set(path, dataUrl);
        img.src = dataUrl;
        img.classList.remove("canvas-img-pending");
      } else {
        failedImages.add(path);
        markImageFailed(img, path);
      }
    } catch {
      failedImages.add(path);
      markImageFailed(img, path);
    }
  }
}

function markImageFailed(img: HTMLImageElement, path: string) {
  const fallback = document.createElement("span");
  fallback.className = "canvas-img-failed";
  fallback.textContent = `图片不可用：${path}`;
  img.replaceWith(fallback);
}

watch([html, () => props.workspaceId], () => { void nextTick(resolveImages); }, { flush: "post" });

// —— 操作：复制 Markdown / 下载 .md ——
const copied = ref(false);
let copiedTimer: ReturnType<typeof setTimeout> | null = null;

async function copyMarkdown() {
  const doc = activeDoc.value;
  if (!doc) return;
  try {
    await navigator.clipboard.writeText(doc.content);
  } catch {
    // 剪贴板 API 不可用（非安全上下文）时退化为选区复制
    const textarea = document.createElement("textarea");
    textarea.value = doc.content;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  copied.value = true;
  if (copiedTimer) clearTimeout(copiedTimer);
  copiedTimer = setTimeout(() => { copied.value = false; }, 1500);
}

function downloadMarkdown() {
  const doc = activeDoc.value;
  if (!doc) return;
  const safeName = (doc.title.replace(/[\\/:*?"<>|]+/g, "-").trim() || "canvas-document").slice(0, 60);
  const blob = new Blob([doc.content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeName}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer);
});
</script>

<template>
  <aside class="canvas-panel" aria-label="文档画布">
    <header class="canvas-panel__header">
      <span class="canvas-panel__icon"><FileText :size="16" :stroke-width="1.8" /></span>
      <b class="canvas-panel__title" :title="activeDoc?.title">{{ activeDoc?.title || "文档画布" }}</b>
      <em v-if="activeDoc" class="canvas-panel__version">v{{ activeDoc.version }}</em>
      <div class="canvas-panel__actions">
        <button type="button" class="canvas-panel__action" :title="copied ? '已复制' : '复制 Markdown'" :aria-label="copied ? '已复制' : '复制 Markdown'" :disabled="!activeDoc" @click="copyMarkdown">
          <Check v-if="copied" :size="15" :stroke-width="2" />
          <Copy v-else :size="15" :stroke-width="1.8" />
        </button>
        <button type="button" class="canvas-panel__action" title="下载 Markdown 文件" aria-label="下载 Markdown 文件" :disabled="!activeDoc" @click="downloadMarkdown">
          <Download :size="15" :stroke-width="1.8" />
        </button>
        <button type="button" class="canvas-panel__action" title="关闭画布" aria-label="关闭画布" @click="emit('close')">
          <X :size="15" :stroke-width="1.8" />
        </button>
      </div>
    </header>

    <nav v-if="docs.length > 1" class="canvas-panel__tabs" aria-label="文档列表">
      <button
        v-for="doc in docs"
        :key="doc.id"
        type="button"
        class="canvas-panel__tab"
        :class="{ active: doc.id === activeDoc?.id }"
        :title="doc.title"
        @click="emit('select', doc.id)"
      >{{ doc.title }}</button>
    </nav>

    <div ref="bodyEl" class="canvas-panel__body markdown-body" v-html="html" />

    <footer v-if="activeDoc" class="canvas-panel__footer">
      <span>{{ activeDoc.content.length }} 字</span>
      <span>更新于 {{ formatTime(activeDoc.updatedAt) }}</span>
    </footer>
  </aside>
</template>
