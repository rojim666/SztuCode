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
const MENU_WIDTH = 252;

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

function closeOnBlur() { void win.hide(); }
// 仅在页面真正不可见时关闭；visibilitychange 在窗口显示时也会触发，直接隐藏会导致菜单闪现即消失
function closeOnHidden() { if (document.visibilityState === "hidden") void win.hide(); }
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
  window.addEventListener("blur", closeOnBlur);
  document.addEventListener("visibilitychange", closeOnHidden);
  document.addEventListener("pointerdown", closeOutside, true);
  window.addEventListener("storage", syncSharedState);
  observer = new ResizeObserver(() => { void fitWindow(); });
  if (menuEl.value) observer.observe(menuEl.value);
  void fitWindow();
  menuEl.value?.focus();
});
onBeforeUnmount(() => {
  document.body.classList.remove("tray-menu-host");
  window.removeEventListener("blur", closeOnBlur);
  document.removeEventListener("visibilitychange", closeOnHidden);
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
    <header><span class="mark">S</span><div><strong>SztuCode</strong><small>{{ t('tray.subtitle') }}</small></div></header>
    <button class="primary" role="menuitem" @click="action('new_chat')"><AppIcon name="MessageSquarePlus" :size="16" />{{ t('tray.newChat') }}</button>
    <div class="section-label">{{ t('tray.quickAccess') }}</div>
    <button role="menuitem" @click="action('show')"><AppIcon name="AppWindow" :size="16" />{{ t('tray.showMainWindow') }}</button>
    <button role="menuitem" @click="action('workspaces')"><AppIcon name="FolderOpen" :size="16" />{{ t('tray.workspaces') }}</button>
    <button role="menuitem" @click="action('settings')"><AppIcon name="Settings" :size="16" />{{ t('tray.settings') }}</button>
    <div class="divider" />
    <button class="quit" role="menuitem" @click="action('quit')"><AppIcon name="Power" :size="16" />{{ t('tray.quit') }}</button>
  </main>
</template>

<style scoped>
.tray-menu, .tray-menu *, .tray-menu *::before, .tray-menu *::after { box-sizing: border-box; }
:global(html), :global(body.tray-menu-host), :global(body.tray-menu-host #app) { width: 100%; height: 100%; margin: 0; overflow: hidden; background: transparent; }
:global(body.tray-menu-host) { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }

.tray-menu {
  width: 252px;
  padding: 6px;
  color: #1f2329;
  background: #fff;
  border: 1px solid #e3e6ea;
  border-radius: 12px;
  box-shadow: 0 12px 32px rgb(28 35 48 / 18%), 0 2px 8px rgb(28 35 48 / 8%);
  outline: none;
  user-select: none;
}

header { display: flex; align-items: center; gap: 10px; padding: 8px 10px 10px; }
.mark { display: grid; width: 30px; height: 30px; place-items: center; flex: none; color: #fff; background: #1f2329; border-radius: 9px; font-size: 14px; font-weight: 700; }
header strong, header small { display: block; }
header strong { font-size: 13px; font-weight: 600; letter-spacing: 0.2px; }
header small { margin-top: 1px; color: #8a919c; font-size: 11px; }

button {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  color: #2b313a;
  background: transparent;
  border: 0;
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}
button:hover { background: #f2f3f5; }
button:focus-visible { background: #f2f3f5; outline: none; }
button .app-icon { color: #646b76; }

.primary { margin: 2px 0 6px; color: #fff; background: #1f2329; font-weight: 600; }
.primary:hover, .primary:focus-visible { background: #33383f; }
.primary .app-icon { color: #fff; }

.section-label { padding: 4px 10px 2px; color: #9aa1ab; font-size: 11px; }
.divider { height: 1px; margin: 6px 10px; background: #eceef1; }

.quit { color: #c8544a; }
.quit .app-icon { color: #c8544a; }
.quit:hover, .quit:focus-visible { background: #fdf1f0; }

/* 暗色主题（托盘是独立窗口，主题通过 sztu.appearance 同步到 data-app-theme） */
:global([data-app-theme="dark"] .tray-menu){ color: #e8eaed; background: #2b2d31; border-color: #43464c; box-shadow: 0 12px 32px rgb(0 0 0 / 45%), 0 2px 8px rgb(0 0 0 / 30%); }
:global([data-app-theme="dark"] .mark){ color: #1f2329; background: #e8eaed; }
:global([data-app-theme="dark"] header small){ color: #9aa1ab; }
:global([data-app-theme="dark"] button){ color: #d6d9de; }
:global([data-app-theme="dark"] button:hover),
:global([data-app-theme="dark"] button:focus-visible){ background: rgb(255 255 255 / 7%); }
:global([data-app-theme="dark"] button .app-icon){ color: #9aa1ab; }
:global([data-app-theme="dark"] .primary){ color: #1f2329; background: #e8eaed; }
:global([data-app-theme="dark"] .primary:hover),
:global([data-app-theme="dark"] .primary:focus-visible){ background: #ffffff; }
:global([data-app-theme="dark"] .primary .app-icon){ color: #1f2329; }
:global([data-app-theme="dark"] .section-label){ color: #7d848e; }
:global([data-app-theme="dark"] .divider){ background: #3f4248; }
:global([data-app-theme="dark"] .quit),
:global([data-app-theme="dark"] .quit .app-icon){ color: #e8a19b; }
:global([data-app-theme="dark"] .quit:hover),
:global([data-app-theme="dark"] .quit:focus-visible){ background: rgb(232 161 155 / 12%); }

@media (prefers-reduced-motion: reduce) {
  button { transition: none; }
}
</style>
