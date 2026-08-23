<script setup lang="ts">
import { computed, ref } from "vue";
import { Braces, ChevronDown, CornerUpLeft, FileClock, Info, ShieldAlert } from "@lucide/vue";
import type { ContextInjectionEntry } from "./types";

const props = defineProps<{ entry: ContextInjectionEntry }>();
const open = ref(false);

const icon = computed(() => {
  if (props.entry.source === "intervention") return ShieldAlert;
  if (props.entry.source === "steering") return CornerUpLeft;
  if (props.entry.source === "compaction") return FileClock;
  if (props.entry.source === "canvas") return Braces;
  return Info;
});
const tag = computed(() => ({
  compaction: "压缩",
  canvas: "进度",
  intervention: "干预",
  steering: "追加",
  system: "注入",
}[props.entry.source] ?? "上下文"));
const body = computed(() => props.entry.text ?? props.entry.preview);
const charLabel = computed(() => props.entry.chars >= 1000 ? `${(props.entry.chars / 1000).toFixed(1)}k` : String(props.entry.chars));
// 折叠头一行摘要：来源标签 + 注入摘要（借鉴 dsh 标题 + 来源标签 + notice 一行摘要）
const summary = computed(() => {
  const preview = props.entry.preview?.trim();
  return preview ? `${tag.value} · ${preview}` : tag.value;
});
const ariaLabel = computed(() => `${props.entry.label}（${tag.value}）`);
</script>

<template>
  <!-- 复用 Tool calls 的 disclosure chrome（借鉴 dsh ContextInjectionRow）：
       与 Think/ToolCall 行同一 34px 节奏与分隔符形状，展开体为 141px 高代码风格滚动区 -->
  <section class="context-injection-row tool-call-event" :class="`ctx-${entry.source}`">
    <button type="button" :aria-label="ariaLabel" :aria-expanded="open" @click="open = !open">
      <component :is="icon" :size="14" />
      <span class="tool-call-event__action">{{ entry.label }}</span>
      <span class="timeline-row__separator">·</span>
      <span class="tool-call-event__detail">{{ summary }}</span>
      <ChevronDown class="timeline-row__chevron" :size="13" />
    </button>
    <div v-if="open" class="tool-call-event__details" aria-label="注入内容">
      <b>注入内容 · {{ charLabel }} 字符</b>
      <pre class="context-injection-row__body">{{ body }}</pre>
    </div>
  </section>
</template>
