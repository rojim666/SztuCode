import { createApp } from "vue";
import GitGraph from "../../../src/components/SourceControl/GitGraph.vue";
import type { GitCommitEntry } from "../../../src/services/sztu-runtime";
import "../../../src/source-control.css";

const hash = (value: string) => value.repeat(40).slice(0, 40);
const commits: GitCommitEntry[] = [
  { hash: hash("a"), short_hash: "aaaaaaa", parents: [hash("b")], author: "rojim666", date: "2026-08-16T10:30:00+08:00", subject: "feat(desktop): 完善源代码管理图表与基础 Git 功能", is_head: true, is_outgoing: true, refs: [{ name: "rojim", kind: "head" }] },
  { hash: hash("b"), short_hash: "bbbbbbb", parents: [hash("c")], author: "rojim666", date: "2026-08-16T09:20:00+08:00", subject: "fix(desktop): refine skill center and visual layouts", is_head: false, is_outgoing: false, refs: [{ name: "origin/rojim", kind: "remote" }] },
  { hash: hash("c"), short_hash: "ccccccc", parents: [hash("d"), hash("f")], author: "肉夹馍", date: "2026-08-15T19:40:00+08:00", subject: "Merge pull request #101 from rojim666/rojim", is_head: false, is_outgoing: false, refs: [{ name: "origin/main", kind: "remote" }, { name: "v0.4.0", kind: "tag" }] },
  { hash: hash("d"), short_hash: "ddddddd", parents: [hash("e")], author: "Miqi9880", date: "2026-08-15T17:10:00+08:00", subject: "feat(workspace): detect project profiles and validation plans", is_head: false, is_outgoing: false, refs: [] },
  { hash: hash("f"), short_hash: "fffffff", parents: [hash("g")], author: "Zixuan", date: "2026-08-15T15:40:00+08:00", subject: "feat(harness): 持久化 run 生命周期记录", is_head: false, is_outgoing: false, refs: [] },
  { hash: hash("g"), short_hash: "ggggggg", parents: [hash("e")], author: "xngyan", date: "2026-08-15T14:10:00+08:00", subject: "Fix compaction shutdown ordering in runner", is_head: false, is_outgoing: false, refs: [] },
  { hash: hash("e"), short_hash: "eeeeeee", parents: [], author: "rojim666", date: "2026-08-14T11:00:00+08:00", subject: "feat(client): desktop bootstrap", is_head: false, is_outgoing: false, refs: [] },
];

const fixtureState = globalThis as typeof globalThis & { __gitGraphLoadMore: number };
fixtureState.__gitGraphLoadMore = 0;
createApp(GitGraph, {
  commits,
  branch: "rojim",
  loading: false,
  hasMore: true,
  onLoadMore: () => { fixtureState.__gitGraphLoadMore += 1; },
}).mount("#app");
