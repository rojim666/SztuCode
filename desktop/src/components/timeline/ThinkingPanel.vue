<script setup lang="ts">
import { computed, ref } from "vue";
import { BrainCircuit, ChevronDown } from "@lucide/vue";
const props = defineProps<{ text?: string; completed?: boolean }>();
const open = ref(false);
const label = computed(() => props.completed ? "思考已完成" : "正在思考");
</script>

<template>
  <section v-if="text" class="thinking-panel" :class="{ open }">
    <button @click="open = !open"><BrainCircuit :size="15" /><span>{{ label }}</span><ChevronDown :size="14" /></button>
    <pre v-if="open">{{ text }}</pre>
  </section>
</template>