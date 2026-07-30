<script setup lang="ts">
import { BrainCircuit, Check, CircleDotDashed, Wrench } from "@lucide/vue";
import type { TimelineStatus } from "./types";
defineProps<{ step: number; status: TimelineStatus }>();
</script>

<template>
  <div class="step-indicator" :class="status" :aria-label="`步骤 ${step}`">
    <span><Check v-if="status === 'done'" :size="13" /><Wrench v-else-if="status === 'acting'" :size="13" /><BrainCircuit v-else-if="status === 'thinking'" :size="13" /><CircleDotDashed v-else :size="13" /></span>
  </div>
</template>