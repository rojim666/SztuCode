<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { confirm as confirmDialog, open as openDialog } from "@tauri-apps/plugin-dialog";
import AppIcon from "../icons/AppIcon.vue";
import PluginIcon from "./PluginIcon.vue";
import SkillIcon from "./SkillIcon.vue";
import {
  addPluginMarketplace, getPluginCatalog, installCatalogPlugin, installPlugin,
  installSkill, listPlugins, listSkills, refreshPluginMarketplaces,
  removePluginMarketplace, setPluginEnabled, uninstallPlugin, uninstallSkill,
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
type PluginView = "installed" | "marketplace";
type InstallKind = "plugin" | "skill";
type InstallScope = "personal" | "workspace";
type SourceOption = { key: string; label: string; scope: SkillSummary["scope"] };
type UnifiedPluginItem = {
  id: string;
  name: string;
  display_name: string;
  description: string;
  version: string;
  installed: boolean;
  enabled?: boolean;
  isLocal?: boolean;
  source?: PluginSummary["source"];
  marketplace_id?: string;
  marketplace_name?: string;
  category?: string;
  publisher?: string;
  isCatalog?: boolean;
};

const activeArea = ref<Area>("plugins");
const activePluginView = ref<PluginView>("installed");
const rootEl = ref<HTMLElement | null>(null);
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
const pluginDetailOpen = ref(false);
const selectedPlugin = ref<PluginSummary | null>(null);
const skillDetailOpen = ref(false);
const selectedSkill = ref<SkillSummary | null>(null);
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

function owningPlugin(skill: SkillSummary): PluginSummary | undefined {
  const scope = skill.scope === "system" ? "builtin" : skill.scope;
  return plugins.value.find((plugin) => plugin.name === skill.plugin && plugin.source === scope);
}
function pluginLabel(skill: SkillSummary): string {
  return owningPlugin(skill)?.display_name || skill.plugin || "";
}
function showPluginSkills(plugin: PluginSummary): void {
  pluginDetailOpen.value = false;
  query.value = "";
  activeSkillSource.value = `${plugin.source === "builtin" ? "builtin" : plugin.source === "personal" ? "user" : "project"}-plugin:${plugin.name}`;
  activeArea.value = "skills";
}

function openPluginDetail(plugin: PluginSummary): void {
  selectedPlugin.value = plugin;
  pluginDetailOpen.value = true;
}

function openSkillDetail(skill: SkillSummary): void {
  selectedSkill.value = skill;
  skillDetailOpen.value = true;
}

function canDeleteSkill(skill: SkillSummary): boolean {
  return !skill.plugin && skill.scope !== "system" && (skill.source === "user" || skill.source === "project");
}

function openUnifiedPluginDetail(item: UnifiedPluginItem): void {
  if (item.isLocal) {
    const localPlugin = plugins.value.find(p => p.id === item.id);
    if (localPlugin) {
      openPluginDetail(localPlugin);
    }
  }
}

function installUnifiedPlugin(item: UnifiedPluginItem): void {
  if (item.isCatalog) {
    const catalogPlugin = catalogPlugins.value.find(p => p.id === item.id);
    if (catalogPlugin) {
      installFromCatalog(catalogPlugin);
    }
  }
}

function getOriginalPlugin(item: UnifiedPluginItem): PluginSummary | MarketplacePluginSummary | undefined {
  if (item.isLocal) {
    return plugins.value.find(p => p.id === item.id);
  }
  return catalogPlugins.value.find(p => p.id === item.id);
}

function safeHomepage(plugin: PluginSummary): string | undefined {
  try { const url = new URL(plugin.homepage || ""); return url.protocol === "https:" ? url.href : undefined; }
  catch { return undefined; }
}

const sourceOptions = computed<SourceOption[]>(() => {
  const options = new Map<string, SourceOption>();
  for (const skill of skills.value) {
    let label = skill.source;
    if (skill.plugin) label = t("skills.fromPlugin", { name: pluginLabel(skill) });
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
  return skills.value.filter((skill) => !value || `${skill.display_name} ${skill.name} ${skill.short_description} ${skill.description} ${pluginLabel(skill)}`.toLocaleLowerCase().includes(value));
});
const installedSkills = computed(() => matchingSkills.value.filter((skill) => skill.enabled));
const visibleInstalledSkills = computed(() => installedSkills.value.slice(0, 6));
const remainingInstalled = computed(() => Math.max(0, installedSkills.value.length - visibleInstalledSkills.value.length));
const catalogSkills = computed(() => matchingSkills.value.filter((skill) => !activeSkillSource.value || skill.source === activeSkillSource.value));

const currentSkillList = computed(() => {
  if (activeSkillSource.value === "") {
    // "已启用"标签：显示所有已启用技能
    return installedSkills.value;
  }
  return catalogSkills.value;
});
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

// 合并已安装和市场插件用于"全部"视图
const allPlugins = computed<UnifiedPluginItem[]>(() => {
  const value = normalizedQuery.value;
  // 已安装插件
  const localItems: UnifiedPluginItem[] = plugins.value
    .filter((plugin) => !value || `${plugin.display_name} ${plugin.name} ${plugin.description} ${plugin.skills.join(" ")}`.toLocaleLowerCase().includes(value))
    .map((plugin) => ({
      id: plugin.id,
      name: plugin.name,
      display_name: plugin.display_name,
      description: pluginDescription(plugin),
      version: plugin.version,
      installed: true,
      enabled: plugin.enabled,
      isLocal: true,
      source: plugin.source,
      publisher: plugin.publisher,
    }));

  if (activeMarketplace.value !== "all") {
    // 特定市场只显示该市场的插件（包括已安装和未安装）
    const marketItems = visibleCatalogPlugins.value.map((plugin) => ({
      id: plugin.id,
      name: plugin.name,
      display_name: plugin.display_name,
      description: plugin.description || "插件",
      version: plugin.version,
      installed: plugin.installed,
      marketplace_id: plugin.marketplace_id,
      marketplace_name: plugin.marketplace_name,
      category: plugin.category,
      publisher: plugin.publisher,
      isCatalog: true,
    }));
    // 去重：已安装的优先
    const installedNames = new Set(localItems.map(i => i.name));
    return [...localItems.filter(p => {
      // 检查这个本地插件是否来自当前市场
      const catalogMatch = catalogPlugins.value.find(c => c.name === p.name && c.marketplace_id === activeMarketplace.value);
      return !!catalogMatch;
    }), ...marketItems.filter(p => !installedNames.has(p.name))];
  }

  // "全部"视图：所有已安装 + 市场中未安装的
  const installedNames = new Set(localItems.map(i => i.name));
  const catalogItems: UnifiedPluginItem[] = catalogPlugins.value
    .filter((plugin) => plugin.installation !== "NOT_AVAILABLE"
      && !installedNames.has(plugin.name)
      && (!value || `${plugin.display_name} ${plugin.name} ${plugin.description} ${plugin.category} ${plugin.publisher}`.toLocaleLowerCase().includes(value)))
    .map((plugin) => ({
      id: plugin.id,
      name: plugin.name,
      display_name: plugin.display_name,
      description: plugin.description || "插件",
      version: plugin.version,
      installed: plugin.installed,
      marketplace_id: plugin.marketplace_id,
      marketplace_name: plugin.marketplace_name,
      category: plugin.category,
      publisher: plugin.publisher,
      isCatalog: true,
    }));

  return [...localItems, ...catalogItems];
});

// 当前视图显示的插件列表
const visiblePlugins = computed<UnifiedPluginItem[]>(() => {
  if (activePluginView.value === "installed") {
    // "已安装"标签：显示所有已安装插件（不过滤市场）
    const value = normalizedQuery.value;
    return plugins.value
      .filter((plugin) => !value || `${plugin.display_name} ${plugin.name} ${plugin.description} ${plugin.skills.join(" ")}`.toLocaleLowerCase().includes(value))
      .map((plugin) => ({
        id: plugin.id,
        name: plugin.name,
        display_name: plugin.display_name,
        description: pluginDescription(plugin),
        version: plugin.version,
        installed: true,
        enabled: plugin.enabled,
        isLocal: true,
        source: plugin.source,
        publisher: plugin.publisher,
      }));
  }
  return allPlugins.value;
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
    const sources = new Set(skills.value.map((skill) => skill.source));
    if (activeSkillSource.value && !sources.has(activeSkillSource.value)) {
      activeSkillSource.value = "";
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

async function togglePlugin(plugin: PluginSummary): Promise<void> {
  updatingPlugin.value = plugin.id;
  error.value = "";
  try {
    const updated = await setPluginEnabled(plugin.id, !plugin.enabled, props.workspaceId);
    plugins.value = plugins.value.map((item) => item.id === updated.id ? updated : item);
    if (selectedPlugin.value?.id === updated.id) selectedPlugin.value = updated;
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
  const confirmed = await confirmDialog(`卸载"${plugin.display_name || plugin.name}"？捆绑技能将不再可用。`, { title: "卸载插件", kind: "warning" });
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

async function removeInstalledSkill(skill: SkillSummary): Promise<void> {
  if (!canDeleteSkill(skill)) return;
  const confirmed = await confirmDialog(`删除“${skill.display_name || skill.name}”？此操作将移除该技能的本地文件。`, { title: "删除技能", kind: "warning" });
  if (!confirmed) return;
  updatingSkill.value = skill.id;
  error.value = "";
  try {
    await uninstallSkill(skill.id, props.workspaceId);
    skillDetailOpen.value = false;
    selectedSkill.value = null;
    await refreshCatalog();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "技能删除失败";
  } finally {
    updatingSkill.value = "";
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
    const added = await addPluginMarketplace(source, marketplaceGitRef.value.trim(), [], props.workspaceId);
    marketplaceDialogOpen.value = false;
    addMenuOpen.value = false;
    activeMarketplace.value = added.id;
    activePluginView.value = "marketplace";
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
watch(activeArea, () => { query.value = ""; addMenuOpen.value = false; rootEl.value?.scrollTo({ top: 0 }); });

// 点击外部关闭添加菜单
function handleDocumentClick(e: MouseEvent): void {
  const target = e.target as HTMLElement;
  if (!target.closest('.skill-add')) {
    addMenuOpen.value = false;
  }
}
onMounted(() => {
  void refreshCatalog();
  document.addEventListener('click', handleDocumentClick);
});
onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick);
});
</script>

<template>
  <section ref="rootEl" class="skill-center" :aria-label="t('skills.sectionAria')">
    <header class="skill-center__topbar">
      <nav :aria-label="t('skills.navAria')">
        <button :class="{ active: activeArea === 'plugins' }" @click="activeArea = 'plugins'">{{ t("skills.pluginsTab") }}</button>
        <button :class="{ active: activeArea === 'skills' }" @click="activeArea = 'skills'">{{ t("skills.skillsTab") }}</button>
      </nav>
      <div class="skill-center__actions">
        <button :title="t('skills.refresh')" :aria-label="t('skills.refresh')" :disabled="loading" @click="refreshCatalog"><AppIcon name="RefreshCw" :size="18" :class="{ spin: loading }" /></button>
        <button class="model-picker-settings" :title="activeArea === 'plugins' ? t('skills.managePlugins') : t('skills.skillSettings')" :aria-label="activeArea === 'plugins' ? t('skills.managePlugins') : t('skills.skillSettings')" :disabled="activeArea !== 'plugins'" @click="pluginManageOpen = true"><AppIcon name="Settings" :size="16" /></button>
        <div class="skill-add">
          <button class="skill-add__trigger" :aria-expanded="addMenuOpen" @click.stop="addMenuOpen = !addMenuOpen"><AppIcon name="Plus" :size="14" />{{ t("skills.add") }}</button>
          <div v-if="addMenuOpen" class="skill-add__menu">
            <button @click.stop="openMarketplaceDialog"><AppIcon name="Package" :size="14" />{{ t("skills.addMarketplace") }}</button>
            <button @click.stop="openInstall('plugin')"><AppIcon name="Plug" :size="14" />{{ t("skills.installPluginLocal") }}</button>
            <button @click.stop="openInstall('skill')"><AppIcon name="Sparkles" :size="14" />{{ t("skills.addSkill") }}</button>
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
        <AppIcon name="Search" :size="18" />
        <input v-model="query" :placeholder="activeArea === 'plugins' ? t('skills.searchPlugins') : t('skills.searchSkills')" />
      </label>

      <p v-if="error" class="skill-runtime-error" role="alert">{{ error }}<button @click="refreshCatalog">{{ t("skills.retry") }}</button></p>

      <template v-if="activeArea === 'skills'">
        <section class="skill-section">
          <header class="skill-header">
            <nav class="skill-tabs">
              <button :class="{ active: activeSkillSource === '' }" @click="activeSkillSource = ''">已启用</button>
              <button v-for="source in sourceOptions" :key="source.key" :class="{ active: activeSkillSource === source.key }" @click="activeSkillSource = source.key">{{ source.label }}</button>
            </nav>
            <span class="skill-count">{{ currentSkillList.length }} 个技能</span>
          </header>

          <div v-if="currentSkillList.length" class="skill-grid">
            <button v-for="skill in currentSkillList" :key="skill.id" v-memo="[skill.id, skill.enabled, skill.display_name, skill.name, skill.short_description, skill.description, skill.plugin]" class="skill-card" :class="{ disabled: !skill.enabled }" @click="openSkillDetail(skill)">
              <SkillIcon :name="skill.name" :size="42" />
              <span class="skill-info">
                <span class="skill-name">{{ skill.display_name }}</span>
                <span class="skill-desc">{{ skillDescription(skill) }}</span>
                <em v-if="skill.plugin" class="skill-source">{{ pluginLabel(skill) }}</em>
              </span>
            </button>
          </div>
          <p v-else-if="!loading" class="section-empty">{{ activeSkillSource === '' ? t("skills.noEnabledSkills") : t("skills.noMatchSkills") }}</p>
        </section>
      </template>

      <template v-else>
        <section class="plugin-section">
          <header class="plugin-header">
            <nav class="plugin-tabs">
              <button :class="{ active: activePluginView === 'installed' }" @click="activePluginView = 'installed'">{{ t("skills.installed") }}</button>
              <button :class="{ active: activePluginView === 'marketplace' && activeMarketplace === 'all' }" @click="activePluginView = 'marketplace'; activeMarketplace = 'all'">全部</button>
              <button v-for="marketplace in marketplaces" :key="marketplace.id" :class="{ active: activePluginView === 'marketplace' && activeMarketplace === marketplace.id }" :title="marketplace.source" @click="activePluginView = 'marketplace'; activeMarketplace = marketplace.id">{{ marketplace.display_name }}</button>
            </nav>
            <div class="plugin-header-actions">
              <button v-if="activePluginView === 'marketplace'" :title="t('skills.refreshMarketplace')" :disabled="refreshingMarketplaces || !marketplaces.some((item) => item.updatable)" @click="refreshMarketplaces"><AppIcon name="RefreshCw" :size="14" :class="{ spin: refreshingMarketplaces }" /></button>
              <button v-if="activePluginView === 'marketplace' && activeMarketplaceInfo?.removable" :title="t('skills.removeMarketplace')" @click="removeMarketplace(activeMarketplaceInfo)"><AppIcon name="Trash2" :size="14" /></button>
              <button :title="t('skills.addMarketplace')" @click="openMarketplaceDialog"><AppIcon name="Plus" :size="15" /></button>
              <button class="plugin-manage-trigger" @click="pluginManageOpen = true"><AppIcon name="Settings" :size="14" />{{ t("skills.manage") }}</button>
            </div>
          </header>

          <div v-if="activePluginView === 'installed'">
            <div v-if="visiblePlugins.length" class="plugin-grid">
              <button v-for="plugin in visiblePlugins" :key="plugin.id" v-memo="[plugin.id, plugin.enabled, plugin.display_name, plugin.name, plugin.description]" class="plugin-capsule-card" :class="{ disabled: plugin.enabled === false }" @click="openUnifiedPluginDetail(plugin)">
                <PluginIcon :name="plugin.name" class="capsule-icon" />
                <span class="capsule-info">
                  <span class="capsule-name">{{ plugin.display_name }}</span>
                  <span class="capsule-desc">{{ plugin.description }}</span>
                </span>
                <span v-if="plugin.enabled === false" class="capsule-status">已禁用</span>
                <span v-else class="capsule-status installed-status">已安装</span>
              </button>
            </div>
            <p v-else-if="!loading" class="section-empty">{{ t("skills.noLocalPlugins") }}</p>
          </div>

          <div v-else class="plugin-market">
            <div v-if="visiblePlugins.length" class="plugin-grid">
              <article v-for="plugin in visiblePlugins" :key="plugin.id" v-memo="[plugin.id, plugin.installed, plugin.display_name, plugin.name, plugin.description, plugin.version, plugin.marketplace_name, installingCatalogPlugin === plugin.id]" class="plugin-capsule-card marketplace-capsule" :class="{ clickable: plugin.installed }" @click="plugin.installed && openUnifiedPluginDetail(plugin)">
                <PluginIcon :name="plugin.name" class="capsule-icon" />
                <span class="capsule-info">
                  <span class="capsule-name">
                    {{ plugin.display_name }}
                    <em v-if="plugin.version"> · v{{ plugin.version }}</em>
                    <em v-if="plugin.marketplace_name && activeMarketplace === 'all'" class="market-badge">{{ plugin.marketplace_name }}</em>
                  </span>
                  <span class="capsule-desc">{{ plugin.description }}</span>
                </span>
                <span v-if="plugin.installed" class="catalog-installed-badge" @click.stop="openUnifiedPluginDetail(plugin)"><AppIcon name="Check" :size="12" />已安装</span>
                <button v-else class="catalog-install-btn" :disabled="installingCatalogPlugin === plugin.id" @click.stop="installUnifiedPlugin(plugin)">
                  <AppIcon v-if="installingCatalogPlugin === plugin.id" name="RefreshCw" :size="12" class="spin" />
                  <AppIcon v-else name="Plus" :size="12" />
                  {{ installingCatalogPlugin === plugin.id ? '安装中' : '安装' }}
                </button>
              </article>
            </div>
            <div v-else-if="!loading" class="plugin-empty">
              <AppIcon name="Plug" :size="22" /><b>{{ marketplaces.length ? t('skills.emptyMarketTitle') : t('skills.noMarketTitle') }}</b><p>{{ marketplaces.length ? t('skills.emptyMarketHint') : t('skills.noMarketHint') }}</p><button @click="openMarketplaceDialog"><AppIcon name="Plus" :size="14" />{{ t("skills.addMarketplace") }}</button>
            </div>
          </div>
        </section>
      </template>
    </main>

    <div v-if="installDialogOpen" class="skill-dialog-backdrop" @mousedown.self="installDialogOpen = false">
      <form class="skill-dialog" role="dialog" aria-modal="true" aria-labelledby="install-title" @submit.prevent="submitInstall">
        <header><h2 id="install-title">{{ installKind === 'plugin' ? '本地安装插件' : '本地添加技能' }}</h2><button type="button" :aria-label="t('skills.close')" @click="installDialogOpen = false"><AppIcon name="X" :size="17" /></button></header>
        <label v-if="workspaceId">安装位置<select v-model="installScope"><option value="personal">个人</option><option value="workspace">当前工作区{{ workspaceName ? ` · ${workspaceName}` : '' }}</option></select></label>
        <label>本地路径<div class="source-path-input"><input v-model="installSource" autofocus placeholder="选择插件/技能目录" /><button type="button" @click="browseInstallSource"><AppIcon name="FolderOpen" :size="14" />浏览</button></div></label>
        <p v-if="installError" class="install-error">{{ installError }}</p>
        <footer><button type="button" @click="installDialogOpen = false">取消</button><button class="primary" :disabled="!installSource.trim() || installing">{{ installing ? '安装中...' : '安装' }}</button></footer>
      </form>
    </div>

    <div v-if="marketplaceDialogOpen" class="skill-dialog-backdrop marketplace-backdrop" @mousedown.self="marketplaceDialogOpen = false">
      <form class="skill-dialog marketplace-dialog" role="dialog" aria-modal="true" aria-labelledby="marketplace-title" @submit.prevent="submitMarketplace">
        <header><h2 id="marketplace-title">添加插件市场</h2><button type="button" :aria-label="t('skills.close')" @click="marketplaceDialogOpen = false"><AppIcon name="X" :size="17" /></button></header>
        <label>市场源地址<input ref="marketplaceSourceInput" v-model="marketplaceSource" placeholder="Git 仓库 URL 或本地路径" /></label>
        <label>Git 分支/标签（可选）<input v-model="marketplaceGitRef" placeholder="留空使用默认分支" /></label>
        <p v-if="marketplaceError" class="install-error">{{ marketplaceError }}</p>
        <footer><button type="button" @click="marketplaceDialogOpen = false">取消</button><button class="primary" :disabled="!marketplaceSource.trim() || addingMarketplace">{{ addingMarketplace ? '添加中...' : '添加' }}</button></footer>
      </form>
    </div>

    <div v-if="pluginDetailOpen && selectedPlugin" class="skill-dialog-backdrop" @mousedown.self="pluginDetailOpen = false">
      <section class="skill-dialog plugin-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="plugin-detail-title">
        <header>
          <div class="plugin-detail-header">
            <PluginIcon :name="selectedPlugin.name" class="detail-icon" />
            <div>
              <h2 id="plugin-detail-title">{{ selectedPlugin.display_name }}</h2>
              <p class="detail-meta">
                <span class="detail-origin">{{ selectedPlugin.source === 'builtin' ? t('skills.bundledPlugin') : t('skills.installed') }}</span>
                <template v-if="selectedPlugin.version"> · v{{ selectedPlugin.version }}</template>
              </p>
            </div>
          </div>
          <button type="button" :aria-label="t('skills.close')" @click="pluginDetailOpen = false"><AppIcon name="X" :size="17" /></button>
        </header>
        <div class="plugin-detail-body">
          <p class="detail-desc">{{ pluginDescription(selectedPlugin) }}</p>
          <div v-if="selectedPlugin.publisher || selectedPlugin.license" class="detail-info">
            <span v-if="selectedPlugin.publisher">{{ selectedPlugin.publisher }}</span>
            <span v-if="selectedPlugin.license">{{ selectedPlugin.license }}</span>
          </div>
          <div v-if="selectedPlugin.skills.length" class="detail-skills">
            <h4>包含技能 ({{ selectedPlugin.skills.length }})</h4>
            <div class="skill-tags">
              <span v-for="skill in selectedPlugin.skills" :key="skill" class="skill-tag">{{ skill }}</span>
            </div>
          </div>
        </div>
        <footer class="detail-footer">
          <button class="plugin-toggle detail-toggle" role="switch" :aria-checked="selectedPlugin.enabled" :aria-label="selectedPlugin.enabled ? t('skills.disablePlugin') : t('skills.enablePlugin')" :class="{ enabled: selectedPlugin.enabled }" :disabled="!connected || updatingPlugin === selectedPlugin.id" :title="selectedPlugin.enabled ? t('skills.disablePlugin') : t('skills.enablePlugin')" @click="togglePlugin(selectedPlugin)">
            <AppIcon v-if="updatingPlugin === selectedPlugin.id" name="RefreshCw" :size="14" class="spin" />
            <span v-else />
          </button>
          <span class="toggle-label">{{ selectedPlugin.enabled ? t('skills.enabledState') : t('skills.disabledState') }}</span>
          <div class="detail-actions">
            <button @click="showPluginSkills(selectedPlugin)"><AppIcon name="Sparkles" :size="13" />{{ t('skills.viewPluginSkills', { n: selectedPlugin.skills.length }) }}</button>
            <a v-if="safeHomepage(selectedPlugin)" :href="safeHomepage(selectedPlugin)" target="_blank" rel="noopener noreferrer"><AppIcon name="ExternalLink" :size="13" />{{ t('skills.pluginSource') }}</a>
            <button v-if="selectedPlugin.source !== 'builtin'" class="detail-remove" :disabled="updatingPlugin === selectedPlugin.id" @click="removeInstalledPlugin(selectedPlugin); pluginDetailOpen = false"><AppIcon name="Trash2" :size="13" />{{ t('skills.uninstallPlugin') }}</button>
          </div>
        </footer>
      </section>
    </div>

    <div v-if="skillDetailOpen && selectedSkill" class="skill-dialog-backdrop" @mousedown.self="skillDetailOpen = false">
      <section class="skill-dialog skill-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="skill-detail-title">
        <header>
          <div class="skill-detail-header">
            <SkillIcon :name="selectedSkill.name" :size="48" class="detail-skill-icon" />
            <div>
              <h2 id="skill-detail-title">{{ selectedSkill.display_name }}</h2>
              <p>{{ selectedSkill.plugin ? `来自插件：${pluginLabel(selectedSkill)}` : selectedSkill.scope === 'workspace' ? '当前工作区技能' : selectedSkill.scope === 'personal' ? '个人技能' : '系统技能' }}</p>
            </div>
          </div>
          <button type="button" :aria-label="t('skills.close')" @click="skillDetailOpen = false"><AppIcon name="X" :size="17" /></button>
        </header>
        <div class="skill-detail-body">
          <h3>技能描述</h3>
          <p class="skill-detail-desc">{{ skillDescription(selectedSkill) }}</p>
          <div v-if="selectedSkill.plugin || owningPlugin(selectedSkill)" class="detail-info">
            <span v-if="owningPlugin(selectedSkill)">所属插件：{{ owningPlugin(selectedSkill)?.display_name }}</span>
          </div>
        </div>
        <footer v-if="canDeleteSkill(selectedSkill)" class="skill-detail-footer">
          <button class="skill-delete-btn" :disabled="updatingSkill === selectedSkill.id" @click="removeInstalledSkill(selectedSkill)">
            <AppIcon v-if="updatingSkill === selectedSkill.id" name="RefreshCw" :size="14" class="spin" />
            <AppIcon v-else name="Trash2" :size="14" />
            {{ updatingSkill === selectedSkill.id ? '删除中…' : '删除技能' }}
          </button>
        </footer>
      </section>
    </div>

    <div v-if="pluginManageOpen" class="skill-dialog-backdrop" @mousedown.self="pluginManageOpen = false">
      <section class="skill-dialog plugin-manage-dialog" role="dialog" aria-modal="true" aria-labelledby="plugin-manage-title">
        <header><div><h2 id="plugin-manage-title">{{ t("skills.managePluginsTitle") }}</h2><p>{{ t("skills.managePluginsDesc") }}</p></div><button type="button" :aria-label="t('skills.close')" @click="pluginManageOpen = false"><AppIcon name="X" :size="17" /></button></header>
        <div v-if="visibleInstalledPlugins.length" class="plugin-manage-list">
          <article v-for="plugin in visibleInstalledPlugins" :key="plugin.id" v-memo="[plugin.id, plugin.enabled, plugin.display_name, plugin.name, plugin.description, plugin.source, plugin.version, updatingPlugin === plugin.id]" :class="{ disabled: !plugin.enabled }">
            <PluginIcon :name="plugin.name" class="plugin-manage-art" />
            <span><b>{{ plugin.display_name }}</b><small>{{ pluginDescription(plugin) }}</small><em>{{ plugin.source === 'workspace' ? t('skills.workspaceScope') : plugin.source === 'builtin' ? t('skills.systemSource') : t('skills.personal') }}<template v-if="plugin.version"> · {{ plugin.version }}</template></em></span>
            <button class="plugin-toggle" role="switch" :aria-checked="plugin.enabled" :aria-label="plugin.enabled ? t('skills.disablePlugin') : t('skills.enablePlugin')" :class="{ enabled: plugin.enabled }" :disabled="updatingPlugin === plugin.id" :title="plugin.enabled ? t('skills.disablePlugin') : t('skills.enablePlugin')" @click="togglePlugin(plugin)"><AppIcon v-if="updatingPlugin === plugin.id" name="RefreshCw" :size="14" class="spin" /><span v-else /></button>
            <button v-if="plugin.source !== 'builtin'" class="plugin-remove" :disabled="updatingPlugin === plugin.id" :title="t('skills.uninstallPlugin')" @click="removeInstalledPlugin(plugin)"><AppIcon name="Trash2" :size="15" /></button>
            <span v-else class="plugin-remove plugin-remove--builtin" :title="t('skills.systemSource')"><AppIcon name="ShieldCheck" :size="15" /></span>
          </article>
        </div>
        <p v-else class="section-empty">{{ t("skills.noMatchPlugins") }}</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.skill-center { overflow-x: hidden; }
.skill-center__body { box-sizing: border-box; width: min(calc(100% - 48px), 1080px); max-width: none; }
.plugin-section { margin-top: 28px; }
.plugin-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 8px 10px; border-bottom: 1px solid #f5f6f7; }
.plugin-tabs { display: flex; gap: 2px; align-items: center; overflow-x: auto; }
.plugin-tabs button { flex: 0 0 auto; height: 30px; padding: 0 12px; color: #888; background: transparent; border: 0; border-radius: 8px; font-size: 14px; font-weight: 500; }
.plugin-tabs button:hover { color: #444; background: #f8f9fa; }
.plugin-tabs button.active { color: #202124; background: #f0f2f5; }
.plugin-header-actions { display: flex; flex: none; gap: 4px; align-items: center; }
.plugin-header-actions > button { display: grid; width: 28px; height: 28px; padding: 0; place-items: center; color: #888; background: transparent; border: 0; border-radius: 6px; }
.plugin-header-actions > button:hover:not(:disabled) { color: #444; background: #f5f7f9; }
.plugin-header-actions > button:disabled { opacity: .38; }

.plugin-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 16px; padding: 0; }
.plugin-capsule-card { display: flex; align-items: center; gap: 10px; min-width: 0; height: 68px; padding: 0 14px 0 10px; overflow: hidden; color: var(--text, #292b2f); background: color-mix(in srgb, var(--surface-soft, #f8f9fa) 62%, var(--surface, #fff)); border: 0; border-radius: 14px; cursor: pointer; transition: background-color .15s ease, transform .15s ease, box-shadow .15s ease; text-align: left; }
.plugin-capsule-card:hover { background: var(--surface-soft, #f5f7f9); transform: translateY(-1px); box-shadow: 0 5px 16px #00000008; }
.plugin-capsule-card.disabled { opacity: .55; }
.plugin-capsule-card.disabled:hover { opacity: .7; }
.capsule-icon { flex: none; width: 40px; height: 40px; }
.capsule-icon :deep(.plugin-icon-svg),
.capsule-icon :deep(.plugin-icon-fallback) { width: 40px !important; height: 40px !important; border-radius: 10px; }
.capsule-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.capsule-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #2c2e31; }
.capsule-name em { font-style: normal; font-weight: 400; color: #aaa; font-size: 11px; }
.capsule-desc { font-size: 11px; color: #999; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.4; }
.capsule-status { font-size: 10px; color: var(--text-muted, #999); padding: 4px 8px; background: color-mix(in srgb, var(--surface-raised, #fff) 70%, transparent); border-radius: 999px; flex: none; }
.capsule-status.installed-status { color: #438d61; background: color-mix(in srgb, #87c99f 14%, var(--surface, #fff)); }
.market-badge { font-style: normal; font-weight: 400; color: #888; font-size: 10px; padding: 1px 5px; background: #f0f2f5; border-radius: 3px; margin-left: 4px; }

.plugin-market { margin-top: 0; }
.marketplace-capsule { cursor: default; }
.marketplace-capsule:hover { transform: none; box-shadow: none; }
.catalog-installed-badge { display: inline-flex; align-items: center; gap: 3px; font-size: 10px; color: #52a370; padding: 3px 7px; background: #eef7f1; border-radius: 5px; flex: none; font-weight: 500; }
.catalog-install-btn { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 10px; color: #444; background: #fff; border: 1px solid #e4e7eb; border-radius: 7px; font-size: 11px; font-weight: 500; cursor: pointer; flex: none; transition: all .15s ease; }
.catalog-install-btn:hover:not(:disabled) { background: #f0f2f5; border-color: #d8dde2; }
.catalog-install-btn:disabled { opacity: .55; }

.plugin-empty { display: grid; min-height: 150px; margin-top: 20px; place-content: center; justify-items: center; color: #a0a2a5; text-align: center; }
.plugin-empty b { margin-top: 8px; color: #55575a; font-size: 13px; }
.plugin-empty p { margin: 4px 0 10px; font-size: 11px; }
.plugin-empty button { display: flex; height: 30px; padding: 0 9px; align-items: center; gap: 4px; color: #44464a; background: #fafbfc; border: 1px solid #f0f1f2; border-radius: 7px; cursor: pointer; }
.plugin-empty button:hover { background: #f5f7f9; border-color: #e4e7eb; }

@media (prefers-reduced-motion: reduce) { .plugin-capsule-card { transition: none; } }
.skill-center button:focus { outline: 0; }
.skill-center button:focus-visible { box-shadow: inset 0 0 0 1px #8e9297; }
.plugin-manage-trigger { display: flex; align-items: center; gap: 4px; padding: 4px 10px; color: #888; background: #fafbfc; border: 1px solid #f0f1f2; border-radius: 7px; font-size: 12px; margin-left: 4px; cursor: pointer; }
.plugin-manage-trigger:hover { color: #444; background: #f5f7f9; border-color: #e4e7eb; }

.marketplace-dialog { width: min(500px, 100%); padding: 22px 24px 24px; border-radius: 14px; border-color: #f0f1f2; }
.marketplace-dialog > header { margin-bottom: 16px; }
.marketplace-dialog > header h2 { font-size: 17px; letter-spacing: -.25px; }
.marketplace-dialog > header p { display: flex; align-items: center; flex-wrap: wrap; gap: 3px; margin-top: 5px; font-size: 12px; }
.marketplace-dialog > header p a { display: inline-flex; align-items: center; gap: 3px; color: #1683ef; text-decoration: none; }
.marketplace-dialog > header p a:hover { color: #006bd6; }
.marketplace-dialog > header > button { color: #666; background: transparent; }
.marketplace-dialog > header > button:hover { background: #f5f5f5; }
.marketplace-dialog > label { margin-top: 14px; gap: 6px; color: #666; font-size: 12px; }
.marketplace-dialog input { height: 36px; padding-inline: 11px; background: #fafbfc; border-color: #f0f1f2; border-radius: 7px; font-size: 13px; }
.marketplace-dialog textarea { min-height: 70px; padding: 10px 11px; resize: vertical; color: #303236; background: #fafbfc; border: 1px solid #f0f1f2; border-radius: 7px; outline: 0; font: inherit; font-size: 13px; }
.marketplace-dialog input:focus, .marketplace-dialog textarea:focus { background: #fff; border-color: #1683ef; box-shadow: 0 0 0 1px #1683ef15; }
.marketplace-dialog > footer { margin-top: 16px; }
.marketplace-dialog > footer button { height: 34px; padding-inline: 14px; border: 1px solid #f0f1f2; border-radius: 7px; font-size: 12px; cursor: pointer; }
.marketplace-dialog > footer button.primary { border-color: #24262a; background: #24262a; color: #fff; }

.plugin-manage-dialog { width: min(520px, 100%); max-height: min(600px, calc(100vh - 40px)); overflow: auto; border-color: #f0f1f2; }
.plugin-manage-list { display: grid; gap: 2px; }
.plugin-manage-list article { display: grid; min-width: 0; padding: 8px 6px; grid-template-columns: 32px minmax(0, 1fr) 34px 28px; align-items: center; gap: 8px; border-radius: 7px; }
.plugin-manage-list article:hover { background: #fafbfc; }
.plugin-manage-list article.disabled { opacity: .6; }
.plugin-manage-art { flex: none; width: 32px; height: 32px; }
.plugin-manage-art :deep(.plugin-icon-svg),
.plugin-manage-art :deep(.plugin-icon-fallback) { width: 32px !important; height: 32px !important; border-radius: 7px; }
.plugin-manage-list article > span:nth-child(2) { display: block; min-width: 0; }
.plugin-manage-list b, .plugin-manage-list small, .plugin-manage-list em { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plugin-manage-list b { color: #333; font-size: 12px; }
.plugin-manage-list small { margin-top: 2px; color: #888; font-size: 11px; }
.plugin-manage-list em { margin-top: 2px; color: #bbb; font-size: 9px; font-style: normal; }
.plugin-toggle { display: grid; width: 32px; height: 18px; padding: 2px; align-items: center; justify-items: start; background: #e0e2e5; border: 0; border-radius: 9px; cursor: pointer; }
.plugin-toggle > span { width: 14px; height: 14px; background: #fff; border-radius: 50%; box-shadow: 0 1px 2px #0002; transition: transform .15s ease; }
.plugin-toggle.enabled { background: #26282b; }
.plugin-toggle.enabled > span { transform: translateX(14px); }
.plugin-remove { display: grid; width: 28px; height: 28px; padding: 0; place-items: center; color: #b08884; background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.plugin-remove:hover { color: #a33d32; background: #fff8f7; }
.plugin-remove--builtin { color: #aaa; cursor: default; }
.plugin-remove--builtin:hover { color: #aaa; background: transparent; }

/* Plugin Detail Dialog */
.plugin-detail-dialog { width: min(440px, 100%); padding: 0; border-color: #f0f1f2; border-radius: 14px; overflow: hidden; }
.plugin-detail-dialog > header { display: flex; align-items: flex-start; justify-content: space-between; padding: 20px 20px 16px; margin: 0; border-bottom: 1px solid #f5f6f7; }
.plugin-detail-header { display: flex; align-items: center; gap: 12px; }
.detail-icon { flex: none; width: 48px; height: 48px; }
.detail-icon :deep(.plugin-icon-svg),
.detail-icon :deep(.plugin-icon-fallback) { width: 48px !important; height: 48px !important; border-radius: 11px; }
.plugin-detail-dialog h2 { margin: 0; font-size: 17px; font-weight: 600; }
.detail-meta { margin: 4px 0 0; font-size: 12px; color: #888; }
.detail-origin { color: #666; }
.plugin-detail-body { padding: 16px 20px; }
.detail-desc { margin: 0; color: #555; font-size: 13px; line-height: 1.6; }
.detail-info { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #f5f6f7; font-size: 11px; color: #888; }
.detail-info span { display: inline-flex; align-items: center; gap: 4px; }
.detail-skills { margin-top: 16px; }
.detail-skills h4 { margin: 0 0 10px; font-size: 12px; font-weight: 600; color: #555; }
.skill-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.skill-tag { padding: 3px 8px; font-size: 11px; color: #666; background: #fafbfc; border: 1px solid #f0f1f2; border-radius: 4px; }
.detail-footer { display: flex; align-items: center; gap: 10px; padding: 14px 20px; border-top: 1px solid #f5f6f7; background: #fcfcfd; }
.detail-toggle { flex: none; }
.toggle-label { font-size: 12px; color: #666; }
.detail-actions { display: flex; gap: 12px; margin-left: auto; }
.detail-actions button, .detail-actions a { display: inline-flex; align-items: center; gap: 4px; padding: 0; background: transparent; border: 0; color: #666; font: inherit; font-size: 11px; text-decoration: none; cursor: pointer; }
.detail-actions button:hover, .detail-actions a:hover { color: #333; text-decoration: underline; }
.detail-remove { color: #b08884 !important; }
.detail-remove:hover { color: #a33d32 !important; }

/* Skill Detail Dialog */
.skill-detail-dialog { width: min(480px, 100%); padding: 0; overflow: hidden; color: var(--text, #292b2f); background: var(--surface-raised, #fff) !important; border-color: transparent; border-radius: 16px; box-shadow: 0 24px 72px #171a2033; }
.skill-detail-dialog > header { display: flex; margin: 0; padding: 20px; align-items: flex-start; justify-content: space-between; border-bottom: 1px solid color-mix(in srgb, var(--border, #e8eaed) 60%, transparent); }
.skill-detail-header { display: flex; min-width: 0; align-items: center; gap: 12px; }
.skill-detail-header > div { min-width: 0; }
.skill-detail-header h2 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-detail-header p { margin-top: 4px; }
.detail-skill-icon { width: 46px; height: 46px; }
.skill-detail-body { min-height: 120px; padding: 20px; }
.skill-detail-body h3 { margin: 0 0 8px; color: var(--text-faint, #8b8e93); font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.skill-detail-body p { margin: 0; color: var(--text, #3f4247); font-size: 13px; line-height: 1.75; white-space: pre-wrap; }
.skill-detail-footer { padding: 14px 20px; border-top: 1px solid color-mix(in srgb, var(--border, #e8eaed) 60%, transparent); background: color-mix(in srgb, var(--surface-soft, #f8f9fa) 58%, transparent); }
.skill-detail-footer .skill-delete-btn { display: inline-flex; height: 32px; margin-left: auto; padding: 0 11px; align-items: center; gap: 6px; color: #a44b43; background: color-mix(in srgb, #df7a70 9%, var(--surface, #fff)); border: 0; border-radius: 8px; font-size: 12px; cursor: pointer; }
.skill-detail-footer .skill-delete-btn:hover:not(:disabled) { background: color-mix(in srgb, #df7a70 15%, var(--surface, #fff)); }
.skill-detail-footer .skill-delete-btn:disabled { opacity: .5; cursor: default; }

/* 覆盖添加按钮下拉菜单样式 */
.skill-add { position: relative; z-index: 100; }
.skill-add__trigger { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 10px; color: var(--accent-contrast, #fff); background: var(--accent, #202124); border: 0; border-radius: 7px; font-size: 12px; font-weight: 500; cursor: pointer; }
.skill-add__trigger:hover { background: color-mix(in srgb, var(--accent, #303236) 88%, var(--accent-contrast, #fff)); }
.skill-add__menu { position: absolute; z-index: 101; top: 34px; right: 0; width: 180px; padding: 4px; background: var(--surface-raised, #fff); border: 1px solid #f0f1f2; border-radius: 9px; box-shadow: 0 8px 24px #00000015; }
.skill-add__menu button { display: flex; width: 100%; padding: 8px 10px; align-items: center; gap: 8px; color: #444; background: transparent; border: 0; border-radius: 6px; font-size: 12px; text-align: left; cursor: pointer; }
.skill-add__menu button:hover { background: #f5f7f9; color: #202124; }
.marketplace-capsule.clickable { cursor: pointer; }
.marketplace-capsule.clickable:hover { transform: translateY(-1px); box-shadow: 0 2px 8px #00000008; }
.marketplace-capsule .catalog-installed-badge { cursor: pointer; }

/* 技能页面样式 */
.skill-section { min-width: 0; margin-top: 18px; }
.skill-header { display: flex; min-width: 0; align-items: flex-start; justify-content: space-between; padding: 0; margin-bottom: 14px; gap: 16px; }
.skill-count { padding-top: 7px; color: var(--text-faint, #999); font-size: 12px; flex: none; }
.skill-grid { display: grid; min-width: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 0; padding: 0; }
.skill-card { display: flex; align-items: center; gap: 12px; width: 100%; min-width: 0; min-height: 72px; padding: 10px 12px; overflow: hidden; color: var(--text, #2c2e31); background: color-mix(in srgb, var(--surface-soft, #f8f9fa) 62%, var(--surface, #fff)); border: 0; border-radius: 14px; cursor: pointer; text-align: left; transition: background-color .15s ease, transform .15s ease, box-shadow .15s ease; }
.skill-card:hover { background: var(--surface-soft, #f5f7f9); transform: translateY(-1px); box-shadow: 0 5px 16px #00000008; }
.skill-card.disabled { opacity: .55; }
.skill-card.disabled:hover { opacity: .7; }
.skill-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.skill-card :is(.skill-info, .skill-name, .skill-desc, .skill-source) { margin-left: 0; padding: 0; align-self: auto; background: transparent; border-radius: 0; }
.skill-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text, #2c2e31); }
.skill-desc { font-size: 11px; color: var(--text-muted, #8f9297); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.45; }
.skill-source { font-size: 10px; color: var(--text-faint, #adb0b5); font-style: normal; margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-status { display: inline-flex; align-items: center; gap: 3px; font-size: 10px; padding: 3px 7px; border-radius: 5px; flex: none; font-weight: 500; }
.skill-status.enabled-badge { color: #52a370; background: #eef7f1; }
.skill-source-tabs { display: flex; gap: 2px; margin-top: 24px; padding: 0 8px; align-items: center; overflow-x: auto; border-bottom: 1px solid #f5f6f7; }
.skill-source-tabs button { flex: 0 0 auto; height: 34px; padding: 0 12px; color: #888; background: transparent; border: 0; border-radius: 8px 8px 0 0; font-size: 13px; font-weight: 500; cursor: pointer; margin-bottom: -1px; border-bottom: 2px solid transparent; }
.skill-source-tabs button:hover { color: #444; background: #f8f9fa; }
.skill-source-tabs button.active { color: #202124; border-bottom-color: #202124; }
.skill-tabs { display: flex; min-width: 0; flex-wrap: wrap; gap: 4px; align-items: center; overflow: visible; }
.skill-tabs button { flex: 0 0 auto; height: 30px; padding: 0 14px; color: #888; background: transparent; border: 0; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all .15s ease; }
.skill-tabs button:hover { color: #444; background: #f5f7f9; }
.skill-tabs button.active { color: var(--text, #303236); background: color-mix(in srgb, var(--surface-soft, #f0f2f5) 78%, var(--surface, #fff)); }

@media (max-width: 768px) { .skill-grid, .plugin-grid { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .skill-center__body { width: calc(100% - 24px); } .plugin-header, .skill-header { flex-direction: column; align-items: stretch; } .skill-count { align-self: flex-end; padding-top: 0; } .plugin-tabs, .skill-source-tabs { justify-content: flex-start; } .plugin-header-actions { justify-content: flex-end; } .skill-grid, .plugin-grid { grid-template-columns: 1fr; gap: 10px; } .marketplace-dialog { padding: 18px 16px; } }
</style>
