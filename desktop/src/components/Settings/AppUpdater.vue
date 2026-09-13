<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import { appUpdateState as update, checkAppUpdate, installAppUpdate, restartAfterUpdate } from "../../services/app-updater";

const { t } = useI18n({ useScope: "global" });
const busy = computed(() => ["checking", "downloading", "installing", "restarting"].includes(update.phase));
const percent = computed(() => update.total > 0 ? Math.min(100, Math.round(update.downloaded / update.total * 100)) : undefined);
const label = computed(() => update.phase === "available" ? "install" : update.phase === "installed" ? "restart" : busy.value ? update.phase : "check");
function act() {
  if (update.phase === "available") void installAppUpdate();
  else if (update.phase === "installed") void restartAfterUpdate();
  else void checkAppUpdate();
}
</script>

<template>
  <section class="app-updater" :aria-label="t('settings.updater.title')" :aria-busy="busy">
    <div class="updater-heading">
      <div>
        <h3>{{ t('settings.updater.title') }}</h3>
        <p>{{ t('settings.updater.description') }}</p>
      </div>
      <button type="button" :disabled="busy" @click="act">
        <AppIcon :name="busy ? 'LoaderCircle' : 'Download'" :size="14" :class="{ spinning: busy }" />
        {{ t(`settings.updater.${label}`) }}
      </button>
    </div>
    <div class="updater-status" role="status" aria-live="polite">
      <p v-if="update.message">{{ t(`settings.updater.${update.message}`) }}</p>
      <p v-else-if="update.phase === 'available'">{{ t('settings.updater.available', { version: update.version }) }}</p>
      <p v-else-if="update.phase === 'latest'">{{ t('settings.updater.latest') }}</p>
      <p v-else-if="update.phase === 'installed'">{{ t('settings.updater.installed') }}</p>
      <p v-else-if="busy">{{ t(`settings.updater.${update.phase}`) }}<span v-if="update.phase === 'downloading' && percent !== undefined"> {{ percent }}%</span></p>
    </div>
    <progress v-if="update.phase === 'downloading'" :value="percent" max="100" :aria-label="t('settings.updater.downloading')" />
    <p v-if="update.phase === 'available'" class="install-notice">{{ t('settings.updater.installNotice') }}</p>
    <details v-if="update.notes">
      <summary>{{ t('settings.updater.notes') }}</summary>
      <p class="release-notes">{{ update.notes }}</p>
    </details>
    <p v-if="update.error" class="updater-error" role="alert">{{ t('settings.updater.failed') }} {{ update.error }}</p>
  </section>
</template>

<style scoped>
.app-updater { border-top: 1px solid var(--border); padding: 16px 0 4px; }
.updater-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h3 { margin: 0; font-size: 13px; font-weight: 600; color: var(--text); }
p { margin: 5px 0 0; font-size: 12px; line-height: 1.6; color: var(--text-muted); overflow-wrap: anywhere; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 32px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-soft); color: var(--text); font: inherit; font-size: 12px; cursor: pointer; }
button:hover:not(:disabled) { border-color: var(--border-strong); }
button:focus-visible { outline: 2px solid var(--text-muted); outline-offset: 3px; }
button:disabled { opacity: .6; cursor: wait; }
.updater-status:has(p) { margin-top: 10px; }
progress { width: 100%; height: 6px; margin-top: 10px; }
details { margin-top: 10px; color: var(--text-muted); font-size: 12px; }
summary { cursor: pointer; }
.release-notes { white-space: pre-wrap; max-height: 180px; overflow-y: auto; }
.updater-error { color: var(--danger, #d85c5c); }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinning { animation: none; } }
</style>
