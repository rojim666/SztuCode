<script setup lang="ts">
import { ArrowLeft, Bot, Brain, Check, ChevronDown, Code2, Cpu, ExternalLink, Eye, EyeOff, Info, LoaderCircle, MessageSquare, Pencil, Plus, Sparkles, Trash2 } from "@lucide/vue";
import { isTauri } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { Teleport, computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useFocusTrap } from "../../composables/useFocusTrap";
import {
  deleteModelProfile, getProviderStatus, listModelProfiles, saveModelProfile, selectModelProfile, testModelProfile,
  type ModelProfile, type ProviderStatus, type RuntimeSettings,
} from "../../services/sztu-runtime";
import { CUSTOM_VENDOR_ID, logoForVendor, modelVendors, vendorIdByName, type ModelVendor } from "./model-vendors";
import type { ApiFormat } from "../../services/sztu-runtime";

const { t } = useI18n({ useScope: "global" });

const emit = defineEmits<{
  close: [];
  updated: [settings: RuntimeSettings, status: ProviderStatus | null];
}>();
const props = defineProps<{ embedded?: boolean }>();

const vendors = modelVendors;

const models = ref<ModelProfile[]>([]);
const addStep = ref<"idle" | "vendor" | "form">("idle");
const editingModel = ref<ModelProfile | null>(null);
const selectedVendor = ref<ModelVendor | null>(null);
const name = ref(""); const icon = ref("sparkles"); const modelId = ref(""); const baseUrl = ref(""); const apiKey = ref("");
const customModelIcons = [
  { id: "sparkles", component: Sparkles },
  { id: "bot", component: Bot },
  { id: "brain", component: Brain },
  { id: "code", component: Code2 },
  { id: "cpu", component: Cpu },
  { id: "chat", component: MessageSquare },
] as const;
const vendorIconOptions = modelVendors.filter((v) => v.id !== CUSTOM_VENDOR_ID && v.logo);
const provider = ref<"anthropic" | "openai">("openai");
const apiFormat = ref<ApiFormat>("openai_chat_completions");
const advancedOpen = ref(false);
const maxOutputTokens = ref(8192); const temperature = ref<number | null>(null); const topP = ref<number | null>(null);
const reasoningEffort = ref<"" | "low" | "medium" | "high" | "xhigh" | "max">("");
const timeoutS = ref(120); const maxRetries = ref(2); const contextWindow = ref(128000); const cacheControl = ref(true);
const showKey = ref(false); const saving = ref(false); const error = ref("");
const testing = ref(false); const testResult = ref("");
const deleteTarget = ref<ModelProfile | null>(null); const deletingId = ref<string | null>(null);
const deleteTrigger = ref<HTMLButtonElement | null>(null); const modelManagerBody = ref<HTMLElement | null>(null);
const deleteCancelButton = ref<HTMLButtonElement | null>(null);
const vendorDialog = ref<HTMLElement | null>(null);
const formDialog = ref<HTMLElement | null>(null);
const deleteDialog = ref<HTMLElement | null>(null);
const editorTrigger = ref<HTMLButtonElement | null>(null);
const managerDialog = ref<HTMLElement | null>(null);
const { setInitialFocus, trapTab, restoreFocus } = useFocusTrap();
let modelRequestVersion = 0;
const canSave = computed(() => Boolean(selectedVendor.value && modelId.value.trim() && (editingModel.value !== null || apiKey.value.trim() || selectedVendor.value?.name === "自定义模型")));
const currentModel = computed(() => models.value.find((item) => item.is_current) ?? null);
const customModelIcon = (value: string) => customModelIcons.find((item) => item.id === value)?.component ?? Sparkles;
const customModelLogo = (value: string) => logoForVendor(value) ?? null;

const CUSTOM_VENDOR_NAME = t("model.vendor.custom");
function isCustomVendor(vendorName: string) {
  return vendorName === CUSTOM_VENDOR_NAME || vendorName === "自定义模型";
}
function vendorLabel(vendor: ModelVendor) {
  const key = `model.vendor.${vendor.id}` as const;
  const translated = t(key);
  return translated !== key ? translated : vendor.name;
}
function freeTierText(vendorId: string) {
  const key = `model.freeTier.${vendorId}` as const;
  const translated = t(key);
  return translated !== key ? translated : "";
}
function iconLabel(iconId: string) {
  const key = `model.icon.${iconId}` as const;
  const translated = t(key);
  return translated !== key ? translated : iconId;
}

