<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import { setRuntimeSettings, type RuntimeSettings } from "../../services/sztu-runtime";

const props = defineProps<{ settings: RuntimeSettings | null }>();
const emit = defineEmits<{ updated: [settings: RuntimeSettings] }>();
const { t } = useI18n({ useScope: "global" });
const enabled = ref(false);
const model = ref("jev-latest");
const threshold = ref(0.8);
const key = ref("");
const configured = ref(false);
const busy = ref(false);
const error = ref("");
const saved = ref(false);
const supported = computed(() => typeof props.settings?.experimental_jev === "boolean");

watch(() => props.settings, settings => {
  enabled.value = settings?.experimental_jev === true;
  model.value = settings?.jev_model ?? "jev-latest";
  threshold.value = settings?.jev_confidence_threshold ?? 0.8;
  configured.value = settings?.jev_api_key_configured === true;
}, { immediate: true });

async function save(nextEnabled = enabled.value) {
  busy.value = true; error.value = ""; saved.value = false;
  try {
    if (!supported.value) throw new Error(t("settings.jev.runtimeOutdated"));
    if (nextEnabled && !configured.value && !key.value.trim()) throw new Error(t("settings.jev.keyRequired"));
    const settings = await setRuntimeSettings({
      experimental_jev: nextEnabled, jev_model: model.value.trim(), jev_confidence_threshold: threshold.value,
      ...(key.value.trim() ? { jev_api_key: key.value.trim() } : {}),
    });
    if (!settings) throw new Error(t("settings.jev.unavailable"));
    if (typeof settings.experimental_jev !== "boolean") throw new Error(t("settings.jev.runtimeOutdated"));
    if (settings.experimental_jev !== nextEnabled || settings.jev_model !== model.value.trim() || settings.jev_confidence_threshold !== threshold.value) throw new Error(t("settings.jev.notApplied"));
    enabled.value = settings.experimental_jev === true;
    configured.value = settings.jev_api_key_configured === true;
    key.value = ""; saved.value = true;
    emit("updated", settings);
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
</script>

<template>
  <section class="jev-settings" :aria-label="t('settings.jev.section')" :aria-busy="busy">
    <h3>{{ t('settings.jev.section') }}</h3>
    <div class="jev-toggle-row">
      <label for="jev-mode">{{ t('settings.jev.title') }}</label>
      <button id="jev-mode" type="button" role="switch" class="jev-toggle" :class="{ enabled }" :aria-checked="enabled" :aria-label="t('settings.jev.title')" :disabled="busy || !supported" @click="save(!enabled)"><span /></button>
    </div>
    <p class="jev-notice">{{ t('settings.jev.notice') }}</p>
    <p v-if="!settings" class="jev-error" role="status">{{ t('settings.jev.unavailable') }}</p>
    <p v-else-if="!supported" class="jev-error" role="alert">{{ t('settings.jev.runtimeOutdated') }}</p>
    <p v-if="error" class="jev-error" role="alert">{{ error }}</p>
    <form class="jev-form" @submit.prevent="save()" @input="saved = false">
      <label>{{ t('settings.jev.apiKey') }}
        <input v-model="key" type="password" autocomplete="new-password" spellcheck="false" :disabled="busy || !settings" :placeholder="configured ? t('settings.jev.keyConfigured') : 'TYPESAFE_API_KEY'" />
      </label>
      <div class="jev-fields">
        <label>{{ t('settings.jev.model') }}
          <input v-model="model" required maxlength="200" :disabled="busy || !settings" spellcheck="false" />
        </label>
        <label>{{ t('settings.jev.threshold') }}
          <input v-model.number="threshold" type="number" min="0" max="1" step="0.05" required :disabled="busy || !settings" />
        </label>
      </div>
      <div class="jev-actions">
        <button type="submit" class="btn" :disabled="busy || !supported"><AppIcon :name="busy ? 'LoaderCircle' : 'Save'" :size="14" />{{ t('settings.jev.save') }}</button>
        <span v-if="saved" role="status">{{ t('settings.jev.saved') }}</span>
      </div>
    </form>
  </section>
</template>

<style scoped>
.jev-settings { padding: 20px 18px; border-top: 1px solid var(--border); }
h3 { margin: 0 0 16px; font-size: 14px; }
.jev-toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: 13px; }
.jev-notice { font-size: 12px; line-height: 1.6; opacity: .7; margin: 8px 0 16px; }
.jev-toggle { width: 34px; height: 20px; flex: 0 0 34px; padding: 2px; border: 0; border-radius: 10px; background: #71717a; cursor: pointer; }
.jev-toggle span { display: block; width: 16px; height: 16px; border-radius: 50%; background: white; transition: transform .15s; }
.jev-toggle.enabled { background: var(--accent); }
.jev-toggle.enabled span { transform: translateX(14px); }
.jev-form { display: grid; gap: 12px; }
.jev-form label { display: grid; gap: 6px; min-width: 0; font-size: 12px; }
.jev-form input { width: 100%; min-width: 0; box-sizing: border-box; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-soft); color: inherit; font: inherit; }
.jev-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(100px, .65fr); gap: 12px; }
.jev-actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; font-size: 12px; }
.jev-actions .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 32px; padding: 0 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-soft); color: var(--text); font: inherit; cursor: pointer; }
.jev-actions .btn:hover:not(:disabled) { background: var(--accent-soft); }
.jev-error { color: var(--danger-color, #d55b65); font-size: 12px; overflow-wrap: anywhere; margin: 0; }
button:disabled { opacity: .5; cursor: default; }
@media (max-width: 520px) { .jev-fields { grid-template-columns: minmax(0, 1fr); } }
</style>
