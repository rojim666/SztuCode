<script setup lang="ts">
import { getCurrentWindow } from "@tauri-apps/api/window";
import { emit } from "@tauri-apps/api/event";
import { onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n({ useScope: "global" });

const win = getCurrentWindow();
onMounted(() => document.body.classList.add("tray-menu-host"));
function closeOnBlur() { void win.hide(); }
function closeOutside(event: PointerEvent) {
  if (!(event.target as Element | null)?.closest(".tray-menu")) void win.hide();
}
onMounted(() => {
  window.addEventListener("blur", closeOnBlur);
  document.addEventListener("visibilitychange", closeOnBlur);
  document.addEventListener("pointerdown", closeOutside, true);
});
onBeforeUnmount(() => {
  document.body.classList.remove("tray-menu-host");
  window.removeEventListener("blur", closeOnBlur);
  document.removeEventListener("visibilitychange", closeOnBlur);
  document.removeEventListener("pointerdown", closeOutside, true);
});
async function action(name: string) {
  await win.hide();
  await emit(`tray://${name}`);
}
</script>

<template>
<main class="tray-menu" tabindex="-1" @keydown.esc="win.hide()" @mousedown.stop>
    <header><span class="mark">S</span><div><strong>SztuCode</strong><small>{{ t('tray.subtitle') }}</small></div></header>
    <button class="primary" @click="action('new_chat')">{{ t('tray.newChat') }}</button>
    <div class="section-label">{{ t('tray.quickAccess') }}</div>
    <button @click="action('show')">{{ t('tray.showMainWindow') }}</button>
    <button @click="action('workspaces')">{{ t('tray.workspaces') }}</button>
    <button @click="action('settings')">{{ t('tray.settings') }}</button>
    <div class="divider" />
    <button class="quit" @click="action('quit')">{{ t('tray.quit') }}</button>
  </main>
</template>

<style scoped>
.tray-menu, .tray-menu *, .tray-menu *::before, .tray-menu *::after { box-sizing: border-box; }
:global(html), :global(body.tray-menu-host), :global(body.tray-menu-host #app) { width: 100%; height: 100%; margin: 0; overflow: hidden; background: transparent; }
:global(body.tray-menu-host) { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
.tray-menu { width: 300px; padding: 14px; color: #1c2330; background: #fff; border: 1px solid #dfe4eb; border-radius: 16px; box-shadow: 0 14px 34px #1c23302b; }
header { display: flex; align-items: center; gap: 10px; padding: 3px 6px 14px; }
.mark { display: grid; width: 34px; height: 34px; place-items: center; color: #1c2330; background: #f1f4f8; border: 2px solid #1c2330; border-radius: 11px; font-weight: 800; }
header strong, header small { display: block; } header strong { font-size: 15px; } header small { margin-top: 2px; color: #8b94a3; font-size: 11px; }
button { width: 100%; padding: 10px 11px; color: #303948; background: transparent; border: 0; border-radius: 9px; font: inherit; font-size: 14px; text-align: left; cursor: pointer; }
button:hover { background: #f1f5f9; } .primary { margin-bottom: 10px; color: #fff; background: #1c2330; font-weight: 600; } .primary:hover { background: #303b4c; }
.section-label { padding: 5px 11px 3px; color: #a0a8b5; font-size: 11px; } .divider { height: 1px; margin: 9px 4px; background: #e8ecf1; } .quit { color: #c0393b; } .quit:hover { background: #fff1f1; }
</style>
