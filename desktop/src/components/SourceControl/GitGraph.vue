<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Check, Clipboard, GitCommitHorizontal, LocateFixed, RefreshCw } from "@lucide/vue";
import type { GitCommitEntry } from "../../services/sztu-runtime";

const props = withDefaults(defineProps<{ commits: GitCommitEntry[]; branch: string | null; loading: boolean; loadingMore?: boolean; hasMore?: boolean }>(), { loadingMore: false, hasMore: false });
const emit = defineEmits<{ refresh: []; loadMore: [] }>();
type Segment = { from: number; to: number; color: string; upper: boolean };
type GraphCommit = GitCommitEntry & { lane: number; color: string; segments: Segment[] };
const rowHeight = 34;
const laneGap = 16;
const laneInset = 10;
const colors = ["#7c3aed", "#e46f00", "#087ea4", "#db2777", "#15803d", "#a16207", "#2563eb"];
const selectedHash = ref("");
const copied = ref(false);
const graphElement = ref<HTMLElement | null>(null);
const graphScroll = ref<HTMLElement | null>(null);

const graph = computed(() => {
  const active: string[] = [];
  const colorByHash = new Map<string, string>();
  let maxLaneCount = 1;
  const rows: GraphCommit[] = props.commits.map((commit) => {
    let lane = active.indexOf(commit.hash);
    if (lane < 0) { lane = active.length; active.push(commit.hash); }
    const commitColor = colorByHash.get(commit.hash) ?? colors[lane % colors.length];
    colorByHash.set(commit.hash, commitColor);
    const before = [...active];
    const next = [...active];
    next.splice(lane, 1);
    commit.parents.forEach((parent, index) => {
      if (!next.includes(parent)) next.splice(Math.min(lane + index, next.length), 0, parent);
      colorByHash.set(parent, index === 0 ? commitColor : colors[(lane + index) % colors.length]);
    });
    const segments: Segment[] = [];
    before.forEach((hash, from) => {
      const laneColor = colorByHash.get(hash) ?? colors[from % colors.length];
      // 每条进入当前行的活跃轨道都必须画到行中点，否则旁路分支会在行间断开。
      segments.push({ from, to: from, color: laneColor, upper: true });
      if (hash === commit.hash) {
        commit.parents.forEach((parent) => {
          const to = next.indexOf(parent);
          if (to >= 0) segments.push({ from, to, color: colorByHash.get(parent) ?? commitColor, upper: false });
        });
      } else {
        const to = next.indexOf(hash);
        if (to >= 0) segments.push({ from, to, color: laneColor, upper: false });
      }
    });
    active.splice(0, active.length, ...next);
    maxLaneCount = Math.max(maxLaneCount, before.length, next.length);
    return { ...commit, lane, color: commitColor, segments };
  });
  return { rows, width: Math.max(44, maxLaneCount * laneGap + 16) };
});
const outgoingCount = computed(() => props.commits.filter((commit) => commit.is_outgoing).length);
const selected = computed(() => props.commits.find((commit) => commit.hash === selectedHash.value) ?? null);
function laneX(lane: number) { return lane * laneGap + laneInset; }
function segmentPath(segment: Segment) {
  const from = laneX(segment.from); const to = laneX(segment.to); const middle = rowHeight / 2;
  if (segment.upper) return `M ${from} 0 L ${from} ${middle}`;
  return `M ${from} ${middle} C ${from} ${middle + 9}, ${to} ${rowHeight - 9}, ${to} ${rowHeight}`;
}
function relativeDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "刚刚";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)} 天前`;
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}
function selectCommit(commit: GitCommitEntry) { selectedHash.value = commit.hash; copied.value = false; }
async function copyHash() {
  if (!selected.value) return;
  await navigator.clipboard.writeText(selected.value.hash);
  copied.value = true;
  window.setTimeout(() => { copied.value = false; }, 1400);
}
async function locateHead() {
  const head = props.commits.find((commit) => commit.is_head);
  if (!head) return;
  selectCommit(head);
  await nextTick();
  graphElement.value?.querySelector<HTMLElement>(`[data-hash="${head.hash}"]`)?.scrollIntoView({ block: "center" });
}
function maybeLoadMore() {
  const element = graphScroll.value;
  if (!element || !props.hasMore || props.loadingMore) return;
  if (element.scrollTop + element.clientHeight >= element.scrollHeight - 180) emit("loadMore");
}
watch(() => props.commits, (commits) => {
  if (!commits.some((commit) => commit.hash === selectedHash.value)) selectedHash.value = commits.find((commit) => commit.is_head)?.hash ?? "";
}, { immediate: true });
</script>

<template>
  <section ref="graphElement" class="git-graph">
    <header class="git-graph-toolbar">
      <div><GitCommitHorizontal :size="15" /><b>图表</b><span>{{ commits.length }} 次提交</span></div>
      <span v-if="branch" class="git-graph-branch">{{ branch }}</span>
      <button type="button" title="定位到 HEAD" aria-label="定位到 HEAD" :disabled="!commits.length" @click="locateHead"><LocateFixed :size="15" /></button>
      <button type="button" :title="copied ? '已复制' : '复制选中提交哈希'" aria-label="复制选中提交哈希" :disabled="!selected" @click="copyHash"><Check v-if="copied" :size="15" /><Clipboard v-else :size="15" /></button>
      <button type="button" title="刷新提交图表" aria-label="刷新提交图表" :disabled="loading" @click="emit('refresh')"><RefreshCw :size="15" :class="{ spin: loading }" /></button>
    </header>
    <div v-if="loading && !commits.length" class="git-graph-empty"><RefreshCw :size="20" class="spin" />正在读取提交历史…</div>
    <div v-else-if="!graph.rows.length" class="git-graph-empty"><GitCommitHorizontal :size="24" /><b>暂无提交记录</b><span>完成第一次提交后，提交图表会显示在这里。</span></div>
    <div v-else ref="graphScroll" class="git-graph-scroll" @scroll.passive="maybeLoadMore">
      <div class="git-graph-list">
        <div v-if="outgoingCount" class="git-graph-outgoing"><i /><span>传出的更改</span><b>{{ outgoingCount }}</b></div>
        <article v-for="commit in graph.rows" :key="commit.hash" :data-hash="commit.hash" class="git-graph-row" :class="{ selected: selectedHash === commit.hash, outgoing: commit.is_outgoing }" tabindex="0" @click="selectCommit(commit)" @keydown.enter="selectCommit(commit)">
          <div class="git-graph-canvas" :style="{ width: `${graph.width}px` }">
            <svg :viewBox="`0 0 ${graph.width} ${rowHeight}`" preserveAspectRatio="none" aria-hidden="true">
              <path v-for="(segment, index) in commit.segments" :key="index" :d="segmentPath(segment)" :stroke="segment.color" />
            </svg>
            <i class="git-graph-node" :class="{ head: commit.is_head, merge: commit.parents.length > 1 }" :style="{ left: `${laneX(commit.lane) - 5}px`, borderColor: commit.color, backgroundColor: commit.is_head ? commit.color : undefined }" />
          </div>
          <div class="git-graph-summary"><b :title="commit.subject">{{ commit.subject }}</b><span>{{ commit.author }}</span></div>
          <div class="git-graph-refs">
            <span v-for="item in commit.refs" :key="`${item.kind}-${item.name}`" :class="`ref-${item.kind}`">{{ item.name }}</span>
          </div>
          <time :datetime="commit.date" :title="new Date(commit.date).toLocaleString('zh-CN')">{{ relativeDate(commit.date) }}</time>
          <code>{{ commit.short_hash }}</code>
        </article>
        <div class="git-graph-page-state">
          <template v-if="loadingMore"><RefreshCw :size="13" class="spin" />正在加载更早的提交…</template>
          <button v-else-if="hasMore" type="button" @click="emit('loadMore')">加载更早的提交</button>
          <template v-else>已到达最早提交</template>
        </div>
      </div>
    </div>
    <footer v-if="selected" class="git-graph-status"><span><i :style="{ background: graph.rows.find((commit) => commit.hash === selected?.hash)?.color }" />{{ selected.subject }}</span><code>{{ selected.hash }}</code><small>{{ selected.parents.length ? `${selected.parents.length} 个父提交` : "根提交" }}</small></footer>
  </section>
</template>
