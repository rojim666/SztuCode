<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { confirm as confirmDialog, open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  Check, ChevronDown, FolderOpen, Package, Plug, Plus, Power,
  RefreshCw, Search, Settings2, Sparkles, Trash2, X,
} from "@lucide/vue";
import {
  addPluginMarketplace, getPluginCatalog, installCatalogPlugin, installPlugin,
  installSkill, listPlugins, listSkills, refreshPluginMarketplaces,
  removePluginMarketplace, setPluginEnabled, setSkillEnabled, uninstallPlugin,
  type MarketplacePluginSummary, type MarketplaceSummary, type PluginSummary,
  type SkillSummary,
} from "../../services/sztu-runtime";
import { builtInSkillItems } from "../CommandPalette/slash-menu";

const { locale, t } = useI18n({ useScope: "global" });

const props = defineProps<{
  connected: boolean;
  workspaceId?: string | null;
  workspaceName?: string | null;
}>();

type Area = "plugins" | "skills";
type InstallKind = "plugin" | "skill";
type InstallScope = "personal" | "workspace";
type SourceOption = { key: string; label: string; scope: SkillSummary["scope"] };

const activeArea = ref<Area>("plugins");
const query = ref("");
const loading = ref(false);
const error = ref("");
const skills = ref<SkillSummary[]>([]);
const plugins = ref<PluginSummary[]>([]);
const marketplaces = ref<MarketplaceSummary[]>([]);
const catalogPlugins = ref<MarketplacePluginSummary[]>([]);
const pluginMarketplaceSupported = ref(true);
const activeSkillSource = ref("");
const activeMarketplace = ref("all");
const addMenuOpen = ref(false);
const installDialogOpen = ref(false);
const installKind = ref<InstallKind>("skill");
const installScope = ref<InstallScope>("personal");
const installSource = ref("");
const installError = ref("");
const installing = ref(false);
const updatingSkill = ref("");
const updatingPlugin = ref("");
const installingCatalogPlugin = ref("");
const pluginManageOpen = ref(false);
const marketplaceDialogOpen = ref(false);
const marketplaceSourceInput = ref<HTMLInputElement | null>(null);
const marketplaceSource = ref("");
const marketplaceGitRef = ref("");
const marketplaceSparsePaths = ref("");
const marketplaceError = ref("");
const addingMarketplace = ref(false);
const refreshingMarketplaces = ref(false);

const title = computed(() => activeArea.value === "plugins" ? "插件" : "技能");
const subtitle = computed(() => activeArea.value === "plugins"
  ? "在常用工具中扩展 SztuCode 的能力"
  : "通过任务专用技能扩展 SztuCode 的能力");
const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase());

const sourceOptions = computed<SourceOption[]>(() => {
  const options = new Map<string, SourceOption>();
  for (const skill of skills.value) {
    let label = skill.source;
    if (skill.plugin) label = skill.plugin;
    else if (skill.source === "project") label = props.workspaceName || t("skills.currentProject");
    else if (skill.source === "user") label = t("skills.personal");
    else if (skill.source === "builtin") label = t("skills.systemSource");
    options.set(skill.source, { key: skill.source, label, scope: skill.scope });
  }
  const rank = { workspace: 0, personal: 1, system: 2 } as const;
  return [...options.values()].sort((left, right) => rank[left.scope] - rank[right.scope] || left.label.localeCompare(right.label));
});

const matchingSkills = computed(() => {
  const value = normalizedQuery.value;
  return skills.value.filter((skill) => !value || `${skill.display_name} ${skill.name} ${skill.short_description} ${skill.description} ${skill.plugin ?? ""}`.toLocaleLowerCase().includes(value));
});
const installedSkills = computed(() => matchingSkills.value.filter((skill) => skill.enabled));
const visibleInstalledSkills = computed(() => installedSkills.value.slice(0, 6));
const remainingInstalled = computed(() => Math.max(0, installedSkills.value.length - visibleInstalledSkills.value.length));
const catalogSkills = computed(() => matchingSkills.value.filter((skill) => !activeSkillSource.value || skill.source === activeSkillSource.value));
const visibleInstalledPlugins = computed(() => {
  const value = normalizedQuery.value;
  return plugins.value.filter((plugin) => !value || `${plugin.display_name} ${plugin.name} ${plugin.description} ${plugin.skills.join(" ")}`.toLocaleLowerCase().includes(value));
});
const visibleCatalogPlugins = computed(() => {
  const value = normalizedQuery.value;
  return catalogPlugins.value.filter((plugin) => (activeMarketplace.value === "all" || plugin.marketplace_id === activeMarketplace.value)
    && plugin.installation !== "NOT_AVAILABLE"
    && (!value || `${plugin.display_name} ${plugin.name} ${plugin.description} ${plugin.category} ${plugin.publisher}`.toLocaleLowerCase().includes(value)));
});
const activeMarketplaceName = computed(() => activeMarketplace.value === "all"
  ? "全部插件"
  : marketplaces.value.find((item) => item.id === activeMarketplace.value)?.display_name ?? "插件市场");
