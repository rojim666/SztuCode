<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { SessionStats } from "../../utils/sessionStats";
import { cacheHitPercent, formatContextPercent, formatDuration, formatTokens, formatTokensPerSecond } from "../../utils/sessionStats";

const props = defineProps<{ stats: SessionStats }>();
const { t } = useI18n({ useScope: "global" });

// 组构建顺序（借鉴 dsh 8.4）：计数 → 用时 → 首 token/吞吐 → 缓存命中 → token 记账；
// 无数据的组整体不渲染。结构化为带 kind 的对象，上下文组不再依赖中文前缀匹配
type StatGroupKind = "turns" | "ttft" | "cache" | "tokens" | "context";
type StatGroup = { kind: StatGroupKind; text: string };
const groups = computed<StatGroup[]>(() => {
  const { stats } = props;
  const g: StatGroup[] = [];

  if (stats.steps > 0) g.push({ kind: "turns", text: t("timeline.stats.turnsSteps", { turns: stats.turns, steps: stats.steps }) });

  if (stats.ttftSteps > 0) {
    const averageSeconds = stats.ttftMsTotal / stats.ttftSteps / 1000;
    // 吞吐 = 输出 token / decode 墙钟（LLM 用时扣除首 token 前的等待）
    const decodeSeconds = Math.max(0.001, (stats.llmMs - stats.ttftMsTotal) / 1000);
    const tokensPerSecond = stats.outputTokens / decodeSeconds;
    g.push({ kind: "ttft", text: t("timeline.stats.ttft", { duration: formatDuration(averageSeconds), speed: formatTokensPerSecond(tokensPerSecond) }) });
  }

  // 缓存命中率（借鉴 dsh 8.3）：计费输入 = 未缓存输入 + 缓存读，命中率 = 缓存读 / 计费输入；
  // 高命中时 cacheRead 会远超 inputTokens，必须同口径否则命中率超 100%；有计费输入即显示
  const hitPercent = cacheHitPercent(stats);
  if (hitPercent !== null) {
    g.push({ kind: "cache", text: t("timeline.stats.cacheHit", { percent: hitPercent.toFixed(1) }) });
  }

  if (stats.inputTokens + stats.outputTokens > 0) {
    g.push({ kind: "tokens", text: t("timeline.stats.tokens", { input: formatTokens(stats.inputTokens), output: formatTokens(stats.outputTokens) }) });
  }

  // 上下文占用（借鉴 dsh 8.7 ContextMeter）：最新样本的占用百分比 + 分段 breakdown 提示；
  // 无样本不渲染
  if (stats.contextPct !== undefined) {
    g.push({ kind: "context", text: t("timeline.stats.context", { percent: formatContextPercent(stats.contextPct) }) });
  }

  return g;
});

const line = computed(() => groups.value.map((group) => group.text).join(" | "));
// 上下文占用等级（借鉴 dsh ContextMeter 警示色）：80% 起警示、95% 起告急
const contextLevel = computed(() => {
  const pct = props.stats.contextPct ?? 0;
  if (pct >= .95) return "critical";
  if (pct >= .8) return "warn";
  return "ok";
});
// 进度条宽度：占用百分比（0~100%），限制在 100 内
const meterWidth = computed(() => {
  const pct = Math.min(100, Math.max(0, (props.stats.contextPct ?? 0) * 100));
  return `${pct}%`;
});
// breakdown 提示（system/tools/messages 三段启发式，对应 dsh contextBreakdown）
const contextTip = computed(() => {
  const breakdown = props.stats.contextBreakdown;
  if (!breakdown) return t("timeline.stats.contextTip");
  return t("timeline.stats.contextTipDetail", {
    percent: formatContextPercent(props.stats.contextPct ?? 0),
    system: formatTokens(breakdown.system),
    summary: formatTokens(breakdown.summary),
    conversation: formatTokens(breakdown.conversation),
    tool: formatTokens(breakdown.tool),
  });
});
</script>

<template>
  <div v-if="line" class="session-stats-line" :title="line" :aria-label="t('timeline.stats.aria')">
    <span v-for="(group, index) in groups" :key="index" class="session-stats-line__group">
      <span v-if="index" class="session-stats-line__sep" aria-hidden="true">|</span>
      <template v-if="group.kind === 'context'">
        <span class="session-stats-line__ctx" :class="`ctx-${contextLevel}`" :title="contextTip">
          <span aria-hidden="true">{{ group.text }}</span>
          <span class="session-stats-line__meter" :class="`meter-${contextLevel}`" aria-hidden="true">
            <span class="session-stats-line__meter-fill" :class="`fill-${contextLevel}`" :style="{ width: meterWidth }"></span>
          </span>
        </span>
      </template>
      <template v-else>{{ group.text }}</template>
    </span>
  </div>
</template>
