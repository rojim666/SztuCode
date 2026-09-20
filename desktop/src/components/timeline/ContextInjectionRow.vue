<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import AgentLogo from "./AgentLogo.vue";
import type { ContextInjectionEntry, ToolCallEntry } from "./types";
import { fileTypeIconUrl } from "../../utils/fileIcon";
import { readContextFiles } from "../../utils/contextFiles";
import { contextLines, diffContext, previousContextIndex } from "../../utils/contextEvolution";

const props = defineProps<{ entries: ContextInjectionEntry[]; toolCalls: ToolCallEntry[]; workspacePath?: string; jevEnabled?: boolean }>();
// 已读文件记录是在工作区文件树中定位文件，而不是打开变更 diff（后者属于任务摘要）
const emit = defineEmits<{ openFileInTree: [path: string] }>();
const { t } = useI18n({ useScope: "global" });
const bodyId = useId();
const open = ref(false);
// null follows new snapshots; manually selected history keeps its stable ID.
const selectedId = ref<string | null>(null);
const selectedIndex = computed(() => {
  const index = props.entries.findIndex(item => item.id === selectedId.value);
  return index < 0 ? props.entries.length - 1 : index;
});
const entry = computed(() => props.entries[selectedIndex.value]);
const body = computed(() => entry.value?.text ?? entry.value?.preview ?? "");
const previousIndex = computed(() => previousContextIndex(props.entries, selectedIndex.value));
const previous = computed(() => props.entries[previousIndex.value]);
const mode = ref<"diff" | "full">("diff");
const lineLimit = ref(300);
const fileLimit = ref(12);
const query = ref("");
const copyState = ref<"idle" | "copied" | "copyFailed">("idle");
watch(() => props.entries.map(item => item.id), ids => {
  if (selectedId.value && !ids.includes(selectedId.value)) selectedId.value = null;
});
watch(() => entry.value?.id, () => { lineLimit.value = 300; copyState.value = "idle"; });
watch(mode, () => { lineLimit.value = 300; });
watch(query, () => { fileLimit.value = 12; });
const diff = computed(() => open.value && mode.value === "diff"
  ? diffContext(previous.value?.text ?? previous.value?.preview ?? "", body.value)
  : { rows: [], added: 0, removed: 0, coarse: false });
const contentRows = computed(() => !open.value ? [] : mode.value === "full"
  ? contextLines(body.value).map(text => ({ kind: "unchanged", text }))
  : diff.value.rows.filter(row => row.kind !== "unchanged"));
// Bound rendered output; copying preserves the exact, unformatted snapshot.
const visibleRows = computed(() => {
  let chars = 0;
  const rows = [];
  for (const row of contentRows.value.slice(0, lineLimit.value)) {
    const text = row.text.slice(0, 4000);
    if (chars + text.length > lineLimit.value * 400) break;
    rows.push({ ...row, text, clipped: text.length < row.text.length });
    chars += text.length;
  }
  return rows;
});
const files = computed(() => readContextFiles(props.toolCalls, props.workspacePath));
const filteredFiles = computed(() => files.value.filter(path => path.toLowerCase().includes(query.value.trim().toLowerCase())));
const fileItems = computed(() => filteredFiles.value.slice(0, fileLimit.value).map(path => ({
  path, name: path.split("/").pop() || path, icon: fileTypeIconUrl(path),
})));
const sourceLabel = (item: ContextInjectionEntry) => t("timeline.context.source." + item.source);
const chars = (item?: ContextInjectionEntry) => (item?.chars ?? 0).toLocaleString();
const charDelta = computed(() => (entry.value?.chars ?? 0) - (previous.value?.chars ?? 0));
async function copyContent() {
  const id = entry.value?.id;
  try {
    await navigator.clipboard.writeText(body.value);
    if (entry.value?.id === id) copyState.value = "copied";
  } catch { if (entry.value?.id === id) copyState.value = "copyFailed"; }
}
</script>

