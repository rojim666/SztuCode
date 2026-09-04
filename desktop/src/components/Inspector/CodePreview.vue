<script setup lang="ts">
import { computed } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import hljs from "highlight.js/lib/common";

const props = defineProps<{
  content: string;
  path: string;
  encoding?: string;
  binary?: boolean;
  truncated?: boolean;
  forceLanguage?: string;
  mediaBase64?: string | null;
  mimeType?: string | null;
  hideChrome?: boolean;
}>();

const languageByExtension: Record<string, { key: string; label: string }> = {
  c: { key: "c", label: "C" }, cpp: { key: "cpp", label: "C++" }, cs: { key: "csharp", label: "C#" },
  css: { key: "css", label: "CSS" }, diff: { key: "diff", label: "Diff" }, go: { key: "go", label: "Go" },
  html: { key: "xml", label: "HTML" }, java: { key: "java", label: "Java" }, js: { key: "javascript", label: "JavaScript" },
  json: { key: "json", label: "JSON" }, jsx: { key: "javascript", label: "JSX" }, md: { key: "markdown", label: "Markdown" },
  php: { key: "php", label: "PHP" }, py: { key: "python", label: "Python" }, rb: { key: "ruby", label: "Ruby" },
  rs: { key: "rust", label: "Rust" }, scss: { key: "scss", label: "SCSS" }, sh: { key: "bash", label: "Shell" },
  sql: { key: "sql", label: "SQL" }, toml: { key: "ini", label: "TOML" }, ts: { key: "typescript", label: "TypeScript" },
  tsx: { key: "typescript", label: "TSX" }, vue: { key: "xml", label: "Vue" }, xml: { key: "xml", label: "XML" },
  yaml: { key: "yaml", label: "YAML" }, yml: { key: "yaml", label: "YAML" }, ps1: { key: "powershell", label: "PowerShell" },
};

const fileName = computed(() => props.path.split(/[\\/]/).pop() ?? props.path);
const extension = computed(() => fileName.value.includes(".") ? fileName.value.split(".").pop()!.toLowerCase() : "");
const language = computed(() => {
  if (props.forceLanguage === "diff") return languageByExtension.diff;
  if (fileName.value === "Dockerfile") return { key: "dockerfile", label: "Dockerfile" };
  if (fileName.value === "Makefile") return { key: "makefile", label: "Makefile" };
  return languageByExtension[extension.value] ?? { key: "plaintext", label: extension.value.toUpperCase() || "Text" };
});
const pathParts = computed(() => props.path.split(/[\\/]/).filter(Boolean));
const highlightedLines = computed(() => {
  const key = hljs.getLanguage(language.value.key) ? language.value.key : "plaintext";
  return hljs.highlight(props.content, { language: key, ignoreIllegals: true }).value.split("\n");
});
</script>

<template>
  <div class="code-preview" :class="{ 'code-preview--bare': hideChrome }">
    <div v-if="!hideChrome" class="code-preview-meta">
      <span class="format-badge">{{ language.label }}</span>
      <span class="encoding-badge">{{ encoding || "UTF-8" }}</span>
      <span v-if="truncated" class="truncated-badge"><AppIcon name="AlertTriangle" :size="12" />仅显示前 1 MB</span>
    </div>
    <div v-if="!hideChrome" class="preview-breadcrumb">
      <span v-for="(part, index) in pathParts" :key="index">{{ part }}<i v-if="index < pathParts.length - 1">/</i></span>
    </div>
    <div v-if="mediaBase64 && mimeType" class="media-preview">
      <img :src="`data:${mimeType};base64,${mediaBase64}`" :alt="fileName" />
    </div>
    <div v-else-if="binary" class="code-preview-empty">
      <AppIcon name="FileWarning" :size="28" />
      <b>无法预览二进制文件</b>
      <span>该文件不是可显示的文本格式</span>
    </div>
    <div v-else class="code-preview-scroll">
      <div v-for="(line, index) in highlightedLines" :key="index" class="code-line">
        <span class="line-number" aria-hidden="true">{{ index + 1 }}</span>
        <code v-html="line || ' '" />
      </div>
    </div>
  </div>
</template>
