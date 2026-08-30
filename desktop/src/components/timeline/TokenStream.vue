<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import DOMPurify from "dompurify";
import { marked, Renderer } from "marked";
import { openUrl } from "@tauri-apps/plugin-opener";
import { isTauri } from "@tauri-apps/api/core";
import { useThrottledVisualUpdate } from "../../composables/useThrottledVisualUpdate";

const props = defineProps<{ tokens: string[]; finalText?: string }>();
const text = computed(() => props.finalText || props.tokens.join(""));
const rendered = ref(text.value);
const scheduleRender = useThrottledVisualUpdate(() => { rendered.value = text.value; });
watch(text, () => scheduleRender());

// 常见代码/文本文件扩展名（用于识别文件路径）
const FILE_EXT_RE = /\.(?:ts|tsx|js|jsx|vue|svelte|py|rb|go|rs|java|kt|c|cpp|h|hpp|cs|php|swift|scala|sh|bash|zsh|fish|ps1|bat|cmd|json|jsonc|yaml|yml|toml|ini|env|xml|html|htm|css|scss|sass|less|md|mdx|txt|log|sql|graphql|gql|proto|dockerfile|makefile|cmake|gradle|lock|cfg|conf|gitignore|npmrc|eslintrc|prettierrc|editorconfig|babelrc|stylelintrc|toml|svg|png|jpg|jpeg|gif|webp|bmp|ico|pdf|zip|tar|gz|rar|7z|mp3|mp4|wav|avi|mov|mjs|cjs|cts|d\.ts|test\.ts|spec\.ts|astro|deno|wasm)$/i;

