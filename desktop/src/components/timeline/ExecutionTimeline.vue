<script setup lang="ts">
import { computed } from "vue";
import { BrainCircuit, ChevronDown, Sparkles } from "@lucide/vue";
import ActivityDetails from "./ActivityDetails.vue";
import ChangeReviewCard from "../Diff/ChangeReviewCard.vue";
import ThinkingPanel from "./ThinkingPanel.vue";
import TokenStream from "./TokenStream.vue";
import ToolCallGroup from "./ToolCallGroup.vue";
import PermissionBadge from "./PermissionBadge.vue";
import type { PermissionDecision, PermissionState, TimelineStep, ToolCallEntry } from "./types";

const props = defineProps<{ steps: TimelineStep[]; workspaceId?: string }>();
defineEmits<{
  decide: [toolUseId: string, decision: PermissionDecision];
  reverted: [runId: string];
  review: [ctx: { workspaceId: string; runId: string; paths: string[] }];
}>();

type TurnView = {
  key: string | number;  // 一轮思考生命周期的全局唯一 ID（优先 runId）
  runId?: string;
  changePaths: string[];
  userMessage?: string;
  steps: TimelineStep[];
  hasContent: boolean;
  hasActivity: boolean;
  pending?: PermissionState;
  text: string;
  thinking: boolean;
  thinkingText: string;
  allToolCalls: ToolCallEntry[];
  aggregatedStep: TimelineStep;
};

// 汇总一轮内所有 step 的思考文本（按内容去重，避免逐 step 堆叠重复标签）
function thinkingTextOf(steps: TimelineStep[]): string {
  return [...new Set(steps.map((step) => step.thinking).filter(Boolean))].join("\n\n");
}

// 汇总一轮内所有 step 的工具调用（按 tool_use_id 去重）
function toolCallsOf(steps: TimelineStep[]): ToolCallEntry[] {
  return [...new Map(steps.flatMap((step) => step.toolCalls).map((call) => [call.id, call])).values()];
}

// 把一轮内多个 step 的活动字段合并成一个伪 step，供 ActivityDetails 一次性渲染
function aggregateStep(steps: TimelineStep[]): TimelineStep {
  return {
    step: steps[0]?.step ?? 0,
    status: "done",
    tokens: [],
    toolCalls: [],
    thinking: "",
    plan: steps.flatMap((step) => step.plan ?? []),
    tests: steps.flatMap((step) => step.tests ?? []),
    changes: steps.flatMap((step) => step.changes ?? []),
    subagents: steps.flatMap((step) => step.subagents ?? []),
    skills: steps.flatMap((step) => step.skills ?? []),
    logs: steps.flatMap((step) => step.logs ?? []),
  };
}

// 判断 step 是否包含助手侧内容（hydrate 会把用户消息与回复合并进同一 step）
function hasAssistantContent(step: TimelineStep): boolean {
  return Boolean(
    step.finalText || step.tokens.length || step.thinking || step.toolCalls.length ||
    step.plan?.length || step.tests?.length || step.changes?.length ||
    step.logs?.length || step.subagents?.length || step.skills?.length,
  );
}

// 将按 step 平铺的时间线按"用户消息为一轮"分组，合并同一轮内的连续 AI step
const turns = computed<TurnView[]>(() => {
  const groups: { userMessage?: string; steps: TimelineStep[] }[] = [];
  for (const item of props.steps) {
    if (item.userMessage) {
      const group: { userMessage?: string; steps: TimelineStep[] } = { userMessage: item.userMessage, steps: [] };
      groups.push(group);
      // hydrate 合并场景：同一 step 里既有用户消息也有回复内容，需纳入本轮 steps 供文本/活动提取
      if (hasAssistantContent(item)) group.steps.push(item);
    } else {
      if (!groups.length) groups.push({ steps: [] });
      groups[groups.length - 1].steps.push(item);
    }
  }
  return groups.map((group, index) => {
    const steps = group.steps;
    const last = steps[steps.length - 1];
    const text = steps
      .map((step) => step.finalText || step.tokens.join(""))
      .filter(Boolean)
      .join("\n\n");
    const allToolCalls = toolCallsOf(steps);
    const thinkingText = thinkingTextOf(steps);
    const aggregatedStep = aggregateStep(steps);
    const hasActivity = Boolean(
      allToolCalls.length || thinkingText || aggregatedStep.plan?.length || aggregatedStep.tests?.length ||
      aggregatedStep.changes?.length || aggregatedStep.subagents?.length || aggregatedStep.skills?.length ||
      aggregatedStep.logs?.length,
    );
    const pending = steps.find((step) => step.permission?.status === "pending")?.permission;
    const thinking = Boolean(
      last && last.status === "thinking" && !last.tokens.length && !last.finalText,
    );
    const runId = steps.find((step) => step.runId)?.runId;
    const changePaths = [
      ...new Set(aggregatedStep.changes?.flatMap((entry) => entry.paths) ?? []),
    ];
    return {
      key: runId ?? `turn-${index}`,
      runId,
      changePaths,
      userMessage: group.userMessage,
      steps,
      hasActivity,
      pending,
      text,
      thinking,
      thinkingText,
      allToolCalls,
      aggregatedStep,
      hasContent: Boolean(text || hasActivity || pending || thinking),
    };
  });
});
</script>

<template>
  <section class="execution-timeline" aria-live="polite">
    <article v-for="turn in turns" :key="turn.key" class="timeline-step">
      <div v-if="turn.userMessage" class="timeline-user-message">{{ turn.userMessage }}</div>
      <div v-if="turn.hasContent" class="timeline-assistant">
        <span class="assistant-avatar" aria-label="SztuCode AI"><Sparkles :size="15" :stroke-width="2" /></span>
        <div class="timeline-step__content">
          <PermissionBadge v-if="turn.pending" :permission="turn.pending" @decide="$emit('decide', turn.pending?.toolUseId ?? '', $event)" />
          <details v-if="turn.hasActivity" class="thinking-collapse">
            <summary><BrainCircuit :size="14" />思考过程<ChevronDown :size="14" /></summary>
            <div class="thinking-collapse__body">
              <ThinkingPanel v-if="turn.thinkingText" :text="turn.thinkingText" :completed="true" />
              <ToolCallGroup v-if="turn.allToolCalls.length" :calls="turn.allToolCalls" />
              <ActivityDetails :step="turn.aggregatedStep" />
            </div>
          </details>
          <TokenStream :tokens="[]" :final-text="turn.text" />
          <ChangeReviewCard
            v-if="workspaceId && turn.runId && turn.changePaths.length"
            :workspace-id="workspaceId"
            :run-id="turn.runId"
            :paths="turn.changePaths"
            @reverted="$emit('reverted', $event)"
            @review="$emit('review', $event)"
          />
          <div v-if="turn.thinking" class="thinking-loading" aria-live="polite"><span class="typing-dots"><i /><i /><i /></span><span>思考中…</span></div>
        </div>
      </div>
    </article>
  </section>
</template>
