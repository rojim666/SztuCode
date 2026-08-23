<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { openUrl } from "@tauri-apps/plugin-opener";
import { isTauri } from "@tauri-apps/api/core";
import { useThrottledVisualUpdate } from "../../composables/useThrottledVisualUpdate";

const props = defineProps<{ tokens: string[]; finalText?: string }>();
const text = computed(() => props.finalText || props.tokens.join(""));
// 流式 Markdown 重解析按 3 帧节流（借鉴 dsh 流式正文管线）：
// 一帧内 N 次文本更新合并为一次 marked 解析 + DOMPurify 清洗，
// 渲染滞后 ≤3 帧（约 50ms）不可感知，长文本流式时解析频率降为 1/3
const rendered = ref(text.value);
const scheduleRender = useThrottledVisualUpdate(() => { rendered.value = text.value; });
watch(text, () => scheduleRender());
const html = computed(() => DOMPurify.sanitize(marked.parse(rendered.value, { async: false }) as string));

// —— 链接安全打开 ——
// v-html 渲染的 <a> 在 Tauri webview 中点击会导航当前窗口（整窗跳走且无法返回），
// 这里通过容器事件委托统一拦截：左键用系统默认浏览器打开；
// 右键提供「默认浏览器 / 右侧浏览器栏 / 复制链接」菜单。
const nativeRuntime = isTauri();
const menu = ref<{ url: string; x: number; y: number } | null>(null);

function anchorFrom(event: Event): HTMLAnchorElement | null {
  const target = event.target;
  if (!(target instanceof Element)) return null;
  const anchor = target.closest("a");
  return anchor instanceof HTMLAnchorElement ? anchor : null;
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

// 右键菜单项：先关闭菜单再打开系统浏览器，避免浮层残留
async function openDefaultBrowserFromMenu() {
  const url = menu.value?.url;
  closeMenu();
  if (url) await openDefaultBrowser(url);
}

function onLinkClick(event: MouseEvent) {
  // 只处理左键（click, button=0）与中键（auxclick, button=1）：
  // 右键会先触发 contextmenu（弹出菜单）再触发 auxclick(button=2)，
  // 若不过滤会导致菜单弹出的同时误打开系统浏览器。
  if (event.type === "auxclick" && event.button !== 1) return;
  const anchor = anchorFrom(event);
  if (!anchor) return;
  const url = safeUrl(anchor.href);
  if (!url) return;
  // 无论左/中键或修饰键组合，一律阻止 webview 内导航
  event.preventDefault();
  void openDefaultBrowser(url);
}

function onLinkContextMenu(event: MouseEvent) {
  const anchor = anchorFrom(event);
  if (!anchor) return;
  const url = safeUrl(anchor.href);
  if (!url) return;
  event.preventDefault();
  // 菜单浮层 clamp 到视口内：靠近窗口右/下边缘时向左上收缩，避免被裁切
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
  window.dispatchEvent(new CustomEvent("sztu:open-in-app-browser", { detail: { url } }));
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

// 菜单为 Teleport 到 body 的浮层：点击菜单外 / 滚动 / 窗口缩放 / Esc 均关闭
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

// 注册时机依赖 v-html 内容挂载，组件卸载时同步清理
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
