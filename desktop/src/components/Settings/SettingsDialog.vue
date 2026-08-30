<script setup lang="ts">
import { getVersion } from "@tauri-apps/api/app";
import { isTauri } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { computed, onMounted, ref, watch } from "vue";
import {
  Bot, Check, Coffee, Cpu, Download, ExternalLink, GitFork, Globe2, Image, Info,
  LoaderCircle, Monitor, Moon, Palette, Plus, Power, Settings2, SlidersHorizontal, Sun, Trash2,
  Type, Upload, X,
} from "@lucide/vue";
import appPackage from "../../../package.json";
import { useFocusTrap } from "../../composables/useFocusTrap";
import {
  applyCcswitchProvider, getNativeSettings, listCcswitchProviders, setNativeSettings,
  type CcswitchProvider, type RuntimeSettings,
} from "../../services/sztu-runtime";
import {
  MAX_UI_FONT_SIZE, MIN_UI_FONT_SIZE, saveAppearanceSettings,
  type AccentColor, type AppearanceSettings, type CodeFont, type ThemePreference,
  type WallpaperStyle, uiFontOptions,
} from "../../services/appearance";
import AgentLogo from "../timeline/AgentLogo.vue";
import ModelManager from "../ModelConfig/ModelManager.vue";

type SettingsSection = "appearance" | "general" | "agent" | "integrations" | "about";

const PROJECT_URL = "https://github.com/rojim666/SztuCode";

const props = defineProps<{
  appearance: AppearanceSettings;
  runtimeSettings: RuntimeSettings | null;
  permissionError: string;
  initialSection?: SettingsSection;
}>();

const emit = defineEmits<{
  close: [];
  appearanceChange: [settings: AppearanceSettings];
  permissionChange: [value: RuntimeSettings["permission_mode"]];
  manageModel: [];
  runtimeUpdated: [settings: RuntimeSettings];
}>();

const activeSection = ref<SettingsSection>(props.initialSection ?? "appearance");
const dialog = ref<HTMLElement | null>(null);
const wallpaperInput = ref<HTMLInputElement | null>(null);
const localAppearance = ref<AppearanceSettings>({ ...props.appearance });
const wallpaperProcessing = ref(false);
const wallpaperError = ref("");
const autostart = ref(false);
const stayAwake = ref(false);
const nativeSettingsAvailable = ref(false);
const nativeSettingsError = ref("");
const notifications = ref(localStorage.getItem("sztu.notifications") !== "false");
const ccswitchOpen = ref(false);
const ccswitchLoading = ref(false);
const ccswitchApplying = ref<string | null>(null);
const ccswitchError = ref("");
const ccswitchProviders = ref<CcswitchProvider[]>([]);
const appVersion = ref(appPackage.version);
const aboutError = ref("");
const { setInitialFocus, trapTab } = useFocusTrap();

const fontSizeLabel = computed(() => `${localAppearance.value.fontSize}px`);
const paragraphSpacingLabel = computed(() => `${localAppearance.value.paragraphSpacing.toFixed(2)}em`);
const lineHeightLabel = computed(() => `${localAppearance.value.paragraphLineHeight.toFixed(2)}x`);

watch(() => props.appearance, (value) => {
  localAppearance.value = { ...value };
}, { deep: true });
watch(() => props.initialSection, (value) => {
  if (value) activeSection.value = value;
});

watch(notifications, (enabled) => localStorage.setItem("sztu.notifications", String(enabled)));

onMounted(() => {
  void setInitialFocus(dialog);
  void loadNativeSettings();
  void loadAppVersion();
});

function close() {
  emit("close");
}
function handleModelUpdated(settings: RuntimeSettings) {
  emit("runtimeUpdated", settings);
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    close();
  } else if (event.key === "Tab") {
    trapTab(event, dialog);
  }
}

async function loadNativeSettings() {
  try {
    const settings = await getNativeSettings();
    autostart.value = settings.autostart;
    stayAwake.value = settings.stay_awake;
    nativeSettingsAvailable.value = settings.supported;
    nativeSettingsError.value = "";
  } catch {
    nativeSettingsAvailable.value = false;
  }
}

async function loadAppVersion() {
  if (!isTauri()) return;
  try {
    appVersion.value = await getVersion();
  } catch {
    appVersion.value = appPackage.version;
  }
}

async function openProjectLink() {
  aboutError.value = "";
  try {
    if (isTauri()) await openUrl(PROJECT_URL);
    else window.open(PROJECT_URL, "_blank", "noopener,noreferrer");
  } catch (error) {
    aboutError.value = error instanceof Error ? error.message : "无法打开项目链接";
  }
}

async function toggleAutostart() {
  const enabled = !autostart.value;
  try {
    const settings = await setNativeSettings({ autostart: enabled });
    autostart.value = settings.autostart;
    nativeSettingsError.value = "";
  } catch (error) {
    nativeSettingsError.value = error instanceof Error ? error.message : String(error);
  }
}

async function toggleStayAwake() {
  const enabled = !stayAwake.value;
  try {
    const settings = await setNativeSettings({ stayAwake: enabled });
    stayAwake.value = settings.stay_awake;
    nativeSettingsError.value = "";
  } catch (error) {
    nativeSettingsError.value = error instanceof Error ? error.message : String(error);
  }
}

