<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Check, ChevronDown, ChevronRight, Circle, Code,
  ExternalLink, FileCode2, FileText, FolderOpen, Globe2,
  ListChecks, LoaderCircle, Maximize2, Minimize2, Monitor, MousePointer2, PackageOpen, PanelRightClose,
  Pencil, Plus, RefreshCw, RotateCw, Share2, SquareTerminal, X,
} from "@lucide/vue";
import {
  changeDiff, listChanges, readFile,
  getWorkspaceProfile,
  type ChangeSummary, type DetectionEvidence, type ProjectComponent, type TechnologyFinding, type ValidationCategory,
} from "../../services/sztu-runtime";
import BrowserWebview from "./BrowserWebview.vue";
import CodePreview from "./CodePreview.vue";
import FileTree from "./FileTree.vue";
import AgentLogo from "../timeline/AgentLogo.vue";
import { createProjectProfileController, type ProjectProfileState } from "./project-profile";
import { fileTypeIconUrl } from "../../utils/fileIcon";
import type { TimelineStep } from "../timeline/types";

const SandboxTerminal = defineAsyncComponent(() => import("./SandboxTerminal.vue"));

const props = defineProps<{
  workspaceId: string;
  runId?: string | null;
  steps?: TimelineStep[];
  attachments?: string[];
  workspaceName?: string;
  workspacePath?: string;
  obscured?: boolean;
  // 「查看项目文件」请求：seq 递增触发切换到文件标签页，workspaceId 覆盖要浏览的项目
  filesRequest?: { workspaceId: string; seq: number } | null;
}>();

const emit = defineEmits<{ close: [] }>();

type SectionKey = "profile" | "todo" | "artifacts" | "references";
type BrowserTab = {
  id: number;
  label: string;
  input: string;
  url: string;
  loading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  webviewRef: InstanceType<typeof BrowserWebview> | null;
  devMenuOpen: boolean;
};
type ActiveTab = "home" | "summary" | "files" | `sandbox-${number}` | `browser-${number}` | "";
type WorkspaceTab = { key: ActiveTab; kind: "summary" | "files" | "browser" | "sandbox" };
type Artifact = { path: string; source: "change" | "attachment"; change?: ChangeSummary; previewPath?: string };

const activeTab = ref<ActiveTab>("home");
const browserSequence = ref(0);
const sandboxSequence = ref(0);
const browserTabs = ref<BrowserTab[]>([]);
const workspaceTabs = ref<WorkspaceTab[]>([]);
const openSections = ref<Set<SectionKey>>(new Set(["profile", "todo", "artifacts", "references"]));
const changes = ref<ChangeSummary[]>([]);
const loadingArtifacts = ref(false);
const notice = ref("");
const selectedPath = ref("");
const preview = ref("");
const previewEncoding = ref("UTF-8");
const previewBinary = ref(false);
const previewTruncated = ref(false);
const previewMediaBase64 = ref<string | null>(null);
const previewMimeType = ref<string | null>(null);
const previewLanguage = ref("");
// 代码预览弹窗：fixed + CSS 居中，脱离父级滚动/裁剪上下文，固定尺寸不被遮挡
const previewModalRef = ref<HTMLElement | null>(null);
const fileTreeRef = ref<InstanceType<typeof FileTree> | null>(null);

// 点击弹窗外部关闭预览（点击遮罩或弹窗外任意处）
function closePreviewOnOutside(event: PointerEvent) {
  if (!selectedPath.value) return;
  if (previewModalRef.value && !previewModalRef.value.contains(event.target as Node)) closePreview();
}
const expandedPanel = ref(false);
const toolMenuOpen = ref(false);
const toolMenuRoot = ref<HTMLElement | null>(null);
const projectProfileController = createProjectProfileController(getWorkspaceProfile);
const profileState = ref<ProjectProfileState>(projectProfileController.state);
const stopProjectProfileSubscription = projectProfileController.subscribe((next) => { profileState.value = next; });

const validationCategories: Array<{ key: ValidationCategory; label: string }> = [
  { key: "format", label: "格式化" },
  { key: "static_check", label: "静态检查" },
  { key: "unit_test", label: "单元测试" },
  { key: "integration_test", label: "集成测试" },
  { key: "build", label: "构建" },
];

const plan = computed(() => [...(props.steps ?? [])].reverse().find((step) => step.plan?.length)?.plan ?? []);
const completed = computed(() => plan.value.filter((item) => item.status === "completed").length);
const selectedName = computed(() => selectedPath.value.split(/[\\/]/).filter(Boolean).pop() ?? selectedPath.value);
const profileOverview = computed(() => {
  const profile = profileState.value.profile;
  if (!profile) return { projects: 0, technologies: 0, validations: 0, evidence: 0 };
  const technologies = new Set<string>();
  let validations = 0;
  let evidence = 0;
  for (const project of profile.projects) {
    for (const group of projectTechnologies(project)) {
      for (const finding of group.findings) technologies.add(`${group.label}:${finding.name.toLocaleLowerCase()}`);
    }
    validations += project.validation_plan.length;
    evidence += project.evidence.length;
  }
  return { projects: profile.projects.length, technologies: technologies.size, validations, evidence };
});
const usedSkills = computed(() => {
  const skills = (props.steps ?? []).flatMap((step) => step.skills ?? []);
  return [...new Map(skills.map((skill) => [skill.name, skill])).values()];
});

