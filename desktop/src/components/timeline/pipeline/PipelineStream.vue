<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ChevronDown, Play } from "@lucide/vue";
import type { PermissionDecision, TimelineStep } from "../types";
import { buildPipelineSegments, phaseStates, type PipelineSegment } from "./phase";
import PipelinePhaseRail from "./PipelinePhaseRail.vue";
import TokenStream from "../TokenStream.vue";
import ToolCallCard from "../ToolCallCard.vue";
import ThinkingPanel from "../ThinkingPanel.vue";
import PermissionBadge from "../PermissionBadge.vue";
import AgentLogo from "../AgentLogo.vue";
import { formatTokens } from "../../../utils/sessionStats";

const props = defineProps<{ steps: TimelineStep[]; workspaceId?: string }>();
const { t } = useI18n({ useScope: "global" });
defineEmits<{
  decide: [toolUseId: string, decision: PermissionDecision];
  reverted: [runId: string];
  review: [ctx: { workspaceId: string; runId: string; paths: string[] }];
  continue: [runId?: string];
}>();

type Turn = {
  key: string | number;
  runId?: string;
  userMessage?: string;
  userMessageTime?: string;
  steps: TimelineStep[];
  segments: PipelineSegment[];
  states: ReturnType<typeof phaseStates>;
  pending?: TimelineStep["permission"];
  running: boolean;
  model?: string;
  runStats?: TimelineStep["runStats"];
  runStartedAt?: string;
  changePaths: string[];
  failureReason?: string;
  interrupted: boolean;
};

const now = ref(Date.now());
let clockTimer: number | undefined;
onMounted(() => { clockTimer = window.setInterval(() => { now.value = Date.now(); }, 1000); });
onBeforeUnmount(() => { if (clockTimer) window.clearInterval(clockTimer); });

const openGroups = ref(new Set<string>());
function toggleGroup(id: string) {
  const next = new Set(openGroups.value);
  if (next.has(id)) next.delete(id); else next.add(id);
  openGroups.value = next;
}
function isGroupOpen(segment: PipelineSegment): boolean {
  // 有工具在跑时强制展开，让当前动作始终可见
  if (segment.calls.some((call) => call.status === "running" || call.status === "awaiting_permission")) return true;
  return openGroups.value.has(segment.id);
}

const turns = computed<Turn[]>(() => {
  const groups: TimelineStep[][] = [];
  for (const step of props.steps) {
    if (step.userMessage) groups.push([step]);
    else if (groups.length) groups[groups.length - 1].push(step);
    else groups.push([step]);
  }
  return groups.map((steps, index) => {
    const running = steps.some((step) => step.toolCalls.some((call) => call.status === "running" || call.status === "awaiting_permission"))
      || steps[steps.length - 1]?.status !== "done";
    const segments = buildPipelineSegments(steps);
    const interrupted = [...steps].reverse().find((step) => step.outcome?.status === "interrupted");
    return {
      key: steps.find((step) => step.runId)?.runId ?? `turn-${index}`,
      runId: steps.find((step) => step.runId)?.runId,
      userMessage: steps.find((step) => step.userMessage)?.userMessage,
      userMessageTime: steps.find((step) => step.userMessageTime)?.userMessageTime,
      steps,
      segments,
      states: phaseStates(segments, running),
      pending: steps.find((step) => step.permission?.status === "pending")?.permission,
      running,
      model: steps.find((step) => step.usage?.model)?.usage?.model,
      runStats: [...steps].reverse().find((step) => step.runStats)?.runStats,
      runStartedAt: steps.find((step) => step.runStartedAt)?.runStartedAt,
      changePaths: [...new Set(steps.flatMap((step) => step.changes?.flatMap((entry) => entry.paths) ?? []))],
      failureReason: [...steps].reverse().find((step) => step.outcome?.status === "failed")?.outcome?.reason,
      interrupted: Boolean(interrupted),
    };
  });
});

