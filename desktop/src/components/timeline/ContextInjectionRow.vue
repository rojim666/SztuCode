<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  Braces,
  ChevronDown,
  CornerUpLeft,
  FileClock,
  FileLock2,
  Folder,
  Image as FileImage,
  Info,
  ShieldAlert,
} from "@lucide/vue";
import type { ContextInjectionEntry } from "./types";
import { fileTypeIconUrl } from "../../utils/fileIcon";

const props = defineProps<{ entry: ContextInjectionEntry }>();
const { t } = useI18n({ useScope: "global" });
const open = ref(false);

// 来源标签取自语言包：computed 内调用 t，切换语言时自动重建
const sourceConfig = computed(() => {
  switch (props.entry.source) {
    case "intervention":
      return { icon: ShieldAlert, label: t("timeline.context.source.intervention"), color: "#b45309", bg: "#fef3c7" };
    case "steering":
      return { icon: CornerUpLeft, label: t("timeline.context.source.steering"), color: "#1d4ed8", bg: "#dbeafe" };
    case "compaction":
      return { icon: FileClock, label: t("timeline.context.source.compaction"), color: "#6b7280", bg: "#f3f4f6" };
    case "canvas":
      return { icon: Braces, label: t("timeline.context.source.canvas"), color: "#7c3aed", bg: "#ede9fe" };
    default:
      return { icon: Info, label: t("timeline.context.source.system"), color: "#4b5563", bg: "#f3f4f6" };
  }
});

const body = computed(() => props.entry.text ?? props.entry.preview);
const charLabel = computed(() =>
  props.entry.chars >= 1000 ? `${(props.entry.chars / 1000).toFixed(1)}k` : String(props.entry.chars),
);

// 解析文件列表
const files = computed(() => {
  const explicit = props.entry.files?.map((file) => file.trim()).filter(Boolean) ?? [];
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
    return { kind: "lucide" as const, icon: Folder, color: "#d97706" };
  }
  const ext = lower.includes(".") ? lower.split(".").pop()! : "";
  const base = lower.split(/[\\/]/).pop()!;
  if (!ext && base.length > 0) {
    return { kind: "lucide" as const, icon: Folder, color: "#d97706" };
  }
  // lock 文件
  if (ext === "lock") {
    return { kind: "lucide" as const, icon: FileLock2, color: "#9ca3af" };
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
  return { kind: "lucide" as const, icon: FileImage, color: "#6b7280" };
};

// 预计算每个文件的图标信息，避免模板中重复调用
const fileItems = computed(() => {
  return files.value.slice(0, 48).map((path) => {
    const name = fileName(path);
    const icon = getFileIcon(name);
    return { path, name, icon };
  });
});

const ariaLabel = computed(() => t("timeline.context.ariaLabel", { label: props.entry.label, source: sourceConfig.value.label }));
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
      <span class="ctx-row__icon" :style="{ color: sourceConfig.color, background: sourceConfig.bg }">
        <component :is="sourceConfig.icon" :size="13" />
      </span>
      <span class="ctx-row__title">{{ entry.label }}</span>
      <span class="ctx-row__badge">{{ t('timeline.context.chars', { count: charLabel }) }}</span>
      <span v-if="files.length" class="ctx-row__badge ctx-row__badge--files">{{ t('timeline.context.filesCount', { count: files.length }) }}</span>
      <ChevronDown class="ctx-row__chevron" :size="13" />
    </button>

    <transition name="ctx-expand">
      <div v-if="open" class="ctx-row__body">
        <div v-if="files.length" class="ctx-row__section">
          <div class="ctx-row__section-header">
            <Folder :size="14" />
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
              <component
                v-else
                :is="item.icon.icon"
                :size="16"
                :style="{ color: item.icon.color }"
              />
              <span>{{ item.name }}</span>
            </div>
          </div>
        </div>
        <div v-if="body" class="ctx-row__section ctx-row__section--content">
          <div class="ctx-row__section-header">
            <component :is="sourceConfig.icon" :size="14" />
            <span>{{ t('timeline.context.injectedContent') }}</span>
          </div>
          <pre class="ctx-row__content">{{ body }}</pre>
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
  width: 22px;
  height: 22px;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 5px;
}

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
  padding: 14px 16px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ctx-row__section-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 9px;
  color: #4b5563;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}

.ctx-row__section-count {
  margin-left: auto;
  color: #9ca3af;
  font-weight: 500;
  font-size: 12px;
}

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
  padding: 5px 10px;
  color: #374151;
  background: #fff;
  border: 1px solid #e5e7eb;
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
  padding-top: 14px;
  border-top: 1px solid #f0f0f0;
}

.ctx-row__content {
  max-height: 280px;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  color: #374151;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font: 12px/1.7 "SF Mono", "JetBrains Mono", Consolas, "Microsoft YaHei Mono", monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ctx-row__content::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.ctx-row__content::-webkit-scrollbar-thumb {
  background: #d1d5db;
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
:global([data-app-theme="dark"]) .ctx-row__trigger:hover {
  background: rgba(255, 255, 255, 0.05);
}

:global([data-app-theme="dark"]) .ctx-row__title {
  color: #d1d5db;
}

:global([data-app-theme="dark"]) .ctx-row__badge {
  color: #9ca3af;
  background: rgba(255, 255, 255, 0.07);
}

:global([data-app-theme="dark"]) .ctx-row__badge--files {
  color: #d1d5db;
}

:global([data-app-theme="dark"]) .ctx-row__chevron {
  color: #6b7280;
}

:global([data-app-theme="dark"]) .ctx-row__body {
  background: #1a1a1a;
  border-color: #2a2a2a;
}

:global([data-app-theme="dark"]) .ctx-row__section-header {
  color: #9ca3af;
}

:global([data-app-theme="dark"]) .ctx-row__section-count {
  color: #6b7280;
}

:global([data-app-theme="dark"]) .ctx-row__file-chip {
  color: #d1d5db;
  background: #232323;
  border-color: #333;
}

:global([data-app-theme="dark"]) .ctx-row__file-chip:hover {
  border-color: #444;
  background: #2a2a2a;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

:global([data-app-theme="dark"]) .ctx-row__section--content {
  border-top-color: #2a2a2a;
}

:global([data-app-theme="dark"]) .ctx-row__content {
  color: #d1d5db;
  background: #171717;
  border-color: #333;
}

:global([data-app-theme="dark"]) .ctx-row__content::-webkit-scrollbar-thumb {
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
