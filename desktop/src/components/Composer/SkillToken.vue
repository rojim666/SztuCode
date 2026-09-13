<script setup lang="ts">
import { computed } from "vue";
import AppIcon from "../icons/AppIcon.vue";
const props = defineProps<{ name: string }>();
defineEmits<{ remove: [] }>();
const label = computed(() => props.name.split(/[-_]/).map(word => word ? word[0].toUpperCase() + word.slice(1) : word).join(" "));
</script>

<template>
  <span class="composer-skill-token" :title="'/' + name">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="m12 2 7 4v12l-7 4-7-4V6l7-4Z"/><path d="m5 6 7 4 7-4M5 12l7 4 7-4M12 10v12"/></svg>
    <span>{{ label }}</span>
    <button type="button" :aria-label="'移除技能' + name" @click="$emit('remove')"><AppIcon name="X" :size="12" /></button>
  </span>
</template>

<style scoped>
.composer-skill-token { display: inline-flex; align-items: center; gap: 5px; max-width: 100%; color: #2583e9; font-size: 13px; font-weight: 600; line-height: 24px; }
.composer-skill-token > span { min-width: 0; overflow-wrap: anywhere; }
.composer-skill-token > svg { flex: none; }
.composer-skill-token button { display: grid; place-items: center; flex: none; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 5px; color: inherit; background: transparent; opacity: 0; cursor: pointer; transition: opacity 120ms, background 120ms; }
.composer-skill-token:hover button, .composer-skill-token:focus-within button { opacity: 1; }
.composer-skill-token button:hover, .composer-skill-token button:focus-visible { background: #2583e916; }
:root[data-app-theme="dark"] .composer-skill-token { color: #6ab0ff; }
@media (hover: none) { .composer-skill-token button { opacity: .6; } }
</style>
