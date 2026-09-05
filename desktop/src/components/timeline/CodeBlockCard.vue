<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import hljs from "highlight.js/lib/common";

interface Props {
  code: string;
  language?: string;
}

const props = withDefaults(defineProps<Props>(), {
  language: "plaintext",
});

const emit = defineEmits<{
  (e: "language-change", lang: string): void;
}>();

const LANGUAGES: { value: string; label: string }[] = [
  { value: "plaintext", label: "Plain Text" },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "jsx", label: "JSX" },
  { value: "tsx", label: "TSX" },
  { value: "python", label: "Python" },
  { value: "java", label: "Java" },
  { value: "c", label: "C" },
  { value: "cpp", label: "C++" },
  { value: "csharp", label: "C#" },
  { value: "go", label: "Go" },
  { value: "rust", label: "Rust" },
  { value: "html", label: "HTML" },
  { value: "css", label: "CSS" },
  { value: "scss", label: "SCSS" },
  { value: "json", label: "JSON" },
  { value: "yaml", label: "YAML" },
  { value: "markdown", label: "Markdown" },
  { value: "bash", label: "Shell" },
  { value: "powershell", label: "PowerShell" },
  { value: "sql", label: "SQL" },
  { value: "xml", label: "XML" },
  { value: "php", label: "PHP" },
  { value: "ruby", label: "Ruby" },
  { value: "swift", label: "Swift" },
  { value: "kotlin", label: "Kotlin" },
  { value: "dockerfile", label: "Dockerfile" },
  { value: "diff", label: "Diff" },
];

function normalizeLanguage(lang: string): string {
  if (!lang) return "plaintext";
  const normalized = lang.toLowerCase();
  const aliasMap: Record<string, string> = {
    js: "javascript",
    ts: "typescript",
    py: "python",
    rb: "ruby",
    sh: "bash",
    shell: "bash",
    zsh: "bash",
    md: "markdown",
    yml: "yaml",
    cs: "csharp",
    "c++": "cpp",
    htm: "html",
    ps: "powershell",
    ps1: "powershell",
    txt: "plaintext",
    text: "plaintext",
  };
  const mapped = aliasMap[normalized] || normalized;
  const found = LANGUAGES.find((l) => l.value === mapped);
  return found ? found.value : "plaintext";
}

const currentLang = ref(normalizeLanguage(props.language));
const dropdownOpen = ref(false);
const searchQuery = ref("");
const copied = ref(false);
const triggerRef = ref<HTMLElement | null>(null);
const dropdownRef = ref<HTMLElement | null>(null);
const dropdownStyle = ref<Record<string, string>>({});

const filteredLanguages = computed(() => {
  const q = searchQuery.value.toLowerCase();
  if (!q) return LANGUAGES;
  return LANGUAGES.filter(
    (l) => l.label.toLowerCase().includes(q) || l.value.toLowerCase().includes(q)
  );
});

const currentLangLabel = computed(() => {
  const found = LANGUAGES.find((l) => l.value === currentLang.value);
  return found ? found.label : "Plain Text";
});

const highlightedLines = computed(() => {
  const key = hljs.getLanguage(currentLang.value) ? currentLang.value : "plaintext";
  const highlighted = hljs.highlight(props.code, { language: key, ignoreIllegals: true }).value;
  return highlighted.split("\n");
});

watch(
  () => props.language,
  (newLang) => {
    currentLang.value = normalizeLanguage(newLang);
  }
);