<template>
  <section v-if="entry" class="ctx-row" :class="{ open }">
    <button type="button" class="ctx-row__trigger" :aria-expanded="open" :aria-controls="bodyId" @click="open = !open">
      <AgentLogo :active="false" size="mini" />
      <span class="ctx-row__title">{{ t('timeline.context.evolution') }}</span>
      <span class="ctx-row__badge">{{ t('timeline.context.snapshots', { count: entries.length }) }}</span>
      <span class="ctx-row__badge">{{ t('timeline.context.filesCount', { count: files.length }) }}</span>
      <span v-if="jevEnabled" class="ctx-row__badge ctx-row__badge--jev" :title="t('settings.jev.title')">Jev</span>
      <AppIcon name="ChevronDown" class="ctx-row__chevron" :size="14" />
    </button>
    <div v-if="open" :id="bodyId" class="ctx-row__body">
      <div class="ctx-row__heading">
        <span>{{ t('timeline.context.snapshotHistory') }}</span>
        <button type="button" class="ctx-row__action" :aria-pressed="selectedId === null" @click="selectedId = null">
          {{ t(selectedId === null ? 'timeline.context.following' : 'timeline.context.followLatest') }}
        </button>
      </div>
      <div class="ctx-row__turns" role="group" :aria-label="t('timeline.context.snapshotHistory')">
        <button v-for="(item, index) in entries" :key="item.id" type="button" class="ctx-row__turn"
          :class="{ selected: index === selectedIndex }" :aria-pressed="index === selectedIndex"
          :title="item.label" @click="selectedId = item.id">
          <span>{{ t('timeline.context.snapshotNumber', { count: index + 1 }) }}</span>
          <small>{{ sourceLabel(item) }} · {{ t('timeline.context.chars', { count: chars(item) }) }}</small>
        </button>
      </div>
      <div class="ctx-row__summary">
        <strong>{{ entry.label || sourceLabel(entry) }}</strong>
        <span>{{ t('timeline.context.chars', { count: chars(entry) }) }}</span>
        <span v-if="previous">{{ t('timeline.context.charDelta', { count: (charDelta > 0 ? '+' : '') + charDelta.toLocaleString() }) }}</span>
      </div>
      <section class="ctx-row__section">
        <div class="ctx-row__toolbar">
          <div role="group" :aria-label="t('timeline.context.contentView')" class="ctx-row__modes">
            <button type="button" :aria-pressed="mode === 'diff'" @click="mode = 'diff'">{{ t('timeline.context.changes') }}</button>
            <button type="button" :aria-pressed="mode === 'full'" @click="mode = 'full'">{{ t('timeline.context.fullContent') }}</button>
          </div>
          <button type="button" class="ctx-row__action" :disabled="!body" @click="copyContent">{{ t('timeline.context.copy') }}</button>
          <span role="status">{{ copyState === 'idle' ? '' : t('timeline.context.' + copyState) }}</span>
        </div>
        <p class="ctx-row__hint" v-if="mode === 'diff'">
          {{ previous ? t('timeline.context.comparedWith', { count: previousIndex + 1 }) : t('timeline.context.initialSnapshot') }}
          <span class="ctx-row__added">+{{ diff.added }}</span> / <span class="ctx-row__removed">−{{ diff.removed }}</span>
          {{ t('timeline.context.lines') }}
        </p>
        <p v-if="diff.coarse && mode === 'diff'" class="ctx-row__hint">{{ t('timeline.context.coarseDiff') }}</p>
        <p v-if="!body" class="ctx-row__empty">{{ t('timeline.context.emptyContent') }}</p>
        <p v-else-if="!contentRows.length" class="ctx-row__empty">{{ t('timeline.context.unchanged') }}</p>
        <pre v-else class="ctx-row__content" tabindex="0" :aria-label="t('timeline.context.contentView')"><code v-for="(row, index) in visibleRows" :key="index" :class="'ctx-diff-' + row.kind">{{ mode === 'diff' ? (row.kind === 'added' ? '+ ' : '− ') : '' }}{{ row.text }}{{ row.clipped ? ' …' : '' }}{{ '\n' }}</code></pre>
        <p v-if="visibleRows.some(row => row.clipped)" class="ctx-row__hint">{{ t('timeline.context.longLines') }}</p>
        <button v-if="visibleRows.length < contentRows.length" type="button" class="ctx-row__action" @click="lineLimit += 300">
          {{ t('timeline.context.moreLines', { count: contentRows.length - visibleRows.length }) }}
        </button>
      </section>
      <section class="ctx-row__section ctx-row__files">
        <div class="ctx-row__heading"><strong>{{ t('timeline.context.readFiles') }}</strong><span>{{ files.length }}</span></div>
        <input v-if="files.length > 6" v-model="query" type="search" class="ctx-row__search" :placeholder="t('timeline.context.searchFiles')" :aria-label="t('timeline.context.searchFiles')" />
        <div v-if="fileItems.length" class="ctx-row__file-grid">
          <button v-for="item in fileItems" :key="item.path" type="button" class="ctx-row__file-chip" :title="item.path" @click="emit('openFileInTree', item.path)">
            <img v-if="item.icon" :src="item.icon" alt="" width="16" height="16" />
            <AppIcon v-else name="FileText" :size="16" />
            <span><b>{{ item.name }}</b><small>{{ item.path }}</small></span>
          </button>
        </div>
        <p v-else class="ctx-row__empty">{{ t(files.length ? 'timeline.context.noMatchingFiles' : 'timeline.context.noReadFiles') }}</p>
        <button v-if="filteredFiles.length > fileLimit" type="button" class="ctx-row__action" @click="fileLimit += 24">
          {{ t('timeline.context.moreFiles', { count: filteredFiles.length - fileLimit }) }}
        </button>
      </section>
    </div>
  </section>