function updateAppearance(patch: Partial<AppearanceSettings>) {
  const previous = localAppearance.value;
  const next = saveAppearanceSettings({ ...previous, ...patch });
  localAppearance.value = next;
  emit("appearanceChange", next);
  const nativeUpdate: { theme?: ThemePreference; wallpaper?: WallpaperStyle } = {};
  if (patch.theme !== undefined) nativeUpdate.theme = next.theme;
  if (patch.wallpaper !== undefined) nativeUpdate.wallpaper = next.wallpaper;
  if (Object.keys(nativeUpdate).length) void setNativeSettings(nativeUpdate).catch(() => undefined);
}

function changeFontSize(delta: number) {
  updateAppearance({
    fontSize: Math.min(MAX_UI_FONT_SIZE, Math.max(MIN_UI_FONT_SIZE, localAppearance.value.fontSize + delta)),
  });
}

function chooseWallpaperFile() {
  wallpaperInput.value?.click();
}

async function compressWallpaper(file: File): Promise<string> {
  if (!file.type.match(/^image\/(png|jpeg|webp)$/)) throw new Error("请选择 PNG、JPG 或 WebP 图片");
  if (file.size > 25 * 1024 * 1024) throw new Error("图片不能超过 25 MB");

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("图片无法读取，请换一张图片");
  }
  try {
    const scale = Math.min(1, 2400 / bitmap.width, 1600 / bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("当前环境无法处理图片");
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    let dataUrl = canvas.toDataURL("image/webp", 0.84);
    if (dataUrl.length > 3_000_000) dataUrl = canvas.toDataURL("image/webp", 0.68);
    if (dataUrl.length > 3_000_000) throw new Error("图片内容过于复杂，请选择尺寸更小的图片");
    return dataUrl;
  } finally {
    bitmap.close();
  }
}

async function uploadWallpaper(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  wallpaperProcessing.value = true;
  wallpaperError.value = "";
  try {
    const customWallpaper = await compressWallpaper(file);
    updateAppearance({ wallpaper: "custom", customWallpaper, customWallpaperName: file.name });
  } catch (error) {
    wallpaperError.value = error instanceof DOMException && error.name === "QuotaExceededError"
      ? "图片保存空间不足，请选择尺寸更小的图片"
      : (error instanceof Error ? error.message : String(error));
  } finally {
    wallpaperProcessing.value = false;
    input.value = "";
  }
}

function selectCustomWallpaper() {
  if (localAppearance.value.customWallpaper) updateAppearance({ wallpaper: "custom" });
  else chooseWallpaperFile();
}

function removeCustomWallpaper() {
  wallpaperError.value = "";
  updateAppearance({ wallpaper: "none", customWallpaper: "", customWallpaperName: "" });
}

async function loadCcswitchProviders() {
  ccswitchLoading.value = true;
  ccswitchError.value = "";
  try {
    ccswitchProviders.value = await listCcswitchProviders();
    ccswitchOpen.value = true;
  } catch (error) {
    ccswitchError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ccswitchLoading.value = false;
  }
}

async function useCcswitchProvider(providerId: string) {
  ccswitchApplying.value = providerId;
  ccswitchError.value = "";
  try {
    const settings = await applyCcswitchProvider(providerId);
    if (settings) emit("runtimeUpdated", settings);
  } catch (error) {
    ccswitchError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ccswitchApplying.value = null;
  }
}

const sections: Array<{ id: SettingsSection; label: string; icon: typeof Palette }> = [
  { id: "appearance", label: "外观", icon: Palette },
  { id: "general", label: "通用", icon: SlidersHorizontal },
  { id: "agent", label: "模型管理", icon: Cpu },
  { id: "integrations", label: "连接", icon: Globe2 },
  { id: "about", label: "关于", icon: Info },
];

const themes: Array<{ id: ThemePreference; label: string; icon: typeof Sun }> = [
  { id: "system", label: "跟随系统", icon: Monitor },
  { id: "light", label: "浅色", icon: Sun },
  { id: "dark", label: "深色", icon: Moon },
];

const wallpapers: Array<{ id: WallpaperStyle; label: string }> = [
  { id: "none", label: "纯色" },
  { id: "mist", label: "薄雾" },
  { id: "grid", label: "网格" },
  { id: "paper", label: "纸纹" },
];

const accents: Array<{ id: AccentColor; label: string }> = [
  { id: "graphite", label: "石墨" },
  { id: "blue", label: "钴蓝" },
  { id: "jade", label: "松绿" },
  { id: "coral", label: "朱砂" },
];
</script>

