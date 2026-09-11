<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import AgentLogo from "./AgentLogo.vue";
import type { ContextInjectionEntry } from "./types";
import { fileTypeIconUrl } from "../../utils/fileIcon";

const props = defineProps<{ entries: ContextInjectionEntry[] }>();
const { t } = useI18n({ useScope: "global" });
const open = ref(false);
const selectedIndex = ref(Math.max(0, props.entries.length - 1));
const entry = computed(() => props.entries[selectedIndex.value] ?? props.entries.at(-1)!);
const latestEntry = computed(() => props.entries.at(-1)!);
watch(() => props.entries.length, (length) => { selectedIndex.value = Math.max(0, length - 1); });

// 来源标签取自语言包：computed 内调用 t，切换语言时自动重建。
// 左侧内嵌 mini AgentLogo（带眨眼/眼珠跟随/随机表情），iconActive 控制顶部三点呼吸动效
const sourceConfig = computed(() => {
  switch (entry.value.source) {
    case "intervention":
      return { label: t("timeline.context.source.intervention"), icon: "ShieldAlert", iconActive: true };
    case "steering":
      return { label: t("timeline.context.source.steering"), icon: "CornerDownRight", iconActive: true };
    case "compaction":
      return { label: t("timeline.context.source.compaction"), icon: "Archive", iconActive: false };
    case "canvas":
      return { label: t("timeline.context.source.canvas"), icon: "PanelTop", iconActive: true };
    default:
      return { label: t("timeline.context.source.system"), icon: "Database", iconActive: false };
  }
});

const body = computed(() => entry.value.text ?? entry.value.preview);
type ContextDiffRow = { kind: "added" | "removed" | "unchanged"; text: string };
const previousBody = computed(() => {
  if (selectedIndex.value <= 0) return "";
  return props.entries[selectedIndex.value - 1]?.text ?? props.entries[selectedIndex.value - 1]?.preview ?? "";
});
const diffRows = computed<ContextDiffRow[]>(() => {
  const currentLines = body.value.split(/\r?\n/);
  const previousLines = previousBody.value.split(/\r?\n/);
  const previousCounts = new Map<string, number>();
  for (const line of previousLines) previousCounts.set(line, (previousCounts.get(line) ?? 0) + 1);
  const currentCounts = new Map<string, number>();
  for (const line of currentLines) currentCounts.set(line, (currentCounts.get(line) ?? 0) + 1);
  const rows: ContextDiffRow[] = [];
  for (const line of previousLines) {
    const remaining = currentCounts.get(line) ?? 0;
    if (remaining > 0) currentCounts.set(line, remaining - 1);
    else rows.push({ kind: "removed", text: line });
  }
  for (const line of currentLines) {
    const remaining = previousCounts.get(line) ?? 0;
    if (remaining > 0) previousCounts.set(line, remaining - 1);
    else rows.push({ kind: "added", text: line });
  }
  if (!rows.length && currentLines.length) return [{ kind: "unchanged", text: `${currentLines.length} 行内容未变化` }];
  return rows.slice(0, 3000);
});
const addedCount = computed(() => diffRows.value.filter((row) => row.kind === "added").length);
const removedCount = computed(() => diffRows.value.filter((row) => row.kind === "removed").length);
const charLabel = computed(() =>
  latestEntry.value.chars >= 1000 ? `${(latestEntry.value.chars / 1000).toFixed(1)}k` : String(latestEntry.value.chars),
);
const turnLabel = computed(() => `${props.entries.length} 轮`);

