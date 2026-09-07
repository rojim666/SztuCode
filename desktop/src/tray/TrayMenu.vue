<script setup lang="ts">
import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { emit } from "@tauri-apps/api/event";
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../components/icons/AppIcon.vue";
import { i18n } from "../i18n";
import { loadAppearanceSettings } from "../services/appearance";

const { t } = useI18n({ useScope: "global" });

const win = getCurrentWindow();
const menuEl = ref<HTMLElement | null>(null);
const MENU_WIDTH = 216;

// 主窗口切换语言/主题后，通过共享 localStorage 的 storage 事件同步到托盘窗口
function syncSharedState(event: StorageEvent) {
  if (event.key === "sztu.locale" && (event.newValue === "zh-CN" || event.newValue === "en-US")) {
    i18n.global.locale.value = event.newValue;
  }
  if (event.key === "sztu.appearance") applyTheme();
}

function applyTheme() {
  const settings = loadAppearanceSettings();
  const dark = settings.theme === "dark"
    || (settings.theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.appTheme = dark ? "dark" : "light";
}

// 内容高度自适应：窗口初始隐藏，挂载即测量内容并调整窗口尺寸，
// 避免 Rust 侧写死高度导致文案变化后裁剪或留白
let observer: ResizeObserver | null = null;
async function fitWindow() {
  await nextTick();
  const el = menuEl.value;
  if (!el) return;
  const height = Math.ceil(el.getBoundingClientRect().height);
  if (height > 0) await win.setSize(new LogicalSize(MENU_WIDTH, height));
}

// 原生 Focused(false) 统一处理失焦关闭，避免 WebView 焦点切换抢先吞掉点击。
function closeOutside(event: PointerEvent) {
  if (!(event.target as Element | null)?.closest(".tray-menu")) void win.hide();
}

// 方向键在菜单项间循环移动焦点
function onKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const items = Array.from(menuEl.value?.querySelectorAll<HTMLButtonElement>("button") ?? []);
  if (!items.length) return;
  event.preventDefault();
  const idx = items.indexOf(document.activeElement as HTMLButtonElement);
  const next = event.key === "ArrowDown"
    ? (idx + 1) % items.length
    : (idx - 1 + items.length) % items.length;
  items[next].focus();
}

onMounted(() => {
  document.body.classList.add("tray-menu-host");
  applyTheme();
  document.addEventListener("pointerdown", closeOutside, true);
  window.addEventListener("storage", syncSharedState);
  observer = new ResizeObserver(() => { void fitWindow(); });
  if (menuEl.value) observer.observe(menuEl.value);
  void fitWindow();
  menuEl.value?.focus();
});
onBeforeUnmount(() => {
  document.body.classList.remove("tray-menu-host");
  document.removeEventListener("pointerdown", closeOutside, true);
  window.removeEventListener("storage", syncSharedState);
  observer?.disconnect();
  observer = null;
});

// 托盘动作前先把主窗口恢复到前台，否则关闭到托盘后点菜单项看不到任何反应
async function revealMainWindow() {
  const main = await WebviewWindow.getByLabel("main");
  if (!main) return;
  if (await main.isMinimized()) await main.unminimize();
  await main.show();
  await main.setFocus();
}

async function action(name: string) {
  await win.hide();
  // 退出无需还原主窗口，直接转发给 Rust 侧退出进程
  if (name === "quit") { await emit("tray://quit"); return; }
  await revealMainWindow();
  // "show" 只需还原主窗口，无需转发事件
  if (name !== "show") await emit(`tray://${name}`);
}
</script>

<template>
<main ref="menuEl" class="tray-menu" tabindex="-1" role="menu" @keydown="onKeydown" @keydown.esc="win.hide()" @mousedown.stop>
    <button role="menuitem" @click="action('new_chat')"><AppIcon name="MessageSquarePlus" :size="16" />{{ t('tray.newChat') }}</button>
    <button role="menuitem" @click="action('show')"><AppIcon name="AppWindow" :size="16" />{{ t('tray.showMainWindow') }}</button>
    <button role="menuitem" @click="action('workspaces')"><AppIcon name="FolderOpen" :size="16" />{{ t('tray.workspaces') }}</button>
    <button role="menuitem" @click="action('settings')"><AppIcon name="Settings" :size="16" />{{ t('tray.settings') }}</button>
    <div class="divider" role="separator" />
    <button role="menuitem" @click="action('quit')"><AppIcon name="Power" :size="16" />{{ t('tray.quit') }}</button>
  </main>
</template>

<style scoped>
.tray-menu, .tray-menu *, .tray-menu *::before, .tray-menu *::after { box-sizing: border-box; }
:global(body.tray-menu-host), :global(body.tray-menu-host #app) { width: 100%; height: 100%; margin: 0; overflow: hidden; background: transparent; }
:global(body.tray-menu-host) { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
.tray-menu {
  --menu-text: #262626;
  --menu-muted: #737373;
  --menu-hover: #f0f0f0;
  --menu-border: #e5e5e5;
  width: 216px;
  padding: 5px;
  color: var(--menu-text);
  background: #fcfcfc;
  border: 1px solid var(--menu-border);
  border-radius: 8px;
  outline: none;
  user-select: none;
}
button {
  display: flex;
  width: 100%;
  height: 32px;
  align-items: center;
  gap: 9px;
  padding: 0 9px;
  color: var(--menu-text);
  background: transparent;
  border: 0;
  border-radius: 4px;
  font: inherit;
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
  text-align: left;
  cursor: default;
}
button:hover, button:focus-visible { background: var(--menu-hover); outline: none; }
button:focus-visible { box-shadow: inset 0 0 0 1px var(--menu-muted); }
button .app-icon { color: var(--menu-muted); flex: none; }
.divider { height: 1px; margin: 4px 8px; background: var(--menu-border); }
:global([data-app-theme="dark"]) .tray-menu {
  --menu-text: #ededed;
  --menu-muted: #a3a3a3;
  --menu-hover: #383838;
  --menu-border: #404040;
  background: #262626;
}
</style>