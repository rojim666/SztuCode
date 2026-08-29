<script setup lang="ts">
import { ArrowLeft, Check, ChevronDown, ExternalLink, Eye, EyeOff, Info, LoaderCircle, Pencil, Play, Plus, Settings2, Trash2, X, Zap } from "@lucide/vue";
import { isTauri } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useFocusTrap } from "../../composables/useFocusTrap";
import {
  deleteModelProfile, getProviderStatus, listModelProfiles, saveModelProfile, selectModelProfile, testModelProfile,
  type ModelProfile, type ProviderStatus, type RuntimeSettings,
} from "../../services/sztu-runtime";
import { logoForVendor, modelVendors, type ModelVendor } from "./model-vendors";
import type { ApiFormat } from "../../services/sztu-runtime";

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
const name = ref(""); const modelId = ref(""); const baseUrl = ref(""); const apiKey = ref("");
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
  selectedVendor.value = null; name.value = ""; modelId.value = ""; baseUrl.value = ""; apiKey.value = "";
  apiFormat.value = "openai_chat_completions"; provider.value = "openai";
  maxOutputTokens.value = 16384; temperature.value = null; topP.value = null; reasoningEffort.value = "";
  timeoutS.value = 120; maxRetries.value = 2; contextWindow.value = 128000; cacheControl.value = true;
  advancedOpen.value = false; error.value = ""; testResult.value = ""; showKey.value = false;
}
function beginEdit(item: ModelProfile, event?: MouseEvent) {
  editorTrigger.value = event?.currentTarget instanceof HTMLButtonElement ? event.currentTarget : editorTrigger.value;
  const latest = models.value.find((m) => m.id === item.id) ?? item;
  editingModel.value = latest;
  const vendor = modelVendors.find((v) => v.name === latest.vendor) ?? { name: latest.vendor, logo: null, mark: latest.vendor.slice(0, 1).toUpperCase() || "M", provider: latest.provider, baseUrl: latest.base_url, apiKeyUrl: null };
  selectedVendor.value = vendor;
  name.value = latest.name;
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
    error.value = `无法打开 API 密钥页面：${reason instanceof Error ? reason.message : String(reason)}`;
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
    const result = await saveModelProfile({ id: editingModel.value?.id, name: finalName, vendor: selectedVendor.value.name, provider: provider.value, api_format: apiFormat.value, model: modelId.value.trim(), base_url: baseUrl.value.trim(), ...(apiKey.value.trim() ? { api_key: apiKey.value.trim() } : {}), max_output_tokens: maxOutputTokens.value, temperature: temperature.value, top_p: topP.value, reasoning_effort: reasoningEffort.value, timeout_s: timeoutS.value, max_retries: maxRetries.value, context_window: contextWindow.value, cache_control: cacheControl.value });
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
  name.value = selectedVendor.value.name;
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
  void setInitialFocus(managerDialog);
});
</script>

