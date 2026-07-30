<script setup lang="ts">
import { computed, ref } from "vue";
import { ChevronDown, CircleAlert, FileText, LoaderCircle, Terminal } from "@lucide/vue";
import type { ToolCallEntry } from "./types";

const props = defineProps<{ call: ToolCallEntry }>();
const open = ref(false);
const request = computed(() => JSON.stringify(props.call.params, null, 2));
const title = computed(() => typeof props.call.params.description === "string" ? props.call.params.description : props.call.name);
const isFileTool = computed(() => /read|file|dir|search/i.test(props.call.name));
</script>

<template>
  <section class="tool-call-event" :class="call.status">
    <button @click="open = !open">
      <FileText v-if="isFileTool" :size="16" />
      <Terminal v-else :size="16" />
      <span>{{ title }}</span>
      <LoaderCircle v-if="call.status === 'running'" class="spin" :size="14" />
      <CircleAlert v-else-if="call.status === 'failed'" :size="14" />
      <ChevronDown :size="14" />
    </button>
    <div v-if="open" class="tool-call-event__details">
      <b>Request</b><pre>{{ request }}</pre>
      <template v-if="call.output || call.error"><b>Response</b><pre>{{ call.error || call.output }}</pre></template>
    </div>
  </section>
</template>