const artifacts = computed<Artifact[]>(() => {
  // 过滤编译产物目录（target、node_modules、__pycache__等）和非源代码文件
  const isIgnoredPath = (p: string) => {
    const normalized = p.replace(/\\/g, "/").toLowerCase();
    const parts = normalized.split("/");
    const ignoredDirs = new Set([
      "target", "node_modules", "__pycache__", ".git", ".venv", "venv",
      "build", "dist", ".cache", ".sztu", ".pytest_cache", ".mypy_cache",
      ".ruff_cache", ".tox", ".nox", ".hypothesis",
    ]);
    if (parts.some((part) => ignoredDirs.has(part))) return true;
    // 过滤编译产物后缀
    if (/\.(d|bin|pyc|pyo|o|obj|class|exe|dll|so|dylib)$/i.test(normalized)) return true;
    return false;
  };
  // 只显示AI修改的文件（agent_owned=true），过滤编译产物等附带文件修改
  const items: Artifact[] = changes.value
    .filter((change) => change.agent_owned && !isIgnoredPath(change.path))
    .map((change) => ({
      path: change.path,
      previewPath: change.path,
      source: "change",
      change,
    }));
  for (const attachment of props.attachments ?? []) {
    const normalized = attachment.replace(/\\/g, "/");
    if (isIgnoredPath(normalized)) continue;
    const workspace = props.workspacePath?.replace(/\\/g, "/").replace(/\/$/, "");
    const previewPath = workspace && normalized.toLowerCase().startsWith(`${workspace.toLowerCase()}/`)
      ? normalized.slice(workspace.length + 1)
      : /^[a-z]:\//i.test(normalized) ? undefined : normalized;
    items.push({ path: attachment, previewPath, source: "attachment" });
  }
  return [...new Map(items.map((item) => [item.path.toLowerCase(), item])).values()];
});

// 弹窗预览只显示附件文件（代码变更点击后跳转到文件工作区）
const previewArtifacts = computed<Artifact[]>(() => artifacts.value.filter((a) => a.source === "attachment"));

// 文件树使用的工作区ID：filesRequest 存在时用它（查看其他项目），否则用当前工作区
// 当通过 previewFile 打开当前工作区文件时，需要强制覆盖 filesRequest
const fileTreeWorkspaceId = ref(props.workspaceId);
watch(() => props.filesRequest?.workspaceId, (reqWsId) => {
  // filesRequest 变化时更新文件树工作区
  fileTreeWorkspaceId.value = reqWsId || props.workspaceId;
}, { immediate: true });
watch(() => props.workspaceId, (wsId) => {
  // 当前工作区变化时，如果没有 filesRequest 则更新
  if (!props.filesRequest?.workspaceId) {
    fileTreeWorkspaceId.value = wsId;
  }
}, { immediate: true });

const currentBrowser = computed(() => {
  if (!activeTab.value.startsWith("browser-")) return null;
  const id = Number(activeTab.value.slice(8));
  return browserTabs.value.find((tab) => tab.id === id) ?? null;
});
const sandboxTabs = computed(() => workspaceTabs.value.filter((tab) => tab.kind === "sandbox"));

