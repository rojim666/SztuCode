<script setup lang="ts">
import { computed } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const props = defineProps<{ tokens: string[]; finalText?: string }>();
const text = computed(() => props.finalText || props.tokens.join(""));
const html = computed(() => DOMPurify.sanitize(marked.parse(text.value, { async: false }) as string));
</script>

<template>
  <div v-if="text" class="token-stream markdown-body" :class="{ streaming: !finalText }">
    <div v-html="html" />
    <i v-if="!finalText" />
  </div>
</template>