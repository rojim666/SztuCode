# TS Runtime 前缀缓存命中率提升：提示词 + 方案

> 目标：让 `packages/runtime-ts`（TS daemon，127.0.0.1:7438）在 Anthropic / OpenAI / DeepSeek 等 provider 上的 **prompt prefix cache 命中率** 接近 Python runtime 已落地的水平。
> 参考基线：当前未提交的 Python 改动（`core/context.py` 的 `dynamic_context_reminder`、`core/prompts/system_prompt.py` 去掉日期、`core/runner.py` 把日期+记忆层 prepend 到 goal）。

---

## 一、可直接粘贴给编码 Agent 的提示词

```
你负责提升 packages/runtime-ts（TS runtime）的 prompt 前缀缓存命中率。这是重构任务，不是新功能。

## 背景
Anthropic 显式 cache_control 与 OpenAI/DeepSeek 自动前缀缓存都遵循同一条规则：
请求体从前往后必须字节稳定，任何中间改动都会让其后所有内容失效。
因此目标顺序是：最稳定的内容在前，最易变的内容在后（system → tools → 历史 → 当前用户消息尾部）。

Python runtime 已经完成同类改造，请以它为准对齐：
- py-runtime/src/sztu_code/core/prompts/system_prompt.py：日期移出 system prompt
- py-runtime/src/sztu_code/core/context.py：system_prompt() 只返回静态 base，动态记忆层改走 dynamic_context_reminder()
- py-runtime/src/sztu_code/core/runner.py：日期 + workspace 快照 + 记忆层 prepend 到 goal 消息
- py-runtime/tests/unit/test_cache_prefix_stability.py：对应的稳定性测试

## 需要你改造的 TS 位置（先读再改）
1. packages/runtime-ts/src/prompt-loader.ts
   - buildSystemPrompt() 第 77 行把 `Date: ...` 和 working directory 写进 system prompt。
   - 第 79-83 行把 `# Project instructions`（AGENT.md/CLAUDE.md 正文）和 `# Available skills` 追加进 system prompt。
2. packages/runtime-ts/src/prompt-harness.ts
   - 第 29-31 行按 taskText 正则动态追加 executing-actions-with-care / auto-mode / memory 提示。
3. packages/runtime-ts/src/run-manager.ts
   - 第 118-121 行组装 system prompt、dynamicContext（git snapshot + memory.prompt()），并把 dynamicContext 作为第 1 条 user 消息插在 system 与 history 之间。
4. packages/runtime-ts/src/memory.ts
   - 第 13 行 todayHeader() 把当天日期写进 `## Consolidated notes (<date>)`。
5. packages/runtime-ts/src/providers/anthropic.ts
   - 第 38 行把整个 system join 成单个 text block 打一个 ephemeral 断点。
   - 第 42 行 cache_control 打在"最后一个工具"上。
6. packages/runtime-ts/src/providers/openai.ts
   - 第 124、133 行给 OpenAI chat 请求发 cache_control。

## 必须达成的改造
A. system prompt 只保留字节稳定的静态前缀：
   - 移除日期（`new Date().toISOString().slice(0,10)`）与任何每次调用都会变的内容。
   - 记忆层（global/project/profile/session notes）不进 system prompt。
   - 项目指令文件正文与 skills 列表移出 system（改为动态层或按需读取），或至少保证其内容变化不影响 system 前缀。
B. 动态内容统一放到"最靠后的可变点"：
   - 日期、git 工作区快照、记忆快照合成一个 reminder，附加到当前用户消息（goal）尾部，而不是插在 history 之前。
   - 记忆快照在单个 run 内冻结；run 内的可见性继续走 readLive / 工具。
C. provider 断点：
   - Anthropic：system 拆成"稳定 block（带 cache_control）+ 易变尾部（不带）"；工具按 name 稳定排序，断点打在固定边界。
   - OpenAI/DeepSeek：不再发无意义的 cache_control；改为保证前缀字节稳定，并在支持时使用稳定的 prompt_cache_key。
D. 可观测与回归测试：
   - 新增 packages/runtime-ts/tests/cache-prefix-stability.test.ts，对齐 Python 的测试：
     * system prompt 不含日期、不含记忆层、不含 git snapshot；
     * 同 workspace 连续两次构建字节相等；
     * 修改工作区文件后 system prompt 不变。
   - 增加一个 append-only 断言：同一会话连续两步的请求消息序列，前一步是后一步的前缀。

## 约束
- 遵守 AGENT.md / CLAUDE.md：协议类型改动放 packages/protocol，runtime 行为放 packages/runtime-ts。
- 不新增依赖，优先用 Node 内置。
- 保留原有安全与权限行为，不降低任何检查。
- 不修改 Python runtime。

## 验收
- npm run typecheck 通过
- npm test 通过（含新增测试）
- npm run build 通过
- 说明每个改动如何减少前缀失效，并给出改动前后 system prompt 字节稳定性的证据。

