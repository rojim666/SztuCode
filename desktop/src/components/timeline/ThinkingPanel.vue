<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import { reasoningSummary } from "../../utils/reasoningSummary";

const props = defineProps<{ text?: string; completed?: boolean }>();
const { t } = useI18n({ useScope: "global" });
const open = ref(false);
const initialText = props.text ?? "";
const displayedText = ref(props.completed ? initialText : "");
let targetCharacters = Array.from(initialText);
let displayedCount = Array.from(displayedText.value).length;
let playbackFrame: number | null = null;

// 大块 thinking 到达时按顺序快速追赶。单帧最多加入 12 个字符，既避免整段跳到末尾，
// 又能让较长积压在约 1 秒内赶上实时输出。
function revealCount(remaining: number): number {
  return Math.min(12, Math.max(1, Math.ceil(remaining / 18)));
}

function advancePlayback() {
  playbackFrame = null;
  const remaining = targetCharacters.length - displayedCount;
  if (remaining <= 0) return;
  displayedCount += revealCount(remaining);
  displayedText.value = targetCharacters.slice(0, displayedCount).join("");
  if (displayedCount < targetCharacters.length) playbackFrame = requestAnimationFrame(advancePlayback);
}

function schedulePlayback() {
  if (playbackFrame !== null || displayedCount >= targetCharacters.length) return;
  playbackFrame = requestAnimationFrame(advancePlayback);
}

watch(() => props.text ?? "", (value) => {
  targetCharacters = Array.from(value);
  if (!value.startsWith(displayedText.value)) {
    displayedCount = 0;
    displayedText.value = "";
  }
  schedulePlayback();
});

watch(() => props.completed, () => schedulePlayback());
onBeforeUnmount(() => {
  if (playbackFrame !== null) cancelAnimationFrame(playbackFrame);
});

if (!props.completed && targetCharacters.length) schedulePlayback();

const catchingUp = computed(() => displayedText.value !== (props.text ?? ""));
const running = computed(() => !props.completed || catchingUp.value);
const label = computed(() => running.value ? t("timeline.thinking.current") : t("timeline.thinking.notes"));

// 折叠摘要（借鉴 dsh ReasoningRow）：流式中显示最后一行非空文本跟随输出，
// 结算后显示首行作为稳定标题 —— 折叠态渲染代价恒定，与文本总长度无关
const summary = computed(() => reasoningSummary(displayedText.value, running.value));

// 每次增量渲染后立即跟到摘要末尾；结算后回到行首。
// flush: post 保证测量的是本次文字更新后的 DOM。
const summaryRef = ref<HTMLElement | null>(null);
watch([summary, running], () => {
  const element = summaryRef.value;
  if (element === null) return;
  element.scrollLeft = running.value ? element.scrollWidth - element.clientWidth : 0;
}, { flush: "post" });
</script>

<template>
  <section v-if="text" class="thinking-panel" :data-state="running ? 'running' : 'ok'" :class="{ open }">
    <button type="button" :aria-label="label" :aria-expanded="open" @click="open = !open">
      <AppIcon name="BrainCircuit" class="thinking-panel__icon" :size="14" />
      <span class="thinking-panel__label">{{ t('timeline.thinking.think') }}</span>
      <span class="timeline-row__separator">·</span>
      <span ref="summaryRef" class="thinking-panel__preview" :data-follow-end="running || undefined">{{ summary }}</span>
      <AppIcon name="ChevronDown" class="timeline-row__chevron" :size="13" />
    </button>
    <pre v-if="open" class="thinking-panel__details">{{ displayedText }}</pre>
  </section>
</template>