function updateDropdownPosition() {
  if (!triggerRef.value) return;
  const triggerRect = triggerRef.value.getBoundingClientRect();
  const viewportHeight = window.innerHeight;
  const viewportWidth = window.innerWidth;

  const dropdownHeight = dropdownRef.value?.offsetHeight || 400;
  const spaceBelow = viewportHeight - triggerRect.bottom;
  const spaceAbove = triggerRect.top;
  const showAbove = spaceBelow < dropdownHeight + 8 && spaceAbove > spaceBelow;

  let left = triggerRect.left;
  const dropdownWidth = Math.max(triggerRect.width, 220);
  if (left + dropdownWidth > viewportWidth - 8) {
    left = viewportWidth - dropdownWidth - 8;
  }

  if (showAbove) {
    dropdownStyle.value = {
      top: `${Math.max(8, triggerRect.top - dropdownHeight - 6)}px`,
      left: `${left}px`,
      minWidth: `${dropdownWidth}px`,
      maxHeight: `${Math.min(dropdownHeight, spaceAbove - 12)}px`,
    };
  } else {
    dropdownStyle.value = {
      top: `${triggerRect.bottom + 6}px`,
      left: `${left}px`,
      minWidth: `${dropdownWidth}px`,
      maxHeight: `${Math.min(dropdownHeight, spaceBelow - 12)}px`,
    };
  }
}

function selectLanguage(lang: string) {
  currentLang.value = lang;
  dropdownOpen.value = false;
  searchQuery.value = "";
  emit("language-change", lang);
}

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value;
  if (dropdownOpen.value) {
    searchQuery.value = "";
    nextTick(() => {
      updateDropdownPosition();
      requestAnimationFrame(() => {
        updateDropdownPosition();
      });
    });
  }
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText(props.code);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = props.code;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  }
}

function onDocClick(e: MouseEvent) {
  if (!dropdownOpen.value) return;
  const target = e.target as Node;
  const inTrigger = triggerRef.value?.contains(target);
  const inDropdown = dropdownRef.value?.contains(target);
  if (!inTrigger && !inDropdown) {
    dropdownOpen.value = false;
    searchQuery.value = "";
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && dropdownOpen.value) {
    dropdownOpen.value = false;
    searchQuery.value = "";
  }
}

function onScroll() {
  if (dropdownOpen.value) {
    updateDropdownPosition();
  }
}

onMounted(() => {
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("scroll", onScroll, true);
  window.addEventListener("resize", onScroll);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("scroll", onScroll, true);
  window.removeEventListener("resize", onScroll);
});
</script>

<template>
  <div class="code-block-card">
    <div class="code-block-header">
      <button type="button" class="lang-selector" ref="triggerRef" @click.stop="toggleDropdown">
        <span class="lang-label">{{ currentLangLabel }}</span>
        <AppIcon name="ChevronDown" :size="14" :class="{ 'chevron-open': dropdownOpen }" />
      </button>

      <div class="header-actions">
        <button
          type="button"
          class="copy-btn"
          :title="copied ? '已复制' : '复制代码'"
          @click="copyCode"
        >
          <AppIcon v-if="copied" name="Check" :size="16" />
          <AppIcon v-else name="Copy" :size="16" />
        </button>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="dropdownOpen"
        ref="dropdownRef"
        class="lang-dropdown"
        :style="dropdownStyle"
        @click.stop
      >
        <div class="dropdown-search">
          <AppIcon name="Search" :size="16" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索语言..."
            class="search-input"
            autocomplete="off"
          />
        </div>
        <div class="dropdown-list">
          <button
            v-for="lang in filteredLanguages"
            :key="lang.value"
            type="button"
            class="lang-option"
            :class="{ 'lang-option--selected': lang.value === currentLang }"
            @click="selectLanguage(lang.value)"
          >
            <span>{{ lang.label }}</span>
            <AppIcon v-if="lang.value === currentLang" name="Check" :size="16" />
          </button>
        </div>
      </div>
    </Teleport>

    <div class="code-block-body">
      <div class="code-lines">
        <div v-for="(line, index) in highlightedLines" :key="index" class="code-line-wrapper">
          <span class="line-number">{{ index + 1 }}</span>
          <code class="code-line" v-html="line || ' '" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.code-block-card {
  margin: 13px 0 18px;
  background: #f5f5f5;
  border: 1px solid #e2e3e5;
  border-radius: 12px;
  overflow: hidden;
  font-size: 13px;
}