async function refresh() {
  error.value = "";
  try { models.value = await listModelProfiles(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
}
function beginAdd(event?: MouseEvent) {
  editorTrigger.value = event?.currentTarget instanceof HTMLButtonElement ? event.currentTarget : editorTrigger.value;
  addStep.value = "vendor"; editingModel.value = null; resetForm();
}
function resetForm() {
  selectedVendor.value = null; name.value = ""; icon.value = "sparkles"; modelId.value = ""; baseUrl.value = ""; apiKey.value = "";
  apiFormat.value = "openai_chat_completions"; provider.value = "openai";
  maxOutputTokens.value = 16384; temperature.value = null; topP.value = null; reasoningEffort.value = "";
  timeoutS.value = 120; maxRetries.value = 2; contextWindow.value = 128000; cacheControl.value = true;
  advancedOpen.value = false; error.value = ""; testResult.value = ""; showKey.value = false;
}
function beginEdit(item: ModelProfile, event?: MouseEvent) {
  editorTrigger.value = event?.currentTarget instanceof HTMLButtonElement ? event.currentTarget : editorTrigger.value;
  const latest = models.value.find((m) => m.id === item.id) ?? item;
  editingModel.value = latest;
  const vendor = modelVendors.find((v) => v.name === latest.vendor) ?? { id: CUSTOM_VENDOR_ID, name: latest.vendor, logo: null, mark: latest.vendor.slice(0, 1).toUpperCase() || "M", provider: latest.provider, baseUrl: latest.base_url, apiKeyUrl: null };
  selectedVendor.value = vendor;
  name.value = latest.name;
  icon.value = latest.icon || "sparkles";
  modelId.value = latest.model;
  baseUrl.value = latest.base_url;
  apiKey.value = "";
  provider.value = latest.provider;
  apiFormat.value = latest.api_format;
  maxOutputTokens.value = latest.max_output_tokens;
  temperature.value = latest.temperature;
  topP.value = latest.top_p;
  reasoningEffort.value = latest.reasoning_effort;
  timeoutS.value = latest.timeout_s;
  maxRetries.value = latest.max_retries;
  contextWindow.value = latest.context_window;
  cacheControl.value = latest.cache_control;
  advancedOpen.value = false;
  error.value = "";
  testResult.value = "";
  addStep.value = "form";
}
watch(addStep, (step) => {
  if (step === "vendor") void setInitialFocus(vendorDialog);
  else if (step === "form") void setInitialFocus(formDialog);
});
function chooseVendor(item: ModelVendor) {
  selectedVendor.value = item;
  name.value = item.name;
  icon.value = "sparkles";
  provider.value = item.provider;
  apiFormat.value = item.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions";
  baseUrl.value = item.baseUrl;
  addStep.value = "form";
}
function backToVendor() {
  addStep.value = "vendor";
  error.value = "";
  testResult.value = "";
}
async function getApiKey() {
  const url = selectedVendor.value?.apiKeyUrl;
  if (!url) return;
  error.value = "";
  try {
    if (isTauri()) await openUrl(url);
    else window.open(url, "_blank", "noopener,noreferrer");
  } catch (reason) {
    error.value = t("model.openKeyPageFailed", { reason: reason instanceof Error ? reason.message : String(reason) });
  }
}
function closeEditor() {
  editingModel.value = null;
  addStep.value = "idle";
  void restoreFocus(editorTrigger.value, modelManagerBody.value);
}
function setContextWindow(v: number) { contextWindow.value = v; }
function setMaxOutput(v: number) { maxOutputTokens.value = v; }
async function save() {
  if (!canSave.value || !selectedVendor.value) return;
  if (baseUrl.value && !/^https?:\/\//i.test(baseUrl.value)) { error.value = "API 地址需要以 http:// 或 https:// 开头"; return; }
  const requestVersion = ++modelRequestVersion;
  saving.value = true; error.value = "";
  const finalName = name.value.trim() || selectedVendor.value.name;
  try {
    const result = await saveModelProfile({ id: editingModel.value?.id, name: finalName, icon: icon.value, vendor: selectedVendor.value.name, provider: provider.value, api_format: apiFormat.value, model: modelId.value.trim(), base_url: baseUrl.value.trim(), ...(apiKey.value.trim() ? { api_key: apiKey.value.trim() } : {}), max_output_tokens: maxOutputTokens.value, temperature: temperature.value, top_p: topP.value, reasoning_effort: reasoningEffort.value, timeout_s: timeoutS.value, max_retries: maxRetries.value, context_window: contextWindow.value, cache_control: cacheControl.value });
    if (requestVersion !== modelRequestVersion) return;
    models.value = result.models; emit("updated", result.settings, await getProviderStatus()); closeEditor();
  } catch (reason) {
    if (requestVersion !== modelRequestVersion) return;
    error.value = reason instanceof Error ? reason.message : String(reason);
  }
  finally { saving.value = false; }
}
async function testConnection() {
  if (!canSave.value || !selectedVendor.value) return;
  testing.value = true; error.value = ""; testResult.value = "";
  try {
    const result = await testModelProfile({ vendor: selectedVendor.value.name, provider: provider.value, api_format: apiFormat.value, model: modelId.value.trim(), base_url: baseUrl.value.trim(), ...(apiKey.value.trim() ? { api_key: apiKey.value.trim() } : {}), max_output_tokens: maxOutputTokens.value, temperature: temperature.value, top_p: topP.value, reasoning_effort: reasoningEffort.value, timeout_s: timeoutS.value, max_retries: maxRetries.value, context_window: contextWindow.value, cache_control: cacheControl.value });
    if (!result.success) throw new Error(result.error || "连接失败");
    testResult.value = `连接成功 · ${Math.round(result.elapsed_ms)} ms`;
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
  finally { testing.value = false; }
}
function remove(item: ModelProfile, event?: MouseEvent) {
  if (item.is_current || item.builtin || deleteTarget.value || deletingId.value) return;
  error.value = "";
  deleteTrigger.value = event?.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
  modelRequestVersion += 1;
  deleteTarget.value = item;
  void focusDeleteDialog();
}
async function focusDeleteDialog() {
  await nextTick();
  deleteCancelButton.value?.focus();
}
async function restoreDeleteFocus() {
  const trigger = deleteTrigger.value;
  deleteTrigger.value = null;
  await nextTick();
  if (trigger?.isConnected) trigger.focus();
  else modelManagerBody.value?.focus();
}
function cancelRemove() {
  if (!deletingId.value) {
    deleteTarget.value = null;
    void restoreDeleteFocus();
  }
}
async function confirmRemove() {
  const target = deleteTarget.value;
  if (!target || target.is_current || target.builtin || deletingId.value) return;
  deletingId.value = target.id;
  error.value = "";
  try {
    models.value = await deleteModelProfile(target.id);
    deleteTarget.value = null;
    void restoreDeleteFocus();
  } catch (reason) {
    deleteTarget.value = null;
    error.value = reason instanceof Error ? reason.message : String(reason);
    void restoreDeleteFocus();
  } finally {
    deletingId.value = null;
  }
}
async function selectModel(item: ModelProfile) {
  if (item.is_current) return;
  const requestVersion = ++modelRequestVersion;
  error.value = "";
  try {
    const result = await selectModelProfile(item.id);
    if (requestVersion !== modelRequestVersion) return;
    models.value = result.models;
    emit("updated", result.settings, await getProviderStatus());
  } catch (reason) {
    if (requestVersion !== modelRequestVersion) return;
    error.value = reason instanceof Error ? reason.message : String(reason);
  }
}
function resetFormDefaults() {
  if (!selectedVendor.value) return;
  name.value = vendorLabel(selectedVendor.value);
  icon.value = "sparkles";
  modelId.value = "";
  baseUrl.value = selectedVendor.value.baseUrl;
  apiKey.value = "";
  provider.value = selectedVendor.value.provider;
  apiFormat.value = selectedVendor.value.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions";
  maxOutputTokens.value = 16384;
  temperature.value = null;
  topP.value = null;
  reasoningEffort.value = "";
  timeoutS.value = 120;
  maxRetries.value = 2;
  contextWindow.value = 128000;
  cacheControl.value = true;
  advancedOpen.value = false;
  error.value = "";
  testResult.value = "";
}
onMounted(() => {
  void refresh();
});
</script>

<template>
  <div ref="managerDialog" class="model-manager" :class="{ 'model-manager--embedded': props.embedded }">
    <div v-if="addStep === 'idle'" ref="modelManagerBody" class="model-manager-body" tabindex="-1" :inert="Boolean(deleteTarget || deletingId)">
      <!-- 当前模型卡片 -->
      <div v-if="currentModel" class="current-model-card">
        <div class="current-model-info">
          <i class="model-provider-logo model-provider-logo--lg">
            <template v-if="currentModel.vendor === '自定义模型'">
              <img v-if="customModelLogo(currentModel.icon)" :src="customModelLogo(currentModel.icon) || undefined" alt="" />
              <component v-else :is="customModelIcon(currentModel.icon)" :size="18" />
            </template>
            <template v-else>
              <img v-if="logoForVendor(currentModel.vendor)" :src="logoForVendor(currentModel.vendor) || undefined" alt="" />
              <span v-else>{{ currentModel.vendor.slice(0, 1).toUpperCase() }}</span>
            </template>
          </i>
          <div class="current-model-text">
            <span class="current-model-label">当前模型</span>
            <b class="current-model-name">{{ currentModel.name }}</b>
            <small class="current-model-id">{{ currentModel.model }}</small>
          </div>
        </div>
        <Check class="current-model-check" :size="22" />
      </div>

      <!-- 模型列表 -->
      <div class="model-list">
        <div class="model-list-header">
          <span class="model-list-title">{{ t("model.all") }}</span>
          <span class="model-list-count">{{ t("model.count", { n: models.length }) }}</span>
        </div>

        <div v-for="item in models" :key="item.id" class="model-card" :class="{ 'model-card--current': item.is_current }">
          <button class="model-card-select" :class="{ active: item.is_current }" :disabled="Boolean(deleteTarget || deletingId)" :aria-pressed="item.is_current" :title="item.is_current ? t('model.current') : t('model.setCurrent')" @click="selectModel(item)">
            <Check v-if="item.is_current" :size="16" />
          </button>
          <i class="model-provider-logo">
            <template v-if="isCustomVendor(item.vendor)">
              <img v-if="customModelLogo(item.icon)" :src="customModelLogo(item.icon) || undefined" alt="" />
              <component v-else :is="customModelIcon(item.icon)" :size="16" />
            </template>
            <template v-else>
              <img v-if="logoForVendor(item.vendor)" :src="logoForVendor(item.vendor) || undefined" alt="" />
              <span v-else>{{ item.vendor.slice(0, 1).toUpperCase() }}</span>
            </template>
          </i>
          <div class="model-card-info">
            <b :title="item.name">{{ item.name }}</b>
            <small :title="item.model">{{ item.model }}</small>
          </div>
          <div class="model-card-actions">
            <span v-if="item.is_current" class="model-badge model-badge--active">{{ t("model.inUse") }}</span>
            <span v-else-if="item.builtin" class="model-badge">{{ t("model.builtin") }}</span>
            <template v-if="!item.builtin">
              <button type="button" class="model-action-btn" :disabled="Boolean(deleteTarget || deletingId)" :aria-label="t('model.editAria', { name: item.name })" @click="beginEdit(item, $event)">
                <Pencil :size="14" />
              </button>
              <button v-if="!item.is_current" type="button" class="model-action-btn model-action-btn--danger" :disabled="Boolean(deleteTarget || deletingId)" :aria-label="t('model.deleteAria', { name: item.name })" @click="remove(item, $event)">
                <Trash2 :size="14" />
              </button>
            </template>
          </div>
        </div>

        <button v-if="!models.length" class="model-empty-btn" ref="editorTrigger" :disabled="Boolean(deleteTarget || deletingId)" @click="beginAdd($event)">
          <Plus :size="18" />
          <span>{{ t("model.addFirst") }}</span>
        </button>
      </div>

      <!-- 添加模型按钮 -->
      <button v-if="models.length > 0" ref="editorTrigger" type="button" class="add-model-btn" :disabled="Boolean(deleteTarget || deletingId)" @click="beginAdd($event)">
        <Plus :size="16" />
        <span>{{ t("model.add") }}</span>
      </button>

      <p v-if="error && addStep === 'idle'" class="model-error" role="alert" aria-live="assertive">{{ error }}</p>
    </div>

    <Teleport to="body">
      <!-- 删除确认 -->
      <div v-if="deleteTarget" class="mm-modal-backdrop" @mousedown.self="cancelRemove">
        <section ref="deleteDialog" class="mm-modal-dialog mm-modal-dialog--sm" role="alertdialog" aria-modal="true" aria-labelledby="model-delete-title" aria-describedby="model-delete-description" @keydown.esc.stop="cancelRemove" @keydown.tab="(e: KeyboardEvent) => trapTab(e, deleteDialog)">
          <div class="mm-modal-icon mm-modal-icon--danger">
            <Trash2 :size="18" />
          </div>
          <h3 id="model-delete-title" class="mm-modal-title">{{ t("model.deleteTitle") }}</h3>
          <p id="model-delete-description" class="mm-modal-desc">{{ t("model.deleteConfirm", { name: deleteTarget.name }) }}</p>
          <div class="mm-modal-actions">
            <button ref="deleteCancelButton" type="button" class="mm-btn mm-btn--ghost" :disabled="Boolean(deletingId)" @click="cancelRemove">{{ t("model.cancel") }}</button>
            <button type="button" class="mm-btn mm-btn--danger" :disabled="Boolean(deletingId)" @click="confirmRemove">
              <LoaderCircle v-if="deletingId" class="mm-spin" :size="11" />
              {{ deletingId ? t("model.deleting") : t("model.confirmDelete") }}
            </button>
          </div>
        </section>
      </div>

      <!-- 服务商选择 -->
      <div v-if="addStep === 'vendor'" class="mm-modal-backdrop" @mousedown.self="closeEditor">
        <section ref="vendorDialog" class="mm-modal-dialog" role="dialog" aria-modal="true" :aria-label="t('model.selectVendor')" @keydown.esc.stop="closeEditor" @keydown.tab="(e: KeyboardEvent) => trapTab(e, vendorDialog)">
          <header class="mm-modal-header">
            <h3>{{ t("model.selectVendor") }}</h3>
          </header>
          <div class="mm-vendor-grid">
            <button v-for="item in vendors" :key="item.name" type="button" class="mm-vendor-card" @click="chooseVendor(item)">
              <i class="mm-vendor-logo">
                <img v-if="item.logo" :src="item.logo" alt="" />
                <span v-else>{{ item.mark }}</span>
              </i>
              <span class="mm-vendor-name">{{ vendorLabel(item) }}</span>
              <span v-if="item.freeTier" class="mm-vendor-free-badge">{{ t("model.freeBadge") }}</span>
              <ChevronDown class="mm-vendor-arrow" :size="14" />
            </button>
          </div>
        </section>
      </div>

      <!-- 配置表单 -->
      <div v-if="addStep === 'form' && selectedVendor" class="mm-modal-backdrop" @mousedown.self="closeEditor">
        <section ref="formDialog" class="mm-modal-dialog mm-modal-dialog--lg" role="dialog" aria-modal="true" :aria-label="editingModel ? t('model.editTitle') : t('model.addTitle')" @keydown.esc.stop="closeEditor" @keydown.tab="(e: KeyboardEvent) => trapTab(e, formDialog)">
          <header class="mm-modal-header">
            <button v-if="!editingModel" type="button" class="mm-modal-back-btn" :aria-label="t('model.back')" @click="backToVendor">
              <ArrowLeft :size="16" />
            </button>
            <h3>{{ editingModel ? t("model.editTitle") : t("model.addTitle") }}</h3>
          </header>

          <div class="mm-modal-body">
            <div class="mm-form-field">
              <label class="mm-form-label"><span class="mm-required">*</span>{{ t("model.vendorLabel") }}</label>
              <select v-model="selectedVendor" class="mm-form-select" @change="chooseVendor(selectedVendor)">
                <option v-for="v in vendors" :key="v.name" :value="v">{{ vendorLabel(v) }}</option>
              </select>
              <p v-if="selectedVendor.freeTier" class="mm-free-tier-note">
                <Sparkles :size="13" />
                {{ t("model.freeTierNote", { tier: freeTierText(selectedVendor.id) }) }}
              </p>
            </div>

            <template v-if="selectedVendor.id === CUSTOM_VENDOR_ID">
              <div class="mm-form-field">
                <label class="mm-form-label"><span class="mm-required">*</span>{{ t("model.displayName") }}</label>
                <input v-model="name" class="mm-form-input" maxlength="100" :placeholder="t('model.displayNamePlaceholder')" />
              </div>

              <div class="mm-form-field">
                <label class="mm-form-label">{{ t("model.iconLabel") }}</label>
                <div class="mm-icon-picker" role="radiogroup" :aria-label="t('model.iconLabel')">
                  <button v-for="v in vendorIconOptions" :key="`v-${v.name}`" type="button" class="mm-icon-option mm-icon-option--logo" :class="{ active: icon === v.name }" role="radio" :aria-checked="icon === v.name" :aria-label="vendorLabel(v)" :title="vendorLabel(v)" @click="icon = v.name">
                    <img v-if="v.logo" :src="v.logo" alt="" />
                  </button>
                  <button v-for="item in customModelIcons" :key="item.id" type="button" class="mm-icon-option" :class="{ active: icon === item.id }" role="radio" :aria-checked="icon === item.id" :aria-label="iconLabel(item.id)" :title="iconLabel(item.id)" @click="icon = item.id">
                    <component :is="item.component" :size="18" />
                  </button>
                </div>
              </div>
            </template>

            <div class="mm-form-field">
              <label class="mm-form-label"><span class="mm-required">*</span>{{ t("model.modelLabel") }}</label>
              <input v-model="modelId" class="mm-form-input" :placeholder="t('model.modelIdPlaceholder')" list="model-suggestions" />
              <datalist id="model-suggestions">
                <option v-if="selectedVendor.id === 'deepseek'" value="deepseek-chat">DeepSeek V3</option>
                <option v-if="selectedVendor.id === 'deepseek'" value="deepseek-reasoner">DeepSeek R1</option>
                <option v-if="selectedVendor.id === 'anthropic'" value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                <option v-if="selectedVendor.id === 'anthropic'" value="claude-opus-4-20250514">Claude Opus 4</option>
                <option v-if="selectedVendor.id === 'anthropic'" value="claude-3-5-sonnet-latest">Claude 3.5 Sonnet</option>
                <option v-if="selectedVendor.id === 'openai'" value="gpt-4o">GPT-4o</option>
                <option v-if="selectedVendor.id === 'openai'" value="gpt-4o-mini">GPT-4o mini</option>
                <option v-if="selectedVendor.id === 'openai'" value="o3-mini">o3-mini</option>
                <option v-if="selectedVendor.id === 'siliconflow'" value="deepseek-ai/DeepSeek-V3">DeepSeek V3</option>
                <option v-if="selectedVendor.id === 'openrouter'" value="anthropic/claude-3.5-sonnet">Claude 3.5 Sonnet</option>
                <option v-if="selectedVendor.id === 'openrouter'" value="openai/gpt-4o">GPT-4o</option>
                <option v-if="selectedVendor.id === 'openrouter'" value="deepseek/deepseek-chat">DeepSeek V3</option>
                <option v-if="selectedVendor.id === 'openrouter'" value="deepseek/deepseek-r1:free">DeepSeek R1{{ t("model.tagFree") }}</option>
                <option v-if="selectedVendor.id === 'openrouter'" value="meta-llama/llama-3.3-70b-instruct:free">Llama 3.3 70B{{ t("model.tagFree") }}</option>
                <option v-if="selectedVendor.id === 'openrouter'" value="qwen/qwen3-coder:free">Qwen3 Coder{{ t("model.tagFree") }}</option>
                <option v-if="selectedVendor.id === 'google'" value="gemini-2.5-flash">Gemini 2.5 Flash{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'google'" value="gemini-2.0-flash">Gemini 2.0 Flash{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'groq'" value="llama-3.3-70b-versatile">Llama 3.3 70B{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'groq'" value="deepseek-r1-distill-llama-70b">DeepSeek R1 Distill 70B{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'cerebras'" value="llama-3.3-70b">Llama 3.3 70B{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'cerebras'" value="qwen-3-32b">Qwen3 32B{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'mistral'" value="mistral-small-latest">Mistral Small{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'mistral'" value="open-mistral-nemo">Mistral Nemo{{ t("model.tagFreeTier") }}</option>
                <option v-if="selectedVendor.id === 'github'" value="openai/gpt-4o-mini">GPT-4o mini{{ t("model.tagFreeQuota") }}</option>
                <option v-if="selectedVendor.id === 'github'" value="meta/Llama-3.3-70B-Instruct">Llama 3.3 70B{{ t("model.tagFreeQuota") }}</option>
                <option v-if="selectedVendor.id === 'nvidia'" value="deepseek-ai/deepseek-r1">DeepSeek R1{{ t("model.tagFree") }}</option>
                <option v-if="selectedVendor.id === 'nvidia'" value="meta/llama-3.3-70b-instruct">Llama 3.3 70B{{ t("model.tagFree") }}</option>
                <option v-if="selectedVendor.id === 'bigmodel'" value="glm-4-flash">GLM-4-Flash{{ t("model.tagPermanentFree") }}</option>
              </datalist>
            </div>

            <div class="mm-form-field">
              <label class="mm-form-label"><span class="mm-required">*</span>{{ t("model.apiKeyLabel") }}</label>
              <div class="mm-input-with-action">
                <input v-model="apiKey" class="mm-form-input" :type="showKey ? 'text' : 'password'" :placeholder="editingModel?.has_api_key ? t('model.apiKeyKeep') : t('model.apiKeyPlaceholder')" />
                <button type="button" class="mm-input-action-btn" :aria-label="showKey ? t('model.hideKey') : t('model.showKey')" @click="showKey = !showKey">
                  <EyeOff v-if="showKey" :size="15" />
                  <Eye v-else :size="15" />
                </button>
              </div>
              <button v-if="selectedVendor.apiKeyUrl" type="button" class="mm-link-btn" @click="getApiKey">
                {{ t("model.getApiKey") }}
                <ExternalLink :size="12" />
              </button>
            </div>

            <div class="mm-form-advanced">
              <button type="button" class="mm-advanced-toggle" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
                <span>{{ t("model.advanced") }}</span>
                <ChevronDown :size="14" :class="{ 'mm-rotated': advancedOpen }" />
              </button>

              <div v-if="advancedOpen" class="mm-advanced-body">
                <div class="mm-form-field">
                  <label class="mm-form-label">{{ t("model.contextWindow") }}</label>
                  <div class="mm-input-with-chips">
                    <input v-model.number="contextWindow" class="mm-form-input" type="number" min="1000" :placeholder="t('model.tokenPlaceholder')" />
                    <div class="mm-chip-group">
                      <button type="button" class="mm-chip" :class="{ active: contextWindow === 131072 }" @click="setContextWindow(131072)">128k</button>
                      <button type="button" class="mm-chip" :class="{ active: contextWindow === 262144 }" @click="setContextWindow(262144)">256k</button>
                      <button type="button" class="mm-chip" :class="{ active: contextWindow === 524288 }" @click="setContextWindow(524288)">512k</button>
                      <button type="button" class="mm-chip" :class="{ active: contextWindow === 1048576 }" @click="setContextWindow(1048576)">1M</button>
                    </div>
                  </div>
                </div>

                <div class="mm-form-field">
                  <label class="mm-form-label">{{ t("model.maxOutput") }}</label>
                  <div class="mm-input-with-chips">
                    <input v-model.number="maxOutputTokens" class="mm-form-input" type="number" min="1" :placeholder="t('model.tokenPlaceholder')" />
                    <div class="mm-chip-group">
                      <button type="button" class="mm-chip" :class="{ active: maxOutputTokens === 4096 }" @click="setMaxOutput(4096)">4k</button>
                      <button type="button" class="mm-chip" :class="{ active: maxOutputTokens === 16384 }" @click="setMaxOutput(16384)">16k</button>
                      <button type="button" class="mm-chip" :class="{ active: maxOutputTokens === 32768 }" @click="setMaxOutput(32768)">32k</button>
                      <button type="button" class="mm-chip" :class="{ active: maxOutputTokens === 131072 }" @click="setMaxOutput(131072)">128k</button>
                    </div>
                  </div>
                </div>

                <div class="mm-form-field">
                  <label class="mm-form-label">{{ t("model.maxRetries") }}</label>
                  <input v-model.number="maxRetries" class="mm-form-input" type="number" min="0" max="100" />
                </div>

                <div v-if="selectedVendor.id === CUSTOM_VENDOR_ID" class="mm-form-field">
                  <label class="mm-form-label">{{ t("model.baseUrl") }}</label>
                  <input v-model="baseUrl" class="mm-form-input" placeholder="https://api.example.com/v1" />
                </div>
              </div>
            </div>

            <p v-if="error" class="mm-form-error">{{ error }}</p>
            <p v-else-if="testResult" class="mm-form-success">{{ testResult }}</p>
          </div>

          <footer class="mm-modal-footer">
            <button type="button" class="mm-btn mm-btn--ghost" @click="testConnection" :disabled="!canSave || saving || testing">
              <LoaderCircle v-if="testing" class="mm-spin" :size="13" />
              {{ testing ? t("model.testing") : t("model.test") }}
            </button>
            <div class="mm-modal-footer-right">
              <button type="button" class="mm-btn mm-btn--ghost" @click="resetFormDefaults">{{ t("model.reset") }}</button>
              <button type="button" class="mm-btn mm-btn--primary" :disabled="!canSave || saving || testing" @click="save">
                <LoaderCircle v-if="saving" class="mm-spin" :size="13" />
                {{ saving ? t("model.saving") : (editingModel ? t("model.save") : t("model.create")) }}
              </button>
            </div>
          </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.model-manager {
  width: 100%;
}

.model-manager-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 当前模型卡片 */
.current-model-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--accent-soft) 50%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 15%, var(--border));
  border-radius: 8px;
}

.current-model-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.current-model-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.current-model-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
}

.current-model-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.current-model-id {
  font-size: 11px;
  font-family: var(--font-mono, 'SF Mono', Consolas, monospace);
  color: var(--text-faint);
}

.current-model-check {
  color: var(--accent);
  flex-shrink: 0;
  width: 18px;
  height: 18px;
}

/* 模型列表 */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.model-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2px;
  margin-bottom: 1px;
}

.model-list-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.model-list-count {
  font-size: 11px;
  color: var(--text-faint);
}

.model-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 7px;
  transition: all 0.12s ease;
}

.model-card:hover {
  border-color: var(--border);
  background: color-mix(in srgb, var(--surface-soft) 60%, transparent);
}

.model-card--current {
  border-color: color-mix(in srgb, var(--accent) 20%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.model-card-select {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  padding: 0;
  color: transparent;
  background: transparent;
  border: 1.5px solid var(--border-strong);
  border-radius: 50%;
  transition: all 0.12s ease;
}

.model-card-select:hover:not(.active) {
  border-color: var(--text-muted);
  background: var(--surface-soft);
}

.model-card-select.active {
  color: var(--accent-contrast);
  background: var(--accent);
  border-color: var(--accent);
}

.model-provider-logo {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  font-style: normal;
  color: var(--text-muted);
}

.model-provider-logo--lg {
  width: 30px;
  height: 30px;
  border-radius: 7px;
}

.model-provider-logo img {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

.model-provider-logo--lg img {
  width: 18px;
  height: 18px;
}

.mm-icon-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mm-icon-option {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  padding: 0;
  color: var(--text-muted);
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.mm-icon-option:hover {
  color: var(--text);
  border-color: var(--border-strong);
}

.mm-icon-option.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent);
}

.mm-icon-option img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.model-card-info {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  flex: 1;
}

.model-card-info b {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-card-info small {
  font-size: 11px;
  font-family: var(--font-mono, 'SF Mono', Consolas, monospace);
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-card-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.model-badge {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--surface-soft);
  border-radius: 4px;
  font-style: normal;
  flex-shrink: 0;
  white-space: nowrap;
}

.model-badge--active {
  color: var(--accent);
  background: var(--accent-soft);
}

.model-action-btn {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  padding: 0;
  color: var(--text-muted);
  background: transparent;
  border-radius: 5px;
  transition: all 0.12s ease;
}

.model-action-btn:hover {
  color: var(--text);
  background: var(--surface-soft);
}

.model-action-btn--danger:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

/* 添加模型按钮 */
.add-model-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  height: 32px;
  padding: 0;
  color: var(--text-muted);
  background: transparent;
  border: 1px dashed var(--border-strong);
  border-radius: 5px;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.12s ease;
}

.add-model-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}

.model-empty-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 80px;
  padding: 16px;
  color: var(--text-muted);
  background: transparent;
  border: 1px dashed var(--border-strong);
  border-radius: 7px;
  font-size: 13px;
  transition: all 0.12s ease;
}

.model-empty-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}

.model-error {
  margin: 0;
  padding: 7px 9px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 6px;
  font-size: 12px;
}

/* Modal 基础样式 - z-index高于设置弹窗 */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  animation: fadeIn 0.15s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-dialog {
  width: 100%;
  max-width: 380px;
  max-height: calc(100vh - 32px);
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  animation: slideUp 0.18s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.modal-dialog--lg {
  max-width: 420px;
}

.modal-dialog--sm {
  max-width: 320px;
  padding: 20px;
  text-align: center;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.modal-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin: 0 auto 12px;
  border-radius: 10px;
}

.modal-icon--danger {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.modal-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.modal-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}

.modal-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  margin: 0;
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.modal-back-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-muted);
  background: transparent;
  border-radius: 6px;
  transition: all 0.12s ease;
}

