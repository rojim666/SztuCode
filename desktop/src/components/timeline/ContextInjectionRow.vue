<script setup lang="ts">
import { computed, ref } from "vue";
import { Braces, ChevronDown, CornerUpLeft, FileClock, FileText, Info, ShieldAlert } from "@lucide/vue";
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
// 旧事件没有 files 字段，从注入正文中的 Markdown 文件标题和 Git 状态兜底推断。
const files = computed(() => {
  const explicit = props.entry.files?.map((file) => file.trim()).filter(Boolean) ?? [];
  const inferred = [...body.value.matchAll(/^##\s+([^\n]+)$/gm)]
    .map((match) => match[1].trim())
    .filter((value) => /(?:^|[\\/])[^\\/]+\.[a-z0-9]{1,12}$/i.test(value));
  const gitFiles = [...body.value.matchAll(/^\s*[MADRCU?!]{1,2}\s+(.+)$/gm)].map((match) => match[1].trim());
  return [...new Set([...explicit, ...inferred, ...gitFiles])].slice(0, 24);
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
      <ChevronDown class="timeline-row__chevron" :size="13" />
    </button>
    <div v-if="open" class="tool-call-event__details" aria-label="注入内容">
      <div class="context-injection-row__meta"><b>注入内容 · {{ charLabel }} 字符</b><span>{{ files.length ? `涉及 ${files.length} 个文件` : "未识别具体文件" }}</span></div>
      <ul v-if="files.length" class="context-injection-row__files" aria-label="涉及文件"><li v-for="file in files" :key="file" :title="file"><FileText :size="13" /><span>{{ file }}</span></li></ul>
      <pre class="context-injection-row__body">{{ body }}</pre>
    </div>
  </section>
</template>