</template>

<style scoped>
.ctx-row { margin: 6px 0; min-width: 0; font-size: 12px; color: var(--text-muted); }
.ctx-row button { cursor: pointer; font: inherit; }
.ctx-row button:focus-visible, .ctx-row input:focus-visible, .ctx-row pre:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ctx-row__trigger { display: flex; align-items: center; gap: 8px; width: 100%; min-height: 32px; padding: 4px 0; border: 0; background: transparent; color: var(--text-muted); text-align: left; flex-wrap: wrap; }
.ctx-row__title { color: var(--text); font-weight: 500; }
.ctx-row__badge { padding: 2px 7px; border-radius: 6px; background: var(--surface-soft); font-size: 11px; }
.ctx-row__badge--jev { color: var(--accent); background: var(--accent-soft); font-weight: 600; }
.ctx-row__chevron { margin-left: auto; transition: transform .15s; }
.open .ctx-row__chevron { transform: rotate(180deg); }
.ctx-row__body { margin-top: 8px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); min-width: 0; }
.ctx-row__heading, .ctx-row__toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ctx-row__heading { justify-content: space-between; }
.ctx-row__heading strong { color: var(--text); font-weight: 500; }
.ctx-row__action { padding: 4px 0; border: 0; background: transparent; color: var(--text-muted); }
.ctx-row__action:hover { color: var(--text); text-decoration: underline; }
.ctx-row__action[aria-pressed="true"] { color: var(--accent); }
.ctx-row__turns { display: flex; gap: 6px; overflow-x: auto; padding: 10px 2px; max-height: 110px; }
.ctx-row__turn { flex: 0 0 auto; display: grid; gap: 4px; padding: 8px 10px; background: var(--surface-soft); border: 1px solid transparent; border-radius: 6px; color: var(--text-muted); text-align: left; }
.ctx-row__turn small { font-size: 10px; }
.ctx-row__turn.selected { border-color: var(--border-strong); background: var(--surface-raised); color: var(--text); }
.ctx-row__summary { display: flex; gap: 10px; flex-wrap: wrap; padding: 4px 0 12px; font-size: 11px; }
.ctx-row__summary strong { color: var(--text); font-weight: 500; }
.ctx-row__modes { display: inline-flex; gap: 2px; border-radius: 6px; padding: 2px; background: var(--surface-soft); margin-right: auto; }
.ctx-row__modes button { padding: 5px 9px; border: 0; border-radius: 4px; background: transparent; color: var(--text-muted); }
.ctx-row__modes button[aria-pressed="true"] { color: var(--text); background: var(--surface-raised); }
.ctx-row__hint { margin: 9px 0; font-size: 11px; line-height: 1.6; }
.ctx-row__empty { padding: 12px 0; margin: 0; color: var(--text-muted); }
.ctx-row__content { max-height: 360px; margin: 8px 0; padding: 10px; overflow: auto; color: var(--text); background: var(--surface-soft); border-radius: 6px; font: 11px/1.7 Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; tab-size: 2; }
.ctx-row__content code { display: block; min-height: 1.7em; padding: 0 6px; }
.ctx-row__added, .ctx-diff-added { color: #237c45; }
.ctx-row__removed, .ctx-diff-removed { color: #b24444; }
.ctx-diff-added { background: #32965312; }
.ctx-diff-removed { background: #c04a4a12; }
.ctx-row__files { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 14px; }
.ctx-row__files .ctx-row__heading { margin-bottom: 10px; }
.ctx-row__search { width: 100%; box-sizing: border-box; margin: 0 0 10px; padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; color: var(--text); background: var(--surface-soft); font: inherit; }
.ctx-row__file-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: 6px; }
.ctx-row__file-chip { display: flex; align-items: center; gap: 8px; min-width: 0; padding: 8px; color: var(--text); border: 1px solid var(--border); border-radius: 6px; background: transparent; text-align: left; }
.ctx-row__file-chip:hover { background: var(--surface-soft); border-color: var(--border-strong); }
.ctx-row__file-chip > img, .ctx-row__file-chip > svg { flex: 0 0 auto; }
.ctx-row__file-chip span { display: grid; gap: 3px; min-width: 0; }
.ctx-row__file-chip b, .ctx-row__file-chip small { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.ctx-row__file-chip b { font-weight: 500; }
.ctx-row__file-chip small { color: var(--text-muted); font-size: 10px; }
:global([data-app-theme="dark"] .ctx-row__added), :global([data-app-theme="dark"] .ctx-diff-added) { color: #86d5a2; }
:global([data-app-theme="dark"] .ctx-row__removed), :global([data-app-theme="dark"] .ctx-diff-removed) { color: #efa0a0; }
@media (prefers-reduced-motion: reduce) { .ctx-row__chevron { transition: none; } }
</style>
