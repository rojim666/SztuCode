<script setup lang="ts">
import { getVersion } from "@tauri-apps/api/app";
import { isTauri } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import appPackage from "../../../package.json";
import { localeOptions, setLocale, type AppLocale } from "../../i18n";
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
const { t, locale } = useI18n({ useScope: "global" });
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
    aboutError.value = error instanceof Error ? error.message : t("settings.errors.openProjectLink");
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
  if (!file.type.match(/^image\/(png|jpeg|webp)$/)) throw new Error(t("settings.errors.wallpaperType"));
  if (file.size > 25 * 1024 * 1024) throw new Error(t("settings.errors.wallpaperSize"));

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error(t("settings.errors.wallpaperRead"));
  }
  try {
    const scale = Math.min(1, 2400 / bitmap.width, 1600 / bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error(t("settings.errors.wallpaperCanvas"));
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    let dataUrl = canvas.toDataURL("image/webp", 0.84);
    if (dataUrl.length > 3_000_000) dataUrl = canvas.toDataURL("image/webp", 0.68);
    if (dataUrl.length > 3_000_000) throw new Error(t("settings.errors.wallpaperComplex"));
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
      ? t("settings.errors.wallpaperQuota")
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

const sections = computed<Array<{ id: SettingsSection; label: string; icon: string }>>(() => [
  { id: "appearance", label: t("settings.sections.appearance"), icon: "Palette" },
  { id: "general", label: t("settings.sections.general"), icon: "SlidersHorizontal" },
  { id: "agent", label: t("settings.sections.agent"), icon: "Cpu" },
  { id: "integrations", label: t("settings.sections.integrations"), icon: "Globe2" },
  { id: "about", label: t("settings.sections.about"), icon: "Info" },
]);

const themes = computed<Array<{ id: ThemePreference; label: string; icon: string }>>(() => [
  { id: "system", label: t("settings.appearance.theme.system"), icon: "Monitor" },
  { id: "light", label: t("settings.appearance.theme.light"), icon: "Sun" },
  { id: "dark", label: t("settings.appearance.theme.dark"), icon: "Moon" },
]);

const wallpapers = computed<Array<{ id: WallpaperStyle; label: string }>>(() => [
  { id: "none", label: t("settings.appearance.wallpaper.none") },
  { id: "mist", label: t("settings.appearance.wallpaper.mist") },
  { id: "grid", label: t("settings.appearance.wallpaper.grid") },
  { id: "paper", label: t("settings.appearance.wallpaper.paper") },
]);

const accents = computed<Array<{ id: AccentColor; label: string }>>(() => [
  { id: "graphite", label: t("settings.appearance.accent.graphite") },
  { id: "blue", label: t("settings.appearance.accent.blue") },
  { id: "jade", label: t("settings.appearance.accent.jade") },
  { id: "coral", label: t("settings.appearance.accent.coral") },
]);

function selectLocale(value: AppLocale) {
  setLocale(value);
}
</script>

<template>
  <div class="settings-backdrop" role="presentation" @mousedown.self="close">
    <section ref="dialog" class="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title" tabindex="-1" @keydown="onKeydown">
      <header class="settings-dialog__header">
        <div>
          <h1 id="settings-title">{{ t('settings.title') }}</h1>
        </div>
        <button type="button" class="icon-btn" :title="t('settings.close')" :aria-label="t('settings.close')" @click="close"><AppIcon name="X" :size="16" /></button>
      </header>

      <div class="settings-dialog__body">
        <nav class="settings-dialog__nav" :aria-label="t('settings.navAria')">
          <button v-for="item in sections" :key="item.id" type="button" class="nav-item" :class="{ active: activeSection === item.id }" @click="activeSection = item.id">
            <AppIcon :name="item.icon" :size="16" :filled="activeSection === item.id" />
            <span>{{ item.label }}</span>
          </button>
          <div class="settings-dialog__nav-foot">
            <span>SztuCode Desktop</span>
            <small>{{ t('settings.brandTagline') }}</small>
          </div>
        </nav>

        <main class="settings-dialog__content">
          <template v-if="activeSection === 'appearance'">
            <header class="settings-pane-title">
              <div>
                <h2>{{ t('settings.appearance.title') }}</h2>
                <p>{{ t('settings.appearance.subtitle') }}</p>
              </div>
              <AppIcon name="Palette" :size="18" />
            </header>

            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.appearance.theme.title') }}</h3>
                  <p>{{ t('settings.appearance.theme.desc') }}</p>
                </div>
              </div>
              <div class="option-grid option-grid--3" role="radiogroup" :aria-label="t('settings.appearance.theme.groupAria')">
                <button v-for="item in themes" :key="item.id" type="button" class="option-btn" role="radio" :aria-checked="localAppearance.theme === item.id" :class="{ selected: localAppearance.theme === item.id }" @click="updateAppearance({ theme: item.id })">
                  <AppIcon :name="item.icon" :size="16" :filled="localAppearance.theme === item.id" />
                  <span>{{ item.label }}</span>
                  <AppIcon v-if="localAppearance.theme === item.id" name="Check" :size="14" class="check-icon" />
                </button>
              </div>
            </section>

            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.appearance.wallpaper.title') }}</h3>
                  <p>{{ t('settings.appearance.wallpaper.desc') }}</p>
                </div>
                <AppIcon name="Image" :size="16" />
              </div>
              <div class="option-grid option-grid--4" role="radiogroup" :aria-label="t('settings.appearance.wallpaper.groupAria')">
                <button v-for="item in wallpapers" :key="item.id" type="button" class="wallpaper-btn" role="radio" :aria-checked="localAppearance.wallpaper === item.id" :class="['wallpaper-btn--' + item.id, { selected: localAppearance.wallpaper === item.id }]" @click="updateAppearance({ wallpaper: item.id })">
                  <span class="wallpaper-preview"><i /><b /></span>
                  <span class="wallpaper-label">{{ item.label }}</span>
                  <AppIcon v-if="localAppearance.wallpaper === item.id" name="Check" :size="14" class="check-icon" />
                </button>
              </div>
              <input ref="wallpaperInput" class="wallpaper-file-input" type="file" accept="image/png,image/jpeg,image/webp" @change="uploadWallpaper" />
              <div :class="['custom-wallpaper', { selected: localAppearance.wallpaper === 'custom' }]">
                <button type="button" class="custom-wallpaper__preview" role="radio" :aria-checked="localAppearance.wallpaper === 'custom'" :aria-label="t('settings.appearance.wallpaper.customAria')" @click="selectCustomWallpaper">
                  <span v-if="localAppearance.customWallpaper" :style="{ backgroundImage: `url(${JSON.stringify(localAppearance.customWallpaper)})` }" />
                  <AppIcon v-else name="Upload" :size="18" />
                </button>
                <div class="custom-wallpaper__meta">
                  <b>{{ localAppearance.customWallpaperName || t('settings.appearance.wallpaper.customDefault') }}</b>
                  <p>{{ localAppearance.customWallpaper ? t('settings.appearance.wallpaper.saved') : t('settings.appearance.wallpaper.hint') }}</p>
                </div>
                <div class="custom-wallpaper__actions">
                  <button type="button" class="btn btn--ghost btn--sm" :disabled="wallpaperProcessing" @click="chooseWallpaperFile">
                    <AppIcon name="Upload" :size="13" />{{ wallpaperProcessing ? t('settings.appearance.wallpaper.processing') : (localAppearance.customWallpaper ? t('settings.appearance.wallpaper.replace') : t('settings.appearance.wallpaper.upload')) }}
                  </button>
                  <button v-if="localAppearance.customWallpaper" type="button" class="icon-btn icon-btn--sm icon-btn--danger" :title="t('settings.appearance.wallpaper.remove')" :aria-label="t('settings.appearance.wallpaper.remove')" @click="removeCustomWallpaper"><AppIcon name="Trash2" :size="13" /></button>
                </div>
              </div>
              <p v-if="wallpaperError" class="form-error" role="alert">{{ wallpaperError }}</p>
              <label class="slider-row">
                <span class="slider-label">
                  <b>{{ t('settings.appearance.wallpaper.intensity') }}</b>
                  <small>{{ localAppearance.wallpaperIntensity }}%</small>
                </span>
                <input :value="localAppearance.wallpaperIntensity" type="range" min="0" max="70" step="5" class="slider" @input="updateAppearance({ wallpaperIntensity: Number(($event.target as HTMLInputElement).value) })" />
              </label>
            </section>

            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.appearance.transparency.title') }}</h3>
                  <p>{{ t('settings.appearance.transparency.desc') }}</p>
                </div>
                <AppIcon name="SlidersHorizontal" :size="16" />
              </div>
              <div :class="['slider-group', { disabled: localAppearance.wallpaper === 'none' }]" :aria-disabled="localAppearance.wallpaper === 'none'">
                <label class="slider-row slider-row--bordered">
                  <span class="slider-label">
                    <b>{{ t('settings.appearance.transparency.chrome') }}</b>
                    <small>{{ localAppearance.chromeTransparency }}%</small>
                  </span>
                  <input :aria-label="t('settings.appearance.transparency.chromeAria')" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.chromeTransparency" type="range" min="0" max="80" step="5" class="slider" @input="updateAppearance({ chromeTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
                <label class="slider-row slider-row--bordered">
                  <span class="slider-label">
                    <b>{{ t('settings.appearance.transparency.conversation') }}</b>
                    <small>{{ localAppearance.conversationTransparency }}%</small>
                  </span>
                  <input :aria-label="t('settings.appearance.transparency.conversationAria')" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.conversationTransparency" type="range" min="0" max="80" step="5" class="slider" @input="updateAppearance({ conversationTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
                <label class="slider-row slider-row--bordered">
                  <span class="slider-label">
                    <b>{{ t('settings.appearance.transparency.composer') }}</b>
                    <small>{{ localAppearance.composerTransparency }}%</small>
                  </span>
                  <input :aria-label="t('settings.appearance.transparency.composerAria')" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.composerTransparency" type="range" min="0" max="80" step="5" class="slider" @input="updateAppearance({ composerTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
                <label class="slider-row slider-row--bordered">
                  <span class="slider-label">
                    <b>{{ t('settings.appearance.transparency.inspector') }}</b>
                    <small>{{ localAppearance.inspectorTransparency }}%</small>
                  </span>
                  <input :aria-label="t('settings.appearance.transparency.inspectorAria')" :disabled="localAppearance.wallpaper === 'none'" :value="localAppearance.inspectorTransparency" type="range" min="0" max="80" step="5" class="slider" @input="updateAppearance({ inspectorTransparency: Number(($event.target as HTMLInputElement).value) })" />
                </label>
              </div>
            </section>

            <section class="settings-card settings-card--split">
              <div>
                <div class="settings-card__heading">
                  <div>
                    <h3>{{ t('settings.appearance.accent.title') }}</h3>
                    <p>{{ t('settings.appearance.accent.desc') }}</p>
                  </div>
                </div>
                <div class="accent-picker" role="radiogroup" :aria-label="t('settings.appearance.accent.groupAria')">
                  <button v-for="item in accents" :key="item.id" type="button" class="accent-dot" role="radio" :aria-label="item.label" :title="item.label" :aria-checked="localAppearance.accent === item.id" :class="['accent-' + item.id, { selected: localAppearance.accent === item.id }]" @click="updateAppearance({ accent: item.id })">
                    <AppIcon v-if="localAppearance.accent === item.id" name="Check" :size="12" />
                  </button>
                </div>
              </div>
              <div class="appearance-preview" :aria-label="t('settings.appearance.accent.previewAria')">
                <div class="appearance-preview__rail"><i /><i /><i /></div>
                <div class="appearance-preview__canvas"><span /><b /><b /><em /></div>
              </div>
            </section>

            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.appearance.font.title') }}</h3>
                  <p>{{ t('settings.appearance.font.desc') }}</p>
                </div>
                <AppIcon name="Type" :size="16" />
              </div>
              <div class="option-grid option-grid--3" role="radiogroup" :aria-label="t('settings.appearance.font.uiGroupAria')">
                <button v-for="item in uiFontOptions" :key="item.id" type="button" class="font-btn" role="radio" :aria-label="item.label" :aria-checked="localAppearance.uiFont === item.id" :class="{ selected: localAppearance.uiFont === item.id }" @click="updateAppearance({ uiFont: item.id })">
                  <span class="font-sample" :style="{ fontFamily: item.family }">{{ t('settings.appearance.font.sampleText') }}</span>
                  <span class="font-name">{{ item.label }}</span>
                  <AppIcon v-if="localAppearance.uiFont === item.id" name="Check" :size="14" class="check-icon" />
                </button>
              </div>
              <div class="form-row">
                <label class="form-field">
                  <span>{{ t('settings.appearance.font.code') }}</span>
                  <select :value="localAppearance.codeFont" class="form-select" @change="updateAppearance({ codeFont: ($event.target as HTMLSelectElement).value as CodeFont })">
                    <option value="cascadia">Cascadia Code</option>
                    <option value="jetbrains">JetBrains Mono</option>
                    <option value="consolas">Consolas</option>
                  </select>
                </label>
              </div>
              <div class="list-row">
                <div class="list-row__text">
                  <b>{{ t('settings.appearance.font.size') }}</b>
                  <p>{{ t('settings.appearance.font.sizeDesc') }}</p>
                </div>
                <div class="stepper">
                  <button type="button" class="stepper-btn" :title="t('settings.appearance.font.decrease')" :aria-label="t('settings.appearance.font.decrease')" :disabled="localAppearance.fontSize <= MIN_UI_FONT_SIZE" @click="changeFontSize(-1)">−</button>
                  <output class="stepper-value">{{ fontSizeLabel }}</output>
                  <button type="button" class="stepper-btn" :title="t('settings.appearance.font.increase')" :aria-label="t('settings.appearance.font.increase')" :disabled="localAppearance.fontSize >= MAX_UI_FONT_SIZE" @click="changeFontSize(1)"><AppIcon name="Plus" :size="12" /></button>
                </div>
              </div>
              <label class="slider-row">
                <span class="slider-label">
                  <b>{{ t('settings.appearance.font.paragraphSpacing') }}</b>
                  <small>{{ paragraphSpacingLabel }}</small>
                </span>
                <input :aria-label="t('settings.appearance.font.paragraphSpacing')" :value="localAppearance.paragraphSpacing" type="range" min="0.2" max="2" step="0.04" class="slider" @input="updateAppearance({ paragraphSpacing: Number(($event.target as HTMLInputElement).value) })" />
              </label>
              <label class="slider-row">
                <span class="slider-label">
                  <b>{{ t('settings.appearance.font.lineHeight') }}</b>
                  <small>{{ lineHeightLabel }}</small>
                </span>
                <input :aria-label="t('settings.appearance.font.lineHeight')" :value="localAppearance.paragraphLineHeight" type="range" min="1" max="2" step="0.05" class="slider" @input="updateAppearance({ paragraphLineHeight: Number(($event.target as HTMLInputElement).value) })" />
              </label>
              <div class="preview-box" :aria-label="t('settings.appearance.font.previewAria')">
                <p>{{ t('settings.appearance.font.previewP1') }}</p>
                <p>{{ t('settings.appearance.font.previewP2') }}</p>
                <ul><li>{{ t('settings.appearance.font.previewLi1') }}</li><li>{{ t('settings.appearance.font.previewLi2') }}</li></ul>
              </div>
              <div class="list-row">
                <div class="list-row__text">
                  <b>{{ t('settings.appearance.font.compact') }}</b>
                  <p>{{ t('settings.appearance.font.compactDesc') }}</p>
                </div>
                <button class="toggle" type="button" role="switch" :aria-checked="localAppearance.compact" :class="{ enabled: localAppearance.compact }" @click="updateAppearance({ compact: !localAppearance.compact })">
                  <span class="toggle-thumb" />
                </button>
              </div>
            </section>
          </template>

          <template v-else-if="activeSection === 'general'">
            <header class="settings-pane-title">
              <div>
                <h2>{{ t('settings.general.title') }}</h2>
                <p>{{ t('settings.general.subtitle') }}</p>
              </div>
              <AppIcon name="Settings2" :size="18" />
            </header>
            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.language.title') }}</h3>
                  <p>{{ t('settings.language.desc') }}</p>
                </div>
                <AppIcon name="Languages" :size="16" />
              </div>
              <div class="form-row">
                <label class="form-field">
                  <span>{{ t('settings.language.select') }}</span>
                  <select :value="locale" class="form-select" @change="selectLocale(($event.target as HTMLSelectElement).value as AppLocale)">
                    <option v-for="item in localeOptions" :key="item.id" :value="item.id">{{ item.nativeLabel }}</option>
                  </select>
                </label>
              </div>
            </section>
            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.general.system.title') }}</h3>
                  <p>{{ t('settings.general.system.desc') }}</p>
                </div>
              </div>
              <div class="list-row">
                <div class="list-row__text">
                  <b>{{ t('settings.general.system.autostart') }}</b>
                  <p>{{ t('settings.general.system.autostartDesc') }}</p>
                </div>
                <button class="toggle" type="button" role="switch" :disabled="!nativeSettingsAvailable" :aria-checked="autostart" :class="{ enabled: autostart }" @click="toggleAutostart">
                  <span class="toggle-thumb" />
                </button>
              </div>
              <div class="list-row">
                <div class="list-row__text">
                  <b>{{ t('settings.general.system.notifications') }}</b>
                  <p>{{ t('settings.general.system.notificationsDesc') }}</p>
                </div>
                <button class="toggle" type="button" role="switch" :aria-checked="notifications" :class="{ enabled: notifications }" @click="notifications = !notifications">
                  <span class="toggle-thumb" />
                </button>
              </div>
              <div class="list-row">
                <div class="list-row__text">
                  <b>{{ t('settings.general.system.stayAwake') }}</b>
                  <p>{{ t('settings.general.system.stayAwakeDesc') }}</p>
                </div>
                <button class="toggle" type="button" role="switch" :disabled="!nativeSettingsAvailable" :aria-checked="stayAwake" :class="{ enabled: stayAwake }" @click="toggleStayAwake">
                  <span class="toggle-thumb" />
                </button>
              </div>
              <p v-if="nativeSettingsError" class="form-error">{{ nativeSettingsError }}</p>
            </section>
          </template>

          <template v-else-if="activeSection === 'agent'">
            <header class="settings-pane-title">
              <div>
                <h2>{{ t('settings.sections.agent') }}</h2>
              </div>
              <AppIcon name="Cpu" :size="18" />
            </header>
            <section class="settings-card settings-card--flush">
              <ModelManager embedded @close="close" @updated="handleModelUpdated" />
            </section>
          </template>

          <template v-else-if="activeSection === 'integrations'">
            <header class="settings-pane-title">
              <div>
                <h2>{{ t('settings.integrations.title') }}</h2>
                <p>{{ t('settings.integrations.subtitle') }}</p>
              </div>
              <AppIcon name="Globe2" :size="18" />
            </header>
            <section class="settings-card">
              <div class="integration-row">
                <span class="integration-icon"><AppIcon name="Link2" :size="17" /></span>
                <div class="integration-text">
                  <b>{{ t('settings.integrations.browser.title') }}</b>
                  <p>{{ t('settings.integrations.browser.desc') }}</p>
                </div>
                <em class="status-badge">{{ t('settings.integrations.browser.status') }}</em>
              </div>
              <div class="integration-row">
                <span class="integration-icon"><AppIcon name="Server" :size="17" /></span>
                <div class="integration-text">
                  <b>{{ t('settings.integrations.runtime.title') }}</b>
                  <p>{{ t('settings.integrations.runtime.desc') }}</p>
                </div>
                <em class="status-badge status-badge--online">{{ t('settings.integrations.runtime.status') }}</em>
              </div>
              <div class="integration-row">
                <span class="integration-icon"><AppIcon name="Clock3" :size="17" /></span>
                <div class="integration-text">
                  <b>{{ t('settings.integrations.background.title') }}</b>
                  <p>{{ t('settings.integrations.background.desc') }}</p>
                </div>
                <em class="status-badge status-badge--online">{{ t('settings.integrations.background.status') }}</em>
              </div>
            </section>
            <section class="settings-card">
              <div class="settings-card__heading">
                <div>
                  <h3>{{ t('settings.integrations.ccswitch.title') }}</h3>
                  <p>{{ t('settings.integrations.ccswitch.desc') }}</p>
                </div>
              </div>
              <button type="button" class="btn btn--primary" :disabled="ccswitchLoading" @click="loadCcswitchProviders">
                <AppIcon name="Download" :size="15" />
                {{ ccswitchLoading ? t('settings.integrations.ccswitch.loading') : t('settings.integrations.ccswitch.import') }}
              </button>
              <div v-if="ccswitchError" class="form-error" role="alert">{{ ccswitchError }}</div>
              <div v-if="ccswitchOpen && ccswitchProviders.length" class="ccswitch-section">
                <p class="ccswitch-hint">{{ t('settings.integrations.ccswitch.hint') }}</p>
                <div class="ccswitch-list">
                  <button v-for="provider in ccswitchProviders" :key="provider.id" type="button" class="ccswitch-item" :disabled="ccswitchApplying === provider.id" @click="useCcswitchProvider(provider.id)">
                    <span class="ccswitch-name">{{ provider.name }}</span>
                    <AppIcon v-if="ccswitchApplying === provider.id" name="LoaderCircle" class="spin" :size="14" />
                    <AppIcon v-else name="Plus" :size="14" />
                  </button>
                </div>
              </div>
            </section>
          </template>

          <template v-else>
            <header class="settings-pane-title">
              <div>
                <h2>{{ t('settings.about.title') }}</h2>
                <p>{{ t('settings.about.subtitle') }}</p>
              </div>
              <AppIcon name="Info" :size="18" />
            </header>
            <section class="settings-card settings-card--about">
              <div class="about-header">
                <AgentLogo class="about-logo" aria-hidden="true" size="small" />
                <div>
                  <h3>SztuCode Desktop</h3>
                  <p>{{ t('settings.about.tagline') }}</p>
                </div>
              </div>
              <dl class="about-list">
                <div class="about-row">
                  <dt>{{ t('settings.about.version') }}</dt>
                  <dd><code>v{{ appVersion }}</code></dd>
                </div>
                <div class="about-row">
                  <dt>{{ t('settings.about.link') }}</dt>
                  <dd>
                    <button type="button" class="link-btn" :aria-label="t('settings.about.openLink')" :title="t('settings.about.openBrowser')" @click="openProjectLink">
                      <AppIcon name="GitFork" :size="14" />
                      <span>github.com/rojim666/SztuCode</span>
                      <AppIcon name="ExternalLink" :size="12" />
                    </button>
                  </dd>
                </div>
              </dl>
              <p v-if="aboutError" class="form-error" role="alert">{{ aboutError }}</p>
            </section>
          </template>
        </main>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ========== 基础动画 ========== */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ========== 背景遮罩 ========== */
.settings-backdrop {
  position: fixed;
  z-index: 900;
  inset: 0;
  display: grid;
  padding: 24px;
  place-items: center;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  animation: fadeIn 0.12s ease;
}

/* ========== 对话框主体 ========== */
.settings-dialog {
  display: grid;
  width: min(960px, 94vw);
  height: min(700px, 88vh);
  min-height: 540px;
  overflow: hidden;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.2);
  grid-template-rows: 48px minmax(0, 1fr);
  outline: 0;
  animation: slideUp 0.15s cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* ========== 头部 ========== */
.settings-dialog__header {
  display: flex;
  align-items: center;
  padding: 0 14px 0 18px;
  border-bottom: 1px solid var(--border);
}

.settings-dialog__header > div {
  min-width: 0;
  margin-right: auto;
}

.settings-dialog__header h1 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
}

/* ========== 图标按钮 - 统一 mm 风格 ========== */
.icon-btn {
  display: grid;
  width: 28px;
  height: 28px;
  padding: 0;
  place-items: center;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.icon-btn:hover {
  color: var(--text);
  background: var(--surface-soft);
}

.icon-btn--sm {
  width: 26px;
  height: 26px;
  border-radius: 5px;
}

.icon-btn--danger:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

/* ========== 主体布局 ========== */
.settings-dialog__body {
  display: grid;
  min-height: 0;
  grid-template-columns: 168px minmax(0, 1fr);
}

/* ========== 侧边导航 ========== */
.settings-dialog__nav {
  display: flex;
  min-height: 0;
  padding: 8px;
  flex-direction: column;
  gap: 1px;
  background: var(--surface-soft);
  border-right: 1px solid var(--border);
}

.nav-item {
  display: flex;
  width: 100%;
  min-height: 32px;
  padding: 0 10px;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: 6px;
  text-align: left;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
}

.nav-item:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--border) 30%, transparent);
}

.nav-item.active {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 70%, var(--surface-soft));
  font-weight: 600;
}

.nav-item.active svg {
  color: var(--accent);
}

.settings-dialog__nav-foot {
  display: grid;
  gap: 1px;
  margin-top: auto;
  padding: 10px 10px 2px;
  border-top: 1px solid var(--border);
}

.settings-dialog__nav-foot span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
}

.settings-dialog__nav-foot small {
  color: var(--text-faint);
  font-size: 10px;
}

/* ========== 内容区 ========== */
.settings-dialog__content {
  min-width: 0;
  min-height: 0;
  padding: 20px 22px 28px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

/* ========== 页面标题 ========== */
.settings-pane-title {
  display: flex;
  align-items: center;
  min-height: 32px;
  margin-bottom: 14px;
}

.settings-pane-title > div {
  margin-right: auto;
}

.settings-pane-title h2 {
  margin: 0;
  color: var(--text);
  font-size: 17px;
  font-weight: 600;
}

.settings-pane-title p {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 12px;
}

.settings-pane-title > svg {
  color: var(--text-faint);
  width: 18px;
  height: 18px;
}

/* ========== 卡片容器 - 统一 model-card 风格 ========== */
.settings-card {
  margin-bottom: 8px;
  padding: 14px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 0.12s ease;
}

.settings-card--flush {
  padding: 0;
  border: none;
}

.settings-card__heading {
  display: flex;
  min-height: 26px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.settings-card__heading > div {
  margin-right: auto;
}

.settings-card__heading h3 {
  margin: 0;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.settings-card__heading p {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 11px;
}

.settings-card__heading > svg {
  color: var(--text-faint);
  width: 16px;
  height: 16px;
}

/* ========== 选项按钮网格 - 统一 vendor-card 风格 ========== */
.option-grid {
  display: grid;
  gap: 6px;
}

.option-grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.option-grid--2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.option-btn--locale {
  grid-template-columns: minmax(0, 1fr) 16px;
  justify-items: center;
}

.option-btn--locale > span {
  justify-self: stretch;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.option-grid--4 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.option-btn {
  display: grid;
  height: 38px;
  padding: 0 12px;
  grid-template-columns: 18px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 7px;
  text-align: left;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
}

.option-btn:hover {
  border-color: var(--border-strong);
}

.option-btn.selected {
  color: var(--text);
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.check-icon {
  color: var(--accent);
}

/* ========== 壁纸选项 ========== */
.wallpaper-btn {
  position: relative;
  display: grid;
  min-width: 0;
  padding: 6px 6px 10px;
  gap: 6px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
}

.wallpaper-btn:hover {
  border-color: var(--border-strong);
}

.wallpaper-btn.selected {
  color: var(--text);
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.wallpaper-btn .check-icon {
  position: absolute;
  right: 8px;
  bottom: 10px;
}

.wallpaper-preview {
  position: relative;
  display: block;
  height: 42px;
  overflow: hidden;
  background: #eef0f1;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 5px;
}

.wallpaper-preview i {
  position: absolute;
  inset: 6px auto 6px 6px;
  width: 22%;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 2px;
}

.wallpaper-preview b {
  position: absolute;
  inset: 6px 6px 6px 31%;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 2px;
}

.wallpaper-label {
  padding: 0 2px;
}

.wallpaper-btn--mist .wallpaper-preview {
  background: linear-gradient(135deg, #fff7ed, #ead7c4 32%, #ded8ef 56%, #dcd8d1 74%, #f5e6d2);
  background-size: 180% 180%;
  animation: wallpaperMistFlow 7s ease-in-out infinite;
}

.wallpaper-btn--grid .wallpaper-preview {
  background-color: #e8edee;
  background-image: linear-gradient(rgba(146, 165, 170, 0.3) 1px, transparent 1px),
    linear-gradient(90deg, rgba(146, 165, 170, 0.3) 1px, transparent 1px);
  background-size: 9px 9px;
}

.wallpaper-btn--paper .wallpaper-preview {
  background: repeating-linear-gradient(0deg, #eae5dc 0 3px, rgba(217, 209, 195, 0.3) 3px 4px);
}

@keyframes wallpaperMistFlow {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.wallpaper-file-input {
  position: fixed;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

/* ========== 自定义壁纸 ========== */
.custom-wallpaper {
  display: grid;
  min-height: 56px;
  margin-top: 8px;
  padding: 8px;
  grid-template-columns: 68px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 7px;
  transition: all 0.12s ease;
}

.custom-wallpaper.selected {
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 40%, transparent);
}

.custom-wallpaper__preview {
  display: grid;
  width: 68px;
  height: 42px;
  padding: 0;
  overflow: hidden;
  place-items: center;
  color: var(--text-faint);
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.custom-wallpaper__preview:hover {
  color: var(--accent);
  border-color: var(--border-strong);
}

.custom-wallpaper__preview > span {
  width: 100%;
  height: 100%;
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
}

.custom-wallpaper__meta {
  min-width: 0;
}

.custom-wallpaper__meta b {
  display: block;
  overflow: hidden;
  color: var(--text);
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-wallpaper__meta p {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 11px;
}

.custom-wallpaper__actions {
  display: flex;
  gap: 4px;
}

/* ========== 滑块 ========== */
.slider-row {
  display: grid;
  margin-top: 10px;
  grid-template-columns: 130px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.slider-row--bordered {
  min-height: 38px;
  padding: 8px 0;
  margin-top: 0;
  border-top: 1px solid var(--border);
}

.slider-row--bordered:first-child {
  border-top: 0;
}

.slider-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.slider-label b {
  color: var(--text);
  font-size: 12px;
  font-weight: 500;
}

.slider-label small {
  color: var(--text-faint);
  font-size: 11px;
  font-family: var(--font-mono, 'SF Mono', Consolas, monospace);
}

.slider {
  min-width: 0;
  width: 100%;
  height: 4px;
  margin: 0;
  accent-color: var(--accent);
  cursor: pointer;
}

.slider-group {
  margin-top: 4px;
}

.slider-group.disabled {
  opacity: 0.45;
  pointer-events: none;
}

/* ========== 按钮系统 - 统一 mm-btn 风格 ========== */
.btn {
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
  transition: all 0.12s ease;
  white-space: nowrap;
  border: 1px solid transparent;
}

.btn--sm {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  border-radius: 5px;
}

.btn--ghost {
  color: var(--text);
  background: var(--surface-soft);
}

.btn--ghost:hover:not(:disabled) {
  background: color-mix(in srgb, var(--border) 40%, var(--surface-soft));
}

.btn--primary {
  color: #fff;
  background: var(--text);
  border-color: var(--text);
}

.btn--primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ========== 表单控件 ========== */
.form-row {
  margin-top: 10px;
}

.form-field {
  display: grid;
  gap: 5px;
  color: var(--text);
  font-size: 12px;
  font-weight: 500;
}

.form-select {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  outline: none;
  font-size: 13px;
  transition: all 0.12s ease;
  box-sizing: border-box;
  cursor: pointer;
}

.form-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

/* ========== 字体选项 ========== */
.font-btn {
  position: relative;
  display: grid;
  min-width: 0;
  min-height: 58px;
  padding: 10px 30px 10px 12px;
  align-content: center;
  gap: 4px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 7px;
  text-align: left;
  cursor: pointer;
  transition: all 0.12s ease;
}

.font-btn:hover {
  border-color: var(--border-strong);
}

.font-btn.selected {
  color: var(--text);
  border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
  background: color-mix(in srgb, var(--accent-soft) 60%, transparent);
}

.font-btn .check-icon {
  position: absolute;
  top: 10px;
  right: 10px;
}

.font-sample {
  overflow: hidden;
  color: var(--text);
  font-size: 18px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.font-name {
  overflow: hidden;
  font-size: 11px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ========== 列表行 - 统一 model-card 风格 ========== */
.list-row {
  display: flex;
  min-height: 50px;
  align-items: center;
  gap: 16px;
  padding: 10px 0;
  border-top: 1px solid var(--border);
}

.list-row:first-child {
  border-top: 0;
}

.form-row + .list-row {
  margin-top: 10px;
}

.list-row__text {
  min-width: 0;
  margin-right: auto;
}

.list-row__text b {
  display: block;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
}

.list-row__text p {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.4;
}

/* ========== 开关 - 精致风格 ========== */
.toggle {
  position: relative;
  display: inline-block;
  flex: 0 0 auto;
  width: 36px;
  height: 20px;
  padding: 0;
  background: var(--border-strong);
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
  transition: transform 0.15s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.toggle.enabled {
  background: var(--accent);
}

.toggle.enabled .toggle-thumb {
  transform: translateX(16px);
}

.toggle:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ========== 步进器 ========== */
.stepper {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: 28px 44px 28px;
  height: 28px;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.stepper-btn {
  display: grid;
  padding: 0;
  place-items: center;
  color: var(--text-muted);
  background: transparent;
  border: none;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.stepper-btn:hover:not(:disabled) {
  color: var(--text);
  background: var(--surface-soft);
}

.stepper-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.stepper-value {
  display: grid;
  place-items: center;
  color: var(--text);
  border-inline: 1px solid var(--border);
  font-size: 12px;
  font-family: var(--font-mono, 'SF Mono', Consolas, monospace);
}

/* ========== 预览框 ========== */
.preview-box {
  margin-top: 12px;
  padding: 12px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  line-height: var(--markdown-line-height, 1.55);
}

.preview-box p {
  margin: 0 0 var(--markdown-paragraph-spacing, 0.72em);
}

.preview-box ul {
  margin: 0 0 var(--markdown-paragraph-spacing, 0.72em);
  padding-left: 1.4em;
}

.preview-box li {
  margin-bottom: var(--markdown-list-item-spacing, 0.28em);
}

.preview-box li:last-child {
  margin-bottom: 0;
}

/* ========== 外观分栏 ========== */
.settings-card--split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 200px;
  gap: 16px;
}

/* ========== 强调色选择 ========== */
.accent-picker {
  display: flex;
  gap: 8px;
}

.accent-dot {
  display: grid;
  width: 26px;
  height: 26px;
  padding: 0;
  place-items: center;
  color: #fff;
  border: 2px solid var(--surface);
  border-radius: 50%;
  box-shadow: 0 0 0 1px var(--border-strong);
  cursor: pointer;
  transition: all 0.12s ease;
}

.accent-dot.selected {
  box-shadow: 0 0 0 2px var(--text);
}

.accent-graphite { background: #30383b; }
.accent-blue { background: #2d6fbe; }
.accent-jade { background: #26745d; }
.accent-coral { background: #aa5146; }

/* ========== 外观预览 ========== */
.appearance-preview {
  display: grid;
  height: 78px;
  grid-template-columns: 40px minmax(0, 1fr);
  overflow: hidden;
  background: var(--app-bg);
  border: 1px solid var(--border);
  border-radius: 7px;
}

.appearance-preview__rail {
  display: flex;
  padding: 10px 8px;
  flex-direction: column;
  gap: 6px;
  background: color-mix(in srgb, var(--surface) 80%, transparent);
  border-right: 1px solid var(--border);
}

.appearance-preview__rail i {
  height: 4px;
  background: var(--text-faint);
  border-radius: 1px;
  opacity: 0.4;
}

.appearance-preview__rail i:first-child {
  background: var(--accent);
  opacity: 1;
}

.appearance-preview__canvas {
  display: grid;
  padding: 12px;
  align-content: start;
  gap: 6px;
  background: color-mix(in srgb, var(--surface) 90%, transparent);
}

.appearance-preview__canvas span {
  width: 42%;
  height: 6px;
  background: var(--text);
  border-radius: 2px;
  opacity: 0.85;
}

.appearance-preview__canvas b {
  width: 84%;
  height: 4px;
  background: var(--text-faint);
  border-radius: 1px;
  opacity: 0.4;
}

.appearance-preview__canvas b:nth-child(3) {
  width: 66%;
}

.appearance-preview__canvas em {
  width: 32px;
  height: 14px;
  margin-top: 2px;
  background: var(--accent);
  border-radius: 3px;
}

/* ========== 连接状态行 ========== */
.integration-row {
  display: flex;
  min-height: 48px;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--border);
}

.integration-row:first-child {
  border-top: 0;
}

.integration-icon {
  display: grid;
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  place-items: center;
  color: var(--accent);
  background: transparent;
}

.integration-icon svg {
  width: 16px;
  height: 16px;
}

.integration-text {
  min-width: 0;
  margin-right: auto;
}

.integration-text b {
  display: block;
  color: var(--text);
  font-size: 15px;
  font-weight: 500;
}

.integration-text p {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 13px;
}

.status-badge {
  color: var(--text-faint);
  font-size: 13px;
  font-style: normal;
  font-weight: 500;
}

.status-badge--online {
  color: #10b981;
}

/* ========== CC Switch ========== */
.ccswitch-section {
  margin-top: 10px;
}

.ccswitch-hint {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.ccswitch-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ccswitch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  color: var(--text);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
  font: inherit;
}

.ccswitch-item:hover:not(:disabled) {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.ccswitch-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ccswitch-name {
  font-weight: 500;
}

.spin {
  animation: spin 0.8s linear infinite;
}

/* ========== 关于页面 ========== */
.settings-card--about {
  padding: 0;
  overflow: hidden;
}

.about-header {
  display: flex;
  min-height: 92px;
  padding: 18px;
  align-items: center;
  gap: 12px;
  background: color-mix(in srgb, var(--surface-soft) 60%, transparent);
  border-bottom: 1px solid var(--border);
  border-radius: 8px 8px 0 0;
  margin: -14px -14px 0;
}

.about-logo {
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  color: inherit;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.about-header h3 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  font-weight: 600;
}

.about-header p {
  margin: 3px 0 0;
  color: var(--text-faint);
  font-size: 12px;
}

.about-list {
  margin: 0;
  padding: 4px 0 0;
}

.about-row {
  display: grid;
  min-height: 48px;
  grid-template-columns: 90px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--border);
}

.about-row:first-child {
  border-top: 0;
}

.about-row dt {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
}

.about-row dd {
  min-width: 0;
  margin: 0;
  color: var(--text);
}

.about-row code {
  color: var(--text);
  font-family: var(--font-mono, 'SF Mono', Consolas, monospace);
  font-size: 12px;
}

.link-btn {
  display: inline-flex;
  max-width: 100%;
  min-height: 28px;
  padding: 0 8px;
  align-items: center;
  gap: 6px;
  color: var(--text);
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 5px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
}

.link-btn:hover {
  background: color-mix(in srgb, var(--border) 30%, var(--surface-soft));
  border-color: var(--border-strong);
}

.link-btn span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-btn svg:first-child {
  flex: 0 0 auto;
  color: var(--text-muted);
  width: 14px;
  height: 14px;
}

.link-btn svg:last-child {
  flex: 0 0 auto;
  color: var(--text-faint);
  width: 12px;
  height: 12px;
}

/* ========== 错误提示 - 统一 model-error 风格 ========== */
.form-error {
  margin: 8px 0 0;
  padding: 7px 9px;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}

/* ========== 暗色主题适配（跟随应用内主题设置，而非操作系统偏好） ========== */
:global([data-app-theme="dark"] .settings-backdrop){
  background: rgba(0, 0, 0, 0.6);
}

:global([data-app-theme="dark"] .wallpaper-preview){
  border-color: rgba(255, 255, 255, 0.08);
  background: #2a2f31;
}

/* ========== 响应式 ========== */
@media (max-width: 760px) {
  .settings-backdrop {
    padding: 12px;
  }
  
  .settings-dialog {
    width: 100%;
    height: min(760px, 94vh);
    min-height: 0;
    border-radius: 8px;
  }
  
  .settings-dialog__body {
    grid-template-columns: 52px minmax(0, 1fr);
  }
  
  .settings-dialog__nav {
    padding-inline: 6px;
  }
  
  .nav-item {
    justify-content: center;
    padding: 0;
    min-height: 36px;
  }
  
  .nav-item span,
  .settings-dialog__nav-foot {
    display: none;
  }
  
  .settings-dialog__content {
    padding: 16px 16px 24px;
  }
  
  .option-grid--4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  
  .custom-wallpaper {
    grid-template-columns: 64px minmax(0, 1fr);
  }
  
  .custom-wallpaper__preview {
    width: 64px;
  }
  
  .custom-wallpaper__actions {
    grid-column: 1 / -1;
  }
  
  .settings-card--split {
    grid-template-columns: 1fr;
  }
  
  .option-grid--3 {
    grid-template-columns: 1fr;
  }
  
  .option-grid--3.font-family-options {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .settings-backdrop,
  .settings-dialog,
  .wallpaper-btn--mist .wallpaper-preview,
  .toggle-thumb,
  .spin {
    animation: none !important;
    transition: none !important;
  }
}
</style>