先给出简短的改动计划，然后直接实施，最后报告验证结果。
```

---

## 二、方案（诊断 → 改造 → 验证）

### 0. 缓存规则（决策依据）

| Provider | 缓存机制 | 稳定前缀要求 |
| --- | --- | --- |
| Anthropic | 显式 `cache_control: {type:"ephemeral"}`，最多 4 个断点，命中断点前的全部内容 | 断点前字节完全一致 |
| OpenAI / DeepSeek / 兼容端点 | 自动前缀缓存（≥1024 token 前缀，命中按前缀计费） | 请求体前缀字节完全一致 |
| OpenAI Responses | 自动前缀缓存 | 同上；`instructions` 也参与前缀 |

**唯一原则：把最稳定的内容放最前，把易变内容放最后；任何位于中间的易变字段都会让其后全部失效。**

### 1. 现状问题（按影响排序）

**P0 — 直接击穿前缀**
1. `prompt-loader.ts:77` system prompt 含 `Date: YYYY-MM-DD`：跨天（甚至跨会话）缓存 100% 失效。
2. `run-manager.ts:119-121` `dynamicContext`（git snapshot + memory 快照）插在 system 与 history 之间：
   - 只要工作区有改动，git snapshot 每 run 都变；
   - `memory.ts:13` 的 `## Consolidated notes (<date>)` 带日期，且笔记更新会重渲染；
   - 它位于索引 1，改动会让其后的全部历史前缀失效。

**P1 — 间歇性失效**
3. `prompt-loader.ts:79-83` 把 AGENT.md/CLAUDE.md 正文与 skills 列表写进 system：agent 编辑这些文件后，下一次 run 的 system 立即改变。
4. `prompt-harness.ts:29-31` 按 `taskText` 正则追加策略提示：不同任务得到不同 system，缓存有效前缀被截断。
5. `providers/anthropic.ts:38` 整个 system 作为单个 block：易变尾部污染整个 system 缓存。
6. `anthropic.ts:42` / `openai.ts:124` cache_control 打在"最后一个工具"：MCP 异步加载或插件增删导致断点位置漂移。

**P2 — 无效字段 / 缺失观测**
7. `openai.ts:133` 给 OpenAI 系发 `cache_control`：OpenAI/DeepSeek 不识别该字段（自动前缀缓存），属于噪声甚至报错风险。
8. 无 TS 版前缀稳定性测试，无命中率回归护栏。

### 2. 改造方案

**改造 1：system prompt 纯静态化**（`prompt-loader.ts`）
- 删除 `Date:` 与 working directory 的动态部分（或整体移出）。
- 保持 `# Runtime context` 只含不随会话变化的内容；易变项一律移出。
- 对同一 `(workspaceRoot, role, prompt 版本, 工具集合)` 的 system prompt 做进程内 memo，避免每 run 重新渲染。

**改造 2：动态层后移**（`run-manager.ts` + `memory.ts`）
- 合成 `dynamicReminder = [日期, git snapshot, memory 快照]`，以 `<system-reminder>` 形式附加到**当前用户消息（goal）尾部**，与 Python `prepend_goal_reminder` 对齐。
- 删除 `memory.ts:13` 的日期头部（或改为不含日期的稳定标题）。
- 记忆快照在 run 启动时冻结；run 内写入仍通过 `readLive` / 工具可见。

**改造 3：provider 断点对齐**（`providers/anthropic.ts`、`providers/openai.ts`）
- Anthropic：system 拆为 `[{稳定前缀, cache_control: ephemeral}, {易变尾部}]`；工具按 `name` 排序，断点打在同一稳定边界；必要时在首条稳定 user 消息再加一个断点（≤4）。
- OpenAI 系：按 provider/api_format 区分，不发 `cache_control`；保证前缀字节稳定，支持时使用稳定 `prompt_cache_key`。

**改造 4：顺序与排序不变性**
- 统一约定：`静态 system → 工具定义（稳定排序）→ 历史（append-only）→ 当前用户消息尾部动态 reminder`。
- 复核 `context.ts` 的 `IncrementalContextSanitizer` 与压缩路径，确保 `toolResultLimit` 稳定、压缩只在阈值触发，避免中途改写前缀。

**改造 5：观测与护栏**
- 复用 `run.finished` 的 `cache_read_input_tokens` / `cache_creation_input_tokens`，新增按 run 聚合的命中率输出。
- 新增 `packages/runtime-ts/tests/cache-prefix-stability.test.ts`（对齐 Python 的 `test_cache_prefix_stability.py`）。
- 新增 append-only 断言：连续两步请求的消息序列满足前缀关系。

### 3. 验收与验证

```bash
npm run typecheck
npm test
npm run build
npm run build --prefix desktop   # UI 有改动时
```

验收标准：
- 同 workspace 连续两次 `buildSystemPrompt` 字节相等；
- 修改工作区文件后 system prompt 不变；
- system prompt 不含日期、记忆层、git snapshot；
- 连续两步请求满足"前一步是后一步前缀"；
- 改造前后各跑一次同一任务，比较 `cache_read_input_tokens` 占比（目标：稳态步骤命中率显著上升）。

### 4. 建议实施顺序

1. P0：日期出 system + 动态层后移（收益最大，改动集中）
2. P1：项目指令/skills 出 system + provider 断点
3. P2：OpenAI cache_control 清理 + 测试与观测护栏
