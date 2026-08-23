<script setup lang="ts">
import { Check, ChevronDown, ExternalLink, Eye, EyeOff, LoaderCircle, Pencil, Play, Plus, Settings2, Trash2, X } from "@lucide/vue";
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

const vendors = modelVendors;

const models = ref<ModelProfile[]>([]);
const editorOpen = ref(false);
const editingModel = ref<ModelProfile | null>(null);
const selectedVendor = ref<ModelVendor | null>(null);
const name = ref(""); const model = ref(""); const baseUrl = ref(""); const apiKey = ref("");
const provider = ref<"anthropic" | "openai">("anthropic");
const apiFormat = ref<ApiFormat>("anthropic_messages");
const advancedOpen = ref(false);
const maxOutputTokens = ref(8192); const temperature = ref<number | null>(null); const topP = ref<number | null>(null);
const reasoningEffort = ref<"" | "low" | "medium" | "high" | "xhigh" | "max">("");
const timeoutS = ref(120); const maxRetries = ref(2); const contextWindow = ref(0); const cacheControl = ref(true);
const showKey = ref(false); const saving = ref(false); const error = ref("");
const testing = ref(false); const testResult = ref("");
const deleteTarget = ref<ModelProfile | null>(null); const deletingId = ref<string | null>(null);
const deleteTrigger = ref<HTMLButtonElement | null>(null); const modelManagerBody = ref<HTMLElement | null>(null);
const deleteCancelButton = ref<HTMLButtonElement | null>(null);
const editorDialog = ref<HTMLElement | null>(null);
const deleteDialog = ref<HTMLElement | null>(null);
const editorTrigger = ref<HTMLButtonElement | null>(null);
const managerDialog = ref<HTMLElement | null>(null);
const { setInitialFocus, trapTab, restoreFocus } = useFocusTrap();
let modelRequestVersion = 0;
const canSave = computed(() => Boolean(selectedVendor.value && name.value.trim() && model.value.trim() && (editingModel.value !== null || apiKey.value.trim())));

