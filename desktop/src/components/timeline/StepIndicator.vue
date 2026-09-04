<script setup lang="ts">
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import type { TimelineStatus } from "./types";
defineProps<{ step: number; status: TimelineStatus }>();
const { t } = useI18n({ useScope: "global" });
</script>

<template>
  <div class="step-indicator" :class="status" :aria-label="t('timeline.stepAria', { step })">
    <span><AppIcon v-if="status === 'done'" name="Check" :size="13" /><AppIcon v-else-if="status === 'acting'" name="Wrench" :size="13" /><AppIcon v-else-if="status === 'thinking'" name="BrainCircuit" :size="13" /><AppIcon v-else name="CircleDotDashed" :size="13" /></span>
  </div>
</template>