.modal-back-btn:hover {
  color: var(--text);
  background: var(--surface-soft);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
}

.modal-footer-right {
  display: flex;
  gap: 6px;
}

/* 服务商网格 */
.vendor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  padding: 12px 14px 14px;
  overflow-y: auto;
}

.vendor-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  text-align: left;
  transition: all 0.12s ease;
}

.vendor-card:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.vendor-logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-style: normal;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
}

.vendor-logo img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.vendor-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.vendor-arrow {
  color: var(--text-faint);
  transform: rotate(-90deg);
  width: 14px;
  height: 14px;
}

/* 表单样式 */
.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}

.required {
  color: #ef4444;
  font-weight: 700;
}

.form-input,
.form-select {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: all 0.12s ease;
  box-sizing: border-box;
}

.form-input:focus,
.form-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.form-input::placeholder {
  color: var(--text-faint);
}

.input-with-action {
  position: relative;
  display: flex;
  align-items: center;
}

.input-with-action .form-input {
  padding-right: 38px;
}

.input-action-btn {
  position: absolute;
  right: 3px;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-muted);
  background: transparent;
  border-radius: 5px;
  transition: all 0.12s ease;
}

.input-action-btn:hover {
  color: var(--text);
  background: var(--surface-soft);
}

.link-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  align-self: flex-start;
  padding: 0;
  margin-top: 2px;
  color: var(--accent);
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  transition: opacity 0.12s ease;
}

