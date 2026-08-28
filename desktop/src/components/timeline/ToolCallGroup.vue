<script setup lang="ts">
import { computed, ref } from "vue";
import { ChevronDown, LoaderCircle, TerminalSquare } from "@lucide/vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";

const props = defineProps<{ calls: ToolCallEntry[] }>();
const open = ref(false);
const running = computed(() => props.calls.some((call) => call.status === "running"));
const summary = computed(() => `${props.calls.length} 项操作`);
</script>

<template>
  <section v-if="calls.length" class="tool-call-group" :class="{ open }">
    <button
      type="button"
      class="tool-call-group__trigger"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="tool-call-group__icon"><TerminalSquare :size="15" /></span>
      <span>{{ summary }}</span>
      <LoaderCircle v-if="running" class="spin" :size="14" />
      <ChevronDown :size="14" />
    </button>
    <div v-if="open" class="tool-call-group__body" aria-label="操作记录">
      <ToolCallCard v-for="call in calls" :key="call.id" :call="call" />
    </div>
  </section>
</template>