.code-block-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: #f0f0f1;
  border-bottom: 1px solid #e2e3e5;
}

.lang-selector {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  color: #4a4f57;
  background: transparent;
  border: 0;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.lang-selector:hover {
  background: #e5e6e8;
}

.lang-selector svg {
  color: #7a808a;
  transition: transform 0.15s ease;
}

.lang-selector .chevron-open {
  transform: rotate(180deg);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.copy-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: #6a6f78;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.copy-btn:hover {
  color: #2a2f38;
  background: #e2e3e5;
}

.lang-dropdown {
  position: fixed;
  z-index: 10000;
  background: #fff;
  border: 1px solid #d8dade;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  overflow: hidden;
  animation: dropdown-in 0.12s ease-out;
}

@keyframes dropdown-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.dropdown-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f1f2;
  color: #8a9099;
}

.search-input {
  flex: 1;
  padding: 0;
  color: #2a2f38;
  background: transparent;
  border: 0;
  outline: 0;
  font-size: 13px;
}

.search-input::placeholder {
  color: #aab0b8;
}

.dropdown-list {
  max-height: 300px;
  padding: 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #d0d3d8 transparent;
}

.dropdown-list::-webkit-scrollbar {
  width: 6px;
}

.dropdown-list::-webkit-scrollbar-track {
  background: transparent;
}

.dropdown-list::-webkit-scrollbar-thumb {
  background: #d0d3d8;
  border-radius: 3px;
}

.lang-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  color: #3a3f48;
  background: transparent;
  border: 0;
  border-radius: 8px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.1s ease;
}

.lang-option:hover {
  background: #f3f5f7;
}

.lang-option--selected {
  background: #f0f0f1;
  color: #1a6fd1;
  font-weight: 500;
}

.lang-option--selected svg {
  color: #1a6fd1;
}

.code-block-body {
  overflow-x: auto;
}

