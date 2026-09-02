<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, nextTick, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import DOMPurify from "dompurify";
import { marked, Renderer } from "marked";
import { openUrl } from "@tauri-apps/plugin-opener";
import { isTauri } from "@tauri-apps/api/core";
import { render, h } from "vue";
import { useThrottledVisualUpdate } from "../../composables/useThrottledVisualUpdate";
import CodeBlockCard from "./CodeBlockCard.vue";

const props = defineProps<{ tokens: string[]; finalText?: string }>();
const { t } = useI18n({ useScope: "global" });
const text = computed(() => props.finalText || props.tokens.join(""));
const rendered = ref(text.value);
const containerRef = ref<HTMLElement | null>(null);
const codeBlockInstances: { el: HTMLElement; cleanup: () => void }[] = [];

const scheduleRender = useThrottledVisualUpdate(() => {
  rendered.value = text.value;
  nextTick(() => {
    mountCodeBlocks();
  });
});
watch(text, () => scheduleRender());

// 常见代码/文本文件扩展名（用于识别文件路径）
const FILE_EXT_RE = /\.(?:ts|tsx|js|jsx|vue|svelte|py|rb|go|rs|java|kt|c|cpp|h|hpp|cs|php|swift|scala|sh|bash|zsh|fish|ps1|bat|cmd|json|jsonc|yaml|yml|toml|ini|env|xml|html|htm|css|scss|sass|less|md|mdx|txt|log|sql|graphql|gql|proto|dockerfile|makefile|cmake|gradle|lock|cfg|conf|gitignore|npmrc|eslintrc|prettierrc|editorconfig|babelrc|stylelintrc|toml|svg|png|jpg|jpeg|gif|webp|bmp|ico|pdf|zip|tar|gz|rar|7z|mp3|mp4|wav|avi|mov|mjs|cjs|cts|d\.ts|test\.ts|spec\.ts|astro|deno|wasm)$/i;

// 判断一个字符串是否像文件路径
function looksLikeFilePath(raw: string): string | null {
  let str = raw.trim();
  if (!str) return null;
  if (str.length > 200) return null;
  str = str.replace(/^[(["'‘“]+/, "").replace(/[)\]"'’”。，、；：]+$/, "").trim();
  if (!str || /[\s<>{}[\]"']/.test(str)) return null;
  if (/^[a-z]+:\/\//i.test(str)) return null;
  const lineMatch = str.match(/^(.+?)(?::(\d+)(?:-\d+)?)?$/);
  if (!lineMatch) return null;
  const pathPart = lineMatch[1];
  const hasSep = /[\\/]/.test(pathPart) || pathPart.startsWith("./") || pathPart.startsWith("../");
  const hasExt = FILE_EXT_RE.test(pathPart);
  if (!hasSep && !hasExt) return null;
  return pathPart;
}

// 自定义 marked renderer
class CustomRenderer extends Renderer {
  constructor(private readonly translate: (key: string) => string) { super(); }

  override codespan({ text }: { text: string }): string {
    const path = looksLikeFilePath(text);
    if (path) {
      const escaped = path.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
      return `<code class="file-link" data-file="${escaped}" tabindex="0" role="link" title="${this.translate("timeline.fileLink.open")}">${text}</code>`;
    }
    return `<code>${text}</code>`;
  }

  override code({ text, lang }: { text: string; lang?: string }): string {
    const codeId = `code-${Math.random().toString(36).slice(2, 11)}`;
    const langAttr = lang || "plaintext";
    const escapedCode = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
    return `<div class="code-block-mount" data-code-id="${codeId}" data-lang="${langAttr}" data-code="${escapedCode}"></div>`;
  }
}

const customRenderer = new CustomRenderer((key) => t(key));

const html = computed(() => {
  const rawMarkdown = rendered.value;
  const parsed = marked.parse(rawMarkdown, { async: false, renderer: customRenderer }) as string;
  return DOMPurify.sanitize(parsed, {
    ADD_ATTR: ["data-file", "tabindex", "role", "title", "data-code-id", "data-lang", "data-code"],
  });
});

function mountCodeBlocks() {
  // 清理旧的实例
  codeBlockInstances.forEach(({ cleanup }) => cleanup());
  codeBlockInstances.length = 0;

  if (!containerRef.value) return;

  const mountPoints = containerRef.value.querySelectorAll<HTMLElement>(".code-block-mount");
  mountPoints.forEach((el) => {
    const code = el.dataset.code || "";
    const lang = el.dataset.lang || "plaintext";

    const decodedCode = code
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"');

    const vnode = h(CodeBlockCard, {
      code: decodedCode,
      language: lang,
    });

    const parent = el.parentNode;
    if (parent) {
      const fragment = document.createDocumentFragment();
      const div = document.createElement("div");
      div.style.display = "contents";
      fragment.appendChild(div);
      parent.replaceChild(fragment, el);
      render(vnode, div);
      codeBlockInstances.push({
        el: div,
        cleanup: () => {
          render(null, div);
        },
      });
    }
  });
}

onMounted(() => {
  nextTick(() => {
    mountCodeBlocks();
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
  if (event.button === 1 || event.ctrlKey || event.metaKey) {
    void openDefaultBrowser(url);
  } else {
    openInAppBrowserFromUrl(url);
  }
}

function onKeyDown(event: KeyboardEvent) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const fileEl = fileLinkFrom(event);
  if (fileEl) {
    const path = fileEl.dataset.file;
    if (!path) return;
    event.preventDefault();
    void openFilePath(path);
    return;
  }
  const anchor = anchorFrom(event);
  if (!anchor) return;
  const url = safeUrl(anchor.href);
  if (!url) return;
  event.preventDefault();
  openInAppBrowserFromUrl(url);
}

function onLinkContextMenu(event: MouseEvent) {
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
  codeBlockInstances.forEach(({ cleanup }) => cleanup());
  codeBlockInstances.length = 0;
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
    ref="containerRef"
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
        <span class="link-context-menu__main">{{ t('timeline.linkMenu.openInApp') }}</span>
        <span class="link-context-menu__hint">{{ t('timeline.linkMenu.openInAppHint') }}</span>
      </button>
      <button type="button" role="menuitem" @click="openDefaultBrowserFromMenu">
        <span class="link-context-menu__main">{{ t('timeline.linkMenu.openExternal') }}</span>
        <span class="link-context-menu__hint">{{ t('timeline.linkMenu.openExternalHint') }}</span>
      </button>
      <button type="button" role="menuitem" @click="copyLink">
        <span class="link-context-menu__main">{{ t('timeline.linkMenu.copy') }}</span>
        <span class="link-context-menu__hint">{{ menu.url }}</span>
      </button>
    </div>
  </Teleport>
</template>
