<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import DiffPreviewPopover from "./DiffPreviewPopover.vue";
import type { ChangeFile } from "./types";

const props = defineProps<{
  files: ChangeFile[];
  workspacePath: string;
  workspaceId?: string;
  runId?: string;
  busy?: boolean;
}>();

const emit = defineEmits<{
  openFile: [path: string];
  undo: [];
  review: [];
}>();

const { t } = useI18n({ useScope: "global" });

const totalAdditions = computed(() => props.files.reduce((sum, file) => sum + Number(file.additions ?? 0), 0));
const totalDeletions = computed(() => props.files.reduce((sum, file) => sum + Number(file.deletions ?? 0), 0));

/** 展示工作区相对路径，路径本就相对或缺省工作区时原样返回。 */
function relativePath(path: string): string {
  if (!props.workspacePath) return path;
  const normalized = path.replace(/\\/g, "/");
  const workspace = props.workspacePath.replace(/\\/g, "/").replace(/\/+$/, "");
  return normalized.startsWith(`${workspace}/`) ? normalized.slice(workspace.length + 1) : normalized;
}

// 文件行 hover/focus 时在该行上方浮出差异预览
const preview = ref<{ file: ChangeFile; style: Record<string, string> } | null>(null);
function openPreview(file: ChangeFile, event: MouseEvent | FocusEvent) {
  const anchor = event.currentTarget as HTMLElement | null;
  if (!anchor) return;
  const rect = anchor.getBoundingClientRect();
  const width = Math.min(660, window.innerWidth - 24);
  preview.value = {
    file,
    style: {
      left: `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`,
      bottom: `${Math.max(8, window.innerHeight - rect.top + 6)}px`,
    },
  };
}
function closePreview() { preview.value = null; }
function handlePreviewFocusOut(event: FocusEvent) {
  const next = event.relatedTarget as HTMLElement | null;
  if (next?.closest(".edited-files-card__row")) return;
  closePreview();
}
</script>

<template>
  <div class="edited-files-card">
    <header class="edited-files-card__head">
      <span class="edited-files-card__icon"><AppIcon name="FileDiff" :size="18" /></span>
      <span class="edited-files-card__title">
        <b>{{ t("timeline.changes.editedTitle", { count: files.length }) }}</b>
        <small class="edited-files-card__stats">
          <span class="additions">+{{ totalAdditions }}</span>
          <span class="deletions">-{{ totalDeletions }}</span>
        </small>
      </span>
      <span class="edited-files-card__actions">
        <button
          type="button"
          class="edited-files-card__undo"
          :disabled="busy"
          @click="emit('undo')"
        >
          <span>{{ t("timeline.changes.undo") }}</span>
          <AppIcon name="RotateCcw" :size="14" />
        </button>
        <button type="button" class="edited-files-card__review" @click="emit('review')">
          {{ t("timeline.changes.review") }}
        </button>
      </span>
    </header>

    <ul class="edited-files-card__list">
      <li v-for="file in files" :key="file.path">
        <button
          type="button"
          class="edited-files-card__row"
          @click="emit('openFile', file.path)"
          @mouseenter="openPreview(file, $event)"
          @mouseleave="closePreview"
          @focusin="openPreview(file, $event)"
          @focusout="handlePreviewFocusOut"
        >
          <span class="edited-files-card__path" :title="file.path">{{ relativePath(file.path) }}</span>
          <span class="edited-files-card__row-stats">
            <span v-if="(file.additions ?? 0) > 0" class="additions">+{{ file.additions }}</span>
            <span v-if="(file.deletions ?? 0) > 0" class="deletions">-{{ file.deletions }}</span>
          </span>
        </button>
      </li>
    </ul>

    <Teleport to="body">
      <DiffPreviewPopover
        v-if="preview"
        :workspace-id="workspaceId ?? ''"
        :run-id="runId ?? ''"
        :path="preview.file.path"
        :additions="preview.file.additions ?? 0"
        :deletions="preview.file.deletions ?? 0"
        :style="preview.style"
      />
    </Teleport>
  </div>
</template>

<style scoped>
.edited-files-card {
  display: flex;
  flex: 1 1 100%;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #e6e8ec;
  border-radius: 12px;
}

.edited-files-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
}

.edited-files-card__icon {
  display: grid;
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  place-items: center;
  color: #4b5563;
  background: #f1f3f5;
  border-radius: 8px;
}

.edited-files-card__title {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.edited-files-card__title b {
  overflow: hidden;
  color: #1f2328;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edited-files-card__stats {
  display: flex;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
}

.edited-files-card__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.edited-files-card__undo {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 8px;
  color: #4b5563;
  background: transparent;
  border: 0;
  border-radius: 7px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.edited-files-card__undo:hover:not(:disabled) {
  color: #1f2328;
  background: #f1f3f5;
}

.edited-files-card__undo:disabled {
  opacity: 0.5;
  cursor: default;
}

.edited-files-card__review {
  padding: 5px 13px;
  color: #1f2328;
  background: #ffffff;
  border: 1px solid #d6dae0;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.12s ease, border-color 0.12s ease;
}

.edited-files-card__review:hover {
  background: #f6f7f9;
  border-color: #c2c8d0;
}

.edited-files-card__list {
  max-height: 264px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
  border-top: 1px solid #eceef1;
}

.edited-files-card__row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 9px 12px;
  color: #4b5563;
  background: transparent;
  border: 0;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.1s ease;
}

.edited-files-card__row:hover {
  background: #f7f8fa;
}

.edited-files-card__list li + li .edited-files-card__row {
  border-top: 1px solid #f4f5f7;
}

.edited-files-card__path {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edited-files-card__row-stats {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
}

.edited-files-card__stats .additions,
.edited-files-card__row-stats .additions {
  color: #16a34a;
}

.edited-files-card__stats .deletions,
.edited-files-card__row-stats .deletions {
  color: #dc2626;
}

/* 暗色主题 */
:global([data-app-theme="dark"] .edited-files-card) {
  background: #1b1f24;
  border-color: #2f353c;
}

:global([data-app-theme="dark"] .edited-files-card__icon) {
  color: #c7ccd2;
  background: #2a3037;
}

:global([data-app-theme="dark"] .edited-files-card__title b) {
  color: #eef1f4;
}

:global([data-app-theme="dark"] .edited-files-card__undo) {
  color: #b7bec6;
}

:global([data-app-theme="dark"] .edited-files-card__undo:hover:not(:disabled)) {
  color: #f1f4f7;
  background: #2a3037;
}

:global([data-app-theme="dark"] .edited-files-card__review) {
  color: #e6e9ed;
  background: #23282e;
  border-color: #3a4149;
}

:global([data-app-theme="dark"] .edited-files-card__review:hover) {
  background: #2b3138;
  border-color: #4a525b;
}

:global([data-app-theme="dark"] .edited-files-card__list) {
  border-top-color: #2b3138;
}

:global([data-app-theme="dark"] .edited-files-card__row) {
  color: #aab2bb;
}

:global([data-app-theme="dark"] .edited-files-card__row:hover) {
  background: #23282e;
}

:global([data-app-theme="dark"] .edited-files-card__list li + li .edited-files-card__row) {
  border-top-color: #23282e;
}

:global([data-app-theme="dark"] .edited-files-card__stats .additions),
:global([data-app-theme="dark"] .edited-files-card__row-stats .additions) {
  color: #4ade80;
}

:global([data-app-theme="dark"] .edited-files-card__stats .deletions),
:global([data-app-theme="dark"] .edited-files-card__row-stats .deletions) {
  color: #f87171;
}
</style>
