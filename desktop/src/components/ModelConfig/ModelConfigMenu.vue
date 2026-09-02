<script setup lang="ts">
import { Bot, Brain, Check, ChevronDown, Code2, Cpu, LoaderCircle, MessageSquare, Settings2, Sparkles } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { CUSTOM_VENDOR_ID, logoForVendor, vendorIdByName } from "./model-vendors";
import {
  getProviderStatus,
  listModelProfiles,
  selectModelProfile,
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
const activeModelName = computed(() =>
  models.value.find((item) => item.is_current)?.name || props.settings?.model || t("model.fallbackName")
);
const modelIcons = [
  { id: "sparkles", component: Sparkles },
  { id: "bot", component: Bot },
  { id: "brain", component: Brain },
  { id: "code", component: Code2 },
  { id: "cpu", component: Cpu },
  { id: "chat", component: MessageSquare },
] as const;
const modelIcon = (value: string) => modelIcons.find((item) => item.id === value)?.component ?? Sparkles;
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

async function toggle() {
  open.value = !open.value;
  if (open.value) await loadModels();
}

async function choose(item: ModelProfile) {
  if (item.is_current) { open.value = false; return; }
  selecting.value = item.id;
  error.value = "";
  try {
    const result = await selectModelProfile(item.id);
    models.value = result.models;
    emit("updated", result.settings, await getProviderStatus());
    open.value = false;
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { selecting.value = ""; }
}

function openManager() { open.value = false; emit("manage"); }
function closeOnOutsideClick(event: PointerEvent) { if (open.value && !root.value?.contains(event.target as Node)) open.value = false; }
function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") open.value = false; }

watch(() => props.settings?.model, () => { if (open.value) void loadModels(); });
onMounted(() => { void loadModels(); document.addEventListener("pointerdown", closeOnOutsideClick); document.addEventListener("keydown", closeOnEscape); });
onBeforeUnmount(() => { document.removeEventListener("pointerdown", closeOnOutsideClick); document.removeEventListener("keydown", closeOnEscape); });
</script>

<template>
  <div ref="root" class="model-config-control">
    <button type="button" class="model-config-trigger" aria-haspopup="menu" :aria-expanded="open" @click.stop="toggle">
      <i :class="{ online: status?.ready_for_next_run }" /><span>{{ activeModelName }}</span><ChevronDown :size="13" />
    </button>
    <section v-if="open" class="model-picker-popover" role="menu" :aria-label="t('model.selectModel')" @click.stop>
      <header><span>{{ t("model.models") }}</span><small>{{ t("model.configCount", { n: models.length }) }}</small></header>
      <div class="model-picker-list">
        <button v-for="item in models" :key="item.id" type="button" role="menuitemradio" :aria-checked="item.is_current" @click="choose(item)">
          <i class="model-picker-logo">
            <template v-if="isCustomVendor(item.vendor)">
              <img v-if="modelLogo(item.icon)" :src="modelLogo(item.icon) || undefined" alt="" />
              <component v-else :is="modelIcon(item.icon)" :size="14" />
            </template>
            <template v-else>
              <img v-if="logoForVendor(item.vendor)" :src="logoForVendor(item.vendor) || undefined" alt="" />
              <span v-else>{{ item.vendor.slice(0, 1).toUpperCase() }}</span>
            </template>
          </i>
          <span class="model-name-cell"><b>{{ item.name }}</b><small>{{ vendorLabel(item.vendor) }}</small></span>
          <LoaderCircle v-if="selecting === item.id" class="spin" :size="14" /><Check v-else-if="item.is_current" :size="14" />
        </button>
        <p v-if="loading">{{ t("model.loading") }}</p><p v-else-if="!models.length">{{ t("model.empty") }}</p>
      </div>
      <p v-if="error" class="model-picker-error">{{ error }}</p>
      <footer><button type="button" role="menuitem" @click="openManager"><Settings2 :size="15" />{{ t("model.manage") }}</button></footer>
    </section>
  </div>
</template>