async function refresh() {
  error.value = "";
  try { models.value = await listModelProfiles(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
}
function beginAdd(event?: MouseEvent) {
  editorTrigger.value = event?.currentTarget instanceof HTMLButtonElement ? event.currentTarget : editorTrigger.value;
  editorOpen.value = true; editingModel.value = null; selectedVendor.value = null; name.value = ""; model.value = ""; baseUrl.value = ""; apiKey.value = ""; apiFormat.value = "anthropic_messages"; maxOutputTokens.value = 8192; temperature.value = null; topP.value = null; reasoningEffort.value = ""; timeoutS.value = 120; maxRetries.value = 2; contextWindow.value = 0; cacheControl.value = true; advancedOpen.value = false; error.value = ""; testResult.value = "";
}
// 打开编辑器并预填指定模型的配置，供修改后按 id 保存
function beginEdit(item: ModelProfile, event?: MouseEvent) {
  editorTrigger.value = event?.currentTarget instanceof HTMLButtonElement ? event.currentTarget : editorTrigger.value;
  const latest = models.value.find((m) => m.id === item.id) ?? item;
  editingModel.value = latest;
  selectedVendor.value = modelVendors.find((v) => v.name === latest.vendor) ?? { name: latest.vendor, logo: null, mark: latest.vendor.slice(0, 1).toUpperCase() || "M", provider: latest.provider, baseUrl: latest.base_url, apiKeyUrl: null };
  name.value = latest.name;
  model.value = latest.model;
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
  editorOpen.value = true;
}
// 编辑器打开后聚焦首个控件（点击 beginAdd 或程序注入 editorOpen 都生效）
watch(editorOpen, (open) => {
  if (open) void setInitialFocus(editorDialog);
});
function chooseVendor(item: ModelVendor) { selectedVendor.value = item; name.value = item.name; provider.value = item.provider; apiFormat.value = item.provider === "openai" ? "openai_chat_completions" : "anthropic_messages"; baseUrl.value = item.baseUrl; }
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
  editorOpen.value = false;
  void restoreFocus(editorTrigger.value, modelManagerBody.value);
}
async function save() {
  if (!canSave.value || !selectedVendor.value) return;
  if (baseUrl.value && !/^https?:\/\//i.test(baseUrl.value)) { error.value = "API 地址需要以 http:// 或 https:// 开头"; return; }
  const requestVersion = ++modelRequestVersion;
  saving.value = true; error.value = "";
  try {
    const result = await saveModelProfile({ id: editingModel.value?.id, name: name.value.trim(), vendor: selectedVendor.value.name, provider: provider.value, api_format: apiFormat.value, model: model.value.trim(), base_url: baseUrl.value.trim(), ...(apiKey.value.trim() ? { api_key: apiKey.value.trim() } : {}), max_output_tokens: maxOutputTokens.value, temperature: temperature.value, top_p: topP.value, reasoning_effort: reasoningEffort.value, timeout_s: timeoutS.value, max_retries: maxRetries.value, context_window: contextWindow.value, cache_control: cacheControl.value });
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
    const result = await testModelProfile({ vendor: selectedVendor.value.name, provider: provider.value, api_format: apiFormat.value, model: model.value.trim(), base_url: baseUrl.value.trim(), ...(apiKey.value.trim() ? { api_key: apiKey.value.trim() } : {}), max_output_tokens: maxOutputTokens.value, temperature: temperature.value, top_p: topP.value, reasoning_effort: reasoningEffort.value, timeout_s: timeoutS.value, max_retries: maxRetries.value, context_window: contextWindow.value, cache_control: cacheControl.value });
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
// 点击开关把该模型设为当前使用；已是当前模型则忽略
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
onMounted(() => {
  void refresh();
  void setInitialFocus(managerDialog);
});
</script>

<template>
  <section ref="managerDialog" class="model-manager" role="dialog" aria-modal="true" aria-label="模型管理" tabindex="-1" @keydown.esc="emit('close')">
    <header><div><h1>模型</h1><p>配置 API Key，添加并管理本机可用模型。</p></div><button type="button" :disabled="Boolean(deleteTarget || deletingId)" aria-label="关闭模型管理" @click="emit('close')"><X :size="18" /></button></header>
    <div ref="modelManagerBody" class="model-manager-body" tabindex="-1" :inert="Boolean(deleteTarget || deletingId)">
      <button ref="editorTrigger" type="button" class="model-add-button" :disabled="Boolean(deleteTarget || deletingId)" @click="beginAdd($event)"><Plus :size="15" />添加模型</button>
      <div class="model-table">
        <header><span>模型</span><span>服务商</span><span>接口</span><span>操作</span></header>
        <div v-for="item in models" :key="item.id" class="model-table-row">
          <span><span class="model-table-name"><button type="button" class="model-toggle" :class="{ on: item.is_current }" :disabled="Boolean(deleteTarget || deletingId)" :aria-pressed="item.is_current" :title="item.is_current ? '当前模型' : '设为当前模型'" :aria-label="item.is_current ? `${item.name} 是当前模型` : `将 ${item.name} 设为当前模型`" @click="selectModel(item)"><i /></button><span><b :title="item.name">{{ item.name }}</b><small :title="item.model">{{ item.model }}</small></span></span></span><span :title="item.vendor">{{ item.vendor }}</span><span>{{ item.provider === 'openai' ? 'OpenAI 兼容' : 'Anthropic' }}</span>
          <span><em v-if="item.is_current"><Check :size="12" />当前</em><small v-else-if="item.builtin">内置</small><template v-else><button type="button" :disabled="Boolean(deleteTarget || deletingId)" :aria-label="`编辑 ${item.name}`" @click="beginEdit(item, $event)"><Pencil :size="14" /></button><button type="button" :disabled="Boolean(deleteTarget || deletingId)" :aria-label="`删除 ${item.name}`" @click="remove(item, $event)"><Trash2 :size="14" /></button></template></span>
        </div>
        <p v-if="!models.length">暂无自定义模型，点击“添加模型”开始配置。</p>
      </div>
      <p v-if="error && !editorOpen" class="model-manager-error" role="alert" aria-live="assertive">{{ error }}</p>
    </div>

    <div v-if="deleteTarget" class="model-delete-backdrop" @mousedown.self="cancelRemove">
      <section ref="deleteDialog" class="model-delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="model-delete-title" aria-describedby="model-delete-description" @keydown.esc.stop="cancelRemove" @keydown.tab="trapTab($event, deleteDialog)">
        <header><span><Trash2 :size="18" /></span><div><h2 id="model-delete-title">删除模型</h2><p id="model-delete-description">确定要删除“{{ deleteTarget.name }}”吗？此操作无法撤销。</p></div></header>
        <footer><button ref="deleteCancelButton" type="button" autofocus :disabled="Boolean(deletingId)" @click="cancelRemove">取消</button><button type="button" class="danger" :disabled="Boolean(deletingId)" @click="confirmRemove"><LoaderCircle v-if="deletingId" class="spin" :size="13" />{{ deletingId ? "删除中" : "确认删除" }}</button></footer>
      </section>
    </div>

    <div v-if="editorOpen" class="model-editor-backdrop" @mousedown.self="closeEditor">
      <section ref="editorDialog" class="model-editor" role="dialog" aria-modal="true" :aria-label="editingModel ? '编辑模型' : '添加模型'" @keydown.esc.stop="closeEditor" @keydown.tab="trapTab($event, editorDialog)">
        <header><h2>{{ editingModel ? "编辑模型" : "添加模型" }}</h2><button type="button" aria-label="关闭" @click="closeEditor"><X :size="18" /></button></header>
        <div class="model-vendor-grid">
          <button v-for="item in vendors" :key="item.name" type="button" :class="{ active: selectedVendor?.name === item.name }" @click="chooseVendor(item)"><i><img v-if="item.logo" :src="item.logo" alt="" /><span v-else>{{ item.mark }}</span></i><span>{{ item.name }}</span><Check v-if="selectedVendor?.name === item.name" :size="14" /><ChevronDown v-else :size="14" /></button>
        </div>
        <div v-if="selectedVendor" class="model-editor-fields">
          <label><span>配置名称</span><input v-model="name" placeholder="例如 DeepSeek V3" /></label>
          <label><span>接口类型</span><select v-model="apiFormat" @change="provider = apiFormat === 'anthropic_messages' ? 'anthropic' : 'openai'"><option value="anthropic_messages">Anthropic Messages</option><option value="openai_chat_completions">OpenAI Chat Completions</option></select></label>
          <label><span>模型 ID</span><input v-model="model" placeholder="例如 deepseek-chat" /></label>
          <label><span>API 地址</span><input v-model="baseUrl" placeholder="留空使用服务商默认地址" /></label>
          <label class="wide"><span class="model-api-key-label"><span>API Key</span><button v-if="selectedVendor.apiKeyUrl" type="button" aria-label="获取 API 密钥" @click="getApiKey">获取 API 密钥<ExternalLink :size="12" /></button></span><div><input v-model="apiKey" :type="showKey ? 'text' : 'password'" :placeholder="editingModel?.has_api_key ? '留空保持不变' : '输入 API Key'" /><button type="button" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" @click="showKey = !showKey"><EyeOff v-if="showKey" :size="15" /><Eye v-else :size="15" /></button></div></label>
          <button type="button" class="model-advanced-toggle wide" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen"><Settings2 :size="14" />请求参数<ChevronDown :size="14" /></button>
          <div v-if="advancedOpen" class="model-request-fields wide">
            <label><span>最大输出 Token</span><input v-model.number="maxOutputTokens" type="number" min="1" max="128000" /></label>
            <label><span>超时（秒）</span><input v-model.number="timeoutS" type="number" min="1" max="600" /></label>
            <label><span>重试次数</span><input v-model.number="maxRetries" type="number" min="0" max="10" /></label>
            <label><span>上下文窗口（0 自动）</span><input v-model.number="contextWindow" type="number" min="0" /></label>
            <label><span>Temperature（留空默认）</span><input v-model.number="temperature" type="number" min="0" max="1" step="0.1" /></label>
            <label><span>Top P（留空默认）</span><input v-model.number="topP" type="number" min="0" max="1" step="0.1" /></label>
            <label><span>推理强度</span><select v-model="reasoningEffort"><option value="">默认</option><option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="xhigh">很高</option><option value="max">最高</option></select></label>
            <label class="model-cache-toggle"><input v-model="cacheControl" type="checkbox" />启用提示词缓存</label>
          </div>
        </div>
        <p v-if="error" class="model-editor-error">{{ error }}</p><p v-else-if="testResult" class="model-editor-success">{{ testResult }}</p>
        <footer><button type="button" @click="closeEditor">取消</button><button type="button" :disabled="!canSave || testing" @click="testConnection"><LoaderCircle v-if="testing" class="spin" :size="13" /><Play v-else :size="13" />{{ testing ? '测试中…' : '测试连接' }}</button><button type="button" class="primary" :disabled="!canSave || saving" @click="save">{{ saving ? '保存中' : '提交' }}</button></footer>
      </section>
    </div>
  </section>
</template>