<template>
  <section ref="managerDialog" class="model-manager" :class="{ 'model-manager--embedded': props.embedded }" :role="props.embedded ? undefined : 'dialog'" :aria-modal="props.embedded ? undefined : 'true'" aria-label="模型管理" tabindex="-1" @keydown.esc="addStep !== 'idle' ? closeEditor() : emit('close')">
    <header>
      <button v-if="addStep === 'idle'" type="button" :disabled="Boolean(deleteTarget || deletingId)" aria-label="关闭模型管理" @click="emit('close')"><X :size="18" /></button>
    </header>

    <div v-if="addStep === 'idle'" ref="modelManagerBody" class="model-manager-body" tabindex="-1" :inert="Boolean(deleteTarget || deletingId)">
      <div class="model-manager-toolbar">
        <button ref="editorTrigger" type="button" class="model-add-button" :disabled="Boolean(deleteTarget || deletingId)" @click="beginAdd($event)">
          <Plus :size="15" />添加模型
        </button>
      </div>
      <div class="model-table">
        <div v-if="models.length" class="model-table-header">
          <span></span>
          <span>模型</span>
          <span>操作</span>
        </div>
        <div v-for="item in models" :key="item.id" class="model-table-row">
          <span class="model-row-check">
            <button type="button" class="model-toggle" :class="{ on: item.is_current }" :disabled="Boolean(deleteTarget || deletingId)" :aria-pressed="item.is_current" :title="item.is_current ? '当前模型' : '设为当前模型'" :aria-label="item.is_current ? `${item.name} 是当前模型` : `将 ${item.name} 设为当前模型`" @click="selectModel(item)"><i /></button>
          </span>
          <span class="model-row-info">
            <i class="model-provider-logo"><img v-if="logoForVendor(item.vendor)" :src="logoForVendor(item.vendor) || undefined" alt="" /><span v-else>{{ item.vendor.slice(0, 1).toUpperCase() }}</span></i>
            <span class="model-name-text">
              <b :title="item.name">{{ item.name }}</b>
              <small :title="item.model">{{ item.model }}</small>
            </span>
          </span>
          <span class="model-row-actions">
            <em v-if="item.is_current" class="model-current-badge"><Check :size="12" />当前</em>
            <template v-else>
              <button type="button" :disabled="Boolean(deleteTarget || deletingId)" :aria-label="`编辑 ${item.name}`" @click="beginEdit(item, $event)"><Pencil :size="14" /></button>
              <button type="button" class="model-delete-btn" :disabled="Boolean(deleteTarget || deletingId)" :aria-label="`删除 ${item.name}`" @click="remove(item, $event)"><Trash2 :size="14" /></button>
            </template>
          </span>
        </div>
        <p v-if="!models.length" class="model-empty">暂无模型，点击「添加模型」开始配置。</p>
      </div>
      <p v-if="error && addStep === 'idle'" class="model-manager-error" role="alert" aria-live="assertive">{{ error }}</p>
    </div>

    <!-- 删除确认 -->
    <div v-if="deleteTarget" class="model-delete-backdrop" @mousedown.self="cancelRemove">
      <section ref="deleteDialog" class="model-delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="model-delete-title" aria-describedby="model-delete-description" @keydown.esc.stop="cancelRemove" @keydown.tab="trapTab($event, deleteDialog)">
        <header><span class="model-delete-icon"><Trash2 :size="18" /></span><div><h2 id="model-delete-title">删除模型</h2><p id="model-delete-description">确定要删除"{{ deleteTarget.name }}"吗？此操作无法撤销。</p></div></header>
        <footer><button ref="deleteCancelButton" type="button" autofocus :disabled="Boolean(deletingId)" @click="cancelRemove">取消</button><button type="button" class="danger" :disabled="Boolean(deletingId)" @click="confirmRemove"><LoaderCircle v-if="deletingId" class="spin" :size="13" />{{ deletingId ? "删除中" : "确认删除" }}</button></footer>
      </section>
    </div>

    <!-- 服务商选择 -->
    <div v-if="addStep === 'vendor'" class="model-editor-backdrop" @mousedown.self="closeEditor">
      <section ref="vendorDialog" class="model-vendor-picker" role="dialog" aria-modal="true" aria-label="添加模型" @keydown.esc.stop="closeEditor" @keydown.tab="trapTab($event, vendorDialog)">
        <header>
          <h2>添加模型</h2>
          <button type="button" aria-label="关闭" @click="closeEditor"><X :size="18" /></button>
        </header>
        <div class="model-vendor-grid">
          <button v-for="item in vendors" :key="item.name" type="button" class="model-vendor-card" @click="chooseVendor(item)">
            <i class="model-vendor-logo"><img v-if="item.logo" :src="item.logo" alt="" /><span v-else class="model-vendor-mark">{{ item.mark }}</span></i>
            <span class="model-vendor-name">{{ item.name }}</span>
            <ChevronDown class="model-vendor-arrow" :size="14" />
          </button>
        </div>
      </section>
    </div>

    <!-- 配置表单 -->
    <div v-if="addStep === 'form' && selectedVendor" class="model-editor-backdrop" @mousedown.self="closeEditor">
      <section ref="formDialog" class="model-form-dialog" role="dialog" aria-modal="true" :aria-label="editingModel ? '编辑模型' : '通过服务商添加'" @keydown.esc.stop="closeEditor" @keydown.tab="trapTab($event, formDialog)">
        <header class="model-form-header">
          <button v-if="!editingModel" type="button" class="model-form-back" aria-label="返回选择服务商" @click="backToVendor"><ArrowLeft :size="16" /></button>
          <h2>{{ editingModel ? "编辑模型" : "通过服务商添加" }}</h2>
          <button type="button" aria-label="关闭" @click="closeEditor"><X :size="18" /></button>
        </header>

        <div class="model-form-body">
          <div class="model-form-field">
            <label class="model-form-label"><span class="model-required">*</span>服务商</label>
            <select v-model="selectedVendor" class="model-form-select" @change="chooseVendor(selectedVendor)">
              <option v-for="v in vendors" :key="v.name" :value="v">{{ v.name }}</option>
            </select>
          </div>

          <div class="model-form-field">
            <label class="model-form-label"><span class="model-required">*</span>模型</label>
            <input v-model="modelId" class="model-form-input" placeholder="选择模型" list="model-suggestions" />
            <datalist id="model-suggestions">
              <option v-if="selectedVendor.name === 'DeepSeek'" value="deepseek-chat">DeepSeek V3</option>
              <option v-if="selectedVendor.name === 'DeepSeek'" value="deepseek-reasoner">DeepSeek R1</option>
              <option v-if="selectedVendor.name === 'Anthropic'" value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
              <option v-if="selectedVendor.name === 'Anthropic'" value="claude-opus-4-20250514">Claude Opus 4</option>
              <option v-if="selectedVendor.name === 'Anthropic'" value="claude-3-5-sonnet-latest">Claude 3.5 Sonnet</option>
              <option v-if="selectedVendor.name === 'OpenAI'" value="gpt-4o">GPT-4o</option>
              <option v-if="selectedVendor.name === 'OpenAI'" value="gpt-4o-mini">GPT-4o mini</option>
              <option v-if="selectedVendor.name === 'OpenAI'" value="o3-mini">o3-mini</option>
              <option v-if="selectedVendor.name === '硅基流动'" value="deepseek-ai/DeepSeek-V3">DeepSeek V3</option>
              <option v-if="selectedVendor.name === 'OpenRouter'" value="anthropic/claude-3.5-sonnet">Claude 3.5 Sonnet</option>
              <option v-if="selectedVendor.name === 'OpenRouter'" value="openai/gpt-4o">GPT-4o</option>
              <option v-if="selectedVendor.name === 'OpenRouter'" value="deepseek/deepseek-chat">DeepSeek V3</option>
            </datalist>
          </div>

          <div class="model-form-field">
            <label class="model-form-label"><span class="model-required">*</span>API 密钥</label>
            <div class="model-form-key-row">
              <input v-model="apiKey" class="model-form-input model-form-key-input" :type="showKey ? 'text' : 'password'" :placeholder="editingModel?.has_api_key ? '留空保持不变' : '请输入 API Key'" />
              <button type="button" class="model-form-key-toggle" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" @click="showKey = !showKey"><EyeOff v-if="showKey" :size="16" /><Eye v-else :size="16" /></button>
            </div>
            <button v-if="selectedVendor.apiKeyUrl" type="button" class="model-form-getkey" @click="getApiKey">获取 API 密钥<ExternalLink :size="12" /></button>
          </div>

          <div class="model-form-advanced">
            <button type="button" class="model-form-advanced-toggle" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
              <span>高级配置</span>
              <ChevronDown :size="14" :class="{ rotated: advancedOpen }" />
            </button>

            <div v-if="advancedOpen" class="model-form-advanced-body">
              <div class="model-form-field model-form-field--inline">
                <label class="model-form-label">上下文窗口（Token）</label>
                <div class="model-input-with-chips">
                  <input v-model.number="contextWindow" class="model-form-input" type="number" min="1000" placeholder="请输入数值，留空则使用最佳默认值" />
                  <div class="model-chips">
                    <button type="button" :class="{ active: contextWindow === 131072 }" @click="setContextWindow(131072)">128k</button>
                    <button type="button" :class="{ active: contextWindow === 262144 }" @click="setContextWindow(262144)">256k</button>
                    <button type="button" :class="{ active: contextWindow === 524288 }" @click="setContextWindow(524288)">512k</button>
                    <button type="button" :class="{ active: contextWindow === 1048576 }" @click="setContextWindow(1048576)">1M</button>
                  </div>
                </div>
              </div>

              <div class="model-form-field model-form-field--inline">
                <label class="model-form-label">输出</label>
                <div class="model-input-with-chips">
                  <input v-model.number="maxOutputTokens" class="model-form-input" type="number" min="1" placeholder="请输入数值，留空则使用最佳默认值" />
                  <div class="model-chips">
                    <button type="button" :class="{ active: maxOutputTokens === 4096 }" @click="setMaxOutput(4096)">4k</button>
                    <button type="button" :class="{ active: maxOutputTokens === 16384 }" @click="setMaxOutput(16384)">16k</button>
                    <button type="button" :class="{ active: maxOutputTokens === 32768 }" @click="setMaxOutput(32768)">32k</button>
                    <button type="button" :class="{ active: maxOutputTokens === 131072 }" @click="setMaxOutput(131072)">128k</button>
                  </div>
                </div>
              </div>

              <div class="model-form-field">
                <label class="model-form-label">工具调用轮数</label>
                <input v-model.number="maxRetries" class="model-form-input" type="number" min="0" max="100" value="500" />
              </div>

              <div class="model-form-field model-form-radio-group">
                <label class="model-form-label model-form-label--radio">
                  支持图片输入
                  <Info :size="12" class="model-form-info" title="模型是否支持图片输入" />
                </label>
                <div class="model-radio-row">
                  <label class="model-radio"><input type="radio" :checked="true" disabled /><span>支持</span></label>
                  <label class="model-radio"><input type="radio" :checked="false" disabled /><span>不支持</span></label>
                </div>
              </div>

              <div class="model-form-field model-form-radio-group">
                <label class="model-form-label model-form-label--radio">
                  思考模式
                  <Info :size="12" class="model-form-info" title="是否启用思考模式" />
                </label>
                <div class="model-radio-row">
                  <label class="model-radio"><input type="radio" name="thinking" :checked="reasoningEffort === ''" @change="reasoningEffort = ''" /><span>跟随模型默认配置</span></label>
                  <label class="model-radio"><input type="radio" name="thinking" :checked="reasoningEffort !== ''" @change="reasoningEffort = 'medium'" /><span>开启</span></label>
                  <label class="model-radio"><input type="radio" name="thinking" :checked="false" disabled /><span>关闭</span></label>
                </div>
              </div>

              <div class="model-form-section-title">
                <span>采样参数</span>
                <Info :size="12" class="model-form-info" title="控制模型输出的随机性" />
              </div>

              <div class="model-form-field model-form-field--inline">
                <label class="model-form-label model-form-label--sampling">Temperature</label>
                <input v-model.number="temperature" class="model-form-input" type="number" min="0" max="2" step="0.1" placeholder="留空使用最佳配置，或输入 0 ~ 2 之间的数值" />
              </div>

              <div class="model-form-field model-form-field--inline">
                <label class="model-form-label model-form-label--sampling">Top P</label>
                <input v-model.number="topP" class="model-form-input" type="number" min="0" max="1" step="0.1" placeholder="留空使用最佳配置，或输入 0 ~ 1 之间的数值" />
              </div>

              <div class="model-form-field model-form-field--inline">
                <label class="model-form-label model-form-label--sampling">Top K</label>
                <input class="model-form-input" type="number" min="1" max="100" placeholder="留空使用最佳配置，或输入 1 ~ 100 之间的数值" disabled />
              </div>

              <div v-if="selectedVendor.name === '自定义模型'" class="model-form-field model-form-field--inline">
                <label class="model-form-label">API 地址</label>
                <input v-model="baseUrl" class="model-form-input" placeholder="https://api.example.com/v1" />
              </div>
            </div>
          </div>

          <p v-if="error" class="model-form-error">{{ error }}</p>
          <p v-else-if="testResult" class="model-form-success">{{ testResult }}</p>
        </div>

        <footer class="model-form-footer">
          <div class="model-form-footer-note">
            <Info :size="12" />
            <span>连通性测试会发起一次真实请求，会消耗少量模型Token</span>
          </div>
          <div class="model-form-footer-actions">
            <button type="button" class="model-form-reset" @click="resetFormDefaults">重置</button>
            <button type="button" class="primary model-form-submit" :disabled="!canSave || saving || testing" @click="save">{{ saving ? '保存中' : (editingModel ? '保存' : '添加模型') }}</button>
          </div>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.model-manager-desc {
  margin: 4px 0 0;
  color: #868b92;
  font-size: 13px;
}

