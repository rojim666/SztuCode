<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { BrainCircuit, Check, CircleDotDashed, Wrench } from "@lucide/vue";
import type { TimelineStatus } from "./types";
defineProps<{ step: number; status: TimelineStatus }>();
const { t } = useI18n({ useScope: "global" });
</script>

<template>
  <div class="step-indicator" :class="status" :aria-label="t('timeline.stepAria', { step })">
    <span><Check v-if="status === 'done'" :size="13" /><Wrench v-else-if="status === 'acting'" :size="13" /><BrainCircuit v-else-if="status === 'thinking'" :size="13" /><CircleDotDashed v-else :size="13" /></span>
  </div>
</template>