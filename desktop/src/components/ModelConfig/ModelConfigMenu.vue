<script setup lang="ts">
import ReasoningEffortSlider from "./ReasoningEffortSlider.vue";
import AppIcon from "../icons/AppIcon.vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { CUSTOM_VENDOR_ID, logoForVendor, vendorIdByName } from "./model-vendors";
import {
  getProviderStatus,
  listModelProfiles,
  selectModelProfile,
  setRuntimeSettings,
  type ModelProfile,
  type ProviderStatus,
  type RuntimeSettings,
} from "../../services/sztu-runtime";

const { t } = useI18n({ useScope: "global" });

const props = defineProps<{ settings: RuntimeSettings | null; status: ProviderStatus | null }>();
const emit = defineEmits<{
  updated: [settings: RuntimeSettings, status: ProviderStatus | null];
  manage: [];
}>();

const root = ref<HTMLElement | null>(null);
const open = ref(false);
const loading = ref(false);
const selecting = ref("");
const models = ref<ModelProfile[]>([]);
const error = ref("");
const trigger = ref<HTMLButtonElement | null>(null);
const reasoningEffort = ref<RuntimeSettings["reasoning_effort"]>(props.settings?.reasoning_effort ?? "");
const savingReasoning = ref(false);
const reasoningApplied = ref(false);
const busy = computed(() => loading.value || Boolean(selecting.value) || savingReasoning.value);

async function applyReasoning(value: RuntimeSettings["reasoning_effort"]) {
  if (busy.value || !props.settings) return;
  if (value === props.settings.reasoning_effort) return;
  const slider = root.value?.querySelector<HTMLInputElement>("input[type=range]");
  const restoreSliderFocus = document.activeElement === slider;
  savingReasoning.value = true;
  reasoningApplied.value = false;
  error.value = "";
  try {
    const settings = await setRuntimeSettings({ reasoning_effort: value });
    if (!settings) throw new Error(t("model.reasoningSaveFailed"));
    reasoningEffort.value = settings.reasoning_effort;
    emit("updated", settings, props.status);
    reasoningApplied.value = true;
  } catch (reason) {
    reasoningEffort.value = props.settings?.reasoning_effort ?? "";
    error.value = reason instanceof Error ? reason.message : t("model.reasoningSaveFailed");
  } finally {
    savingReasoning.value = false;
    await nextTick();
    if (restoreSliderFocus && open.value && document.activeElement === document.body) slider?.focus();
  }
}

watch(() => [props.settings?.model, props.settings?.reasoning_effort] as const, () => {
  reasoningEffort.value = props.settings?.reasoning_effort ?? "";
});
const activeModelName = computed(() =>
  models.value.find((item) => item.is_current)?.name || props.settings?.model || t("model.fallbackName")
);
const modelIcons = [
  { id: "sparkles", icon: "Sparkles" },
  { id: "bot", icon: "Bot" },
  { id: "brain", icon: "Brain" },
  { id: "code", icon: "Code2" },
  { id: "cpu", icon: "Cpu" },
  { id: "chat", icon: "MessageSquare" },
] as const;
const modelIcon = (value: string) => modelIcons.find((item) => item.id === value)?.icon ?? "Sparkles";
const modelLogo = (value: string) => logoForVendor(value) ?? null;
/** 服务商展示名：已知服务商按 id 走 i18n（model.vendor.*），未知服务商回退存储的原始名称 */
const vendorLabel = (vendor: string) => {
  const id = vendorIdByName(vendor);
  return id ? t(`model.vendor.${id}`) : vendor;
};
/** 按存储的服务商名称判断是否为"自定义模型" */
const isCustomVendor = (vendor: string) => vendorIdByName(vendor) === CUSTOM_VENDOR_ID;

