<script setup lang="ts">
import { computed, ref } from "vue";
import { Beaker, Bot, CheckCircle2, ChevronDown, CircleX, FileDiff, ListChecks, ScrollText, Sparkles } from "@lucide/vue";
import type { TimelineStep } from "./types";

const props = defineProps<{ step: TimelineStep }>();
const logsOpen = ref(false);
const completedPlans = computed(() => props.step.plan?.filter((item) => item.status === "completed").length ?? 0);
</script>

<template>
  <section v-if="step.plan?.length" class="timeline-activity plan-activity">
    <header><ListChecks :size="15" /><b>计划</b><span>{{ completedPlans }}/{{ step.plan.length }}</span></header>
    <ol>
      <li v-for="item in step.plan" :key="item.id" :class="item.status">
        <CheckCircle2 :size="14" /><span>{{ item.subject }}</span>
      </li>
    </ol>
  </section>

  <section v-if="step.tests?.length" class="timeline-activity">
    <header><Beaker :size="15" /><b>测试</b></header>
    <div v-for="(test, index) in step.tests" :key="index" class="activity-row" :class="test.status">
      <CheckCircle2 v-if="test.status === 'passed'" :size="14" />
      <CircleX v-else :size="14" />
      <span>{{ test.summary }}</span>
    </div>
  </section>

  <section v-if="step.changes?.length" class="timeline-activity">
    <header><FileDiff :size="15" /><b>变更</b></header>
    <div v-for="(change, index) in step.changes" :key="index" class="activity-files">
      <code v-for="path in change.paths" :key="path">{{ path }}</code>
    </div>
  </section>

  <section v-if="step.subagents?.length" class="timeline-activity">
    <header><Bot :size="15" /><b>Agent 集群</b></header>
    <div v-for="agent in step.subagents" :key="agent.runId" class="activity-row" :class="agent.status">
      <i /><span>{{ agent.description || agent.runId }}</span><small>{{ agent.status === 'running' ? '运行中' : agent.status === 'success' ? '完成' : '失败' }}</small>
    </div>
  </section>

  <section v-if="step.skills?.length" class="timeline-activity">
    <header><Sparkles :size="15" /><b>技能</b></header>
    <div v-for="(skill, index) in step.skills" :key="index" class="activity-row"><span>/{{ skill.name }} {{ skill.arguments }}</span></div>
  </section>

  <section v-if="step.logs?.length" class="timeline-activity logs-activity">
    <button type="button" @click="logsOpen = !logsOpen">
      <ScrollText :size="15" /><b>日志</b><span>{{ step.logs.length }}</span><ChevronDown :size="14" />
    </button>
    <pre v-if="logsOpen"><code v-for="(log, index) in step.logs" :key="index">[{{ log.level }}] {{ log.source }}: {{ log.message }}{{ '\n' }}</code></pre>
  </section>
</template>