// 解析文件列表
const files = computed(() => {
  const explicit = entry.value.files?.map((file) => file.trim()).filter(Boolean) ?? [];
  const inferred = [...body.value.matchAll(/^##\s+([^\n]+)$/gm)]
    .map((match) => match[1].trim())
    .filter((value) => /(?:^|[\\/])[^\\/]+\.[a-z0-9]{1,12}$/i.test(value));
  const gitFiles = [...body.value.matchAll(/^\s*[MADRCU?!]{1,2}\s+(.+)$/gm)].map((match) => match[1].trim());
  return [...new Set([...explicit, ...inferred, ...gitFiles])];
});

// 取文件名
const fileName = (path: string) => {
  const parts = path.replace(/[\\/]+$/, "").split(/[\\/]/);
  return parts[parts.length - 1] || path;
};

// 根据文件名返回图标 URL（使用项目自带的 file-icons 资源集）
// 目录/无扩展名/lock文件等特殊情况回退到 lucide 图标
const getFileIcon = (name: string) => {
  const lower = name.toLowerCase();
  // 目录（末尾带斜杠或无扩展名）
  if (lower.endsWith("/") || lower.endsWith("\\")) {
    return { kind: "lucide" as const, icon: "Folder", color: "#d97706" };
  }
  const ext = lower.includes(".") ? lower.split(".").pop()! : "";
  const base = lower.split(/[\\/]/).pop()!;
  if (!ext && base.length > 0) {
    return { kind: "lucide" as const, icon: "Folder", color: "#d97706" };
  }
  // lock 文件
  if (ext === "lock") {
    return { kind: "lucide" as const, icon: "FileLock2", color: "#9ca3af" };
  }
  // 图片（本地图标已包含 image 类型，无需特判，走 fileTypeIconUrl 即可）
  const url = fileTypeIconUrl(name);
  if (url) {
    return { kind: "url" as const, url };
  }
  // 未匹配到图标的文件使用默认文档图标
  const defaultUrl = fileTypeIconUrl("a.txt");
  if (defaultUrl) {
    return { kind: "url" as const, url: defaultUrl };
  }
  return { kind: "lucide" as const, icon: "FileImage", color: "#6b7280" };
};

// 预计算每个文件的图标信息，避免模板中重复调用
const fileItems = computed(() => {
  return files.value.slice(0, 48).map((path) => {
    const name = fileName(path);
    const icon = getFileIcon(name);
    return { path, name, icon };
  });
});

const ariaLabel = computed(() => t("timeline.context.ariaLabel", { label: "上下文演进", source: sourceConfig.value.label }));
</script>

<template>
  <section class="ctx-row" :class="[`ctx-${entry.source}`, { open }]">
    <button
      type="button"
      class="ctx-row__trigger"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="ctx-row__icon">
        <AgentLogo :active="sourceConfig.iconActive" size="mini" />
      </span>
      <span class="ctx-row__title">上下文演进</span>
      <span class="ctx-row__badge">{{ t('timeline.context.chars', { count: charLabel }) }}</span>
      <span class="ctx-row__badge">{{ turnLabel }}</span>
      <span v-if="files.length" class="ctx-row__badge ctx-row__badge--files">{{ t('timeline.context.filesCount', { count: files.length }) }}</span>
      <AppIcon name="ChevronDown" class="ctx-row__chevron" :size="13" />
    </button>

    <transition name="ctx-expand">
      <div v-if="open" class="ctx-row__body">
        <div class="ctx-row__turns" role="list" aria-label="上下文轮次">
          <button
            v-for="(item, index) in props.entries"
            :key="item.id"
            type="button"
            class="ctx-row__turn"
            :class="{ selected: index === selectedIndex }"
            @click="selectedIndex = index"
          >
            <span>第 {{ index + 1 }} 轮</span>
            <small>{{ item.chars >= 1000 ? `${(item.chars / 1000).toFixed(1)}k` : item.chars }} 字符</small>
          </button>
        </div>
        <div v-if="files.length" class="ctx-row__section">
          <div class="ctx-row__section-header">
            <AppIcon name="Folder" :size="14" />
            <span>{{ t('timeline.context.filesSection') }}</span>
            <span class="ctx-row__section-count">{{ t('timeline.context.fileCount', { count: files.length }) }}</span>
          </div>
          <div class="ctx-row__file-grid">
            <div
              v-for="item in fileItems"
              :key="item.path"
              class="ctx-row__file-chip"
              :title="item.path"
            >
              <img
                v-if="item.icon.kind === 'url'"
                :src="item.icon.url"
                class="ctx-row__file-icon-img"
                :alt="item.name"
              />
              <AppIcon
                v-else
                :name="item.icon.icon"
                :size="16"
                :style="{ color: item.icon.color }"
              />
              <span>{{ item.name }}</span>
            </div>
          </div>
        </div>
        <div v-if="body" class="ctx-row__section ctx-row__section--content">
          <div class="ctx-row__section-header">
            <AppIcon :name="sourceConfig.icon" :size="14" />
            <span>本轮变化</span>
            <span class="ctx-row__diff-stat ctx-row__diff-stat--added">+{{ addedCount }}</span>
            <span class="ctx-row__diff-stat ctx-row__diff-stat--removed">-{{ removedCount }}</span>
          </div>
          <div class="ctx-row__legend">
            <span class="ctx-row__legend-item ctx-row__legend-item--added">新增上下文</span>
            <span class="ctx-row__legend-item ctx-row__legend-item--removed">删除 / 压缩上下文</span>
          </div>
          <pre class="ctx-row__content ctx-row__diff-content"><code v-for="(row, index) in diffRows" :key="`${index}-${row.kind}`" :class="`ctx-diff-${row.kind}`">{{ row.kind === 'added' ? '+ ' : row.kind === 'removed' ? '- ' : '  ' }}{{ row.text }}{{ '\n' }}</code></pre>
        </div>
      </div>
    </transition>
  </section>
</template>

<style scoped>
.ctx-row {
  margin: 6px 0;
  font-size: 13px;
}

.ctx-row__trigger {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 4px 6px;
  margin: 0 -6px;
  color: #6b7280;
  background: transparent;
  border: 0;
  border-radius: 5px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}

.ctx-row__trigger:hover {
  background: rgba(0, 0, 0, 0.04);
}

.ctx-row__icon {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 7px;
  background: transparent;
}
.ctx-row__icon .app-icon { margin: 0; }

.ctx-row__title {
  flex: 0 0 auto;
  color: #374151;
  font-weight: 500;
  font-size: 13px;
}

.ctx-row__badge {
  padding: 2px 8px;
  color: #6b7280;
  background: #f3f4f6;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  line-height: 17px;
}

.ctx-row__badge--files {
  color: #4b5563;
}

.ctx-row__chevron {
  flex: 0 0 auto;
  margin-left: auto;
  color: #9ca3af;
  transition: transform 0.18s ease;
  opacity: 0;
}

.ctx-row__trigger:hover .ctx-row__chevron,
.ctx-row.open .ctx-row__chevron {
  opacity: 1;
}

.ctx-row.open .ctx-row__chevron {
  transform: rotate(180deg);
}

.ctx-row__body {
  margin: 5px 0 7px 0;
  padding: 16px 18px 18px;
  background: #ffffff;
  border: 0;
  border-left: 2px solid #e5e7eb;
  border-radius: 0;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ctx-row__turns {
  display: flex;
  gap: 5px;
  padding: 0 0 12px;
  overflow-x: auto;
  border-bottom: 1px solid #f1f5f9;
}

.ctx-row__turn {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: baseline;
  gap: 5px;
  padding: 6px 10px;
  color: #6b7280;
  background: #f8fafc;
  border: 1px solid transparent;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
}

.ctx-row__turn small {
  color: #9ca3af;
  font-size: 11px;
}

.ctx-row__turn:hover {
  color: #374151;
  background: #e5e7eb;
}

.ctx-row__turn.selected {
  color: #111827;
  background: #ffffff;
  border-color: #cbd5e1;
  box-shadow: 0 1px 3px rgba(17, 24, 39, 0.08);
}

.ctx-row__section-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 11px;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
}

.ctx-row__section-count {
  margin-left: auto;
  color: #9ca3af;
  font-weight: 500;
  font-size: 12px;
}

.ctx-row__diff-stat {
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
}

.ctx-row__diff-stat--added,
.ctx-row__legend-item--added {
  color: #15803d;
}

.ctx-row__diff-stat--removed,
.ctx-row__legend-item--removed {
  color: #b91c1c;
}

.ctx-row__legend {
  display: flex;
  gap: 12px;
  margin: -3px 0 7px;
  color: #64748b;
  font-size: 11px;
}

.ctx-row__legend-item::before {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin: 0 4px 1px 0;
  border-radius: 50%;
  content: "";
}

.ctx-row__legend-item--added::before { background: #4ade80; }
.ctx-row__legend-item--removed::before { background: #f87171; }

.ctx-row__file-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ctx-row__file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  padding: 6px 10px;
  color: #374151;
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  font: 12px/1.5 "SF Mono", "JetBrains Mono", Consolas, "Microsoft YaHei Mono", monospace;
  transition: all 0.12s ease;
  cursor: default;
}

.ctx-row__file-chip:hover {
  border-color: #c7cdd4;
  background: #f9fafb;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transform: translateY(-0.5px);
}

.ctx-row__file-chip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ctx-row__file-icon-img {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  object-fit: contain;
  display: block;
}

.ctx-row__section--content {
  margin-top: 2px;
  padding-top: 16px;
  border-top: 1px solid #f1f5f9;
}

.ctx-row__content {
  max-height: 360px;
  margin: 0;
  padding: 14px 16px;
  overflow: auto;
  color: #1e293b;
  background: #fbfdff;
  border: 0;
  border-radius: 5px;
  box-shadow: inset 0 0 0 1px #edf2f7;
  font: 13px/1.8 "SF Mono", "JetBrains Mono", Consolas, "Microsoft YaHei Mono", monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ctx-row__diff-content code {
  display: block;
  min-height: 23px;
  padding: 1px 10px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ctx-row__diff-content .ctx-diff-added {
  color: #166534;
  background: #effcf3;
  box-shadow: inset 3px 0 #34d399;
}

.ctx-row__diff-content .ctx-diff-removed {
  color: #991b1b;
  background: #fff5f5;
  box-shadow: inset 3px 0 #f87171;
}

.ctx-row__diff-content .ctx-diff-unchanged {
  color: #94a3b8;
  background: #fbfdff;
}

.ctx-row__content::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.ctx-row__content::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.ctx-row__content::-webkit-scrollbar-track {
  background: transparent;
}

/* 展开/折叠动画 */
.ctx-expand-enter-active,
.ctx-expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.ctx-expand-enter-from,
.ctx-expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
  max-height: 0;
  margin-top: 0;
  margin-bottom: 0;
}

.ctx-expand-enter-to,
.ctx-expand-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 800px;
}

/* 暗色主题 */
:global([data-app-theme="dark"] .ctx-row__trigger:hover){
  background: rgba(255, 255, 255, 0.05);
}

:global([data-app-theme="dark"] .ctx-row__icon){
  background: transparent !important;
}

:global([data-app-theme="dark"] .ctx-row__title){
  color: #d1d5db;
}

:global([data-app-theme="dark"] .ctx-row__badge){
  color: #9ca3af;
  background: rgba(255, 255, 255, 0.07);
}

:global([data-app-theme="dark"] .ctx-row__badge--files){
  color: #d1d5db;
}

:global([data-app-theme="dark"] .ctx-row__chevron){
  color: #6b7280;
}

:global([data-app-theme="dark"] .ctx-row__body){
  background: #171b21;
  border-left-color: #374151;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.18);
}

:global([data-app-theme="dark"] .ctx-row__turns){
  border-bottom-color: #28303a;
}

:global([data-app-theme="dark"] .ctx-row__turn){
  color: #aab4c0;
  background: #20262e;
}

:global([data-app-theme="dark"] .ctx-row__turn:hover){
  color: #e5e7eb;
  background: #2b3440;
}

:global([data-app-theme="dark"] .ctx-row__turn.selected){
  color: #f3f4f6;
  background: #252d37;
  border-color: #4b5563;
}

:global([data-app-theme="dark"] .ctx-row__section-header){
  color: #9ca3af;
}

:global([data-app-theme="dark"] .ctx-row__section-count){
  color: #6b7280;
}

:global([data-app-theme="dark"] .ctx-row__file-chip){
  color: #d1d5db;
  background: #232323;
  border-color: #333;
}

:global([data-app-theme="dark"] .ctx-row__file-chip:hover){
  border-color: #444;
  background: #2a2a2a;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

:global([data-app-theme="dark"] .ctx-row__section--content){
  border-top-color: #28303a;
}

:global([data-app-theme="dark"] .ctx-row__content){
  color: #dbe4ee;
  background: #14181d;
  box-shadow: inset 0 0 0 1px #28303a;
}

:global([data-app-theme="dark"] .ctx-row__diff-content .ctx-diff-added){
  color: #86efac;
  background: #14291d;
}

:global([data-app-theme="dark"] .ctx-row__diff-content .ctx-diff-removed){
  color: #fda4af;
  background: #321b20;
}

:global([data-app-theme="dark"] .ctx-row__diff-content .ctx-diff-unchanged){
  color: #718096;
  background: #14181d;
}

:global([data-app-theme="dark"] .ctx-row__content::-webkit-scrollbar-thumb){
  background: #404040;
}

@media (prefers-reduced-motion: reduce) {
  .ctx-expand-enter-active,
  .ctx-expand-leave-active {
    transition: none;
  }

  .ctx-row__file-chip {
    transition: none;
  }

  .ctx-row__file-chip:hover {
    transform: none;
  }
}
</style>