function basename(path: string) {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

// 任务产物 → 本地打包的类型图标 URL 映射（缺失的扩展名不映射，回退通用图标）
const artifactIconUrls = computed(() => {
  const map = new Map<string, string>();
  for (const a of artifacts.value) {
    const url = fileTypeIconUrl(basename(a.path));
    if (url) map.set(a.path, url);
  }
  return map;
});
// 类型图标加载失败（本地缺失/损坏）的产物路径，回退 FileCode2/FileText
const failedArtifactIcons = ref(new Set<string>());
function onArtifactIconError(path: string) {
  failedArtifactIcons.value = new Set(failedArtifactIcons.value).add(path);
}

function toggleSection(section: SectionKey) {
  const next = new Set(openSections.value);
  if (next.has(section)) next.delete(section);
  else next.add(section);
  openSections.value = next;
}

function openSummary() {
  if (!workspaceTabs.value.some((tab) => tab.kind === "summary")) workspaceTabs.value.unshift({ key: "summary", kind: "summary" });
  activeTab.value = "summary";
  selectedPath.value = "";
  toolMenuOpen.value = false;
}

function goHome() {
  activeTab.value = "home";
  selectedPath.value = "";
  toolMenuOpen.value = false;
}

function projectTechnologies(project: ProjectComponent): Array<{ label: string; findings: TechnologyFinding[] }> {
  return [
    { label: "语言", findings: project.languages },
    { label: "框架", findings: project.frameworks },
    { label: "包管理器", findings: project.package_managers },
    { label: "构建工具", findings: project.build_tools },
  ];
}

function commandsFor(project: ProjectComponent, category: ValidationCategory) {
  return project.validation_plan.filter((command) => command.category === category);
}

function validationGroups(project: ProjectComponent) {
  return validationCategories
    .map((category) => ({ ...category, commands: commandsFor(project, category.key) }))
    .filter((category) => category.commands.length);
}

function evidenceLabel(evidence: DetectionEvidence): string {
  const detail = evidence.detail ? `：${evidence.detail}` : "";
  return `${evidence.path} · ${evidence.rule}${detail}`;
}

function confidenceLabel(confidence: TechnologyFinding["confidence"]): string {
  return confidence === "confirmed" ? "已确认" : "可能";
}

async function refreshProjectProfile() {
  await projectProfileController.refresh();
}

function activateBrowser(id: number) {
  activeTab.value = `browser-${id}`;
  selectedPath.value = "";
}

function createBrowserTab() {
  const id = ++browserSequence.value;
  const key = `browser-${id}` as const;
  browserTabs.value.push({
    id,
    label: "新标签页",
    input: "",
    url: "",
    loading: false,
    canGoBack: false,
    canGoForward: false,
    webviewRef: null,
    devMenuOpen: false,
  });
  workspaceTabs.value.push({ key, kind: "browser" });
  activateBrowser(id);
  toolMenuOpen.value = false;
}

function closeWorkspaceTab(key: ActiveTab) {
  if (!key) return;
  const index = workspaceTabs.value.findIndex((tab) => tab.key === key);
  if (key.startsWith("browser-")) {
    const id = Number(key.slice(8));
    browserTabs.value = browserTabs.value.filter((tab) => tab.id !== id);
  }
  workspaceTabs.value = workspaceTabs.value.filter((tab) => tab.key !== key);
  if (activeTab.value !== key) return;
  const fallback = workspaceTabs.value[Math.min(index, workspaceTabs.value.length - 1)];
  activeTab.value = fallback?.key ?? "home";
  selectedPath.value = "";
}

function browserForKey(key: ActiveTab) {
  if (!key.startsWith("browser-")) return null;
  return browserTabs.value.find((tab) => tab.id === Number(key.slice(8))) ?? null;
}

function openFiles() {
  if (!workspaceTabs.value.some((tab) => tab.kind === "files")) workspaceTabs.value.push({ key: "files", kind: "files" });
  activeTab.value = "files";
  selectedPath.value = "";
  toolMenuOpen.value = false;
}

// 在右侧「文件」标签页中预览指定路径的文件（供 AI 输出中的文件链接调用）
async function previewFile(filePath: string) {
  // 强制使用当前工作区（而非 filesRequest 的其他项目）
  fileTreeWorkspaceId.value = props.workspaceId;
  if (!workspaceTabs.value.some((tab) => tab.kind === "files")) workspaceTabs.value.push({ key: "files", kind: "files" });
  activeTab.value = "files";
  toolMenuOpen.value = false;
  // FileTree 组件使用 v-show 始终挂载，等待一个 nextTick 确保 DOM 切换完成后再调用
  await nextTick();
  fileTreeRef.value?.previewFileAtPath(filePath);
}

async function openChangeDiff(filePath: string) {
  // 先打开summary面板，它会自动加载changes
  openSummary();
  await nextTick();
  await refreshArtifacts();
  await nextTick();
  // 查找对应的change artifact（优先精确匹配，再按文件名匹配）
  const normalizedPath = filePath.replace(/\\/g, "/").toLowerCase();
  const fileName = normalizedPath.split("/").pop() ?? "";
  const artifact = artifacts.value.find((a) => a.source === "change" && a.path.replace(/\\/g, "/").toLowerCase() === normalizedPath)
    ?? artifacts.value.find((a) => a.source === "change" && a.path.replace(/\\/g, "/").toLowerCase().endsWith("/" + fileName))
    ?? artifacts.value.find((a) => a.source === "change");
  if (artifact) await openArtifact(artifact);
}

function openChangesPanel() {
  openSummary();
}

function openBrowser() {
  const tab = browserTabs.value[0];
  if (tab) {
    activateBrowser(tab.id);
    toolMenuOpen.value = false;
  } else createBrowserTab();
}

function openTerminal() {
  const id = ++sandboxSequence.value;
  const key = `sandbox-${id}` as const;
  workspaceTabs.value.push({ key, kind: "sandbox" });
  activeTab.value = key;
  selectedPath.value = "";
  toolMenuOpen.value = false;
}

function sandboxLabel(key: ActiveTab) {
  if (!key.startsWith("sandbox-")) return "沙盒";
  const id = Number(key.slice(8));
  return id > 1 ? `沙盒 ${id}` : "沙盒";
}

function normalizedUrl(value: string) {
  const input = value.trim();
  if (!input) return "";
  return /^[a-z][a-z\d+.-]*:\/\//i.test(input) ? input : `https://${input}`;
}

function navigateBrowser(tab: BrowserTab) {
  const url = normalizedUrl(tab.input);
  if (!url) return;
  try {
    const parsed = new URL(url);
    tab.url = parsed.toString();
    tab.input = tab.url;
    tab.label = parsed.hostname.replace(/^www\./, "") || "新标签页";
    tab.loading = true;
    // webviewRef will be available after next render when tab.url is set
    nextTick(() => {
      if (tab.webviewRef) {
        void tab.webviewRef.navigateTo(tab.url);
      }
    });
  } catch {
    notice.value = "请输入有效的网址";
  }
}

async function moveBrowserHistory(tab: BrowserTab, direction: -1 | 1) {
  if (!tab.webviewRef) return;
  tab.loading = true;
  if (direction === -1) {
    await tab.webviewRef.goBack();
  } else {
    await tab.webviewRef.goForward();
  }
}

async function reloadBrowser(tab: BrowserTab) {
  if (!tab.webviewRef || !tab.url) return;
  tab.loading = true;
  await tab.webviewRef.reload();
}

function browserLoadStart(tab: BrowserTab) {
  tab.loading = true;
  // 8秒超时自动结束加载状态，防止一直转圈
  setTimeout(() => {
    if (tab.loading) {
      tab.loading = false;
    }
  }, 8000);
}

function browserLoaded(tab: BrowserTab, url: string) {
  tab.loading = false;
  if (url && url !== tab.url) {
    tab.url = url;
    tab.input = url;
    try {
      const parsed = new URL(url);
      tab.label = parsed.hostname.replace(/^www\./, "") || "新标签页";
    } catch {
      // ignore
    }
  }
}

function browserUrlChange(tab: BrowserTab, url: string) {
  tab.url = url;
  tab.input = url;
  try {
    const parsed = new URL(url);
    tab.label = parsed.hostname.replace(/^www\./, "") || "新标签页";
  } catch {
    // ignore
  }
}

function openExternalBrowser(tab: BrowserTab) {
  if (!tab.url) return;
  window.open(tab.url, "_blank");
}

function copyBrowserUrl(tab: BrowserTab) {
  if (!tab.url) return;
  navigator.clipboard.writeText(tab.url).catch(() => {});
}

async function toggleDevTools(tab: BrowserTab) {
  tab.devMenuOpen = false;
  if (tab.webviewRef) {
    await tab.webviewRef.openDevTools();
  }
}

function selectElement(tab: BrowserTab) {
  tab.devMenuOpen = false;
  notice.value = "元素选择功能开发中";
}

function cssInspector(tab: BrowserTab) {
  tab.devMenuOpen = false;
  notice.value = "CSS检查器功能开发中";
}

function deviceToolbar(tab: BrowserTab) {
  tab.devMenuOpen = false;
  notice.value = "设备工具栏功能开发中";
}

function setWebviewRef(tab: BrowserTab, el: any) {
  tab.webviewRef = el;
}

function openUrlInAppBrowser(url: string) {
  // 复用第一个浏览器标签或新建：从输出链接直达内置浏览器栏
  let tab = browserTabs.value[0];
  if (!tab) {
    createBrowserTab();
    tab = browserTabs.value[browserTabs.value.length - 1];
  }
  if (tab) {
    tab.input = url;
    navigateBrowser(tab);
    activateBrowser(tab.id);
    toolMenuOpen.value = false;
  }
}

function clearBrowserInput(tab: BrowserTab) {
  tab.input = "";
}

function browserLoadError(tab: BrowserTab, message: string) {
  tab.loading = false;
  notice.value = `网页加载失败：${message}`;
}

async function refreshArtifacts() {
  loadingArtifacts.value = true;
  notice.value = "";
  try {
    changes.value = await listChanges(props.workspaceId, props.runId);
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  } finally {
    loadingArtifacts.value = false;
  }
}

async function openArtifact(artifact: Artifact) {
  if (!artifact.previewPath) {
    notice.value = "该附件不在当前项目内，暂不支持直接预览";
    return;
  }
  // 代码变更文件：跳转到文件工作区展示，而不是弹窗
  if (artifact.source === "change") {
    await previewFile(artifact.path);
    return;
  }
  // 附件：保持弹窗预览
  selectedPath.value = artifact.path;
  await loadArtifact(artifact);
}

// 加载指定产物的内容到预览区（openArtifact 与弹窗内文件切换共用）
async function loadArtifact(artifact: Artifact) {
  preview.value = "";
  previewLanguage.value = artifact.change ? "diff" : "";
  previewEncoding.value = "UTF-8";
  previewBinary.value = false;
  previewTruncated.value = false;
  previewMediaBase64.value = null;
  previewMimeType.value = null;
  notice.value = "";
  try {
    if (artifact.change) {
      preview.value = await changeDiff(props.workspaceId, artifact.previewPath);
    } else {
      const result = await readFile(props.workspaceId, artifact.previewPath);
      preview.value = result.content;
      previewEncoding.value = result.encoding;
      previewBinary.value = result.binary;
      previewTruncated.value = result.truncated;
      previewMediaBase64.value = result.media_base64 ?? null;
      previewMimeType.value = result.mime_type ?? null;
    }
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  }
}

// 弹窗顶部下拉切换查看其他附件
function onSelectFile() {
  const artifact = previewArtifacts.value.find((a) => a.path === selectedPath.value);
  if (artifact) void loadArtifact(artifact);
}

function closeToolMenu(event: PointerEvent) {
  if (toolMenuOpen.value && !toolMenuRoot.value?.contains(event.target as Node)) toolMenuOpen.value = false;
}

// 关闭代码预览浮窗（点击遮罩或 Escape 触发），同时清空选中态
function closePreview() {
  selectedPath.value = "";
  preview.value = "";
}

function closeToolMenuOnEscape(event: KeyboardEvent) {
  if (event.key === "Escape") {
    toolMenuOpen.value = false;
    closePreview();
    if (expandedPanel.value) expandedPanel.value = false; // 全屏态按 Esc 退出全屏
  }
}

watch(() => [props.workspaceId, props.runId], () => {
  activeTab.value = "home";
  browserSequence.value = 0;
  sandboxSequence.value = 0;
  browserTabs.value = [];
  workspaceTabs.value = [];
  selectedPath.value = "";
  void refreshArtifacts();
}, { immediate: true });

watch(() => props.workspaceId, (workspaceId) => {
  void projectProfileController.setWorkspace(workspaceId || null);
}, { immediate: true });

// 「查看项目文件」信号：seq 变化时切换到文件标签页（在 workspaceId/runId 重置之后执行）。
// immediate 保证「先建会话再挂载 inspector」的路径（无活动会话点查看项目文件）也能打开文件标签页
watch(() => props.filesRequest?.seq, (seq, prev) => {
  if (seq !== undefined && seq !== prev) openFiles();
}, { immediate: true });

onMounted(() => {
  document.addEventListener("pointerdown", closeToolMenu);
  document.addEventListener("pointerdown", closePreviewOnOutside);
  document.addEventListener("keydown", closeToolMenuOnEscape);
});
onBeforeUnmount(() => {
  stopProjectProfileSubscription();
  document.removeEventListener("pointerdown", closeToolMenu);
  document.removeEventListener("pointerdown", closePreviewOnOutside);
  document.removeEventListener("keydown", closeToolMenuOnEscape);
});
defineExpose({ openUrlInAppBrowser, openFiles, openBrowser, openTerminal, previewFile, openChangeDiff, openChangesPanel });
</script>

<template>
  <aside class="project-inspector file-rail" :class="{ 'is-expanded': expandedPanel }">
    <header v-if="activeTab !== 'home'" class="workspace-tab-strip">
      <div ref="toolMenuRoot" class="workspace-tool-menu-root">
        <button type="button" class="workspace-tool-menu-trigger" :class="{ active: toolMenuOpen }" aria-label="打开功能" aria-haspopup="menu" :aria-expanded="toolMenuOpen" @click="toolMenuOpen = !toolMenuOpen"><Plus :size="16" /></button>
        <nav v-if="toolMenuOpen" class="workspace-tool-menu" aria-label="选择功能" role="menu">
          <button type="button" role="menuitem" :class="{ active: activeTab === 'home' }" @click="goHome"><BookOpen :size="15" /><span>首页</span></button>
          <button type="button" role="menuitem" :class="{ active: activeTab === 'summary' }" @click="openSummary"><ListChecks :size="15" /><span>任务摘要</span></button>
          <button type="button" role="menuitem" :class="{ active: currentBrowser }" @click="openBrowser"><Globe2 :size="15" /><span>浏览器</span></button>
          <button type="button" role="menuitem" :class="{ active: activeTab.startsWith('sandbox-') }" @click="openTerminal"><SquareTerminal :size="15" /><span>终端</span></button>
          <button type="button" role="menuitem" :class="{ active: activeTab === 'files' }" @click="openFiles"><FolderOpen :size="15" /><span>文件</span></button>
        </nav>
      </div>
      <nav class="workspace-open-tabs" aria-label="已打开功能">
        <div v-for="tab in workspaceTabs" :key="tab.key" class="workspace-open-tab" :class="{ active: activeTab === tab.key }">
          <button type="button" :aria-pressed="activeTab === tab.key" @click="activeTab = tab.key">
            <span class="workspace-tab-icon">
              <ListChecks v-if="tab.kind === 'summary'" class="workspace-tab-kind-icon" :size="14" />
              <FolderOpen v-else-if="tab.kind === 'files'" class="workspace-tab-kind-icon" :size="14" />
              <Globe2 v-else-if="tab.kind === 'browser'" class="workspace-tab-kind-icon" :size="14" />
              <SquareTerminal v-else class="workspace-tab-kind-icon" :size="14" />
            </span>
            <span>{{ tab.kind === 'summary' ? '任务摘要' : tab.kind === 'files' ? '文件' : tab.kind === 'sandbox' ? sandboxLabel(tab.key) : (browserForKey(tab.key)?.label ?? '新标签页') }}</span>
          </button>
          <button type="button" class="workspace-tab-close" :aria-label="`关闭${tab.kind === 'summary' ? '任务摘要' : tab.kind === 'files' ? '文件' : tab.kind === 'sandbox' ? sandboxLabel(tab.key) : (browserForKey(tab.key)?.label ?? '新标签页')}`" @click.stop="closeWorkspaceTab(tab.key)"><X :size="12" /></button>
        </div>
      </nav>
      <button type="button" class="workspace-browser-add" aria-label="新建浏览器标签页" @click="createBrowserTab"><Plus :size="16" /></button>
      <span class="workspace-header-divider" />
      <button type="button" class="workspace-expand" :aria-label="expandedPanel ? '退出全屏' : '全屏'" @click="expandedPanel = !expandedPanel"><Minimize2 v-if="expandedPanel" :size="15" /><Maximize2 v-else :size="15" /></button>
      <button type="button" class="workspace-panel-close" aria-label="退出分屏布局" @click="emit('close')"><PanelRightClose :size="16" /></button>
    </header>

    <header v-else class="workspace-home-header">
      <div class="workspace-home-header__right">
        <button type="button" class="workspace-expand" :aria-label="expandedPanel ? '退出全屏' : '全屏'" @click="expandedPanel = !expandedPanel"><Minimize2 v-if="expandedPanel" :size="15" /><Maximize2 v-else :size="15" /></button>
        <button type="button" class="workspace-panel-close" aria-label="退出分屏布局" @click="emit('close')"><PanelRightClose :size="16" /></button>
      </div>
    </header>

    <main v-if="activeTab === 'home'" class="home-workspace">
      <div class="home-launcher">
        <p class="home-launcher__prompt">从这里开始</p>
        <button class="home-launcher__button" @click="openFiles">
          <FolderOpen :size="20" />文件
        </button>
        <button class="home-launcher__button" @click="openSummary">
          <ListChecks :size="20" />任务摘要
        </button>
        <button class="home-launcher__button" @click="openBrowser">
          <Globe2 :size="20" />浏览器
        </button>
        <button class="home-launcher__button" @click="openTerminal">
          <SquareTerminal :size="20" />终端
        </button>
      </div>
    </main>

    <main v-if="activeTab === 'summary'" class="task-summary-view">
      <section class="summary-section project-profile-section" :class="{ collapsed: !openSections.has('profile') }">
        <button type="button" class="summary-section-trigger" :aria-expanded="openSections.has('profile')" @click="toggleSection('profile')">
          <b>项目画像</b><ChevronDown :size="13" /><small v-if="profileState.profile">{{ profileState.profile.monorepo ? `Monorepo · ${profileState.profile.projects.length} 个项目` : `${profileState.profile.projects.length} 个项目` }}</small>
        </button>
        <div v-if="openSections.has('profile')" class="summary-section-body project-profile-body">
          <div class="project-profile-toolbar">
            <p><b>基于工作区结构生成</b><small>仅建议，未执行；实际运行仍需经过工具权限与审批。</small></p>
            <button type="button" class="summary-refresh" :disabled="profileState.loading" @click="refreshProjectProfile"><RefreshCw :size="13" :class="{ spin: profileState.loading }" />{{ profileState.refreshing ? '正在刷新' : '刷新项目画像' }}</button>
          </div>
          <div v-if="profileState.loading && !profileState.profile" class="project-profile-loading"><LoaderCircle :size="16" class="spin" /><span>正在识别项目结构</span></div>
          <p v-if="profileState.error" class="project-profile-error" role="alert">{{ profileState.profile ? `刷新失败，仍显示上次检测结果：${profileState.error}` : `项目画像加载失败：${profileState.error}` }}</p>
          <template v-if="profileState.profile">
            <div class="project-profile-meta">
              <span><b>根目录</b><code :title="profileState.profile.root_path">{{ profileState.profile.root_path }}</code></span>
              <span v-if="profileState.profile.monorepo" class="project-profile-badge">Monorepo</span>
              <span v-if="profileState.profile.scan_limited" class="project-profile-warning">扫描范围受限，结果可能不完整</span>
            </div>
            <div class="project-profile-overview" aria-label="项目画像概览">
              <span><strong>{{ profileOverview.projects }}</strong><small>项目</small></span>
              <span><strong>{{ profileOverview.technologies }}</strong><small>技术项</small></span>
              <span><strong>{{ profileOverview.validations }}</strong><small>验证建议</small></span>
              <span><strong>{{ profileOverview.evidence }}</strong><small>识别证据</small></span>
            </div>
            <article v-for="(project, projectIndex) in profileState.profile.projects" :key="project.path" class="project-profile-component">
              <header>
                <span class="project-profile-component__icon"><FolderOpen :size="17" /></span>
                <div><b>{{ project.path === '.' ? '工作区根项目' : project.path }}</b><small>{{ project.path === '.' ? '位于工作区根目录' : `相对路径 ${project.path}` }}</small></div>
                <span class="project-profile-component__index">{{ String(projectIndex + 1).padStart(2, '0') }}</span>
              </header>
              <div class="project-profile-subheading"><b>技术识别</b><small>{{ projectTechnologies(project).reduce((total, group) => total + group.findings.length, 0) }} 项结果</small></div>
              <div class="project-technology-grid">
                <section v-for="group in projectTechnologies(project)" :key="group.label">
                  <b>{{ group.label }}</b>
                  <div v-if="group.findings.length" class="project-technology-list">
                    <span v-for="finding in group.findings" :key="finding.name" :title="finding.evidence.map(evidenceLabel).join('\n')"><em>{{ finding.name }}</em><small>{{ confidenceLabel(finding.confidence) }}</small></span>
                  </div>
                  <small v-else>未识别</small>
                </section>
              </div>
              <div class="project-profile-subheading"><b>推荐验证</b><small>{{ project.validation_plan.length ? `${validationGroups(project).length} 类 · ${project.validation_plan.length} 条命令` : '暂无建议' }}</small></div>
              <div class="project-validation-plan">
                <section v-for="category in validationGroups(project)" :key="category.key" class="project-validation-group">
                  <header><b>{{ category.label }}</b><small>{{ category.commands.length }} 条</small></header>
                  <article v-for="command in category.commands" :key="`${command.working_directory}:${command.command}`" class="project-validation-command">
                    <div><code>{{ command.command }}</code><span>目录：{{ command.working_directory || '.' }}</span></div>
                    <p>{{ command.reason }}</p>
                    <small v-if="command.evidence.length">依据：{{ command.evidence.map(evidenceLabel).join('；') }}</small>
                  </article>
                </section>
                <p v-if="!project.validation_plan.length" class="project-validation-empty">当前结构下暂无可靠的验证命令建议。</p>
              </div>
              <p v-if="project.validation_plan.length" class="project-recommendation-note"><SquareTerminal :size="13" />以上命令仅作为验证建议，不会自动执行。</p>
              <details v-if="project.evidence.length" class="project-evidence">
                <summary>识别证据（{{ project.evidence.length }}）</summary>
                <ul><li v-for="evidence in project.evidence" :key="`${evidence.path}:${evidence.rule}`"><code>{{ evidence.path }}</code><span>{{ evidence.rule }}</span><small v-if="evidence.detail">{{ evidence.detail }}</small></li></ul>
              </details>
            </article>
          </template>
          <div v-else-if="!profileState.loading && !profileState.error" class="summary-empty project-profile-empty">
            <span class="summary-empty-icon"><ListChecks :size="15" /></span>
            <b>暂无项目画像</b>
            <p>可点击“刷新项目画像”重新检测当前工作区。</p>
          </div>
        </div>
      </section>

      <section class="summary-section" :class="{ collapsed: !openSections.has('todo') }">
        <button type="button" class="summary-section-trigger" :aria-expanded="openSections.has('todo')" @click="toggleSection('todo')">
          <b>待办</b><ChevronDown :size="13" /><small v-if="plan.length">{{ completed }}/{{ plan.length }}</small>
        </button>
        <div v-if="openSections.has('todo')" class="summary-section-body todo-section-body">
          <template v-if="plan.length">
            <!-- 分段状态点（替代进度条）：每计划项一个点，完成实心/进行中脉冲光晕/待办浅灰，
                 与侧栏 StateDot 语言统一（借鉴 dsh 状态可视化） -->
            <div class="summary-progress-dots" :aria-label="`进度 ${completed}/${plan.length}`">
              <i v-for="item in plan" :key="item.id" :class="item.status" :title="item.subject" />
            </div>
            <ol class="summary-plan-list">
              <li v-for="item in plan" :key="item.id" :class="item.status">
                <span><Check v-if="item.status === 'completed'" :size="11" /><LoaderCircle v-else-if="item.status === 'in_progress'" :size="12" /><Circle v-else :size="9" /></span>
                <p>{{ item.subject }}</p>
              </li>
            </ol>
          </template>
          <div v-else class="summary-empty">
            <span class="summary-empty-icon"><ListChecks :size="15" /></span>
            <b>暂无待办</b>
            <p>复杂任务的进展会显示在这里</p>
          </div>
        </div>
      </section>

      <section class="summary-section" :class="{ collapsed: !openSections.has('artifacts') }">
        <button type="button" class="summary-section-trigger" :aria-expanded="openSections.has('artifacts')" @click="toggleSection('artifacts')">
          <b>任务产物</b><ChevronDown :size="13" /><small v-if="artifacts.length">{{ artifacts.length }} 项</small>
        </button>
        <div v-if="openSections.has('artifacts')" class="summary-section-body">
          <div v-if="artifacts.length" class="artifact-list">
            <button v-for="artifact in artifacts" :key="artifact.path" type="button" :title="artifact.path" @click="openArtifact(artifact)">
              <span>
                <img v-if="!failedArtifactIcons.has(artifact.path) && artifactIconUrls.get(artifact.path)" :src="artifactIconUrls.get(artifact.path)" class="artifact-type-icon" alt="" draggable="false" @error="onArtifactIconError(artifact.path)" />
                <FileCode2 v-else-if="artifact.source === 'change'" :size="15" />
                <FileText v-else :size="15" />
              </span>
              <span><b>{{ basename(artifact.path) }}</b><small>{{ artifact.source === 'change' ? '代码变更' : '任务附件' }}</small></span>
              <code v-if="artifact.change">{{ artifact.change.index_status }}{{ artifact.change.worktree_status }}</code>
              <ExternalLink v-else :size="13" />
            </button>
          </div>
          <div v-else class="summary-empty">
            <span class="summary-empty-icon"><PackageOpen :size="15" /></span>
            <b>暂无产物</b>
            <p>任务完成后，生成的文件将展示在这里</p>
          </div>
          <button v-if="artifacts.length" type="button" class="summary-refresh" :disabled="loadingArtifacts" @click="refreshArtifacts"><RefreshCw :size="13" :class="{ spin: loadingArtifacts }" />刷新产物</button>
        </div>
      </section>

      <section class="summary-section" :class="{ collapsed: !openSections.has('references') }">
        <button type="button" class="summary-section-trigger" :aria-expanded="openSections.has('references')" @click="toggleSection('references')">
          <b>参考信息</b><ChevronDown :size="13" />
        </button>
        <div v-if="openSections.has('references')" class="summary-section-body reference-body">
          <div class="reference-row">
            <span>技能</span>
            <div v-if="usedSkills.length" class="skill-list"><span v-for="skill in usedSkills" :key="skill.name"><BookOpen :size="14" />{{ skill.name }}</span></div>
            <small v-else>本轮任务暂未加载技能</small>
          </div>
          <div class="reference-context">
            <span>上下文</span>
            <p><b>{{ workspaceName || '当前项目' }}</b><small :title="workspacePath">{{ workspacePath }}</small></p>
            <p v-if="attachments?.length || changes.length"><b>{{ (attachments?.length ?? 0) + changes.length }} 项关联内容</b><small>{{ attachments?.length ?? 0 }} 个附件 · {{ changes.length }} 个文件变更</small></p>
          </div>
        </div>
      </section>
    </main>

    <main v-else-if="currentBrowser" class="browser-workspace">
      <form class="browser-toolbar" aria-label="网页导航" @submit.prevent="navigateBrowser(currentBrowser)">
        <div class="browser-nav-group">
          <button
            type="button"
            class="browser-nav-btn"
            title="后退"
            aria-label="后退"
            :disabled="currentBrowser.loading"
            @click="moveBrowserHistory(currentBrowser, -1)"
          >
            <ArrowLeft :size="18" />
          </button>
          <button
            type="button"
            class="browser-nav-btn"
            title="前进"
            aria-label="前进"
            :disabled="currentBrowser.loading"
            @click="moveBrowserHistory(currentBrowser, 1)"
          >
            <ArrowRight :size="18" />
          </button>
          <button
            type="button"
            class="browser-nav-btn"
            title="刷新网页"
            aria-label="刷新网页"
            :disabled="!currentBrowser.url || currentBrowser.loading"
            @click="reloadBrowser(currentBrowser)"
          >
            <RotateCw :size="18" :class="{ spin: currentBrowser.loading }" />
          </button>
        </div>

        <div class="browser-address-bar">
          <input
            v-model="currentBrowser.input"
            aria-label="网页地址"
            placeholder="输入URL或选择正在运行的服务"
            spellcheck="false"
            autocomplete="url"
            class="browser-address-input"
          />
          <ChevronDown :size="16" class="browser-address-chev" />
        </div>

        <div class="browser-toolbar-actions">
          <button type="button" class="browser-action-btn" title="编辑" :disabled="!currentBrowser.url">
            <Pencil :size="18" />
          </button>
          <button type="button" class="browser-action-btn" title="分享" :disabled="!currentBrowser.url" @click="copyBrowserUrl(currentBrowser)">
            <Share2 :size="18" />
          </button>

          <div class="browser-dev-menu-wrap">
            <button
              type="button"
              class="browser-action-btn browser-dev-trigger"
              title="更多工具"
              :class="{ active: currentBrowser.devMenuOpen }"
              @click.stop="currentBrowser.devMenuOpen = !currentBrowser.devMenuOpen"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>
              </svg>
            </button>

            <div v-if="currentBrowser.devMenuOpen" class="browser-dev-popover" @click.stop>
              <button type="button" @click="selectElement(currentBrowser)">
                <MousePointer2 :size="16" />
                <span>选择元素</span>
              </button>
              <div class="browser-popover-divider" />
              <button type="button" @click="cssInspector(currentBrowser)">
                <Code :size="16" />
                <span>CSS检查器</span>
              </button>
              <button type="button" @click="deviceToolbar(currentBrowser)">
                <Monitor :size="16" />
                <span>Device Toolbar</span>
              </button>
              <div class="browser-popover-divider" />
              <button type="button" @click="toggleDevTools(currentBrowser)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                </svg>
                <span>DevTools</span>
              </button>
            </div>
          </div>
        </div>
      </form>
      <div class="browser-stage" @click="currentBrowser.devMenuOpen = false">
        <BrowserWebview
          v-if="currentBrowser.url"
          :ref="(el) => setWebviewRef(currentBrowser, el)"
          :key="currentBrowser.id"
          :tab-id="currentBrowser.id"
          :url="currentBrowser.url"
          :visible="activeTab === `browser-${currentBrowser.id}` && !toolMenuOpen && !obscured && !currentBrowser.devMenuOpen"
          @load-start="browserLoadStart(currentBrowser)"
          @loaded="browserLoaded(currentBrowser, $event)"
          @url-change="browserUrlChange(currentBrowser, $event)"
          @error="browserLoadError(currentBrowser, $event); currentBrowser.devMenuOpen = false"
        />
        <div v-else class="browser-empty">
          <div class="browser-empty-inner">
            <AgentLogo size="large" class="browser-empty-logo" />
            <p class="browser-empty-title">内置浏览器</p>
            <p class="browser-empty-desc">输入网址访问网页，或点击AI输出中的链接直接预览</p>
            <div class="browser-quick-links">
              <button type="button" @click="currentBrowser.input = 'https://www.bing.com'; navigateBrowser(currentBrowser)">必应搜索</button>
              <button type="button" @click="currentBrowser.input = 'https://github.com'; navigateBrowser(currentBrowser)">GitHub</button>
              <button type="button" @click="currentBrowser.input = 'https://developer.mozilla.org'; navigateBrowser(currentBrowser)">MDN</button>
            </div>
          </div>
        </div>
        <div v-if="currentBrowser.loading" class="browser-loading-bar" />
      </div>
    </main>

    <main v-show="activeTab === 'files'" class="files-workspace"><FileTree ref="fileTreeRef" :workspace-id="fileTreeWorkspaceId" :workspace-name="workspaceName" :workspace-path="workspacePath" /></main>
    <main v-for="tab in sandboxTabs" v-show="activeTab === tab.key" :key="`${workspacePath}-${tab.key}`" class="sandbox-workspace"><SandboxTerminal :workspace-path="workspacePath || ''" /></main>
    <main v-if="!activeTab" class="workspace-empty-view" />

    <Teleport to="body">
      <div v-if="selectedPath" class="preview-modal-backdrop" @click="closePreview" />
      <section v-if="selectedPath" ref="previewModalRef" class="preview-modal">
        <header>
          <span class="preview-modal__title"><FileText :size="15" /><b>{{ selectedName }}</b></span>
          <select v-if="previewArtifacts.length > 1" v-model="selectedPath" class="preview-modal__select" aria-label="查看其他附件" @change="onSelectFile">
            <option v-for="artifact in previewArtifacts" :key="artifact.path" :value="artifact.path">{{ basename(artifact.path) }}</option>
          </select>
          <button title="关闭预览" @click="closePreview"><X :size="17" /></button>
        </header>
        <CodePreview :content="preview" :path="selectedPath" :encoding="previewEncoding" :binary="previewBinary" :truncated="previewTruncated" :force-language="previewLanguage" :media-base64="previewMediaBase64" :mime-type="previewMimeType" />
      </section>
    </Teleport>
    <p v-if="notice" class="inspector-notice"><span>{{ notice }}</span><button type="button" aria-label="关闭提示" @click="notice = ''"><X :size="13" /></button></p>
  </aside>
</template>
