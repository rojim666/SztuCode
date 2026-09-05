<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import type { ChangeFile } from "./types";

const props = defineProps<{
  files: ChangeFile[];
  workspacePath: string;
}>();
const { t } = useI18n({ useScope: "global" });

const emit = defineEmits<{
  openFile: [path: string];
  openAll: [];
}>();

const open = ref(false);

const totalAdditions = computed(() => props.files.reduce((sum, f) => sum + Number(f.additions ?? 0), 0));
const totalDeletions = computed(() => props.files.reduce((sum, f) => sum + Number(f.deletions ?? 0), 0));
const hasStats = computed(() => totalAdditions.value > 0 || totalDeletions.value > 0);

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function relativePath(path: string): string {
  if (!props.workspacePath) return path;
  const normalized = path.replace(/\//g, "\\");
  const ws = props.workspacePath.replace(/\//g, "\\");
  if (normalized.startsWith(ws)) {
    const rel = normalized.slice(ws.length);
    return rel.replace(/^\\+/, "");
  }
  return path;
}
</script>

<template>
  <div class="file-changes-badge" :class="{ open }">
    <!-- 触发区为容器 + 两个兄弟按钮：避免 button 嵌套 button 的非法 HTML -->
    <div class="file-changes-badge__trigger">
      <button type="button" class="file-changes-badge__toggle" :aria-expanded="open" @click="open = !open">
        <span class="file-changes-badge__icon">
          <AppIcon name="FileDiff" :size="16" />
        </span>
        <span class="file-changes-badge__label">
          <b>{{ files.length }}</b> {{ t('timeline.changes.filesSuffix') }}
        </span>
        <AppIcon name="ChevronDown" class="file-changes-badge__chevron" :size="16" />
        <span v-if="hasStats" class="file-changes-badge__stats">
          <span class="additions">+{{ totalAdditions }}</span>
          <span class="deletions">-{{ totalDeletions }}</span>
        </span>
      </button>
      <span class="file-changes-badge__divider" />
      <button type="button" class="file-changes-badge__open-all" :title="t('timeline.changes.openAll')" :aria-label="t('timeline.changes.openAll')" @click.stop="emit('openAll')">
        <AppIcon name="ExternalLink" :size="16" />
      </button>
    </div>

    <div v-if="open" class="file-changes-badge__list">
      <button
        v-for="file in files"
        :key="file.path"
        class="file-changes-badge__item"
        @click="emit('openFile', file.path)"
      >
        <span class="file-changes-badge__item-icon">
          <AppIcon name="FileDiff" :size="14" />
        </span>
        <span class="file-changes-badge__item-name">{{ fileName(file.path) }}</span>
        <span class="file-changes-badge__item-path" :title="file.path">.{{ relativePath(file.path) }}</span>
        <span v-if="(file.additions ?? 0) > 0 || (file.deletions ?? 0) > 0" class="file-changes-badge__item-stats">
          <span v-if="(file.additions ?? 0) > 0" class="additions">+{{ file.additions }}</span>
          <span v-if="(file.deletions ?? 0) > 0" class="deletions">-{{ file.deletions }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.file-changes-badge {
  display: inline-flex;
  flex-direction: column;
  min-width: 0;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.15s ease;
}

.file-changes-badge:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.file-changes-badge__trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 4px 8px 10px;
}

/* 展开/收起主按钮：占满触发区左侧，样式与原 trigger 一致 */
.file-changes-badge__toggle {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  align-items: center;
  gap: 8px;
  padding: 0;
  background: transparent;
  border: 0;
  color: #334155;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
}

.file-changes-badge__icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  color: #64748b;
  background: #e2e8f0;
  border-radius: 8px;
}

.file-changes-badge__label {
  flex: 0 1 auto;
  white-space: nowrap;
}

.file-changes-badge__label b {
  font-weight: 700;
  color: #1e293b;
}

.file-changes-badge__chevron {
  flex: 0 0 auto;
  color: #94a3b8;
  transition: transform 0.2s ease;
}

.file-changes-badge.open .file-changes-badge__chevron {
  transform: rotate(180deg);
}

.file-changes-badge__stats {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 0 4px;
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 600;
}

.file-changes-badge__stats .additions {
  color: #16a34a;
}

.file-changes-badge__stats .deletions {
  color: #dc2626;
}

.file-changes-badge__divider {
  width: 1px;
  height: 20px;
  background: #e2e8f0;
  flex: 0 0 auto;
}

.file-changes-badge__open-all {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  color: #64748b;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.file-changes-badge__open-all:hover {
  color: #2563eb;
  background: #eff6ff;
}

.file-changes-badge__list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid #e2e8f0;
  background: #fff;
}

.file-changes-badge__item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 6px 12px 6px 10px;
  background: transparent;
  border: 0;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: background 0.1s ease;
}

.file-changes-badge__item:hover {
  background: #f1f5f9;
}

.file-changes-badge__item + .file-changes-badge__item {
  border-top: 1px solid #f1f5f9;
}

.file-changes-badge__item-icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  flex: 0 0 auto;
  color: #f59e0b;
  background: #fef3c7;
  border-radius: 6px;
}

.file-changes-badge__item-name {
  flex: 0 0 auto;
  font-weight: 600;
  color: #1e293b;
}

.file-changes-badge__item-path {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  color: #94a3b8;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-changes-badge__item-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 600;
}

.file-changes-badge__item-stats .additions {
  color: #16a34a;
}

.file-changes-badge__item-stats .deletions {
  color: #dc2626;
}

/* 暗色主题 */
:global([data-app-theme="dark"] .file-changes-badge){
  background: #1e293b;
  border-color: #334155;
}

:global([data-app-theme="dark"] .file-changes-badge:hover){
  border-color: #475569;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

:global([data-app-theme="dark"] .file-changes-badge__trigger){
  color: #cbd5e1;
}

:global([data-app-theme="dark"] .file-changes-badge__toggle){
  color: #cbd5e1;
}

:global([data-app-theme="dark"] .file-changes-badge__icon){
  color: #94a3b8;
  background: #334155;
}

:global([data-app-theme="dark"] .file-changes-badge__label b){
  color: #f1f5f9;
}

:global([data-app-theme="dark"] .file-changes-badge__chevron){
  color: #64748b;
}

:global([data-app-theme="dark"] .file-changes-badge__divider){
  background: #334155;
}

:global([data-app-theme="dark"] .file-changes-badge__open-all){
  color: #94a3b8;
}

:global([data-app-theme="dark"] .file-changes-badge__open-all:hover){
  color: #60a5fa;
  background: rgba(37, 99, 235, 0.15);
}

:global([data-app-theme="dark"] .file-changes-badge__list){
  border-top-color: #334155;
  background: #0f172a;
}

:global([data-app-theme="dark"] .file-changes-badge__item){
  color: #94a3b8;
}

:global([data-app-theme="dark"] .file-changes-badge__item:hover){
  background: #1e293b;
}

:global([data-app-theme="dark"] .file-changes-badge__item + .file-changes-badge__item){
  border-top-color: #1e293b;
}

:global([data-app-theme="dark"] .file-changes-badge__item-icon){
  color: #fbbf24;
  background: rgba(245, 158, 11, 0.15);
}

:global([data-app-theme="dark"] .file-changes-badge__item-name){
  color: #f1f5f9;
}

:global([data-app-theme="dark"] .file-changes-badge__item-path){
  color: #64748b;
}
</style>
