<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import type { TimelineStep } from "./types";

const props = defineProps<{ step: TimelineStep; hideEvidence?: boolean }>();
const { t } = useI18n({ useScope: "global" });
const logsOpen = ref(false);
const completedPlans = computed(() => props.step.plan?.filter((item) => item.status === "completed").length ?? 0);
const completedWorkflowTasks = computed(() => props.step.workflowTasks?.filter((item) => item.status === "succeeded").length ?? 0);
</script>

<template>
  <section v-if="step.plan?.length" class="timeline-activity plan-activity">
    <header><AppIcon name="ListChecks" :size="15" /><b>{{ t('timeline.details.plan') }}</b><span>{{ completedPlans }}/{{ step.plan.length }}</span></header>
    <ol>
      <li v-for="item in step.plan" :key="item.id" :class="item.status">
        <AppIcon name="CheckCircle2" :size="14" /><span>{{ item.subject }}</span>
      </li>
    </ol>
  </section>

  <section v-if="!hideEvidence && step.tests?.length" class="timeline-activity">
    <header><AppIcon name="Beaker" :size="15" /><b>{{ t('timeline.details.tests') }}</b></header>
    <div v-for="(test, index) in step.tests" :key="index" class="activity-row" :class="test.status">
      <AppIcon v-if="test.status === 'passed'" name="CheckCircle2" :size="14" />
      <AppIcon v-else name="CircleX" :size="14" />
      <span>{{ test.summary }}</span>
    </div>
  </section>

  <section v-if="!hideEvidence && step.changes?.length" class="timeline-activity">
    <header><AppIcon name="FileDiff" :size="15" /><b>{{ t('timeline.details.changes') }}</b></header>
    <div v-for="(change, index) in step.changes" :key="index" class="activity-files">
      <code v-for="path in change.paths" :key="path">{{ path }}</code>
    </div>
  </section>

  <section v-if="step.subagents?.length" class="timeline-activity">
    <header><AppIcon name="Bot" :size="15" /><b>{{ t('timeline.details.agents') }}</b></header>
    <div v-for="agent in step.subagents" :key="agent.runId" class="activity-row" :class="agent.status">
      <i /><span>{{ agent.description || agent.runId }}</span><small>{{ agent.status === 'running' ? t('timeline.details.agentRunning') : agent.status === 'success' ? t('timeline.details.agentDone') : t('timeline.details.agentFailed') }}</small>
    </div>
  </section>

  <section v-if="step.workflowTasks?.length" class="timeline-activity workflow-activity">
    <header><AppIcon name="GitBranch" :size="15" /><b>{{ t('timeline.details.workflowTasks') }}</b><span>{{ completedWorkflowTasks }}/{{ step.workflowTasks.length }}</span></header>
    <div v-for="task in step.workflowTasks" :key="task.id" class="activity-row" :class="task.status">
      <i /><span><b>{{ task.owner }}</b> · {{ task.title }}<small v-if="task.dependencies.length">{{ t('timeline.details.dependencies', { deps: task.dependencies.join(", ") }) }}</small><small v-if="task.error">{{ task.error }}</small></span><small>{{ task.status }}<template v-if="task.attempt"> · #{{ task.attempt }}</template></small>
    </div>
  </section>

  <section v-if="step.workflowHandoffs?.length" class="timeline-activity workflow-activity">
    <header><AppIcon name="ArrowRightLeft" :size="15" /><b>{{ t('timeline.details.handoffs') }}</b><span>{{ step.workflowHandoffs.length }}</span></header>
    <div v-for="(handoff, index) in step.workflowHandoffs" :key="`${handoff.taskId}-${index}`" class="activity-row" :class="handoff.status">
      <AppIcon v-if="handoff.status === 'succeeded'" name="CheckCircle2" :size="14" /><AppIcon v-else name="CircleX" :size="14" />
      <span><b>{{ handoff.role }}</b> · {{ handoff.summary }}<small v-if="handoff.commands.length">{{ handoff.commands.join(" · ") }}</small><small v-if="handoff.conclusion">{{ handoff.conclusion }}</small><small v-if="handoff.scopeEscalations.length" class="scope-escalation">{{ t('timeline.details.scopeEscalations', { items: handoff.scopeEscalations.join(", ") }) }}</small></span>
    </div>
  </section>

  <section v-if="step.workflowReviews?.length" class="timeline-activity workflow-activity">
    <header><AppIcon name="ShieldCheck" :size="15" /><b>{{ t('timeline.details.reviews') }}</b></header>
    <div v-for="(review, index) in step.workflowReviews" :key="`${review.taskId}-${index}`" class="activity-row" :class="review.decision === 'accept' ? 'succeeded' : 'rejected'">
      <AppIcon v-if="review.decision === 'accept'" name="CheckCircle2" :size="14" /><AppIcon v-else name="CircleX" :size="14" />
      <span><b>{{ review.decision === "accept" ? t('timeline.details.accept') : t('timeline.details.return') }}</b> · {{ review.conclusion }}<small>{{ t('timeline.details.diff') }}{{ review.diffSummary }}</small><small>{{ t('timeline.details.test') }}{{ review.testSummary }}</small><small>{{ t('timeline.details.security') }}{{ review.securitySummary }}</small></span>
    </div>
  </section>

  <section v-if="step.skills?.length" class="timeline-activity">
    <header><AppIcon name="Sparkles" :size="15" /><b>{{ t('timeline.details.skills') }}</b></header>
    <div v-for="(skill, index) in step.skills" :key="index" class="activity-row"><span>/{{ skill.name }} {{ skill.arguments }}</span></div>
  </section>

  <section v-if="step.logs?.length" class="timeline-activity logs-activity">
    <button type="button" @click="logsOpen = !logsOpen">
      <AppIcon name="ScrollText" :size="15" /><b>{{ t('timeline.details.logs') }}</b><span>{{ step.logs.length }}</span><AppIcon name="ChevronDown" :size="14" />
    </button>
    <pre v-if="logsOpen"><code v-for="(log, index) in step.logs" :key="index">[{{ log.level }}] {{ log.source }}: {{ log.message }}{{ '\n' }}</code></pre>
  </section>
</template>
