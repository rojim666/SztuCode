<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { semanticIndex, type SemanticIndexStatus } from "../services/sztu-runtime";

const props = defineProps<{ workspaceId: string; connected: boolean }>();
const { t } = useI18n();
const status = ref<SemanticIndexStatus | null>(null);
const error = ref("");
const pending = ref(false);
const expanded = ref(false);
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const indexing = computed(() => status.value?.state === "indexing");
const label = computed(() => t(`app.semanticIndex.${error.value ? 'unavailable' : status.value?.state ?? 'not_started'}`));

async function refresh(token: number) {
  try {
    const next = await semanticIndex(props.workspaceId);
    if (token !== generation) return;
    status.value = next;
    error.value = "";
  } catch (cause) { if (token === generation) error.value = String(cause); }
  finally { if (token === generation) timer = setTimeout(() => void refresh(token), indexing.value ? 1000 : 5000); }
}

async function change(action: "build" | "clear") {
  const token = generation;
  pending.value = true;
  try {
    const next = await semanticIndex(props.workspaceId, action);
    if (token === generation) { status.value = next; error.value = ""; }
  } catch (cause) { if (token === generation) error.value = String(cause); }
  finally { if (token === generation) pending.value = false; }
}

watch(() => [props.workspaceId, props.connected], () => {
  generation += 1;
  clearTimeout(timer);
  status.value = null;
  error.value = "";
  pending.value = false;
  if (props.workspaceId && props.connected) void refresh(generation);
}, { immediate: true });
onBeforeUnmount(() => { generation += 1; clearTimeout(timer); });
</script>

<template>
  <div v-if="connected" class="semantic-index">
    <button type="button" :aria-expanded="expanded" @click="expanded = !expanded">{{ label }}<span v-if="indexing && status?.total"> {{ status.processed }}/{{ status.total }}</span></button>
    <section v-if="expanded" :aria-label="t('app.semanticIndex.manage')" class="semantic-index__panel">
      <strong>{{ label }}</strong>
      <p>{{ t('app.semanticIndex.counts', { files: status?.files ?? 0, chunks: status?.chunks ?? 0 }) }}</p>
      <progress v-if="indexing" :max="status?.total || 1" :value="status?.total ? status.processed : undefined" />
      <p v-if="status?.error || error" role="alert">{{ status?.error || error }}</p>
      <p>{{ t('app.semanticIndex.hint') }}</p>
      <button type="button" :disabled="pending || indexing" @click="change('build')">{{ t('app.semanticIndex.build') }}</button>
      <button type="button" :disabled="pending || indexing" @click="change('clear')">{{ t('app.semanticIndex.clear') }}</button>
    </section>
  </div>
</template>

<style scoped>
.semantic-index { position: relative; margin-left: auto; padding: 5px 14px; font-size: 12px; }
button { color: inherit; background: transparent; border: 1px solid #8884; border-radius: 5px; padding: 4px 8px; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.semantic-index__panel { position: absolute; right: 14px; bottom: 100%; z-index: 30; width: min(320px, 80vw); padding: 14px; border: 1px solid #8885; border-radius: 8px; background: var(--sztu-surface, #fff); box-shadow: 0 6px 24px #0003; }
.semantic-index__panel p { overflow-wrap: anywhere; margin: 8px 0; }
.semantic-index__panel button + button { margin-left: 8px; }
:global([data-app-theme="dark"]) .semantic-index__panel { background: #22272b; color: #e6e6e6; }
progress { width: 100%; }
</style>
