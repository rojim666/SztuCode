<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Brain, ChevronRight, LoaderCircle } from "@lucide/vue";
import { reasoningSummary } from "../../utils/reasoningSummary";

const props = defineProps<{
  text: string;
  running?: boolean;
  completed?: boolean;
  defaultOpen?: boolean;
}>();
const { t } = useI18n({ useScope: "global" });

const open = ref(!!props.defaultOpen);
const userToggled = ref(false);

// 父组件切换历史展开/折叠时，同步默认打开状态；用户手动点击过则尊重用户选择
watch(() => props.defaultOpen, (val) => {
  if (!userToggled.value) open.value = !!val;
});

watch(() => props.running, (isRunning, wasRunning) => {
  if (isRunning) { open.value = false; userToggled.value = false; }
  else if (wasRunning && props.completed) { open.value = !!props.defaultOpen; userToggled.value = false; }
});

// 思考过程快速播放
const displayed = ref(props.completed ? props.text : "");
let chars = Array.from(props.text);
let shown = Array.from(displayed.value).length;
let frame: number | null = null;

function step() {
  frame = null;
  const remaining = chars.length - shown;
  if (remaining <= 0) return;
  const take = Math.min(18, Math.max(1, Math.ceil(remaining / 14)));
  shown += take;
  displayed.value = chars.slice(0, shown).join("");
  if (shown < chars.length) frame = requestAnimationFrame(step);
}

function schedule() {
  if (frame !== null || shown >= chars.length) return;
  frame = requestAnimationFrame(step);
}

watch(() => props.text, (val) => {
  chars = Array.from(val);
  if (!val.startsWith(displayed.value)) {
    shown = 0;
    displayed.value = "";
  }
  schedule();
});

watch(() => props.completed, () => schedule());
onBeforeUnmount(() => { if (frame !== null) cancelAnimationFrame(frame); });
if (!props.completed && chars.length) schedule();

const catchingUp = computed(() => displayed.value !== props.text);
const thinkingActive = computed(() => props.running || catchingUp.value);
const preview = computed(() => reasoningSummary(displayed.value, thinkingActive.value));
</script>

<template>
  <div class="thinking-block" :class="{ open, running: thinkingActive }">
    <button
      type="button"
      class="thinking-block__trigger"
      :aria-expanded="open"
      @click="userToggled = true; open = !open"
    >
      <span class="thinking-block__icon">
        <LoaderCircle v-if="thinkingActive" class="spin" :size="14" />
        <Brain v-else :size="14" />
      </span>
      <span class="thinking-block__label">{{ t('timeline.thinking.label') }}</span>
      <span v-if="!open && thinkingActive" ref="previewRef" class="thinking-block__preview">{{ preview }}</span>
      <ChevronRight class="thinking-block__chevron" :size="12" />
    </button>

    <transition name="think-expand">
      <div v-if="open" class="thinking-block__body">
        <div class="thinking-block__bubble">{{ displayed }}</div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.thinking-block {
  margin: 4px 0;
  font-size: 13px;
}

.thinking-block__trigger {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 2px 4px;
  margin: 0 -4px;
  color: #8c9299;
  background: transparent;
  border: 0;
  border-radius: 4px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s ease;
}

.thinking-block__trigger:hover {
  background: rgba(0, 0, 0, 0.03);
}

.thinking-block__icon {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  color: #8c9299;
}

.thinking-block.running .thinking-block__icon {
  color: #6366f1;
}

.thinking-block__icon .spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.thinking-block__label {
  flex: 0 0 auto;
  color: #6b7280;
  font-weight: 500;
}

.thinking-block.running .thinking-block__label {
  color: #6366f1;
}

.thinking-block__preview {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: #9ca3af;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thinking-block__chevron {
  flex: 0 0 auto;
  margin-left: auto;
  color: #b0b5bc;
  transition: transform 0.15s ease;
}

.thinking-block.open .thinking-block__chevron {
  transform: rotate(90deg);
}

.thinking-block__body {
  margin: 4px 0;
  padding-left: 24px;
}

.thinking-block__bubble {
  padding: 10px 14px;
  color: #6b7280;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  border-radius: 10px;
  border-top-left-radius: 4px;
  font: 13px/1.7 var(--font-ui, "Microsoft YaHei UI"), -apple-system, BlinkMacSystemFont, sans-serif;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 300px;
  overflow: auto;
}

.thinking-block__bubble::-webkit-scrollbar {
  width: 5px;
}
.thinking-block__bubble::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

.think-expand-enter-active,
.think-expand-leave-active {
  transition: all 0.15s ease;
  overflow: hidden;
}
.think-expand-enter-from,
.think-expand-leave-to {
  opacity: 0;
  max-height: 0;
  transform: translateY(-3px);
}
.think-expand-enter-to,
.think-expand-leave-from {
  opacity: 1;
  max-height: 400px;
  transform: translateY(0);
}

/* 暗色主题 */
:global([data-app-theme="dark"]) .thinking-block__trigger:hover {
  background: rgba(255, 255, 255, 0.04);
}
:global([data-app-theme="dark"]) .thinking-block__icon { color: #6b7280; }
:global([data-app-theme="dark"]) .thinking-block.running .thinking-block__icon { color: #a5b4fc; }
:global([data-app-theme="dark"]) .thinking-block__label { color: #9ca3af; }
:global([data-app-theme="dark"]) .thinking-block.running .thinking-block__label { color: #a5b4fc; }
:global([data-app-theme="dark"]) .thinking-block__preview { color: #6b7280; }
:global([data-app-theme="dark"]) .thinking-block__chevron { color: #4b5563; }
:global([data-app-theme="dark"]) .thinking-block__bubble {
  color: #9ca3af;
  background: #1f2937;
  border-color: #374151;
}
:global([data-app-theme="dark"]) .thinking-block__bubble::-webkit-scrollbar-thumb {
  background: #4b5563;
}

@media (prefers-reduced-motion: reduce) {
  .think-expand-enter-active,
  .think-expand-leave-active { transition: none; }
  .thinking-block__icon .spin { animation: none; }
}
</style>