async function loadModels() {
  loading.value = true;
  error.value = "";
  try { models.value = await listModelProfiles(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { loading.value = false; }
}

function navigateModels(event: KeyboardEvent) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const buttons = Array.from(root.value?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]:not(:disabled)') ?? []);
  if (!buttons.length) return;
  event.preventDefault();
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
  buttons[next].focus();
}

async function toggle() {
  open.value = !open.value;
  if (open.value) {
    await loadModels();
    await nextTick();
    root.value?.querySelector<HTMLElement>('[aria-checked="true"]')?.scrollIntoView({ block: "nearest" });
  }
}

async function choose(item: ModelProfile) {
  if (busy.value || item.is_current) return;
  reasoningApplied.value = false;
  selecting.value = item.id;
  error.value = "";
  try {
    const result = await selectModelProfile(item.id);
    models.value = result.models;
    emit("updated", result.settings, await getProviderStatus());
    reasoningEffort.value = result.settings.reasoning_effort ?? "";
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { selecting.value = ""; }
}

function openManager() { open.value = false; emit("manage"); }
function closeOnOutsideClick(event: PointerEvent) { if (open.value && !root.value?.contains(event.target as Node)) open.value = false; }
function closeOnEscape(event: KeyboardEvent) { if (open.value && event.key === "Escape") { open.value = false; trigger.value?.focus(); } }

watch(() => props.settings?.model, () => { if (open.value) void loadModels(); });
onMounted(() => { void loadModels(); document.addEventListener("pointerdown", closeOnOutsideClick); document.addEventListener("keydown", closeOnEscape); });
onBeforeUnmount(() => { document.removeEventListener("pointerdown", closeOnOutsideClick); document.removeEventListener("keydown", closeOnEscape); });
</script>

<template>
  <div ref="root" class="model-config-control">
    <button ref="trigger" type="button" class="model-config-trigger" aria-haspopup="dialog" :aria-expanded="open" @click.stop="toggle">
      <i :class="{ online: status?.ready_for_next_run }" /><span>{{ activeModelName }}</span><AppIcon name="ChevronDown" :size="13" />
    </button>
    <section v-if="open" class="model-picker-popover" role="dialog" :aria-label="t('model.selectModel')" @click.stop>
      <header><span>{{ t("model.models") }}</span><small>{{ t("model.configCount", { n: models.length }) }}</small></header>
      <div class="model-picker-list" role="menu" :aria-label="t('model.models')" @keydown="navigateModels">
        <button v-for="item in models" :key="item.id" type="button" role="menuitemradio" :aria-checked="item.is_current" :tabindex="item.is_current ? 0 : -1" :disabled="busy" @click="choose(item)">
          <i class="model-picker-logo">
            <template v-if="isCustomVendor(item.vendor)">
              <img v-if="modelLogo(item.icon)" :src="modelLogo(item.icon) || undefined" alt="" />
              <AppIcon v-else :name="modelIcon(item.icon)" :size="14" />
            </template>
            <template v-else>
              <img v-if="logoForVendor(item.vendor)" :src="logoForVendor(item.vendor) || undefined" alt="" />
              <span v-else>{{ item.vendor.slice(0, 1).toUpperCase() }}</span>
            </template>
          </i>
          <span class="model-name-cell"><b :title="item.name">{{ item.name }}</b><small v-if="vendorLabel(item.vendor).toLowerCase() !== item.name.toLowerCase()">{{ vendorLabel(item.vendor) }}</small></span>
          <AppIcon v-if="selecting === item.id" name="LoaderCircle" class="spin" :size="14" /><AppIcon v-else-if="item.is_current" name="Check" :size="14" />
        </button>
        <p v-if="loading">{{ t("model.loading") }}</p><p v-else-if="!models.length">{{ t("model.empty") }}</p>
      </div>
      <div v-if="settings" class="model-picker-reasoning">
        <ReasoningEffortSlider v-model="reasoningEffort" :model-name="activeModelName" compact :status-text="savingReasoning ? t('model.saving') : reasoningApplied ? t('model.reasoningApplied') : ''" :disabled="busy" @update:model-value="reasoningApplied = false" @change="applyReasoning" />
      </div>
      <p v-if="error" class="model-picker-error" role="alert">{{ error }}</p>
      <footer><button type="button" :disabled="busy" @click="openManager"><AppIcon name="Settings2" :size="15" />{{ t("model.manage") }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.model-picker-popover { border-radius: 14px; }
.model-picker-popover > header { padding: 12px 14px 8px; font-size: 11px; }
.model-picker-popover > header small { font-size: 10px; }
.model-picker-list { padding: 0 6px 6px; max-height: 222px; overscroll-behavior: contain; scrollbar-color: #c9cdd3 transparent; }
.model-picker-list > button { min-height: 42px; padding: 6px 8px; gap: 8px; border-radius: 8px; }
.model-picker-list b { color: #343940; font-size: 13px; font-weight: 500; line-height: 18px; }
.model-picker-list small { font-size: 10px; line-height: 14px; }
.model-picker-list > button[aria-checked="true"] { background: #edf5ff; }
.model-picker-list > button[aria-checked="true"] b { color: #1d589a; font-weight: 600; }
.model-picker-list > button:focus-visible { outline: 2px solid #3498ff; outline-offset: -2px; }
.model-picker-popover > footer { padding: 5px 7px; }
.model-picker-popover > footer button { min-height: 32px; padding: 0 7px; font-size: 11px; color: #737980; }
.model-picker-popover { display: flex; flex-direction: column; width: min(300px, calc(100vw - 32px)); max-height: min(460px, calc(100dvh - 90px)); }
.model-picker-list { min-height: 0; overflow-y: auto; flex: 1 1 auto; }
.model-picker-popover > header, .model-picker-popover > footer, .model-picker-reasoning { flex-shrink: 0; }
.model-picker-reasoning { padding: 10px 14px 12px; border-top: 1px solid #eef0f3; background: #fafbfd; }
.model-picker-list button:disabled { cursor: wait; opacity: 0.6; }
</style>