.link-btn:hover {
  opacity: 0.8;
}

/* 高级配置 */
.form-advanced {
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 0;
  color: var(--text);
  background: transparent;
  font-size: 12px;
  font-weight: 500;
}

.advanced-toggle svg:last-child {
  margin-left: auto;
  color: var(--text-muted);
  transition: transform 0.2s ease;
  width: 14px;
  height: 14px;
}

.advanced-toggle svg.rotated {
  transform: rotate(180deg);
}

.advanced-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
  padding: 12px;
  background: var(--surface-soft);
  border-radius: 8px;
}

.input-with-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chip-group {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.chip {
  height: 24px;
  padding: 0 10px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  transition: all 0.12s ease;
}

.chip:hover {
  color: var(--text);
  border-color: var(--border-strong);
}

.chip.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
}

.form-error {
  margin: 0;
  padding: 8px 10px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 6px;
  font-size: 12px;
}

.form-success {
  margin: 0;
  padding: 8px 10px;
  color: #10b981;
  background: rgba(16, 185, 129, 0.08);
  border-radius: 6px;
  font-size: 12px;
}

/* 按钮样式 */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.12s ease;
  white-space: nowrap;
}

.btn--ghost {
  color: var(--text);
  background: var(--surface-soft);
  border: 1px solid transparent;
}

