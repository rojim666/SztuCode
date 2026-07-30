<script setup lang="ts">
import ThinkingPanel from "./ThinkingPanel.vue";
import TokenStream from "./TokenStream.vue";
import ToolCallGroup from "./ToolCallGroup.vue";
import PermissionBadge from "./PermissionBadge.vue";
import StepIndicator from "./StepIndicator.vue";
import type { TimelineStep } from "./types";

defineProps<{ steps: TimelineStep[] }>();
defineEmits<{ decide: [toolUseId: string, decision: "allow_once" | "deny_once"] }>();
</script>

<template>
  <section class="execution-timeline" aria-live="polite">
    <article v-for="item in steps" :key="item.step" class="timeline-step">
      <StepIndicator :step="item.step" :status="item.status" />
      <div class="timeline-step__rail" />
      <div class="timeline-step__content">
        <div v-if="item.userMessage" class="timeline-user-message">{{ item.userMessage }}</div>
        <ThinkingPanel :text="item.thinking" :completed="item.status === 'done'" />
        <ToolCallGroup :calls="item.toolCalls" />
        <PermissionBadge v-if="item.permission" :permission="item.permission" @decide="$emit('decide', item.permission.toolUseId, $event)" />
        <TokenStream :tokens="item.tokens" :final-text="item.finalText" />
      </div>
    </article>
  </section>
</template>