.model-manager-body {
  padding: 20px 24px 32px;
}

.model-add-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 16px;
  color: #fff;
  background: #2f3338;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  transition: background 0.15s ease;
}
.model-add-button:hover { background: #1f2327; }
.model-add-button:disabled { opacity: 0.4; cursor: default; }

.model-table {
  margin-top: 8px;
  overflow: hidden;
  border: 1px solid #e8eaec;
  border-radius: 8px;
}
.model-table-header {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  min-height: 40px;
  padding: 0 16px;
  color: #868b92;
  background: #f7f8f9;
  border-bottom: 1px solid #e8eaec;
  font-size: 12px;
  font-weight: 500;
}
.model-table-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  min-height: 56px;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #f0f1f2;
  transition: background 0.12s ease;
}
.model-table-row:last-child { border-bottom: none; }
.model-table-row:hover { background: #fafbfc; }

.model-row-check { display: flex; align-items: center; justify-content: center; }
.model-toggle {
  position: relative;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  padding: 0;
  background: transparent;
  border: 2px solid #d1d5db;
  border-radius: 50%;
  transition: all 0.15s ease;
}
.model-toggle i { display: none; }
.model-toggle.on {
  background: #2563eb;
  border-color: #2563eb;
}
.model-toggle.on::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 8px;
  height: 8px;
  background: #fff;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}
.model-toggle:hover:not(.on) { border-color: #9ca3af; background: #f3f4f6; }
.model-toggle.on:hover { background: #1d4ed8; border-color: #1d4ed8; }

.model-row-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.model-provider-logo {
  display: grid;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  place-items: center;
  background: #f5f6f7;
  border: 1px solid #e8eaec;
  border-radius: 8px;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  color: #6b7280;
}
.model-provider-logo img { width: 22px; height: 22px; object-fit: contain; }
.model-name-text { display: flex; flex-direction: column; min-width: 0; gap: 2px; }
.model-name-text b { font-size: 14px; font-weight: 600; color: #1f2937; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-name-text small { font-size: 12px; color: #9ca3af; font-family: "SF Mono", Consolas, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.model-row-actions { display: flex; align-items: center; gap: 4px; }
.model-current-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  color: #059669;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 20px;
  font-size: 12px;
  font-style: normal;
  font-weight: 500;
}
.model-row-actions button {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  color: #6b7280;
  background: transparent;
  border-radius: 6px;
  transition: all 0.12s ease;
}
.model-row-actions button:hover { color: #374151; background: #f3f4f6; }
.model-row-actions .model-delete-btn:hover { color: #dc2626; background: #fef2f2; }

.model-empty {
  padding: 48px 16px;
  margin: 0;
  color: #9ca3af;
  font-size: 13px;
  text-align: center;
}

/* 删除对话框图标 */
.model-delete-icon {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  color: #dc2626;
  background: #fef2f2;
  border-radius: 10px;
}

/* 服务商选择弹窗 */
.model-vendor-picker {
  width: min(520px, calc(100vw - 28px));
  max-height: calc(100vh - 28px);
  overflow: hidden;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 25px 65px rgba(0,0,0,0.18);
  display: flex;
  flex-direction: column;
}
.model-vendor-picker > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f1f2;
}
.model-vendor-picker h2 { margin: 0; font-size: 17px; font-weight: 600; }
.model-vendor-picker > header button {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  color: #6b7280;
  background: transparent;
  border-radius: 8px;
}
.model-vendor-picker > header button:hover { background: #f3f4f6; }

.model-vendor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 16px 20px 20px;
  overflow-y: auto;
  background: #fafbfc;
}
.model-vendor-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #e8eaec;
  border-radius: 8px;
  text-align: left;
  transition: all 0.15s ease;
}
.model-vendor-card:hover {
  background: #fff;
  border-color: #2563eb;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}
.model-vendor-logo {
  display: grid;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  place-items: center;
  background: #f8f9fa;
  border: 1px solid #f0f1f2;
  border-radius: 8px;
  font-style: normal;
}
.model-vendor-logo img { width: 20px; height: 20px; object-fit: contain; }
.model-vendor-mark {
  font-size: 13px;
  font-weight: 700;
  color: #6b7280;
}
.model-vendor-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
}
.model-vendor-arrow {
  color: #9ca3af;
  transform: rotate(-90deg);
}

/* 配置表单弹窗 */
.model-form-dialog {
  width: min(520px, calc(100vw - 28px));
  max-height: calc(100vh - 28px);
  overflow: hidden;
  background: #f7f8f9;
  border-radius: 12px;
  box-shadow: 0 25px 65px rgba(0,0,0,0.18);
  display: flex;
  flex-direction: column;
}
.model-form-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  background: #fff;
  border-bottom: 1px solid #f0f1f2;
}
.model-form-header h2 { margin: 0; flex: 1; font-size: 16px; font-weight: 600; }
.model-form-back {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  color: #4b5563;
  background: transparent;
  border-radius: 8px;
}
.model-form-back:hover { background: #f3f4f6; }
.model-form-header > button:last-child {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  color: #6b7280;
  background: transparent;
  border-radius: 8px;
}
.model-form-header > button:last-child:hover { background: #f3f4f6; }

.model-form-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.model-form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.model-form-field--inline {
  flex-direction: column;
}
.model-form-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}
.model-required { color: #ef4444; font-weight: 700; }
.model-form-input,
.model-form-select {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  color: #1f2937;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 7px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.model-form-input:focus,
.model-form-select:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
.model-form-input::placeholder { color: #9ca3af; }

.model-form-key-row { position: relative; display: flex; align-items: center; }
.model-form-key-input { padding-right: 44px; }
.model-form-key-toggle {
  position: absolute;
  right: 4px;
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  color: #6b7280;
  background: transparent;
  border-radius: 6px;
}
.model-form-key-toggle:hover { background: #f3f4f6; color: #374151; }
.model-form-getkey {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  align-self: flex-start;
  padding: 0;
  margin-top: 2px;
  color: #2563eb;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
}
.model-form-getkey:hover { color: #1d4ed8; text-decoration: underline; }

.model-form-advanced { border-top: 1px solid #e8eaec; padding-top: 12px; }
.model-form-advanced-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 0;
  color: #374151;
  background: transparent;
  font-size: 13px;
  font-weight: 500;
}
.model-form-advanced-toggle svg:last-child {
  margin-left: auto;
  transition: transform 0.2s ease;
  color: #9ca3af;
}
.model-form-advanced-toggle svg.rotated { transform: rotate(180deg); }

.model-form-advanced-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 12px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e8eaec;
  border-radius: 8px;
}

.model-input-with-chips { display: flex; flex-direction: column; gap: 8px; }
.model-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.model-chips button {
  height: 28px;
  padding: 0 12px;
  color: #6b7280;
  background: #f3f4f6;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.12s ease;
}
.model-chips button:hover { background: #e5e7eb; color: #374151; }
.model-chips button.active { color: #2563eb; background: #eff6ff; border-color: #bfdbfe; }

.model-form-radio-group { gap: 8px; }
.model-form-label--radio { display: inline-flex; align-items: center; gap: 4px; }
.model-form-info { color: #9ca3af; cursor: help; }
.model-radio-row { display: flex; gap: 20px; padding-top: 2px; }
.model-radio { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #374151; cursor: pointer; }
.model-radio input[type="radio"] {
  width: 16px;
  height: 16px;
  accent-color: #2563eb;
  margin: 0;
}
.model-radio input:disabled { cursor: not-allowed; opacity: 0.5; }

.model-form-section-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding-top: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.model-form-label--sampling { width: 100px; flex-shrink: 0; }

.model-form-error {
  margin: 0;
  padding: 10px 12px;
  color: #dc2626;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 7px;
  font-size: 12px;
  line-height: 1.5;
}
.model-form-success {
  margin: 0;
  padding: 10px 12px;
  color: #059669;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 7px;
  font-size: 12px;
}

.model-form-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid #f0f1f2;
}
.model-form-footer-note {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #9ca3af;
  font-size: 11px;
}
.model-form-footer-actions { display: flex; gap: 8px; }
.model-form-reset {
  height: 36px;
  padding: 0 16px;
  color: #6b7280;
  background: #f3f4f6;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 500;
  transition: background 0.12s ease;
}
.model-form-reset:hover { background: #e5e7eb; color: #374151; }
.model-form-submit {
  height: 36px;
  padding: 0 20px;
  color: #fff;
  background: #1f2937;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 500;
  transition: background 0.15s ease;
}
.model-form-submit:hover:not(:disabled) { background: #111827; }
.model-form-submit:disabled { opacity: 0.5; cursor: not-allowed; }

/* 暗色主题 */
:global(.dark) .model-manager { color: #e5e7eb; background: #1a1a1a; border-color: #2a2a2a; }
:global(.dark) .model-manager > header { background: #1e1e1e; border-color: #2a2a2a; }
:global(.dark) .model-manager-desc { color: #9ca3af; }
:global(.dark) .model-add-button { background: #3b82f6; }
:global(.dark) .model-add-button:hover { background: #2563eb; }
:global(.dark) .model-table { border-color: #2a2a2a; background: #1e1e1e; }
:global(.dark) .model-table-header { background: #232323; border-color: #2a2a2a; color: #9ca3af; }
:global(.dark) .model-table-row { background: #1e1e1e; border-color: #252525; }
:global(.dark) .model-table-row:hover { background: #252525; }
:global(.dark) .model-provider-logo { background: #252525; border-color: #333; color: #9ca3af; }
:global(.dark) .model-name-text b { color: #e5e7eb; }
:global(.dark) .model-name-text small { color: #6b7280; }
:global(.dark) .model-toggle { border-color: #4b5563; }
:global(.dark) .model-toggle:hover:not(.on) { background: #333; border-color: #6b7280; }
:global(.dark) .model-row-actions button { color: #9ca3af; }
:global(.dark) .model-row-actions button:hover { color: #e5e7eb; background: #333; }
:global(.dark) .model-row-actions .model-delete-btn:hover { color: #f87171; background: rgba(239,68,68,0.1); }
:global(.dark) .model-current-badge { color: #34d399; background: rgba(5,150,105,0.15); border-color: rgba(52,211,153,0.3); }
:global(.dark) .model-empty { color: #6b7280; }
:global(.dark) .model-vendor-picker { background: #1e1e1e; }
:global(.dark) .model-vendor-picker > header { background: #1e1e1e; border-color: #2a2a2a; }
:global(.dark) .model-vendor-picker > header button:hover { background: #333; }
:global(.dark) .model-vendor-grid { background: #1a1a1a; }
:global(.dark) .model-vendor-card { background: #252525; border-color: #333; }
:global(.dark) .model-vendor-card:hover { border-color: #3b82f6; background: #2a2a2a; box-shadow: 0 2px 8px rgba(59,130,246,0.15); }
:global(.dark) .model-vendor-logo { background: #1a1a1a; border-color: #333; }
:global(.dark) .model-vendor-mark { color: #9ca3af; }
:global(.dark) .model-vendor-name { color: #e5e7eb; }
:global(.dark) .model-form-dialog { background: #1a1a1a; }
:global(.dark) .model-form-header { background: #1e1e1e; border-color: #2a2a2a; }
:global(.dark) .model-form-header h2 { color: #e5e7eb; }
:global(.dark) .model-form-back:hover { background: #333; }
:global(.dark) .model-form-header > button:last-child:hover { background: #333; }
:global(.dark) .model-form-body { background: #1a1a1a; }
:global(.dark) .model-form-label { color: #d1d5db; }
:global(.dark) .model-form-input, :global(.dark) .model-form-select { background: #252525; border-color: #404040; color: #e5e7eb; }
:global(.dark) .model-form-input:focus, :global(.dark) .model-form-select:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.2); }
:global(.dark) .model-form-key-toggle:hover { background: #333; color: #d1d5db; }
:global(.dark) .model-form-getkey { color: #60a5fa; }
:global(.dark) .model-form-advanced { border-color: #2a2a2a; }
:global(.dark) .model-form-advanced-body { background: #252525; border-color: #333; }
:global(.dark) .model-chips button { background: #333; color: #9ca3af; }
:global(.dark) .model-chips button:hover { background: #404040; color: #d1d5db; }
:global(.dark) .model-chips button.active { color: #60a5fa; background: rgba(59,130,246,0.15); border-color: rgba(59,130,246,0.3); }
:global(.dark) .model-radio { color: #d1d5db; }
:global(.dark) .model-form-section-title { color: #d1d5db; }
:global(.dark) .model-form-error { background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.2); color: #f87171; }
:global(.dark) .model-form-success { background: rgba(5,150,105,0.1); border-color: rgba(52,211,153,0.2); color: #34d399; }
:global(.dark) .model-form-footer { background: #1e1e1e; border-color: #2a2a2a; }
:global(.dark) .model-form-reset { background: #333; color: #d1d5db; }
:global(.dark) .model-form-reset:hover { background: #404040; color: #fff; }
:global(.dark) .model-form-submit { background: #3b82f6; }
:global(.dark) .model-form-submit:hover:not(:disabled) { background: #2563eb; }
:global(.dark) .model-delete-dialog { background: #1e1e1e; color: #e5e7eb; }
:global(.dark) .model-delete-dialog header p { color: #9ca3af; }
:global(.dark) .model-delete-dialog > footer { background: #252525; }
:global(.dark) .model-delete-dialog > footer button { background: #333; border-color: #404040; color: #d1d5db; }
:global(.dark) .model-delete-dialog > footer button:hover { background: #404040; }
</style>