.code-lines {
  display: table;
  min-width: 100%;
  padding: 12px 0;
  font: 12.5px/1.65 "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

.code-line-wrapper {
  display: table-row;
}

.line-number {
  display: table-cell;
  width: 1%;
  min-width: 40px;
  padding: 0 12px 0 16px;
  color: #9ea3ab;
  text-align: right;
  user-select: none;
  font-variant-numeric: tabular-nums;
}

.code-line {
  display: table-cell;
  padding-right: 16px;
  color: #30343a;
  white-space: pre;
}

/* Syntax highlighting - light theme (matches code-preview) */
:global(.hljs-comment),
:global(.hljs-quote) {
  color: #73808a;
  font-style: italic;
}

:global(.hljs-keyword),
:global(.hljs-selector-tag),
:global(.hljs-literal) {
  color: #8c3fb0;
  font-weight: 600;
}

:global(.hljs-string),
:global(.hljs-regexp),
:global(.hljs-addition) {
  color: #167442;
}

:global(.hljs-number),
:global(.hljs-built_in),
:global(.hljs-type) {
  color: #b25b16;
}

:global(.hljs-title),
:global(.hljs-title.function_),
:global(.hljs-section) {
  color: #176ac2;
}

:global(.hljs-variable),
:global(.hljs-template-variable),
:global(.hljs-attr),
:global(.hljs-attribute) {
  color: #9b451f;
}

:global(.hljs-meta),
:global(.hljs-symbol),
:global(.hljs-bullet) {
  color: #326f87;
}

:global(.hljs-deletion) {
  color: #b53a34;
}

:global(.hljs-name),
:global(.hljs-selector-id),
:global(.hljs-selector-class) {
  color: #2f6f9f;
}

:global(.hljs-params) {
  color: #4a5568;
}

:global(.hljs-emphasis) {
  font-style: italic;
}

:global(.hljs-strong) {
  font-weight: 700;
}

/* Dark theme：整体灰色系（卡片 #262626 / 头部 #2e2e2e / 边框 #3d3d3d），!important 防止被其他全局规则覆盖 */
:global([data-app-theme="dark"] .code-block-card){
  background: #262626 !important;
  border-color: #3d3d3d !important;
}

:global([data-app-theme="dark"] .code-block-header){
  background: #2e2e2e !important;
  border-bottom-color: #3d3d3d !important;
}

:global([data-app-theme="dark"] .lang-selector){
  color: #e8e8e8;
}

:global([data-app-theme="dark"] .lang-selector:hover){
  background: #3a3a3a;
}

:global([data-app-theme="dark"] .lang-selector svg){
  color: #a0a0a0;
}

:global([data-app-theme="dark"] .copy-btn){
  color: #a0a0a0;
}

:global([data-app-theme="dark"] .copy-btn:hover){
  color: #f0f0f0;
  background: #3a3a3a;
}

:global([data-app-theme="dark"] .lang-dropdown){
  background: #2e2e2e;
  border-color: #3d3d3d;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2);
}

:global([data-app-theme="dark"] .dropdown-search){
  border-bottom-color: #3d3d3d;
  color: #7a7a7a;
}

:global([data-app-theme="dark"] .search-input){
  color: #e5e7eb;
}

:global([data-app-theme="dark"] .search-input::placeholder){
  color: #5a606a;
}

:global([data-app-theme="dark"] .dropdown-list){
  scrollbar-color: #3f444d transparent;
}

:global([data-app-theme="dark"] .dropdown-list::-webkit-scrollbar-thumb){
  background: #3f444d;
}

:global([data-app-theme="dark"] .lang-option){
  color: #e0e0e0;
}

:global([data-app-theme="dark"] .lang-option:hover){
  background: #3a3a3a;
}

:global([data-app-theme="dark"] .lang-option--selected){
  background: #2a3748;
  color: #5ba0f5;
}

:global([data-app-theme="dark"] .lang-option--selected svg){
  color: #5ba0f5;
}

:global([data-app-theme="dark"] .line-number){
  color: #6e6e6e;
}

:global([data-app-theme="dark"] .code-line){
  color: #e0e0e0;
}

/* Dark theme syntax highlighting */
:global([data-app-theme="dark"] .hljs-comment),
:global([data-app-theme="dark"] .hljs-quote){
  color: #6a737d;
  font-style: italic;
}

:global([data-app-theme="dark"] .hljs-keyword),
:global([data-app-theme="dark"] .hljs-selector-tag),
:global([data-app-theme="dark"] .hljs-literal){
  color: #c586c0;
  font-weight: 600;
}

:global([data-app-theme="dark"] .hljs-string),
:global([data-app-theme="dark"] .hljs-regexp),
:global([data-app-theme="dark"] .hljs-addition){
  color: #6a9955;
}

:global([data-app-theme="dark"] .hljs-number),
:global([data-app-theme="dark"] .hljs-built_in),
:global([data-app-theme="dark"] .hljs-type){
  color: #b5cea8;
}

:global([data-app-theme="dark"] .hljs-title),
:global([data-app-theme="dark"] .hljs-title.function_),
:global([data-app-theme="dark"] .hljs-section){
  color: #569cd6;
}

:global([data-app-theme="dark"] .hljs-variable),
:global([data-app-theme="dark"] .hljs-template-variable),
:global([data-app-theme="dark"] .hljs-attr),
:global([data-app-theme="dark"] .hljs-attribute){
  color: #9cdcfe;
}

:global([data-app-theme="dark"] .hljs-meta),
:global([data-app-theme="dark"] .hljs-symbol),
:global([data-app-theme="dark"] .hljs-bullet){
  color: #4ec9b0;
}

:global([data-app-theme="dark"] .hljs-deletion){
  color: #f48771;
}

:global([data-app-theme="dark"] .hljs-name),
:global([data-app-theme="dark"] .hljs-selector-id),
:global([data-app-theme="dark"] .hljs-selector-class){
  color: #d7ba7d;
}

:global([data-app-theme="dark"] .hljs-params){
  color: #c9d1d9;
}
</style>
