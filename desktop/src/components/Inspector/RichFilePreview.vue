<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import DOMPurify from "dompurify";
import { marked, Renderer } from "marked";
import { Code2, Eye } from "@lucide/vue";
import CodePreview from "./CodePreview.vue";
import { readFile } from "../../services/sztu-runtime";

// 富文本文件预览：HTML 页面 / Markdown 报告 / SVG 矢量图支持「渲染预览 ⇄ 源码」切换，
// 其余类型（代码、位图等）直接回退到 CodePreview。
const props = defineProps<{
  path: string;
  content: string;
  encoding?: string;
  binary?: boolean;
  truncated?: boolean;
  mediaBase64?: string | null;
  mimeType?: string | null;
  workspaceId?: string;
  hideChrome?: boolean;
}>();

type RichKind = "html" | "markdown" | "svg";

const extension = computed(() => {
  const name = props.path.split(/[\\/]/).pop() ?? props.path;
  return name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
});
const richKind = computed<RichKind | null>(() => {
  if (props.binary) return null;
  if (/^(?:html?|xhtml)$/.test(extension.value)) return "html";
  if (/^(?:md|markdown)$/.test(extension.value)) return "markdown";
  if (extension.value === "svg" && props.content) return "svg";
  return null;
});

const mode = ref<"rendered" | "source">("rendered");
// 切换文件时回到渲染态，让用户直接看到可视化效果
watch(() => props.path, () => { mode.value = "rendered"; });

// —— SVG：文本内容转 data URL 用 <img> 渲染（不执行内嵌脚本）——
const svgDataUrl = computed(() =>
  richKind.value === "svg" ? `data:image/svg+xml;utf8,${encodeURIComponent(props.content)}` : "",
);

// —— Markdown 渲染：工作区相对路径的图片先渲染为占位，再异步解析为 data URL ——
const imageUrlCache = new Map<string, string>();
const failedImages = new Set<string>();

class MarkdownRenderer extends Renderer {
  override image({ href, title, text }: { href: string; title: string | null | undefined; text: string }): string {
    const alt = text.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    if (/^(?:https?:|data:|blob:)/i.test(href)) {
      const titleAttr = title ? ` title="${title.replace(/"/g, "&quot;")}"` : "";
      return `<img src="${href}" alt="${alt}"${titleAttr} loading="lazy">`;
    }
    const escaped = href.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    return `<img class="rich-img-pending" data-rich-img="${escaped}" alt="${alt}">`;
  }
}
const markdownRenderer = new MarkdownRenderer();

const markdownHtml = computed(() => {
  if (richKind.value !== "markdown") return "";
  const parsed = marked.parse(props.content, { async: false, renderer: markdownRenderer }) as string;
  return DOMPurify.sanitize(parsed, { ADD_ATTR: ["data-rich-img", "loading"] });
});

// Markdown 所在目录：相对图片路径基于它解析
const fileDir = computed(() => {
  const parts = props.path.replace(/\\/g, "/").split("/");
  parts.pop();
  return parts.join("/");
});

function resolveRelative(baseDir: string, rel: string): string {
  const segments = (baseDir ? `${baseDir}/` : "").split("/").filter(Boolean);
  for (const part of rel.replace(/\\/g, "/").split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") segments.pop();
    else segments.push(part);
  }
  return segments.join("/");
}

const markdownBodyEl = ref<HTMLElement | null>(null);
let resolveToken = 0;

async function resolveImages() {
  const root = markdownBodyEl.value;
  const workspaceId = props.workspaceId;
  if (!root) return;
  const token = ++resolveToken;
  const pendings = [...root.querySelectorAll<HTMLImageElement>("img[data-rich-img]")];
  for (const img of pendings) {
    const rawPath = img.dataset.richImg ?? "";
    if (!rawPath) continue;
    const path = resolveRelative(fileDir.value, rawPath);
    const cached = imageUrlCache.get(path);
    if (cached) {
      img.src = cached;
      img.classList.remove("rich-img-pending");
      continue;
    }
    if (failedImages.has(path) || !workspaceId) {
      markImageFailed(img, rawPath);
      continue;
    }
    try {
      const result = await readFile(workspaceId, path);
      if (token !== resolveToken) return; // 文件已切换，放弃本次注入
      if (result.media_base64 && result.mime_type) {
        const dataUrl = `data:${result.mime_type};base64,${result.media_base64}`;
        imageUrlCache.set(path, dataUrl);
        img.src = dataUrl;
        img.classList.remove("rich-img-pending");
      } else if (!result.binary && result.content && result.mime_type === null && /\.svg$/i.test(path)) {
        // SVG 以文本形式返回时手动包装
        const dataUrl = `data:image/svg+xml;utf8,${encodeURIComponent(result.content)}`;
        imageUrlCache.set(path, dataUrl);
        img.src = dataUrl;
        img.classList.remove("rich-img-pending");
      } else {
        failedImages.add(path);
        markImageFailed(img, rawPath);
      }
    } catch {
      failedImages.add(path);
      markImageFailed(img, rawPath);
    }
  }
}

