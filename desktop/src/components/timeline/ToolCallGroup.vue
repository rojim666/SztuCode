<script setup lang="ts">
import { computed, ref } from "vue";
import { Bot, ChevronDown, LoaderCircle } from "@lucide/vue";
import ToolCallCard from "./ToolCallCard.vue";
import type { ToolCallEntry } from "./types";

const props = defineProps<{ calls: ToolCallEntry[] }>();
const open = ref(false);
const toolCount = computed(() => new Set(props.calls.map((call) => call.name)).size);
const running = computed(() => props.calls.some((call) => call.status === "running"));
const summary = computed(() => "使用 " + toolCount.value + " 个工具，运行 " + props.calls.length + " 个命令");
</script>

<template>
  <section v-if="calls.length" class="tool-call-group" :class="{ open }">
    <button class="tool-call-group__trigger" @click="open = !open">
      <span class="tool-call-group__icon"><Bot :size="14" /></span>
      <span>{{ summary }}</span>
      <LoaderCircle v-if="running" class="spin" :size="14" />
      <ChevronDown :size="14" />
    </button>
    <div v-if="open" class="tool-call-group__body">
      <ToolCallCard v-for="call in calls" :key="call.id" :call="call" />
    </div>
  </section>
</template>