const activeMarketplaceInfo = computed(() => marketplaces.value.find((item) => item.id === activeMarketplace.value) ?? null);

function initials(name: string): string {
  return name.split(/[-_\s/]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "S";
}

function fallbackColor(name: string): string {
  const colors = ["#24282e", "#7867d9", "#1d8f6f", "#d36b44", "#307bc4", "#a27a20"];
  return colors[[...name].reduce((sum, item) => sum + (item.codePointAt(0) ?? 0), 0) % colors.length];
}

function skillStyle(skill: SkillSummary): Record<string, string> {
  return { "--skill-color": skill.brand_color || fallbackColor(skill.name) };
}

function skillDescription(skill: SkillSummary): string {
  return skill.short_description || skill.description || t("skills.fallbackSkillDesc");
}

function pluginDescription(plugin: PluginSummary): string {
  if (plugin.description) return plugin.description;
  if (plugin.skills.length) return t("skills.pluginSkillsDesc", { n: plugin.skills.length, skills: plugin.skills.slice(0, 3).join(locale.value === "zh-CN" ? "、" : ", ") });
  return t("skills.localPluginDesc");
}

async function refreshCatalog(): Promise<void> {
  if (!props.connected) {
    // 离线时展示内建技能目录（与斜杠命令菜单的内建目录一致），连接本地服务后由运行时技能列表替换。
    skills.value = builtInSkillItems((key) => t(key)).map((skill, index) => ({
      id: `builtin-${index}`,
      name: skill.name,
      display_name: skill.name,
      description: skill.description,
      short_description: skill.description,
      source: "builtin",
      scope: "system" as const,
      path: "",
      enabled: true,
      allow_implicit_invocation: false,
    }));
    plugins.value = [];
    marketplaces.value = [];
    catalogPlugins.value = [];
    pluginMarketplaceSupported.value = true;
    error.value = "";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const [nextSkills, nextPlugins, nextCatalog] = await Promise.all([
      listSkills(props.workspaceId),
      listPlugins(props.workspaceId),
      getPluginCatalog(props.workspaceId),
    ]);
    // 内建技能始终在目录中（与斜杠命令菜单一致）；同名技能以运行时版本为准
    const mergedSkills = new Map(nextSkills.map((skill) => [skill.name.toLocaleLowerCase(), skill]));
    for (const skill of builtInSkillItems((key) => t(key))) {
      if (mergedSkills.has(skill.name.toLocaleLowerCase())) continue;
      mergedSkills.set(skill.name.toLocaleLowerCase(), {
        id: `builtin-${skill.name}`,
        name: skill.name,
        display_name: skill.name,
        description: skill.description,
        short_description: skill.description,
        source: "builtin",
        scope: "system" as const,
        path: "",
        enabled: true,
        allow_implicit_invocation: false,
      });
    }
    skills.value = [...mergedSkills.values()];
    plugins.value = nextPlugins;
    marketplaces.value = nextCatalog.marketplaces;
    catalogPlugins.value = nextCatalog.plugins;
    pluginMarketplaceSupported.value = nextCatalog.supported;
    if (!nextCatalog.supported) {
      error.value = "本地服务版本过旧，不支持插件市场。请完全退出旧的 SztuCode daemon 后重新打开客户端。";
    }
    const sources = new Set(nextSkills.map((skill) => skill.source));
    if (!activeSkillSource.value || !sources.has(activeSkillSource.value)) {
      activeSkillSource.value = sourceOptions.value[0]?.key ?? "";
    }
    if (activeMarketplace.value !== "all" && !nextCatalog.marketplaces.some((item) => item.id === activeMarketplace.value)) {
      activeMarketplace.value = "all";
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("skills.catalogLoadFailed");
  } finally {
    loading.value = false;
  }
}

async function toggleSkill(skill: SkillSummary): Promise<void> {
  updatingSkill.value = skill.id;
  error.value = "";
  try {
    const updated = await setSkillEnabled(skill.id, !skill.enabled, props.workspaceId);
    skills.value = skills.value.map((item) => item.id === updated.id ? updated : item);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "技能状态更新失败";
  } finally {
    updatingSkill.value = "";
  }
}

async function togglePlugin(plugin: PluginSummary): Promise<void> {
  updatingPlugin.value = plugin.id;
  error.value = "";
  try {
    const updated = await setPluginEnabled(plugin.id, !plugin.enabled, props.workspaceId);
    plugins.value = plugins.value.map((item) => item.id === updated.id ? updated : item);
    await refreshCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "插件状态更新失败";
  } finally {
    updatingPlugin.value = "";
  }
}

async function installFromCatalog(plugin: MarketplacePluginSummary): Promise<void> {
  installingCatalogPlugin.value = plugin.id;
  error.value = "";
  try {
    const scope: InstallScope = props.workspaceId ? "workspace" : "personal";
    await installCatalogPlugin(plugin.id, scope, props.workspaceId);
    await refreshCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("skills.marketInstallFailed");
  } finally {
    installingCatalogPlugin.value = "";
  }
}

async function removeInstalledPlugin(plugin: PluginSummary): Promise<void> {
  const confirmed = await confirmDialog(`卸载“${plugin.display_name || plugin.name}”？捆绑技能将不再可用。`, { title: "卸载插件", kind: "warning" });
  if (!confirmed) return;
  updatingPlugin.value = plugin.id;
  try {
    await uninstallPlugin(plugin.id, props.workspaceId);
    await refreshCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "插件卸载失败";
  } finally {
    updatingPlugin.value = "";
  }
}

function openMarketplaceDialog(): void {
  addMenuOpen.value = false;
  if (!pluginMarketplaceSupported.value) {
    error.value = "本地服务版本过旧，不支持插件市场。请完全退出旧的 SztuCode daemon 后重新打开客户端。";
    return;
  }
  marketplaceSource.value = "";
  marketplaceGitRef.value = "";
  marketplaceSparsePaths.value = "";
  marketplaceError.value = "";
  marketplaceDialogOpen.value = true;
  void nextTick(() => marketplaceSourceInput.value?.focus());
}

async function submitMarketplace(): Promise<void> {
  const source = marketplaceSource.value.trim();
  if (!source) return;
  addingMarketplace.value = true;
  marketplaceError.value = "";
  try {
    const sparsePaths = marketplaceSparsePaths.value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
    const added = await addPluginMarketplace(source, marketplaceGitRef.value.trim(), sparsePaths, props.workspaceId);
    marketplaceDialogOpen.value = false;
    activeMarketplace.value = added.id;
    await refreshCatalog();
  } catch (reason) {
    marketplaceError.value = reason instanceof Error ? reason.message : "添加插件市场失败";
  } finally {
    addingMarketplace.value = false;
  }
}

async function refreshMarketplaces(): Promise<void> {
  refreshingMarketplaces.value = true;
  error.value = "";
  try {
    await refreshPluginMarketplaces(null, props.workspaceId);
    await refreshCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("skills.marketplaceRefreshFailed");
  } finally {
    refreshingMarketplaces.value = false;
  }
}

async function removeMarketplace(marketplace: MarketplaceSummary): Promise<void> {
  const confirmed = await confirmDialog(t("skills.removeMarketConfirm", { name: marketplace.display_name }), { title: t("skills.removeMarketTitle"), kind: "warning" });
  if (!confirmed) return;
  try {
    await removePluginMarketplace(marketplace.id, props.workspaceId);
    activeMarketplace.value = "all";
    await refreshCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("skills.marketplaceRemoveFailed");
  }
}

function openInstall(kind: InstallKind): void {
  installKind.value = kind;
  installScope.value = props.workspaceId ? "workspace" : "personal";
  installSource.value = "";
  installError.value = "";
  addMenuOpen.value = false;
  installDialogOpen.value = true;
}

async function browseInstallSource(): Promise<void> {
  try {
    const selected = await openDialog({ directory: true, multiple: false, title: installKind.value === "plugin" ? "选择插件目录" : "选择技能目录" });
    if (typeof selected === "string") installSource.value = selected;
  } catch (reason) {
    installError.value = reason instanceof Error ? reason.message : "无法打开目录选择器";
  }
}

async function submitInstall(): Promise<void> {
  const source = installSource.value.trim();
  if (!source) return;
  installing.value = true;
  installError.value = "";
  try {
    if (installKind.value === "skill") await installSkill(source, installScope.value, props.workspaceId);
    else await installPlugin(source, installScope.value, props.workspaceId);
    installDialogOpen.value = false;
    await refreshCatalog();
    activeArea.value = installKind.value === "skill" ? "skills" : "plugins";
  } catch (reason) {
    installError.value = reason instanceof Error ? reason.message : t("skills.installFailed");
  } finally {
    installing.value = false;
  }
}

watch(() => [props.workspaceId, props.connected], () => void refreshCatalog());
watch(activeArea, () => { query.value = ""; addMenuOpen.value = false; });
onMounted(() => void refreshCatalog());
</script>

<template>
  <section class="skill-center" :aria-label="t('skills.sectionAria')">
    <header class="skill-center__topbar">
      <nav :aria-label="t('skills.navAria')">
        <button :class="{ active: activeArea === 'plugins' }" @click="activeArea = 'plugins'">{{ t("skills.pluginsTab") }}</button>
        <button :class="{ active: activeArea === 'skills' }" @click="activeArea = 'skills'">{{ t("skills.skillsTab") }}</button>
      </nav>
      <div class="skill-center__actions">
        <button :title="t('skills.refresh')" :aria-label="t('skills.refresh')" :disabled="loading" @click="refreshCatalog"><RefreshCw :size="18" :class="{ spin: loading }" /></button>
        <button :title="activeArea === 'plugins' ? t('skills.managePlugins') : t('skills.skillSettings')" :aria-label="activeArea === 'plugins' ? t('skills.managePlugins') : t('skills.skillSettings')" :disabled="activeArea !== 'plugins'" @click="pluginManageOpen = true"><Settings2 :size="18" /></button>
        <div class="skill-add">
          <button class="skill-add__trigger" :aria-expanded="addMenuOpen" @click="addMenuOpen = !addMenuOpen"><span>{{ t("skills.add") }}</span><ChevronDown :size="15" /></button>
          <div v-if="addMenuOpen" class="skill-add__menu">
            <button @click="openMarketplaceDialog"><Package :size="15" /><span><b>{{ t("skills.addMarketplace") }}</b><small>{{ t("skills.addMarketplaceHint") }}</small></span></button>
            <button @click="openInstall('plugin')"><Plug :size="15" /><span><b>{{ t("skills.installPluginLocal") }}</b><small>{{ t("skills.installPluginLocalHint") }}</small></span></button>
            <button @click="openInstall('skill')"><Sparkles :size="15" /><span><b>{{ t("skills.addSkill") }}</b><small>{{ t("skills.addSkillHint") }}</small></span></button>
          </div>
        </div>
      </div>
    </header>

    <main class="skill-center__body">
      <header class="skill-page-heading">
        <h1>{{ title }}</h1>
        <p>{{ subtitle }}</p>
      </header>

      <label class="skill-search">
        <Search :size="18" />
        <input v-model="query" :placeholder="activeArea === 'plugins' ? t('skills.searchPlugins') : t('skills.searchSkills')" />
      </label>

      <p v-if="error" class="skill-runtime-error" role="alert">{{ error }}<button @click="refreshCatalog">{{ t("skills.retry") }}</button></p>

      <template v-if="activeArea === 'skills'">
        <section class="installed-section" aria-labelledby="installed-skills-title">
          <h2 id="installed-skills-title">{{ t("skills.installed") }}</h2>
          <div v-if="visibleInstalledSkills.length" class="capability-list capability-list--installed">
            <article v-for="skill in visibleInstalledSkills" :key="skill.id" class="capability-row">
              <span class="capability-icon" :style="skillStyle(skill)">{{ initials(skill.display_name) }}</span>
              <span class="capability-copy"><b>{{ skill.display_name }}</b><small>{{ skillDescription(skill) }}</small></span>
              <Check :size="18" class="installed-check" />
            </article>
          </div>
          <p v-else-if="!loading" class="section-empty">{{ t("skills.noEnabledSkills") }}</p>
          <p v-if="remainingInstalled" class="installed-more">{{ t("skills.moreInstalled", { n: remainingInstalled }) }}</p>
        </section>

        <nav v-if="sourceOptions.length" class="source-tabs" :aria-label="t('skills.sourceAria')">
          <button v-for="source in sourceOptions" :key="source.key" :class="{ active: activeSkillSource === source.key }" @click="activeSkillSource = source.key">{{ source.label }}</button>
        </nav>

        <section class="catalog-section" :aria-label="t('skills.catalogAria')">
          <div v-if="catalogSkills.length" class="capability-list">
            <article v-for="skill in catalogSkills" :key="skill.id" class="capability-row" :class="{ disabled: !skill.enabled }">
              <span class="capability-icon" :style="skillStyle(skill)">{{ initials(skill.display_name) }}</span>
              <span class="capability-copy"><b>{{ skill.display_name }}</b><small>{{ skillDescription(skill) }}</small><em v-if="skill.plugin">{{ skill.plugin }}</em></span>
              <button class="skill-state" :class="{ enabled: skill.enabled }" :disabled="updatingSkill === skill.id" :title="skill.enabled ? t('skills.disableSkill') : t('skills.enableSkill')" @click="toggleSkill(skill)">
                <RefreshCw v-if="updatingSkill === skill.id" :size="16" class="spin" />
                <Check v-else-if="skill.enabled" :size="18" />
                <Power v-else :size="16" />
              </button>
            </article>
          </div>
          <p v-else-if="!loading" class="section-empty">{{ t("skills.noMatchSkills") }}</p>
        </section>
      </template>

      <template v-else>
        <section class="plugin-installed-strip" aria-labelledby="installed-plugins-title">
          <header><h2 id="installed-plugins-title">{{ t("skills.installed") }}</h2><button class="plugin-manage-trigger" @click="pluginManageOpen = true"><Settings2 :size="16" />{{ t("skills.manage") }}</button></header>
          <div v-if="plugins.length" class="plugin-icons">
            <button v-for="plugin in plugins.slice(0, 9)" :key="plugin.id" :title="t('skills.pluginState', { name: plugin.display_name, state: plugin.enabled ? t('skills.enabledState') : t('skills.disabledState') })" :class="{ disabled: !plugin.enabled }" :style="{ '--plugin-color': plugin.brand_color || fallbackColor(plugin.name) }" @click="pluginManageOpen = true"><Plug :size="19" /></button>
          </div>
          <p v-else-if="!loading" class="section-empty">{{ t("skills.noLocalPlugins") }}</p>
        </section>

        <div class="marketplace-toolbar">
          <nav class="source-tabs plugin-source-tabs" :aria-label="t('skills.marketAria')">
            <button :class="{ active: activeMarketplace === 'all' }" @click="activeMarketplace = 'all'">{{ t("skills.all") }}</button>
            <button v-for="marketplace in marketplaces" :key="marketplace.id" :class="{ active: activeMarketplace === marketplace.id }" :title="marketplace.source" @click="activeMarketplace = marketplace.id">{{ marketplace.display_name }}</button>
          </nav>
          <div class="marketplace-toolbar__actions">
            <button :title="t('skills.refreshMarketplace')" :disabled="refreshingMarketplaces || !marketplaces.some((item) => item.updatable)" @click="refreshMarketplaces"><RefreshCw :size="15" :class="{ spin: refreshingMarketplaces }" /></button>
            <button v-if="activeMarketplaceInfo?.removable" :title="t('skills.removeMarketplace')" @click="removeMarketplace(activeMarketplaceInfo)"><Trash2 :size="15" /></button>
            <button :title="t('skills.addMarketplace')" @click="openMarketplaceDialog"><Plus :size="16" /></button>
          </div>
        </div>

        <section class="catalog-section plugin-catalog" :aria-label="t('skills.catalogAria')">
          <header><h2>{{ activeMarketplaceName }}</h2><small v-if="activeMarketplaceInfo">{{ t("skills.pluginCount", { n: activeMarketplaceInfo.plugin_count }) }}</small></header>
          <div v-if="visibleCatalogPlugins.length" class="capability-list">
            <article v-for="plugin in visibleCatalogPlugins" :key="plugin.id" class="capability-row plugin-row marketplace-plugin-row">
              <span class="capability-icon plugin-icon" :style="{ '--skill-color': fallbackColor(plugin.name) }"><Package :size="18" /></span>
              <span class="capability-copy"><b>{{ plugin.display_name }}<em v-if="plugin.version">{{ plugin.version }}</em></b><small>{{ plugin.description || t('skills.codexPlugin') }}</small><em>{{ plugin.marketplace_name }}<template v-if="plugin.publisher"> · {{ plugin.publisher }}</template><template v-if="plugin.category"> · {{ plugin.category }}</template></em></span>
              <span v-if="plugin.installed" class="catalog-installed"><Check :size="15" />{{ t("skills.installed") }}</span>
              <button v-else class="catalog-install" :disabled="installingCatalogPlugin === plugin.id" @click="installFromCatalog(plugin)"><RefreshCw v-if="installingCatalogPlugin === plugin.id" :size="14" class="spin" /><Plus v-else :size="14" />{{ installingCatalogPlugin === plugin.id ? t('skills.installing') : t('skills.install') }}</button>
            </article>
          </div>
          <div v-else-if="!loading" class="plugin-empty">
            <Plug :size="22" /><b>{{ marketplaces.length ? t('skills.emptyMarketTitle') : t('skills.noMarketTitle') }}</b><p>{{ marketplaces.length ? t('skills.emptyMarketHint') : t('skills.noMarketHint') }}</p><button @click="openMarketplaceDialog"><Plus :size="14" />{{ t("skills.addMarketplace") }}</button>
          </div>
        </section>
      </template>
    </main>

    <div v-if="installDialogOpen" class="skill-dialog-backdrop" @mousedown.self="installDialogOpen = false">
      <form class="skill-dialog" role="dialog" aria-modal="true" aria-labelledby="install-title" @submit.prevent="submitInstall">
        <header><div><h2 id="install-title">{{ installKind === 'plugin' ? t('skills.addPlugin') : t('skills.addSkill') }}</h2><p>{{ installKind === 'plugin' ? t('skills.installPluginDesc') : t('skills.installSkillDesc') }}</p></div><button type="button" :aria-label="t('skills.close')" @click="installDialogOpen = false"><X :size="17" /></button></header>
        <label>{{ t("skills.installLocation") }}<select v-model="installScope"><option value="personal">{{ t("skills.personal") }}</option><option value="workspace" :disabled="!workspaceId">{{ t("skills.currentWorkspace") }}{{ workspaceName ? ` · ${workspaceName}` : '' }}</option></select></label>
        <label>{{ t("skills.localSource") }}<div class="source-path-input"><input v-model="installSource" autofocus :placeholder="t('skills.sourcePlaceholder')" /><button type="button" @click="browseInstallSource"><FolderOpen :size="15" />{{ t("skills.browse") }}</button></div></label>
        <p v-if="installError" class="install-error">{{ installError }}</p>
        <footer><button type="button" @click="installDialogOpen = false">{{ t("skills.cancel") }}</button><button class="primary" :disabled="!installSource.trim() || installing">{{ installing ? t('skills.installingDots') : t('skills.installNow') }}</button></footer>
      </form>
    </div>

    <div v-if="marketplaceDialogOpen" class="skill-dialog-backdrop marketplace-backdrop" @mousedown.self="marketplaceDialogOpen = false">
      <form class="skill-dialog marketplace-dialog" role="dialog" aria-modal="true" aria-labelledby="marketplace-title" @submit.prevent="submitMarketplace">
        <header><div><h2 id="marketplace-title">{{ t("skills.marketplaceTitle") }}</h2><p>{{ t("skills.marketplaceDesc") }} <a href="https://developers.openai.com/plugins/build/plugins" target="_blank" rel="noreferrer">{{ t("skills.learnMore") }}</a></p></div><button type="button" :aria-label="t('skills.close')" @click="marketplaceDialogOpen = false"><X :size="19" /></button></header>
        <label>{{ t("skills.sourceLabel") }}<input ref="marketplaceSourceInput" v-model="marketplaceSource" :placeholder="t('skills.sourceInputPlaceholder')" /></label>
        <label>{{ t("skills.gitRef") }}<input v-model="marketplaceGitRef" :placeholder="t('skills.gitRefPlaceholder')" /></label>
        <label>{{ t("skills.sparsePaths") }}<textarea v-model="marketplaceSparsePaths" rows="4" placeholder="plugins/codex" /></label>
        <p v-if="marketplaceError" class="install-error">{{ marketplaceError }}</p>
        <footer><button type="button" @click="marketplaceDialogOpen = false">{{ t("skills.cancel") }}</button><button class="primary" :disabled="!marketplaceSource.trim() || addingMarketplace">{{ addingMarketplace ? t('skills.addingMarketplace') : t('skills.addMarketplaceBtn') }}</button></footer>
      </form>
    </div>

    <div v-if="pluginManageOpen" class="skill-dialog-backdrop" @mousedown.self="pluginManageOpen = false">
      <section class="skill-dialog plugin-manage-dialog" role="dialog" aria-modal="true" aria-labelledby="plugin-manage-title">
        <header><div><h2 id="plugin-manage-title">{{ t("skills.managePluginsTitle") }}</h2><p>{{ t("skills.managePluginsDesc") }}</p></div><button type="button" :aria-label="t('skills.close')" @click="pluginManageOpen = false"><X :size="17" /></button></header>
        <div v-if="visibleInstalledPlugins.length" class="plugin-manage-list">
          <article v-for="plugin in visibleInstalledPlugins" :key="plugin.id" :class="{ disabled: !plugin.enabled }">
            <span class="plugin-manage-icon" :style="{ '--plugin-color': plugin.brand_color || fallbackColor(plugin.name) }"><Plug :size="17" /></span>
            <span><b>{{ plugin.display_name }}</b><small>{{ pluginDescription(plugin) }}</small><em>{{ plugin.source === 'workspace' ? t('skills.workspaceScope') : t('skills.personal') }}<template v-if="plugin.version"> · {{ plugin.version }}</template></em></span>
            <button class="plugin-toggle" :class="{ enabled: plugin.enabled }" :disabled="updatingPlugin === plugin.id" :title="plugin.enabled ? t('skills.disablePlugin') : t('skills.enablePlugin')" @click="togglePlugin(plugin)"><RefreshCw v-if="updatingPlugin === plugin.id" :size="14" class="spin" /><span v-else /></button>
            <button class="plugin-remove" :disabled="updatingPlugin === plugin.id" :title="t('skills.uninstallPlugin')" @click="removeInstalledPlugin(plugin)"><Trash2 :size="15" /></button>
          </article>
        </div>
        <p v-else class="section-empty">{{ t("skills.noMatchPlugins") }}</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.skill-center button:focus { outline: 0; }
.skill-center button:focus-visible { box-shadow: inset 0 0 0 1px #8e9297; }
.plugin-manage-trigger { display: flex; align-items: center; gap: 5px; padding: 4px 7px; color: #777a7e; background: transparent; border: 0; border-radius: 6px; font-size: 11px; }
.plugin-manage-trigger:hover { color: #292b2e; background: #f3f3f3; }
.plugin-icons button { display: grid; width: 46px; height: 46px; padding: 0; place-items: center; color: #fff; background: var(--plugin-color, #333); border: 0; border-radius: 11px; box-shadow: inset 0 0 0 1px #ffffff26, 0 2px 5px #00000012; }
.plugin-icons button:hover { transform: translateY(-1px); box-shadow: inset 0 0 0 1px #ffffff26, 0 5px 12px #0000001c; }
.plugin-icons button.disabled { opacity: .42; filter: grayscale(.45); }
.marketplace-toolbar { display: flex; margin-top: 38px; align-items: end; justify-content: space-between; gap: 14px; }
.marketplace-toolbar .source-tabs { min-width: 0; margin-top: 0; }
.marketplace-toolbar__actions { display: flex; flex: none; gap: 4px; }
.marketplace-toolbar__actions button { display: grid; width: 31px; height: 31px; padding: 0; place-items: center; color: #777a7e; background: #f5f5f5; border: 1px solid #e8e8e8; border-radius: 8px; }
.marketplace-toolbar__actions button:hover:not(:disabled) { color: #25272a; background: #ededed; }
.marketplace-toolbar__actions button:disabled { opacity: .38; }
.plugin-catalog > header { display: flex; align-items: baseline; justify-content: space-between; }
.plugin-catalog > header small { color: #a1a3a7; font-size: 11px; }
.marketplace-plugin-row { grid-template-columns: 50px minmax(0, 1fr) auto; }
.catalog-install { display: flex; height: 31px; padding: 0 10px; align-items: center; gap: 4px; color: #34363a; background: #f1f2f3; border: 1px solid #e1e2e3; border-radius: 8px; font-size: 12px; }
.catalog-install:hover:not(:disabled) { background: #e8e9ea; }
.catalog-install:disabled { opacity: .55; }
.catalog-installed { display: flex; align-items: center; gap: 4px; color: #8d9094; font-size: 11px; white-space: nowrap; }
.marketplace-dialog { width: min(520px, 100%); padding: 28px 30px 30px; border-radius: 20px; }
.marketplace-dialog > header { margin-bottom: 22px; }
.marketplace-dialog > header h2 { font-size: 20px; letter-spacing: -.25px; }
.marketplace-dialog > header p { display: flex; align-items: center; flex-wrap: wrap; gap: 3px; margin-top: 7px; font-size: 13px; }
.marketplace-dialog > header p a { display: inline-flex; align-items: center; gap: 3px; color: #1683ef; text-decoration: none; }
.marketplace-dialog > header p a:hover { color: #006bd6; }
.marketplace-dialog > header > button { color: #55585c; background: transparent; }
.marketplace-dialog > header > button:hover { background: #f2f2f2; }
.marketplace-dialog > label { margin-top: 16px; gap: 8px; color: #73767a; font-size: 13px; }
.marketplace-dialog input { height: 43px; padding-inline: 12px; background: #fff; border-color: #dcdddf; border-radius: 8px; font-size: 14px; }
.marketplace-dialog textarea { min-height: 88px; padding: 11px 12px; resize: vertical; color: #303236; background: #fff; border: 1px solid #dcdddf; border-radius: 8px; outline: 0; font: inherit; font-size: 14px; }
.marketplace-dialog input:focus, .marketplace-dialog textarea:focus { border-color: #1683ef; box-shadow: 0 0 0 1px #1683ef; }
.marketplace-dialog > footer { margin-top: 18px; }
.marketplace-dialog > footer button { height: 40px; padding-inline: 17px; border: 1px solid #e2e3e5; border-radius: 10px; font-size: 13px; }
.marketplace-dialog > footer button.primary { border-color: #24262a; }
.plugin-manage-dialog { width: min(610px, 100%); max-height: min(680px, calc(100vh - 40px)); overflow: auto; }
.plugin-manage-list { display: grid; gap: 4px; }
.plugin-manage-list article { display: grid; min-width: 0; padding: 9px 7px; grid-template-columns: 42px minmax(0, 1fr) 38px 32px; align-items: center; gap: 9px; border-radius: 9px; }
.plugin-manage-list article:hover { background: #f7f7f7; }
.plugin-manage-list article.disabled { opacity: .62; }
.plugin-manage-icon { display: grid; width: 40px; height: 40px; place-items: center; color: #fff; background: var(--plugin-color, #333); border-radius: 9px; }
.plugin-manage-list article > span:nth-child(2) { display: block; min-width: 0; }
.plugin-manage-list b, .plugin-manage-list small, .plugin-manage-list em { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plugin-manage-list b { color: #303236; font-size: 13px; }
.plugin-manage-list small { margin-top: 3px; color: #8e9195; font-size: 11px; }
.plugin-manage-list em { margin-top: 3px; color: #b0b2b5; font-size: 9px; font-style: normal; }
.plugin-toggle { display: grid; width: 34px; height: 20px; padding: 2px; align-items: center; justify-items: start; background: #d5d6d8; border: 0; border-radius: 10px; }
.plugin-toggle > span { width: 16px; height: 16px; background: #fff; border-radius: 50%; box-shadow: 0 1px 3px #0003; transition: transform .15s ease; }
.plugin-toggle.enabled { background: #26282b; }
.plugin-toggle.enabled > span { transform: translateX(14px); }
.plugin-remove { display: grid; width: 30px; height: 30px; padding: 0; place-items: center; color: #9a7773; background: transparent; border: 0; border-radius: 7px; }
.plugin-remove:hover { color: #a33d32; background: #fff0ee; }
@media (max-width: 620px) { .marketplace-toolbar { align-items: stretch; flex-direction: column; } .marketplace-toolbar__actions { justify-content: flex-end; } .marketplace-plugin-row { grid-template-columns: 44px minmax(0, 1fr) auto; } .catalog-install { width: 31px; padding: 0; justify-content: center; font-size: 0; } .marketplace-dialog { padding: 23px 20px 22px; } }
</style>
