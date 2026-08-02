<script setup lang="ts">
import ActivityDetails from "./ActivityDetails.vue";
import ThinkingPanel from "./ThinkingPanel.vue";
import TokenStream from "./TokenStream.vue";
import ToolCallGroup from "./ToolCallGroup.vue";
import PermissionBadge from "./PermissionBadge.vue";
import { Sparkles } from "@lucide/vue";
import type { PermissionDecision, TimelineStep } from "./types";

defineProps<{ steps: TimelineStep[] }>();
defineEmits<{ decide: [toolUseId: string, decision: PermissionDecision] }>();

function hasAssistantActivity(item: TimelineStep) {
  return item.status !== "done" || Boolean(
    item.thinking || item.tokens.length || item.finalText || item.toolCalls.length || item.permission ||
    item.plan?.length || item.tests?.length || item.changes?.length || item.logs?.length ||
    item.subagents?.length || item.skills?.length,
  );
}
// 思考中且尚未产出任何可见内容时，展示加载提示
function isThinkingUnanswered(item: TimelineStep) {
  return item.status === "thinking" && !item.tokens.length && !item.finalText;
}
</script>

<template>
  <section class="execution-timeline" aria-live="polite">
    <article v-for="item in steps" :key="item.step" class="timeline-step">
      <div v-if="item.userMessage" class="timeline-user-message">{{ item.userMessage }}</div>
      <div v-if="hasAssistantActivity(item)" class="timeline-assistant">
        <span class="assistant-avatar" aria-label="SztuCode AI"><Sparkles :size="15" :stroke-width="2" /></span>
        <div class="timeline-step__content">
          <ThinkingPanel :text="item.thinking" :completed="item.status === 'done'" />
          <ActivityDetails :step="item" />
          <ToolCallGroup :calls="item.toolCalls" />
          <PermissionBadge v-if="item.permission" :permission="item.permission" @decide="$emit('decide', item.permission.toolUseId, $event)" />
          <TokenStream :tokens="item.tokens" :final-text="item.finalText" />
          <div v-if="isThinkingUnanswered(item)" class="thinking-loading" aria-live="polite"><span class="typing-dots"><i /><i /><i /></span><span>思考中…</span></div>
        </div>
      </div>
    </article>
  </section>
</template>