function markImageFailed(img: HTMLImageElement, path: string) {
  const fallback = document.createElement("span");
  fallback.className = "rich-img-failed";
  fallback.textContent = `图片不可用：${path}`;
  img.replaceWith(fallback);
}

watch([markdownHtml, mode], () => {
  if (richKind.value === "markdown" && mode.value === "rendered") void nextTick(resolveImages);
});
</script>

<template>
  <div class="rich-file-preview">
    <div v-if="richKind" class="rich-preview-toolbar">
      <div class="rich-preview-toggle" role="tablist" aria-label="预览方式">
        <button type="button" role="tab" :aria-selected="mode === 'rendered'" :class="{ active: mode === 'rendered' }" @click="mode = 'rendered'"><Eye :size="13" />预览</button>
        <button type="button" role="tab" :aria-selected="mode === 'source'" :class="{ active: mode === 'source' }" @click="mode = 'source'"><Code2 :size="13" />源码</button>
      </div>
      <span v-if="truncated && mode === 'rendered'" class="rich-preview-truncated">文件过大，预览可能不完整</span>
    </div>

    <template v-if="richKind && mode === 'rendered'">
      <iframe
        v-if="richKind === 'html'"
        class="rich-preview-frame"
        sandbox="allow-scripts"
        :srcdoc="content"
        title="HTML 渲染预览"
      />
      <div v-else-if="richKind === 'svg'" class="rich-preview-svg">
        <img :src="svgDataUrl" :alt="path.split(/[\\/]/).pop() ?? path" draggable="false" />
      </div>
      <div v-else ref="markdownBodyEl" class="rich-preview-markdown" v-html="markdownHtml" />
    </template>

    <CodePreview
      v-else
      :content="content"
      :path="path"
      :encoding="encoding"
      :binary="binary"
      :truncated="truncated"
      :media-base64="mediaBase64"
      :mime-type="mimeType"
      :hide-chrome="hideChrome"
    />
  </div>
</template>

<style scoped>
.rich-file-preview {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  flex: 1;
}

.rich-preview-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border, #eceef0);
  background: var(--surface-soft, #f7f8f9);
  flex-shrink: 0;
}

.rich-preview-toggle {
  display: inline-flex;
  padding: 2px;
  gap: 2px;
  background: var(--surface-raised, #eceef0);
  border-radius: 8px;
}

.rich-preview-toggle button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.rich-preview-toggle button.active {
  color: var(--text, #1f2328);
  background: var(--surface, #fff);
  box-shadow: 0 1px 3px rgb(0 0 0 / 10%);
}

.rich-preview-truncated {
  font-size: 11px;
  color: var(--text-muted, #6b7280);
}

.rich-preview-frame {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: 0;
  background: #fff;
}

.rich-preview-svg {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  overflow: auto;
  background:
    repeating-conic-gradient(var(--surface-raised, #eceef0) 0% 25%, transparent 0% 50%) 0 0 / 16px 16px;
}

.rich-preview-svg img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.rich-preview-markdown {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 20px 24px;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text, #1f2328);
}

.rich-preview-markdown :deep(h1),
.rich-preview-markdown :deep(h2),
.rich-preview-markdown :deep(h3),
.rich-preview-markdown :deep(h4) {
  margin: 1.2em 0 0.5em;
  line-height: 1.35;
}

.rich-preview-markdown :deep(h1) { font-size: 20px; }
.rich-preview-markdown :deep(h2) { font-size: 17px; }
.rich-preview-markdown :deep(h3) { font-size: 15px; }

.rich-preview-markdown :deep(p) { margin: 0.6em 0; }

.rich-preview-markdown :deep(a) {
  color: var(--accent, #2563eb);
  text-decoration: none;
}

.rich-preview-markdown :deep(code) {
  padding: 2px 5px;
  font-size: 12.5px;
  background: var(--surface-raised, #eceef0);
  border-radius: 4px;
}

.rich-preview-markdown :deep(pre) {
  padding: 10px 12px;
  overflow: auto;
  background: var(--surface-raised, #eceef0);
  border-radius: 8px;
}

.rich-preview-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
}

.rich-preview-markdown :deep(table) {
  border-collapse: collapse;
  margin: 0.8em 0;
  width: 100%;
  font-size: 12.5px;
}

.rich-preview-markdown :deep(th),
.rich-preview-markdown :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--border, #e3e5e7);
  text-align: left;
}

.rich-preview-markdown :deep(th) {
  background: var(--surface-soft, #f7f8f9);
  font-weight: 600;
}

.rich-preview-markdown :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}

.rich-preview-markdown :deep(blockquote) {
  margin: 0.8em 0;
  padding: 2px 12px;
  color: var(--text-muted, #6b7280);
  border-left: 3px solid var(--border, #e3e5e7);
}

.rich-preview-markdown :deep(.rich-img-pending) {
  min-width: 120px;
  min-height: 60px;
  background: var(--surface-raised, #eceef0);
  border-radius: 6px;
}

.rich-preview-markdown :deep(.rich-img-failed) {
  display: inline-block;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  background: var(--surface-raised, #eceef0);
  border-radius: 6px;
}

@media (prefers-reduced-motion: reduce) {
  .rich-preview-toggle button {
    transition: none;
  }
}
</style>