function groupTitle(segment: PipelineSegment): string {
  const count = segment.calls.length;
  if (segment.category === "write") return t("timeline.pipeline.groupWrite", { count });
  if (segment.category === "verify") return t("timeline.pipeline.groupVerify", { count });
  if (segment.category === "read") return t("timeline.pipeline.groupRead", { count });
  return t("timeline.pipeline.groupExec", { count });
}

function groupProgress(segment: PipelineSegment): number {
  return segment.calls.filter((call) => call.status === "done" || call.status === "failed").length;
}

function elapsedOf(turn: Turn): string {
  const stats = turn.runStats;
  if (stats?.elapsedSeconds) return `${Math.round(stats.elapsedSeconds)}s`;
  if (!turn.runStartedAt) return "";
  const seconds = Math.max(0, Math.round((now.value - new Date(turn.runStartedAt).getTime()) / 1000));
  return `${seconds}s`;
}

function formatTime(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
</script>

<template>
  <div class="pipeline-stream">
    <article v-for="turn in turns" :key="turn.key" class="pipeline-turn">
      <div v-if="turn.userMessage" class="pipeline-user">
        <span class="pipeline-user__bubble">{{ turn.userMessage }}</span>
        <span v-if="turn.userMessageTime" class="pipeline-user__time">{{ formatTime(turn.userMessageTime) }}</span>
      </div>

      <div class="pipeline-turn__body">
        <div class="pipeline-turn__head">
          <AgentLogo size="small" :active="turn.running" />
          <PipelinePhaseRail :states="turn.states" />
          <span v-if="elapsedOf(turn)" class="pipeline-turn__elapsed">{{ elapsedOf(turn) }}</span>
        </div>

        <template v-for="segment in turn.segments" :key="segment.id">
          <section v-if="segment.kind === 'thinking'" class="pipeline-thinking">
            <ThinkingPanel :text="segment.text" :completed="!turn.running" />
          </section>

          <section v-else-if="segment.kind === 'text'" class="pipeline-text">
            <TokenStream :tokens="[]" :final-text="segment.text" />
          </section>

          <section v-else-if="segment.calls.length === 1" class="pipeline-tool">
            <ToolCallCard :call="segment.calls[0]" :expanded="true" />
          </section>

          <section v-else class="pipeline-tool-group">
            <button type="button" class="pipeline-tool-group__trigger" :aria-expanded="isGroupOpen(segment)" @click="toggleGroup(segment.id)">
              <span class="pipeline-tool-group__title">{{ groupTitle(segment) }}</span>
              <span class="pipeline-tool-group__meta">{{ groupProgress(segment) }}/{{ segment.calls.length }}</span>
              <ChevronDown :size="13" :class="{ 'is-open': isGroupOpen(segment) }" />
            </button>
            <div v-if="isGroupOpen(segment)" class="pipeline-tool-group__body">
              <ToolCallCard v-for="call in segment.calls" :key="call.id" :call="call" />
            </div>
          </section>
        </template>

        <p v-if="turn.running && !turn.segments.length" class="pipeline-pending">{{ t('timeline.pipeline.thinking') }}</p>

        <PermissionBadge
          v-if="turn.pending"
          :permission="turn.pending"
          @decide="$emit('decide', turn.pending.toolUseId, $event)"
        />

        <p v-if="turn.failureReason" class="pipeline-failure">{{ turn.failureReason }}</p>

        <footer v-if="!turn.running && (turn.runStats || turn.model)" class="pipeline-turn__foot">
          <span v-if="turn.model">{{ turn.model }}</span>
          <span v-if="turn.runStats">· {{ formatTokens(turn.runStats.inputTokens + turn.runStats.outputTokens) }} tokens</span>
          <span v-if="turn.changePaths.length">{{ t('timeline.pipeline.changedFiles', { count: turn.changePaths.length }) }}</span>
        </footer>

        <button v-if="turn.interrupted" type="button" class="pipeline-continue" @click="$emit('continue', turn.runId)">
          <Play :size="13" />{{ t('timeline.pipeline.continue') }}
        </button>
      </div>
    </article>
  </div>
</template>