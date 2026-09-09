<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { changeDiff } from "../../services/sztu-runtime";
import { parseDiffPreview, type DiffPreviewLine } from "../../utils/diffPreview";

const props = defineProps<{
  workspaceId: string;
  runId: string;
  path: string;
  additions: number;
  deletions: number;
}>();

const { t } = useI18n({ useScope: "global" });

const lines = ref<DiffPreviewLine[]>([]);
const loading = ref(true);
const failed = ref(false);

onMounted(async () => {
  if (!props.workspaceId) {
    loading.value = false;
    failed.value = true;
    return;
  }
  try {
    const diff = await changeDiff(props.workspaceId, props.path, props.runId || null);
    lines.value = parseDiffPreview(diff);
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="diff-preview-popover" role="tooltip">
    <header class="diff-preview-popover__head">
      <span class="diff-preview-popover__path" :title="path">{{ path }}</span>
      <span class="diff-preview-popover__stats">
        <span class="additions">+{{ additions }}</span>
        <span class="deletions">-{{ deletions }}</span>
      </span>
    </header>
    <div class="diff-preview-popover__body">
      <p v-if="loading" class="diff-preview-popover__status">{{ t("timeline.changes.previewLoading") }}</p>
      <p v-else-if="failed" class="diff-preview-popover__status">{{ t("timeline.changes.previewError") }}</p>
      <p v-else-if="!lines.length" class="diff-preview-popover__status">{{ t("timeline.changes.previewEmpty") }}</p>
      <pre v-else class="diff-preview-popover__pre"><code v-for="(line, index) in lines" :key="index" :class="line.kind"><span class="diff-preview-popover__gutter">{{ line.lineNo ?? "" }}</span><span class="diff-preview-popover__code">{{ line.text || " " }}</span></code></pre>
    </div>
  </div>
</template>

<style scoped>
.diff-preview-popover {
  position: fixed;
  z-index: 70;
  display: flex;
  width: 660px;
  max-width: calc(100vw - 24px);
  max-height: 380px;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #e6e8ec;
  border-radius: 10px;
  box-shadow: 0 14px 36px rgb(16 24 40 / 18%);
}

.diff-preview-popover__head {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid #eef0f2;
}

.diff-preview-popover__path {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  color: #1f2328;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diff-preview-popover__stats {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 600;
}

.diff-preview-popover__stats .additions { color: #16a34a; }
.diff-preview-popover__stats .deletions { color: #dc2626; }

.diff-preview-popover__body { flex: 1 1 auto; min-height: 0; overflow: auto; }

.diff-preview-popover__status {
  margin: 0;
  padding: 14px 12px;
  color: #8b929a;
  font-size: 12.5px;
}

.diff-preview-popover__pre {
  margin: 0;
  padding: 4px 0;
  color: #24292f;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 12px;
  line-height: 1.7;
  tab-size: 2;
}

.diff-preview-popover__pre code {
  display: flex;
  white-space: pre;
}

.diff-preview-popover__gutter {
  flex: 0 0 auto;
  width: 46px;
  padding-right: 10px;
  color: #9aa1a8;
  text-align: right;
  user-select: none;
}

.diff-preview-popover__code { flex: 1 1 auto; min-width: 0; padding-right: 12px; white-space: pre; }

.diff-preview-popover__pre code.add { background: #e9f7ee; box-shadow: inset 3px 0 #2ea043; }
.diff-preview-popover__pre code.del { background: #fdecec; box-shadow: inset 3px 0 #d1242f; }

/* 暗色主题 */
:global([data-app-theme="dark"] .diff-preview-popover) {
  background: #1b1f24;
  border-color: #2f353c;
  box-shadow: 0 14px 36px rgb(0 0 0 / 48%);
}

:global([data-app-theme="dark"] .diff-preview-popover__head) { border-bottom-color: #2b3138; }
:global([data-app-theme="dark"] .diff-preview-popover__path) { color: #e6e9ed; }
:global([data-app-theme="dark"] .diff-preview-popover__pre) { color: #c9d1d9; }
:global([data-app-theme="dark"] .diff-preview-popover__status) { color: #8b929a; }
:global([data-app-theme="dark"] .diff-preview-popover__gutter) { color: #6b737c; }
:global([data-app-theme="dark"] .diff-preview-popover__stats .additions) { color: #4ade80; }
:global([data-app-theme="dark"] .diff-preview-popover__stats .deletions) { color: #f87171; }
:global([data-app-theme="dark"] .diff-preview-popover__pre code.add) { background: #12261a; box-shadow: inset 3px 0 #3fb950; }
:global([data-app-theme="dark"] .diff-preview-popover__pre code.del) { background: #2a1416; box-shadow: inset 3px 0 #f85149; }
</style>