<template>
  <div class="settings-backdrop" role="presentation" @mousedown.self="close">
    <section ref="dialog" class="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title" tabindex="-1" @keydown="onKeydown">
      <header class="settings-dialog__header">
        <div>
          <h1 id="settings-title">设置</h1>

        </div>
        <button type="button" title="关闭设置" aria-label="关闭设置" @click="close"><X :size="18" /></button>
      </header>

      <div class="settings-dialog__body">
        <nav class="settings-dialog__nav" aria-label="设置分类">
          <button v-for="item in sections" :key="item.id" type="button" :class="{ active: activeSection === item.id }" @click="activeSection = item.id">
            <component :is="item.icon" :size="17" :stroke-width="1.8" />
            <span>{{ item.label }}</span>
          </button>
          <div class="settings-dialog__nav-foot">
            <span>SztuCode Desktop</span>
            <small>本地优先工作台</small>
          </div>
        </nav>

        <main class="settings-dialog__content">
          <template v-if="activeSection === 'appearance'">
            <header class="settings-pane-title"><div><h2>外观</h2><p>所有调整即时生效</p></div><Palette :size="20" /></header>

            <section class="settings-block">
              <div class="settings-block__heading"><div><h3>主题</h3><p>选择界面的明暗模式</p></div></div>
              <div class="theme-options" role="radiogroup" aria-label="主题模式">
                <button v-for="item in themes" :key="item.id" type="button" role="radio" :aria-checked="localAppearance.theme === item.id" :class="{ selected: localAppearance.theme === item.id }" @click="updateAppearance({ theme: item.id })">
                  <component :is="item.icon" :size="17" />
                  <span>{{ item.label }}</span>
                  <Check v-if="localAppearance.theme === item.id" :size="15" />
                </button>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block__heading"><div><h3>工作台背景</h3><p>纹理只作用于窗口底层，不影响内容可读性</p></div><Image :size="17" /></div>
              <div class="wallpaper-options" role="radiogroup" aria-label="背景样式">
                <button v-for="item in wallpapers" :key="item.id" type="button" role="radio" :aria-checked="localAppearance.wallpaper === item.id" :class="['wallpaper-option', `wallpaper-option--${item.id}`, { selected: localAppearance.wallpaper === item.id }]" @click="updateAppearance({ wallpaper: item.id })">
                  <span class="wallpaper-option__preview"><i /><b /></span>
                  <span>{{ item.label }}</span>
                  <Check v-if="localAppearance.wallpaper === item.id" :size="14" />
                </button>
              </div>
              <input ref="wallpaperInput" class="wallpaper-file-input" type="file" accept="image/png,image/jpeg,image/webp" @change="uploadWallpaper" />
              <div :class="['custom-wallpaper', { selected: localAppearance.wallpaper === 'custom' }]">
                <button type="button" class="custom-wallpaper__preview" role="radio" :aria-checked="localAppearance.wallpaper === 'custom'" aria-label="自定义背景图" @click="selectCustomWallpaper">
                  <span v-if="localAppearance.customWallpaper" :style="{ backgroundImage: `url(${JSON.stringify(localAppearance.customWallpaper)})` }" />
                  <Upload v-else :size="20" />
                </button>
                <div class="custom-wallpaper__meta">
                  <b>{{ localAppearance.customWallpaperName || '自定义图片' }}</b>
                  <p>{{ localAppearance.customWallpaper ? '图片已保存在本机' : 'PNG、JPG 或 WebP，最大 25 MB' }}</p>
                </div>
                <div class="custom-wallpaper__actions">
                  <button type="button" :disabled="wallpaperProcessing" @click="chooseWallpaperFile"><Upload :size="14" />{{ wallpaperProcessing ? '处理中' : (localAppearance.customWallpaper ? '替换' : '上传') }}</button>
                  <button v-if="localAppearance.customWallpaper" type="button" class="icon-button" title="移除背景图" aria-label="移除背景图" @click="removeCustomWallpaper"><Trash2 :size="15" /></button>
                </div>
              </div>
              <p v-if="wallpaperError" class="settings-error" role="alert">{{ wallpaperError }}</p>
              <label class="range-row">
                <span><b>背景强度</b><small>{{ localAppearance.wallpaperIntensity }}%</small></span>
                <input :value="localAppearance.wallpaperIntensity" type="range" min="0" max="70" step="5" @input="updateAppearance({ wallpaperIntensity: Number(($event.target as HTMLInputElement).value) })" />
              </label>
            </section>

            <section class="settings-block">
              <div class="settings-block__heading"><div><h3>区域透明度</h3><p>分别控制工作台各层与底层背景的融合程度</p></div><SlidersHorizontal :size="17" /></div>
              <div :class="['transparency-controls', { disabled: localAppearance.wallpaper === 'none' }]" :aria-disabled="localAppearance.wallpaper === 'none'">
                <label class="range-row">
                  <span><b>侧栏与顶部栏</b><small>{{ localAppearance.chromeTransparency }}%</small></span>
                  <input aria-label="侧栏与顶部栏透明度" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.chromeTransparency" type="range" min="0" max="80" step="5" @input="updateAppearance({ chromeTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
                <label class="range-row">
                  <span><b>会话区</b><small>{{ localAppearance.conversationTransparency }}%</small></span>
                  <input aria-label="会话区透明度" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.conversationTransparency" type="range" min="0" max="80" step="5" @input="updateAppearance({ conversationTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
                <label class="range-row">
                  <span><b>输入框</b><small>{{ localAppearance.composerTransparency }}%</small></span>
                  <input aria-label="输入框透明度" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.composerTransparency" type="range" min="0" max="80" step="5" @input="updateAppearance({ composerTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
                <label class="range-row">
                  <span><b>右侧功能栏</b><small>{{ localAppearance.inspectorTransparency }}%</small></span>
                  <input aria-label="右侧功能栏透明度" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.inspectorTransparency" type="range" min="0" max="80" step="5" @input="updateAppearance({ inspectorTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
              </div>
            </section>

            <section class="settings-block appearance-split">
              <div>
                <div class="settings-block__heading"><div><h3>强调色</h3><p>用于选中、按钮与状态反馈</p></div></div>
                <div class="accent-options" role="radiogroup" aria-label="强调色">
                  <button v-for="item in accents" :key="item.id" type="button" role="radio" :aria-label="item.label" :title="item.label" :aria-checked="localAppearance.accent === item.id" :class="[`accent-${item.id}`, { selected: localAppearance.accent === item.id }]" @click="updateAppearance({ accent: item.id })"><Check v-if="localAppearance.accent === item.id" :size="14" /></button>
                </div>
              </div>
              <div class="appearance-preview" aria-label="外观预览">
                <div class="appearance-preview__rail"><i /><i /><i /></div>
                <div class="appearance-preview__canvas"><span /><b /><b /><em /></div>
              </div>
            </section>

            <section class="settings-block">
              <div class="settings-block__heading"><div><h3>字体</h3><p>分别设置界面与代码显示</p></div><Type :size="17" /></div>
              <div class="font-family-options" role="radiogroup" aria-label="界面字体">
                <button v-for="item in uiFontOptions" :key="item.id" type="button" role="radio" :aria-label="item.label" :aria-checked="localAppearance.uiFont === item.id" :class="{ selected: localAppearance.uiFont === item.id }" @click="updateAppearance({ uiFont: item.id })">
                  <span class="font-family-options__sample" :style="{ fontFamily: item.family }">Aa 字</span>
                  <span>{{ item.label }}</span>
                  <Check v-if="localAppearance.uiFont === item.id" :size="14" />
                </button>
              </div>
              <div class="form-grid font-secondary-controls">
                <label><span>代码字体</span><select :value="localAppearance.codeFont" @change="updateAppearance({ codeFont: ($event.target as HTMLSelectElement).value as CodeFont })"><option value="cascadia">Cascadia Code</option><option value="jetbrains">JetBrains Mono</option><option value="consolas">Consolas</option></select></label>
              </div>
              <div class="setting-row">
                <div><b>界面字号</b><p>调整正文与控件的基础字号</p></div>
                <div class="stepper"><button type="button" title="减小字号" aria-label="减小字号" :disabled="localAppearance.fontSize <= MIN_UI_FONT_SIZE" @click="changeFontSize(-1)">−</button><output>{{ fontSizeLabel }}</output><button type="button" title="增大字号" aria-label="增大字号" :disabled="localAppearance.fontSize >= MAX_UI_FONT_SIZE" @click="changeFontSize(1)"><Plus :size="14" /></button></div>
              </div>
              <label class="range-row">
                <span><b>段落间距</b><small>段落与列表之间的空隙 · {{ paragraphSpacingLabel }}</small></span>
                <input aria-label="段落间距" :value="localAppearance.paragraphSpacing" type="range" min="0.2" max="2" step="0.04" @input="updateAppearance({ paragraphSpacing: Number(($event.target as HTMLInputElement).value) })" />
              </label>
              <label class="range-row">
                <span><b>行高</b><small>段落内每行文字之间的行距 · {{ lineHeightLabel }}</small></span>
                <input aria-label="行高" :value="localAppearance.paragraphLineHeight" type="range" min="1" max="2" step="0.05" @input="updateAppearance({ paragraphLineHeight: Number(($event.target as HTMLInputElement).value) })" />
              </label>
              <div class="paragraph-spacing-preview" aria-label="行距预览">
                <p>调整上方滑块，下面两段文字之间的空隙会实时变化，与任务区 AI 输出的段落间距一致。</p>
                <p>列表项之间的间距会按固定比例同步缩放。</p>
                <ul><li>列表项示例一</li><li>列表项示例二</li></ul>
              </div>
              <div class="setting-row">
                <div><b>紧凑布局</b><p>缩短导航与列表行高，显示更多内容</p></div>
                <button class="switch" type="button" role="switch" :aria-checked="localAppearance.compact" :class="{ enabled: localAppearance.compact }" @click="updateAppearance({ compact: !localAppearance.compact })"><span /></button>
              </div>
            </section>
          </template>

          <template v-else-if="activeSection === 'general'">
            <header class="settings-pane-title"><div><h2>通用</h2><p>系统行为与通知</p></div><Settings2 :size="20" /></header>
            <section class="settings-block">
              <div class="settings-block__heading"><div><h3>系统设置</h3><p>控制桌面应用的启动与运行行为</p></div></div>
              <div class="setting-row"><div><b>开机自启动</b><p>登录系统时自动启动 SztuCode</p></div><button class="switch" type="button" role="switch" :disabled="!nativeSettingsAvailable" :aria-checked="autostart" :class="{ enabled: autostart }" @click="toggleAutostart"><span /></button></div>
              <div class="setting-row"><div><b>系统通知</b><p>发送任务结果与重要提醒</p></div><button class="switch" type="button" role="switch" :aria-checked="notifications" :class="{ enabled: notifications }" @click="notifications = !notifications"><span /></button></div>
              <div class="setting-row"><div><b>保持电脑唤醒</b><p>任务运行期间阻止电脑进入睡眠</p></div><button class="switch" type="button" role="switch" :disabled="!nativeSettingsAvailable" :aria-checked="stayAwake" :class="{ enabled: stayAwake }" @click="toggleStayAwake"><span /></button></div>
              <p v-if="nativeSettingsError" class="settings-error">{{ nativeSettingsError }}</p>
            </section>
          </template>

          <template v-else-if="activeSection === 'agent'">
            <header class="settings-pane-title"><div><h2>模型管理</h2></div><Cpu :size="20" /></header>
            <section class="settings-block settings-block--full">
              <ModelManager embedded @close="close" @updated="handleModelUpdated" />
            </section>
          </template>

          <template v-else-if="activeSection === 'integrations'">
            <header class="settings-pane-title"><div><h2>连接</h2><p>浏览器与本机服务</p></div><Globe2 :size="20" /></header>
            <section class="settings-block">
              <div class="integration-row"><span><Globe2 :size="18" /></span><div><b>浏览器连接</b><p>连接状态与网站操作权限</p></div><em>未连接</em></div>
              <div class="integration-row"><span><Power :size="18" /></span><div><b>本地运行时</b><p>Agent、终端与项目文件服务</p></div><em class="online">已启用</em></div>
              <div class="integration-row"><span><Coffee :size="18" /></span><div><b>后台任务</b><p>关闭设置后继续执行当前任务</p></div><em class="online">可用</em></div>
            </section>
            <section class="settings-block">
              <div class="settings-block__heading"><div><h3>模型供应商导入</h3><p>从 CC Switch 一键导入已配置的模型</p></div></div>
              <button type="button" class="btn btn--primary" :disabled="ccswitchLoading" @click="loadCcswitchProviders">
                <Download :size="15" />
                {{ ccswitchLoading ? '加载中...' : '从 CC Switch 导入' }}
              </button>
              <div v-if="ccswitchError" class="settings-error" role="alert">{{ ccswitchError }}</div>
              <div v-if="ccswitchOpen && ccswitchProviders.length" class="ccswitch-list">
                <p class="ccswitch-hint">选择要导入的供应商配置：</p>
                <div class="ccswitch-providers">
                  <button v-for="provider in ccswitchProviders" :key="provider.id" type="button" class="ccswitch-provider" :disabled="ccswitchApplying === provider.id" @click="useCcswitchProvider(provider.id)">
                    <span class="ccswitch-provider-name">{{ provider.name }}</span>
                    <LoaderCircle v-if="ccswitchApplying === provider.id" class="spin" :size="14" />
                    <Plus v-else :size="14" />
                  </button>
                </div>
              </div>
            </section>
          </template>

          <template v-else>
            <header class="settings-pane-title"><div><h2>关于</h2><p>SztuCode Desktop 项目信息</p></div><Info :size="20" /></header>
            <section class="settings-block about-product">
              <div class="about-product__identity">
                <AgentLogo class="about-product__mark" aria-hidden="true" size="small" />
                <div><h3>SztuCode Desktop</h3><p>本地优先的智能编码工作台</p></div>
              </div>
              <dl class="about-details">
                <div><dt>项目版本</dt><dd><code>v{{ appVersion }}</code></dd></div>
                <div>
                  <dt>项目链接</dt>
                  <dd><button type="button" aria-label="打开项目链接" title="在浏览器中打开项目" @click="openProjectLink"><GitFork :size="16" /><span>github.com/rojim666/SztuCode</span><ExternalLink :size="14" /></button></dd>
                </div>
              </dl>
              <p v-if="aboutError" class="settings-error" role="alert">{{ aboutError }}</p>
            </section>
          </template>
        </main>
      </div>
    </section>
  </div>
</template>

<style scoped>
.settings-backdrop { position: fixed; z-index: 900; inset: 0; display: grid; padding: 34px; place-items: center; background: rgb(22 27 29 / 42%); backdrop-filter: blur(7px); animation: settings-fade .16s ease-out; }
.settings-dialog { display: grid; width: min(980px, 94vw); height: min(720px, 88vh); min-height: 560px; overflow: hidden; color: var(--text); background: color-mix(in srgb, var(--surface) 97%, transparent); border: 1px solid var(--border-strong); border-radius: 8px; box-shadow: var(--shadow-modal); grid-template-rows: 58px minmax(0, 1fr); outline: 0; animation: settings-rise .2s cubic-bezier(.2,.75,.3,1); }
.settings-dialog__header { display: flex; align-items: center; padding: 0 14px 0 21px; border-bottom: 1px solid var(--border); }
.settings-dialog__header > div { min-width: 0; margin-right: auto; }
.settings-dialog__header h1 { margin: 0; color: var(--text); font-size: var(--text-section-title); font-weight: 650; }
.settings-dialog__header p { margin: 3px 0 0; color: var(--text-faint); font-size: var(--text-micro); }
.settings-dialog__header button { display: grid; width: 32px; height: 32px; padding: 0; place-items: center; color: var(--text-muted); background: transparent; border-radius: 6px; }
.settings-dialog__header button:hover { color: var(--text); background: var(--surface-soft); }
.settings-dialog__body { display: grid; min-height: 0; grid-template-columns: 184px minmax(0, 1fr); }
.settings-dialog__nav { display: flex; min-height: 0; padding: 13px 10px 12px; flex-direction: column; gap: 3px; background: color-mix(in srgb, var(--surface-soft) 82%, transparent); border-right: 1px solid var(--border); }
.settings-dialog__nav > button { display: flex; width: 100%; min-height: 38px; padding: 0 10px; align-items: center; gap: 10px; color: var(--text-muted); background: transparent; border-radius: 6px; text-align: left; font-size: var(--text-control); }
.settings-dialog__nav > button:hover { color: var(--text); background: color-mix(in srgb, var(--accent-soft) 55%, transparent); }
.settings-dialog__nav > button.active { color: var(--text); background: var(--accent-soft); font-weight: 600; }
.settings-dialog__nav > button.active svg { color: var(--accent); }
.settings-dialog__nav-foot { display: grid; gap: 3px; margin-top: auto; padding: 11px 10px 2px; border-top: 1px solid var(--border); }
.settings-dialog__nav-foot span { color: var(--text-muted); font-size: 11px; }
.settings-dialog__nav-foot small { color: var(--text-faint); font-size: 10px; }
.settings-dialog__content { min-width: 0; min-height: 0; padding: 24px 30px 38px; overflow-y: auto; scrollbar-gutter: stable; }
.settings-pane-title { display: flex; align-items: center; min-height: 43px; margin-bottom: 18px; }
.settings-pane-title > div { margin-right: auto; }
.settings-pane-title h2 { margin: 0; color: var(--text); font-size: var(--text-page-title); font-weight: 650; }
.settings-pane-title p { margin: 4px 0 0; color: var(--text-faint); font-size: var(--text-caption); }
.settings-pane-title > svg { color: var(--text-faint); }
.settings-block { margin-bottom: 14px; padding: 16px; background: color-mix(in srgb, var(--surface-soft) 76%, transparent); border: 1px solid var(--border); border-radius: 8px; }
.settings-block--full { padding: 0; background: transparent; border: none; }
.settings-block__heading { display: flex; min-height: 34px; align-items: flex-start; margin-bottom: 13px; }
.settings-block__heading > div { margin-right: auto; }
.settings-block__heading h3 { margin: 0; color: var(--text); font-size: var(--text-control); font-weight: 650; }
.settings-block__heading p { margin: 4px 0 0; color: var(--text-faint); font-size: var(--text-micro); }
.settings-block__heading > svg { color: var(--text-faint); }
.theme-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.theme-options button { display: grid; height: 42px; padding: 0 10px; grid-template-columns: 20px minmax(0, 1fr) 16px; align-items: center; gap: 7px; color: var(--text-muted); background: var(--surface); border: 1px solid var(--border); border-radius: 7px; text-align: left; font-size: 12px; }
.theme-options button:hover { border-color: var(--border-strong); }
.theme-options button.selected { color: var(--text); border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.theme-options button.selected > svg:last-child { color: var(--accent); }
.wallpaper-options { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.wallpaper-option { position: relative; display: grid; min-width: 0; padding: 5px 5px 8px; gap: 6px; color: var(--text-muted); background: var(--surface); border: 1px solid var(--border); border-radius: 7px; font-size: 11px; }
.wallpaper-option:hover { border-color: var(--border-strong); }
.wallpaper-option.selected { color: var(--text); border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.wallpaper-option > svg { position: absolute; right: 8px; bottom: 8px; color: var(--accent); }
.wallpaper-option__preview { position: relative; display: block; height: 46px; overflow: hidden; background: #eef0f1; border: 1px solid rgb(0 0 0 / 7%); border-radius: 4px; }
.wallpaper-option__preview i { position: absolute; inset: 6px auto 6px 6px; width: 22%; background: rgb(255 255 255 / 64%); border-radius: 2px; }
.wallpaper-option__preview b { position: absolute; inset: 6px 6px 6px 31%; background: rgb(255 255 255 / 82%); border-radius: 2px; }
.wallpaper-option--mist .wallpaper-option__preview { background: linear-gradient(135deg, #fff7ed, #ead7c4 32%, #ded8ef 56%, #dcd8d1 74%, #f5e6d2); background-size: 180% 180%; animation: wallpaper-mist-flow 7s ease-in-out infinite; }
.wallpaper-option--grid .wallpaper-option__preview { background-color: #e8edee; background-image: linear-gradient(#92a5aa55 1px, transparent 1px), linear-gradient(90deg, #92a5aa55 1px, transparent 1px); background-size: 9px 9px; }
.wallpaper-option--paper .wallpaper-option__preview { background: repeating-linear-gradient(0deg, #eae5dc 0 3px, #d9d1c355 3px 4px); }
.wallpaper-file-input { position: fixed; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.custom-wallpaper { display: grid; min-height: 62px; margin-top: 10px; padding: 7px; grid-template-columns: 82px minmax(0, 1fr) auto; align-items: center; gap: 11px; background: var(--surface); border: 1px solid var(--border); border-radius: 7px; }
.custom-wallpaper.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.custom-wallpaper__preview { display: grid; width: 82px; height: 48px; padding: 0; overflow: hidden; place-items: center; color: var(--text-faint); background: var(--surface-soft); border: 1px solid var(--border); border-radius: 4px; }
.custom-wallpaper__preview:hover { color: var(--accent); border-color: var(--border-strong); }
.custom-wallpaper__preview > span { width: 100%; height: 100%; background-position: center; background-repeat: no-repeat; background-size: cover; }
.custom-wallpaper__meta { min-width: 0; }
.custom-wallpaper__meta b { display: block; overflow: hidden; color: var(--text); font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.custom-wallpaper__meta p { margin: 4px 0 0; color: var(--text-faint); font-size: 10px; }
.custom-wallpaper__actions { display: flex; gap: 6px; }
.custom-wallpaper__actions button { display: flex; height: 30px; padding: 0 9px; align-items: center; gap: 5px; color: var(--text-muted); background: var(--surface-soft); border: 1px solid var(--border); border-radius: 6px; font-size: 10px; }
.custom-wallpaper__actions button:hover:not(:disabled) { color: var(--text); border-color: var(--border-strong); }
.custom-wallpaper__actions .icon-button { width: 30px; padding: 0; justify-content: center; color: var(--danger); }
.range-row { display: grid; margin-top: 14px; grid-template-columns: 130px minmax(0, 1fr); align-items: center; gap: 16px; }
.range-row > span { display: flex; align-items: center; gap: 8px; }
.range-row b { color: var(--text-muted); font-size: 11px; font-weight: 550; }
.range-row small { color: var(--text-faint); font-size: 10px; }
.range-row input { min-width: 0; width: 100%; max-width: 100%; height: 4px; box-sizing: border-box; margin: 0; accent-color: var(--accent); }
.transparency-controls { margin-top: 2px; }
.transparency-controls .range-row { min-height: 48px; padding: 8px 0; margin-top: 0; grid-template-columns: 170px minmax(0, 1fr); border-top: 1px solid var(--border); }
.transparency-controls .range-row:first-child { border-top: 0; }
.transparency-controls .range-row > span { min-width: 0; justify-content: space-between; }
.paragraph-spacing-preview { margin-top: 14px; padding: 12px 14px; color: var(--text-muted); background: var(--surface); border: 1px solid var(--border); border-radius: 7px; font-size: var(--text-caption); line-height: var(--markdown-line-height, 1.55); }
.paragraph-spacing-preview p { margin: 0 0 var(--markdown-paragraph-spacing, .72em); }
.paragraph-spacing-preview ul { margin: 0 0 var(--markdown-paragraph-spacing, .72em); padding-left: 1.4em; }
.paragraph-spacing-preview li { margin-bottom: var(--markdown-list-item-spacing, .28em); }
.paragraph-spacing-preview li:last-child { margin-bottom: 0; }
.transparency-controls.disabled { opacity: .48; }
.appearance-split { display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 20px; }
.accent-options { display: flex; gap: 9px; }
.accent-options button { display: grid; width: 28px; height: 28px; padding: 0; place-items: center; color: #fff; border: 2px solid var(--surface); border-radius: 50%; box-shadow: 0 0 0 1px var(--border-strong); }
.accent-options button.selected { box-shadow: 0 0 0 2px var(--text); }
.accent-graphite { background: #30383b; }.accent-blue { background: #2d6fbe; }.accent-jade { background: #26745d; }.accent-coral { background: #aa5146; }
.appearance-preview { display: grid; height: 82px; grid-template-columns: 46px minmax(0, 1fr); overflow: hidden; background: var(--app-bg); border: 1px solid var(--border-strong); border-radius: 6px; box-shadow: 0 5px 12px rgb(20 26 29 / 8%); }
.appearance-preview__rail { display: flex; padding: 10px 7px; flex-direction: column; gap: 7px; background: color-mix(in srgb, var(--surface) 78%, transparent); border-right: 1px solid var(--border); }
.appearance-preview__rail i { height: 5px; background: var(--text-faint); border-radius: 1px; opacity: .48; }
.appearance-preview__rail i:first-child { background: var(--accent); opacity: 1; }
.appearance-preview__canvas { display: grid; padding: 12px; align-content: start; gap: 7px; background: color-mix(in srgb, var(--surface) 86%, transparent); }
.appearance-preview__canvas span { width: 42%; height: 7px; background: var(--text); border-radius: 2px; opacity: .85; }
.appearance-preview__canvas b { width: 84%; height: 4px; background: var(--text-faint); border-radius: 1px; opacity: .45; }
.appearance-preview__canvas b:nth-child(3) { width: 66%; }
.appearance-preview__canvas em { width: 34px; height: 15px; margin-top: 3px; background: var(--accent); border-radius: 3px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.form-grid label { display: grid; gap: 6px; color: var(--text-muted); font-size: 11px; }
.form-grid select, .select-row select { width: 100%; height: 36px; padding: 0 9px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 6px; outline: 0; }
.form-grid select:focus, .select-row select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
.font-family-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.font-family-options button { position: relative; display: grid; min-width: 0; min-height: 62px; padding: 8px 28px 8px 10px; align-content: center; gap: 3px; color: var(--text-muted); background: var(--surface); border: 1px solid var(--border); border-radius: 7px; text-align: left; }
.font-family-options button:hover { color: var(--text); border-color: var(--border-strong); }
.font-family-options button.selected { color: var(--text); border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.font-family-options button > svg { position: absolute; top: 8px; right: 8px; color: var(--accent); }
.font-family-options__sample { overflow: hidden; color: var(--text); font-size: calc(var(--text-body) + 3px); line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.font-family-options button > span:nth-child(2) { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.font-secondary-controls { grid-template-columns: minmax(0, 1fr); margin-top: 12px; }
.setting-row, .select-row, .integration-row { display: flex; min-height: 62px; align-items: center; gap: 18px; border-top: 1px solid var(--border); }
.form-grid + .setting-row { margin-top: 14px; }
.setting-row > div:first-child, .select-row > span, .integration-row > div { min-width: 0; margin-right: auto; }
.setting-row b, .select-row b, .integration-row b, .model-current b { display: block; color: var(--text); font-size: var(--text-control); font-weight: 600; }
.setting-row p, .select-row small, .integration-row p, .model-current p { margin: 4px 0 0; color: var(--text-faint); font-size: var(--text-caption); font-weight: 400; line-height: 1.45; }
.switch { display: flex; flex: 0 0 auto; width: 36px; height: 20px; padding: 2px; align-items: center; background: var(--border-strong); border-radius: 10px; }
.switch span { width: 16px; height: 16px; background: #fff; border-radius: 50%; box-shadow: 0 1px 3px rgb(0 0 0 / 24%); transition: transform .16s ease; }
.switch.enabled { background: var(--accent); }
.switch.enabled span { transform: translateX(16px); }
.stepper { display: grid; flex: 0 0 auto; grid-template-columns: 28px 44px 28px; height: 29px; overflow: hidden; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; }
.stepper button { display: grid; padding: 0; place-items: center; color: var(--text-muted); background: transparent; }
.stepper button:hover:not(:disabled) { color: var(--text); background: var(--surface-soft); }
.stepper output { display: grid; place-items: center; color: var(--text); border-inline: 1px solid var(--border); font-size: var(--text-micro); }
.select-row { padding-block: 4px; }
.select-row select { width: 180px; }
.model-current { display: grid; min-height: 58px; grid-template-columns: 34px minmax(0, 1fr) 8px; align-items: center; gap: 11px; }
.model-current__mark { display: grid; width: 34px; height: 34px; place-items: center; color: var(--accent-contrast); background: var(--accent); border-radius: 7px; font-size: 10px; font-weight: 750; }
.model-current > i, .provider-list article > i { width: 7px; height: 7px; background: var(--text-faint); border-radius: 50%; }
.model-current > i.online, .provider-list article > i.online { background: #41a36d; box-shadow: 0 0 0 3px rgb(65 163 109 / 14%); }
.button-row { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border); }
.button-row button, .provider-list article button { display: flex; min-height: 32px; padding: 0 10px; align-items: center; gap: 6px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 6px; font-size: 11px; }
.button-row button:hover, .provider-list article button:hover { border-color: var(--border-strong); background: var(--surface-soft); }
.button-row button.primary { color: var(--accent-contrast); background: var(--accent); border-color: var(--accent); }
.provider-list { margin-top: 12px; border-top: 1px solid var(--border); }
.provider-list article { display: grid; min-height: 58px; grid-template-columns: 7px minmax(0, 1fr) auto; align-items: center; gap: 10px; border-bottom: 1px solid var(--border); }
.provider-list article div { display: grid; min-width: 0; gap: 2px; }
.provider-list article b { color: var(--text); font-size: 11px; }.provider-list article span { color: var(--text-muted); font-size: 10px; }.provider-list article small { overflow: hidden; color: var(--text-faint); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.provider-list > p { color: var(--text-faint); font-size: 11px; }
.integration-row:first-child { border-top: 0; }
.integration-row > span { display: grid; flex: 0 0 auto; width: 34px; height: 34px; place-items: center; color: var(--accent); background: var(--accent-soft); border-radius: 7px; }
.integration-row em { color: var(--text-faint); font-size: 11px; font-style: normal; }.integration-row em.online { color: #36825a; }
.about-product { padding: 0; overflow: hidden; }
.about-product__identity { display: flex; min-height: 112px; padding: 22px; align-items: center; gap: 15px; background: color-mix(in srgb, var(--surface) 68%, transparent); border-bottom: 1px solid var(--border); }
.about-product__mark { width: 48px; height: 48px; flex: 0 0 auto; color: inherit; background: transparent; border: 0; border-radius: 0; box-shadow: none; }
.about-product__identity h3 { margin: 0; color: var(--text); font-size: var(--text-section-title); font-weight: 650; }
.about-product__identity p { margin: 6px 0 0; color: var(--text-faint); font-size: var(--text-caption); }
.about-details { margin: 0; padding: 4px 22px 8px; }
.about-details > div { display: grid; min-height: 62px; grid-template-columns: 116px minmax(0, 1fr); align-items: center; gap: 14px; border-top: 1px solid var(--border); }
.about-details > div:first-child { border-top: 0; }
.about-details dt { color: var(--text-muted); font-size: var(--text-control); }
.about-details dd { min-width: 0; margin: 0; color: var(--text); }
.about-details code { color: var(--text); font-family: var(--font-code); font-size: var(--text-caption); }
.about-details button { display: flex; max-width: 100%; min-height: 34px; padding: 0 9px; align-items: center; gap: 7px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 6px; font-size: var(--text-caption); }
.about-details button:hover { background: var(--surface-soft); border-color: var(--border-strong); }
.about-details button span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.about-details button svg:first-child { flex: 0 0 auto; color: var(--text-muted); }
.about-details button svg:last-child { flex: 0 0 auto; color: var(--text-faint); }
.about-product > .settings-error { margin: 0 22px 14px; }
.settings-error { margin: 9px 0 0; color: var(--danger); font-size: 11px; line-height: 1.5; }

/* CC Switch 导入 */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 32px; padding: 0 14px; border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.12s ease; white-space: nowrap; border: 1px solid transparent; }
.btn--primary { color: #fff; background: var(--text); border-color: var(--text); }
.btn--primary:hover:not(:disabled) { opacity: 0.9; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ccswitch-list { margin-top: 12px; }
.ccswitch-hint { margin: 0 0 8px; font-size: 11px; color: var(--text-muted); }
.ccswitch-providers { display: flex; flex-direction: column; gap: 4px; }
.ccswitch-provider { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 8px 12px; background: var(--surface-soft); border: 1px solid var(--border); border-radius: 6px; font-size: 12px; color: var(--text); cursor: pointer; transition: all 0.12s ease; }
.ccswitch-provider:hover:not(:disabled) { border-color: var(--accent); background: var(--accent-soft); }
.ccswitch-provider:disabled { opacity: 0.6; cursor: not-allowed; }
.ccswitch-provider-name { font-weight: 500; }
.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

@keyframes settings-fade { from { opacity: 0; } }
@keyframes settings-rise { from { opacity: 0; transform: translateY(8px) scale(.99); } }
@keyframes wallpaper-mist-flow { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@media (max-width: 760px) { .settings-backdrop { padding: 14px; }.settings-dialog { width: 100%; height: min(760px, 94vh); min-height: 0; }.settings-dialog__body { grid-template-columns: 58px minmax(0, 1fr); }.settings-dialog__nav { padding-inline: 7px; }.settings-dialog__nav > button { justify-content: center; padding: 0; }.settings-dialog__nav > button span, .settings-dialog__nav-foot { display: none; }.settings-dialog__content { padding: 20px 18px 30px; }.wallpaper-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }.custom-wallpaper { grid-template-columns: 70px minmax(0, 1fr); }.custom-wallpaper__preview { width: 70px; }.custom-wallpaper__actions { grid-column: 1 / -1; }.appearance-split { grid-template-columns: 1fr; }.theme-options { grid-template-columns: 1fr; }.form-grid { grid-template-columns: 1fr; }.font-family-options { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (prefers-reduced-motion: reduce) { .settings-backdrop, .settings-dialog, .wallpaper-option--mist .wallpaper-option__preview { animation: none; } }
</style>
