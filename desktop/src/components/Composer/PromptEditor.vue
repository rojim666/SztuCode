<script setup lang="ts">
import { ref, watch, onMounted } from "vue";

const props = defineProps<{ modelValue: string; skill: { name: string } | null; plugins: { id: string; display_name: string }[]; disabled?: boolean; placeholder: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: string]; input: []; 'remove-skill': []; 'remove-plugin': [id: string]; keydown: [event: KeyboardEvent]; paste: [event: ClipboardEvent] }>();
const editor = ref<HTMLDivElement>();
let composing = false;
function textValue() {
  const visit = (node: Node): string => {
    if (node instanceof HTMLElement && node.dataset.token) return "";
    if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
    if (node.nodeName === "BR") return "\n";
    const value = Array.from(node.childNodes).map(visit).join("");
    return node.nodeName === "DIV" && node !== editor.value && node.previousSibling ? "\n" + value : value;
  };
  return editor.value ? visit(editor.value).replace(/\u200b/g, "") : "";
}
function sync() {
  const root = editor.value;
  if (!root || composing) return;
  const tokens = [...(props.skill ? [{ id: 'skill', label: props.skill.name.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }] : []), ...props.plugins.map(p => ({ id: p.id, label: p.display_name }))];
  if (textValue() === props.modelValue && JSON.stringify(Array.from(root.querySelectorAll('[data-token]')).map(n => (n as HTMLElement).dataset.token)) === JSON.stringify(tokens.map(t => t.id))) return;
  const focused = document.activeElement === root;
  root.replaceChildren();
  for (const token of tokens) {
    const span = document.createElement('span');
    span.dataset.token = token.id;
    span.contentEditable = 'false';
    span.className = 'prompt-inline-token';
    span.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="m12 2 7 4v12l-7 4-7-4V6l7-4Z"/><path d="m5 6 7 4 7-4M5 12l7 4 7-4M12 10v12"/></svg>';
    span.append(document.createTextNode(token.label));
    root.append(span);
  }
  root.append(document.createTextNode(props.modelValue || '\u200b'));
  if (focused) focus();
}
function focus() {
  const root = editor.value;
  if (!root) return;
  root.focus();
  const range = document.createRange();
  range.selectNodeContents(root);
  range.collapse(false);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}
function input() {
  if (composing) return;
  if (props.skill && !editor.value?.querySelector('[data-token="skill"]')) emit('remove-skill');
  const ids = Array.from(editor.value?.querySelectorAll('[data-token]') ?? []).map(n => (n as HTMLElement).dataset.token);
  for (const p of props.plugins) if (!ids.includes(p.id)) emit('remove-plugin', p.id);
  emit('update:modelValue', textValue());
  emit('input');
}
function paste(event: ClipboardEvent) {
  emit('paste', event);
  if (event.defaultPrevented) return;
  event.preventDefault();
  document.execCommand('insertText', false, event.clipboardData?.getData('text/plain') ?? '');
}
function keydown(event: KeyboardEvent) {
  emit('keydown', event);
  if (event.key === 'Enter' && !event.defaultPrevented && !event.isComposing) {
    event.preventDefault();
    document.execCommand('insertLineBreak');
  }
}
watch(() => [props.modelValue, props.skill, props.plugins], sync, { flush: 'post', deep: true });
onMounted(sync);
defineExpose({ focus });
</script>

<template>
  <div ref="editor" class="prompt-editor" role="textbox" aria-multiline="true" :aria-disabled="disabled" :contenteditable="!disabled" :data-placeholder="placeholder" :class="{ 'is-empty': !modelValue && !skill && !plugins.length }" @input="input" @keydown="keydown" @paste="paste" @compositionstart="composing = true" @compositionend="composing = false; input()" />
</template>

<style>
.prompt-editor { min-width: 0; min-height: 72px; padding: 8px 10px; color: var(--text, #30343a); background: transparent; font-size: 13px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; outline: none; cursor: text; }
.prompt-editor.is-empty::before { content: attr(data-placeholder); color: var(--text-muted, #9298a1); pointer-events: none; float: left; height: 0; }
.prompt-editor[aria-disabled="true"] { opacity: .6; cursor: default; }
.prompt-editor .prompt-inline-token { display: inline-flex; align-items: center; gap: 5px; margin-right: 7px; color: #2583e9; font-size: 13px; font-weight: 600; vertical-align: baseline; user-select: all; }
.prompt-inline-token svg { flex: none; align-self: center; }
.task-launcher .prompt-editor { order: 2; min-height: 112px; padding: 20px 14px 10px; }
:root[data-app-theme="dark"] .prompt-editor .prompt-inline-token { color: #6ab0ff; }
</style>