.btn--ghost:hover {
  background: color-mix(in srgb, var(--border) 40%, var(--surface-soft));
}

.btn--primary {
  color: #fff;
  background: var(--text);
  border: 1px solid var(--text);
}

.btn--primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn--danger {
  color: #fff;
  background: #ef4444;
  border: 1px solid #ef4444;
}

.btn--danger:hover:not(:disabled) {
  background: #dc2626;
  border-color: #dc2626;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spin {
  animation: spin 0.8s linear infinite;
  width: 12px;
  height: 12px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 嵌入模式 */
.model-manager--embedded {
  padding: 0;
}

/* 暗色主题适配（跟随应用内主题设置，而非操作系统偏好） */
:global([data-app-theme="dark"]) .current-model-card {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

:global([data-app-theme="dark"]) .modal-backdrop {
  background: rgba(0, 0, 0, 0.6);
}

:global([data-app-theme="dark"]) .model-card--current {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

/* 响应式 */
@media (max-width: 640px) {
  .vendor-grid {
    grid-template-columns: 1fr;
  }
  
  .modal-footer {
    flex-direction: column-reverse;
  }
  
  .modal-footer-right {
    width: 100%;
  }
  
  .modal-footer-right .btn {
    flex: 1;
  }
  
  .modal-footer .btn--ghost:first-child {
    width: 100%;
  }
}
</style>

<style>
/* Teleport 到 body 的弹窗样式 - 全局样式确保生效，z-index 高于设置弹窗 */
.mm-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: grid;
  place-items: center;
  padding: 12px;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  animation: mmFadeIn 0.12s ease;
}

@keyframes mmFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.mm-modal-dialog {
  width: 100%;
  max-width: 400px;
  max-height: calc(100vh - 24px);
  overflow: hidden;
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  animation: mmSlideUp 0.15s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.mm-modal-dialog--lg {
  max-width: 460px;
}

.mm-modal-dialog--sm {
  max-width: 320px;
  padding: 18px;
  text-align: center;
}

@keyframes mmSlideUp {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.mm-modal-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin: 0 auto 10px;
  border-radius: 10px;
}

.mm-modal-icon--danger {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.mm-modal-title {
  margin: 0 0 5px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text, #111);
}

.mm-modal-desc {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--text-muted, #6b7280);
  line-height: 1.5;
}

.mm-modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.mm-modal-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.mm-modal-header h3 {
  margin: 0;
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--text, #111);
}

.mm-modal-back-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-muted, #6b7280);
  background: transparent;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.1s ease;
}

.mm-modal-back-btn:hover {
  color: var(--text, #111);
  background: var(--surface-soft, #f3f4f6);
}

.mm-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mm-modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border, #e5e7eb);
}

.mm-modal-footer-right {
  display: flex;
  gap: 6px;
}

/* 服务商网格 */
.mm-vendor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  padding: 12px 16px 16px;
  overflow-y: auto;
}

.mm-vendor-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: transparent;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  font: inherit;
  transition: all 0.1s ease;
}

.mm-vendor-card:hover {
  border-color: var(--accent, #3b82f6);
  background: var(--accent-soft, rgba(59,130,246,0.08));
}

.mm-vendor-logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: var(--surface-soft, #f3f4f6);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  font-style: normal;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted, #6b7280);
}

.mm-vendor-logo img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.mm-vendor-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--text, #111);
}

/* 有免费额度的服务商徽标 */
.mm-vendor-free-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  padding: 3px 7px;
  border-radius: 999px;
  color: var(--success, #1f7a46);
  background: var(--success-soft, #eaf5ee);
  border: 1px solid color-mix(in srgb, var(--success, #1f7a46) 25%, transparent);
}

/* 表单中的免费额度提示 */
.mm-free-tier-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--success, #1f7a46);
  background: var(--success-soft, #eaf5ee);
  border: 1px solid color-mix(in srgb, var(--success, #1f7a46) 20%, transparent);
  border-radius: 6px;
  padding: 7px 10px;
}

.mm-free-tier-note svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.mm-vendor-arrow {
  color: var(--text-faint, #9ca3af);
  transform: rotate(-90deg);
  width: 14px;
  height: 14px;
}

/* 表单样式 */
.mm-form-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.mm-form-label {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text, #111);
}

.mm-required {
  color: #ef4444;
  font-weight: 700;
}

.mm-form-input,
.mm-form-select {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  color: var(--text, #111);
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: all 0.1s ease;
  box-sizing: border-box;
}

.mm-form-input:focus,
.mm-form-select:focus {
  border-color: var(--accent, #3b82f6);
  box-shadow: 0 0 0 2px var(--accent-soft, rgba(59,130,246,0.12));
}

.mm-form-input::placeholder {
  color: var(--text-faint, #9ca3af);
}

.mm-input-with-action {
  position: relative;
  display: flex;
  align-items: center;
}

.mm-input-with-action .mm-form-input {
  padding-right: 36px;
}

.mm-input-action-btn {
  position: absolute;
  right: 3px;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-muted, #6b7280);
  background: transparent;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.1s ease;
}

.mm-input-action-btn:hover {
  color: var(--text, #111);
  background: var(--surface-soft, #f3f4f6);
}

.mm-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  align-self: flex-start;
  padding: 0;
  margin-top: 2px;
  color: var(--accent, #3b82f6);
  background: transparent;
  border: none;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.1s ease;
}

.mm-link-btn:hover {
  opacity: 0.8;
}

/* 高级配置 */
.mm-form-advanced {
  border-top: 1px solid var(--border, #e5e7eb);
  padding-top: 10px;
}

.mm-advanced-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  padding: 0;
  color: var(--text, #111);
  background: transparent;
  border: none;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.mm-advanced-toggle svg:last-child {
  margin-left: auto;
  color: var(--text-muted, #6b7280);
  transition: transform 0.2s ease;
  width: 14px;
  height: 14px;
}

.mm-advanced-toggle svg.mm-rotated {
  transform: rotate(180deg);
}

.mm-advanced-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
  padding: 12px;
  background: var(--surface-soft, #f3f4f6);
  border-radius: 8px;
}

.mm-input-with-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mm-chip-group {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.mm-chip {
  height: 26px;
  padding: 0 12px;
  color: var(--text-muted, #6b7280);
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 5px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.1s ease;
}

.mm-chip:hover {
  color: var(--text, #111);
  border-color: var(--border-strong, #d1d5db);
}

.mm-chip.active {
  color: var(--accent, #3b82f6);
  background: var(--accent-soft, rgba(59,130,246,0.08));
  border-color: color-mix(in srgb, var(--accent, #3b82f6) 40%, var(--border, #e5e7eb));
}

.mm-form-error {
  margin: 0;
  padding: 6px 10px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 5px;
  font-size: 12px;
}

.mm-form-success {
  margin: 0;
  padding: 6px 10px;
  color: #10b981;
  background: rgba(16, 185, 129, 0.08);
  border-radius: 5px;
  font-size: 12px;
}

/* 按钮样式 */
.mm-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.1s ease;
  white-space: nowrap;
  border: 1px solid transparent;
}

.mm-btn--ghost {
  color: var(--text, #111);
  background: var(--surface-soft, #f3f4f6);
}

.mm-btn--ghost:hover {
  background: color-mix(in srgb, var(--border, #e5e7eb) 40%, var(--surface-soft, #f3f4f6));
}

.mm-btn--primary {
  color: #fff;
  background: var(--text, #111);
  border-color: var(--text, #111);
}

.mm-btn--primary:hover:not(:disabled) {
  opacity: 0.9;
}

.mm-btn--danger {
  color: #fff;
  background: #ef4444;
  border-color: #ef4444;
}

.mm-btn--danger:hover:not(:disabled) {
  background: #dc2626;
  border-color: #dc2626;
}

.mm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mm-spin {
  animation: mmSpin 0.8s linear infinite;
  width: 13px !important;
  height: 13px !important;
}

@keyframes mmSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 暗色主题适配 */
[data-app-theme="dark"] .btn--primary,
[data-app-theme="dark"] .mm-btn--primary {
  color: var(--accent-contrast);
  background: var(--accent);
  border-color: var(--accent);
}

/* 响应式 */
@media (max-width: 480px) {
  .mm-vendor-grid {
    grid-template-columns: 1fr;
  }
  .mm-modal-footer {
    flex-direction: column-reverse;
  }
  .mm-modal-footer-right {
    width: 100%;
  }
  .mm-modal-footer-right .mm-btn {
    flex: 1;
  }
  .mm-modal-footer .mm-btn--ghost:first-child {
    width: 100%;
  }
}
</style>