// 判断一个字符串是否像文件路径
function looksLikeFilePath(raw: string): string | null {
  let str = raw.trim();
  if (!str) return null;
  if (str.length > 200) return null;
  // 剥离成对包裹的引号/括号（如 (foo.ts)、“foo.ts”）与尾部常见标点（。，、；：））
  str = str.replace(/^[(["'‘“]+/, "").replace(/[)\]"'’”。，、；：]+$/, "").trim();
  if (!str || /[\s<>{}[\]"']/.test(str)) return null;
  // 排除 URL
  if (/^[a-z]+:\/\//i.test(str)) return null;
  // 先剥离行号后缀（foo.ts:25、foo.ts:25-30），避免把 :25 当作路径的一部分
  const lineMatch = str.match(/^(.+?)(?::(\d+)(?:-\d+)?)?$/);
  if (!lineMatch) return null;
  const pathPart = lineMatch[1];
  // 必须包含路径分隔符或以 ./ ../ 开头 或 包含文件扩展名
  const hasSep = /[\\/]/.test(pathPart) || pathPart.startsWith("./") || pathPart.startsWith("../");
  const hasExt = FILE_EXT_RE.test(pathPart);
  if (!hasSep && !hasExt) return null;
  return pathPart;
}

// 自定义 marked renderer：拦截 codespan（行内 `code`），把识别为文件路径的渲染为可点击链接
class FileLinkRenderer extends Renderer {
  override codespan({ text }: { text: string }): string {
    const path = looksLikeFilePath(text);
    if (path) {
      const escaped = path.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
      return `<code class="file-link" data-file="${escaped}" tabindex="0" role="link" title="点击打开文件">${text}</code>`;
    }
    return `<code>${text}</code>`;
  }
}

const fileLinkRenderer = new FileLinkRenderer();

const html = computed(() => {
  const rawMarkdown = rendered.value;
  // 使用自定义 renderer 解析 markdown
  const parsed = marked.parse(rawMarkdown, { async: false, renderer: fileLinkRenderer }) as string;
  return DOMPurify.sanitize(parsed, {
    ADD_ATTR: ["data-file", "tabindex", "role", "title"],
  });
});

// —— 链接与文件链接统一处理 ——
const nativeRuntime = isTauri();
const menu = ref<{ url: string; x: number; y: number } | null>(null);

function anchorFrom(event: Event): HTMLAnchorElement | null {
  const target = event.target;
  if (!(target instanceof Element)) return null;
  const anchor = target.closest("a");
  return anchor instanceof HTMLAnchorElement ? anchor : null;
}

function fileLinkFrom(event: Event): HTMLElement | null {
  const target = event.target;
  if (!(target instanceof Element)) return null;
  const el = target.closest(".file-link");
  return el instanceof HTMLElement ? el : null;
}

function safeUrl(raw: string): string {
  try {
    return new URL(raw).toString();
  } catch {
    return "";
  }
}

async function openDefaultBrowser(url: string) {
  if (nativeRuntime) {
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener");
  }
}

async function openFilePath(path: string) {
  // 统一派发全局事件，由 App.vue 解析相对路径并打开（需要当前 workspace 路径）
  window.dispatchEvent(new CustomEvent("sztu:open-file", { detail: { path } }));
}

async function openDefaultBrowserFromMenu() {
  const url = menu.value?.url;
  closeMenu();
  if (url) await openDefaultBrowser(url);
}

function openInAppBrowserFromUrl(url: string) {
  window.dispatchEvent(new CustomEvent("sztu:open-in-app-browser", { detail: { url } }));
}

function onLinkClick(event: MouseEvent) {
  if (event.type === "auxclick" && event.button !== 1) return;
  // 优先处理文件链接
  const fileEl = fileLinkFrom(event);
  if (fileEl) {
    const path = fileEl.dataset.file;
    if (path) {
      event.preventDefault();
      void openFilePath(path);
    }
    return;
  }
  const anchor = anchorFrom(event);
  if (!anchor) return;
  const url = safeUrl(anchor.href);
  if (!url) return;
  event.preventDefault();
  // 中键点击 → 系统默认浏览器；左键点击 → 内置浏览器（右侧栏）
  if (event.button === 1 || event.ctrlKey || event.metaKey) {
    void openDefaultBrowser(url);
  } else {
    openInAppBrowserFromUrl(url);
  }
}

// 键盘可访问性：Enter/Space 触发文件链接或URL链接
function onKeyDown(event: KeyboardEvent) {
  if (event.key !== "Enter" && event.key !== " ") return;
  // 优先处理文件链接
  const fileEl = fileLinkFrom(event);
  if (fileEl) {
    const path = fileEl.dataset.file;
    if (!path) return;
    event.preventDefault();
    void openFilePath(path);
    return;
  }
  // 普通 URL 链接：Enter 在内置浏览器打开
  const anchor = anchorFrom(event);
  if (!anchor) return;
  const url = safeUrl(anchor.href);
  if (!url) return;
  event.preventDefault();
  openInAppBrowserFromUrl(url);
}

function onLinkContextMenu(event: MouseEvent) {
  // 文件链接暂不处理右键菜单
  if (fileLinkFrom(event)) return;
  const anchor = anchorFrom(event);
  if (!anchor) return;
  const url = safeUrl(anchor.href);
  if (!url) return;
  event.preventDefault();
  const menuWidth = 260; const menuHeight = 150;
  const x = Math.max(4, Math.min(event.clientX, window.innerWidth - menuWidth - 8));
  const y = Math.max(4, Math.min(event.clientY, window.innerHeight - menuHeight - 8));
  menu.value = { url, x, y };
}

function closeMenu() {
  menu.value = null;
}

function openInAppBrowser() {
  const url = menu.value?.url;
  closeMenu();
  if (!url) return;
  openInAppBrowserFromUrl(url);
}

async function copyLink() {
  const url = menu.value?.url;
  closeMenu();
  if (!url) return;
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = url;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}

function onWindowPointerDown(event: MouseEvent) {
  if (menu.value && !(event.target as Element | null)?.closest?.(".link-context-menu")) closeMenu();
}
function onWindowScroll(event: Event) {
  if (menu.value) {
    if ((event.target as Element | null)?.contains?.(document.body) || event.target === document) closeMenu();
  }
}
function onWindowKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") closeMenu();
}

onBeforeUnmount(() => {
  window.removeEventListener("pointerdown", onWindowPointerDown, true);
  window.removeEventListener("scroll", onWindowScroll, true);
  window.removeEventListener("keydown", onWindowKeydown);
});

watch(menu, () => {
  if (menu.value) {
    window.addEventListener("pointerdown", onWindowPointerDown, true);
    window.addEventListener("scroll", onWindowScroll, true);
    window.addEventListener("keydown", onWindowKeydown);
  } else {
    window.removeEventListener("pointerdown", onWindowPointerDown, true);
    window.removeEventListener("scroll", onWindowScroll, true);
    window.removeEventListener("keydown", onWindowKeydown);
  }
});
</script>

<template>
  <div
    v-if="text"
    class="token-stream markdown-body"
    :class="{ streaming: !finalText }"
    @click="onLinkClick"
    @auxclick="onLinkClick"
    @keydown="onKeyDown"
    @contextmenu="onLinkContextMenu"
  >
    <div v-html="html" />
    <i v-if="!finalText" />
  </div>

  <Teleport to="body">
    <div
      v-if="menu"
      class="link-context-menu"
      role="menu"
      :style="{ left: `${menu.x}px`, top: `${menu.y}px` }"
    >
      <button type="button" role="menuitem" @click="openInAppBrowser">
        <span class="link-context-menu__main">在右侧浏览器栏打开</span>
        <span class="link-context-menu__hint">内置预览</span>
      </button>
      <button type="button" role="menuitem" @click="openDefaultBrowserFromMenu">
        <span class="link-context-menu__main">在默认浏览器中打开</span>
        <span class="link-context-menu__hint">系统浏览器</span>
      </button>
      <button type="button" role="menuitem" @click="copyLink">
        <span class="link-context-menu__main">复制链接地址</span>
        <span class="link-context-menu__hint">{{ menu.url }}</span>
      </button>
    </div>
  </Teleport>
</template>
