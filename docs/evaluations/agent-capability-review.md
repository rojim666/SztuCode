# TypeScript Runtime Agent 能力评审（滚动版）

[返回文档中心](../README.md) · [第二版快照](agent-capability-review-v2.md) · [第三版快照](agent-capability-review-v3.md)

本文是对 `packages/runtime-ts` 的持续能力评审，随代码演进滚动更新。当前为**第四轮**
（2026-08-30，基线 `759a6b9`）：阶段一至三全部落地、durable checkpoint 上线之后的全面
复审。方法：对 runtime 全部模块逐行审查 + 故障路径推演；没有真实基准数据的项目不作
产品成绩推断。

## 1. 能力评分卡（v1 → v4 演进）

| 能力维度 | v1 | v4 | 判词 |
| --- | ---: | ---: | --- |
| 上下文管理 | 72 | **80** | 增量 token 计数、后台并行压缩、熔断+硬丢弃退路齐备；缺 microcompact 分层，摘要无 provenance |
| 工具系统 | 65 | **78** | 行号 Read、锚定 Edit、原子 MultiEdit 成立；grep 截断静默、无 rg/LSP/结构化 patch |
| 权限与安全 | 60 | **70** | 参数级 glob + per-workspace 作用域到位；但 MCP 工具 blanket `danger_full_access`（见 2.1） |
| 韧性 | 35 | **62** | 错误回注、partial messages、durable checkpoint 成立；无 resume、provider 重试纪律缺失（见 2.2） |
| 编排能力 | 55 | **74** | spawn_agent + DAG + 证据一致性校验闭环；子代理同步阻塞、无后台任务控制面 |
| 可观测性 | 85 | **81** | 事件总线 + telemetry span + TaskCanvas；EventBus 逐事件 appendFile 仍在 |
| 记忆系统 | 50 | **59** | 三层 catalog + 渐进披露 + notes 版本链；无巩固管道、无语义检索 |
| 扩展生态 | 45 | **60** | Skills 渐进披露成立；MCP 协议陈旧且无超时/取消（见 2.1） |
| **综合** | **58** | **68** | 短任务与交互可信度显著提升；重启恢复、限流纪律、并行副作用仍是高风险 |

与第三版的差异说明：权限 72→70、扩展 62→60，因本轮新确认 MCP 安全面与超时面缺口；
其余维度持平。综合维持 68——自 v3 以来新增的是评测基建（Terminal-Bench 接入），不是
runtime 能力本身。

## 2. 本轮新增的关键发现（P0）

阶段一修复了 v1 的四大致命缺陷，但本轮深挖出四个新的一级问题。

### 2.1 MCP 三重洞：无超时 + blanket 权限 + 旧协议

`mcp.ts` 是当前安全与韧性模型的一个旁路：

1. **调用无超时**（[mcp.ts:16](../../packages/runtime-ts/src/mcp.ts#L16)）：`call()` 把
   pending promise 放进 Map 后无限等待。一个挂死的 MCP server 进程 = 永久 pending 的
   工具调用 = 整个 run 卡死（bash 有 timeout，MCP 调用没有）。
2. **全部工具 blanket `danger_full_access`**（[mcp.ts:23](../../packages/runtime-ts/src/mcp.ts#L23)）：
   任何 MCP server 暴露的任何工具，不经任何能力审查即获得最高权限档。恶意/被入侵的
   MCP server 等于直接拿到 danger 档执行权——参数级 glob、bash 白名单等所有防御
   对 MCP 工具一律失效。
3. **协议版本 2024-11-05**：落后两个规范版本，无 resources/prompts 能力、无能力协商、
   无重连。且 `callTool` 只保留 text content（[mcp.ts:13](../../packages/runtime-ts/src/mcp.ts#L13)），
   图片等非文本内容静默丢弃。

对比：Claude Code 对 MCP 工具默认套用权限系统（可配置 `mcp__server__tool` 粒度规则），
调用带 deadline，server 崩溃自动重连。

### 2.2 Provider 重试纪律缺失 + 双层重试叠加

[configurable.ts:26](../../packages/runtime-ts/src/providers/configurable.ts#L26)：
`Math.min(2_000, 200 * 2 ** attempt)`——退避上限 2 秒、不读 Retry-After、无 jitter。
429 限流窗口通常 30-60 秒，2 秒间隔等于在限流窗口内持续锤击 API。v1 障碍清单第 4 项，
两个版本后仍未修复。

更糟的是**双层重试叠加**：`ConfigurableProvider` 内部重试 `max_retries` 次，而
agent-loop 的 `maxLlmFailures`（默认 3）错误回注后再次调用 provider——每次逻辑重试都
重新走一遍完整 provider 重试循环。最坏情况单个 step 产生 `(1+max_retries) ×
maxLlmFailures` 次 API 调用，且全部落在限流窗口内。两层重试没有共享预算，也没有
Retry-After 传导。

另外可重试性判断仍是正则匹配错误消息（`/\b(429|500|...)\b|timeout|.../`）——脆弱且
无法区分"请求未送达（可安全重试）"与"响应已产生但中断（可能重复计费/副作用）"。

### 2.3 Checkpoint 写入 O(n²)

[run-manager.ts:104](../../packages/runtime-ts/src/run-manager.ts#L104)：每个 tool_batch
checkpoint 触发 `replaceModelHistory` —— 全量 `JSON.stringify(messages)` + `.bak` 拷贝
+ tmp 写入 + rename，即**每步 3 次全量 IO**。200 条消息的会话跑 100 步，写入量是
初始上下文的百倍以上。v3 已指出（P1），本轮确认仍在且是长会话最大的 IO 放大源；
修法明确：每 N 步快照 + 增量 delta，或 hash 相同跳过。

### 2.4 conclude 路径无容错 + goal 破坏 prompt cache 前缀

- [agent-loop.ts:544](../../packages/runtime-ts/src/agent-loop.ts#L544)：`conclude()` 的
  provider 调用没有 try/catch——与主循环"错误回注"哲学不一致。跑到 maxSteps 后的收尾
  总结若恰逢一次 API 抖动，整个 run 以 failed 告终，[COMPLETE]/[INCOMPLETE] 判定丢失。
- [run-manager.ts:101](../../packages/runtime-ts/src/run-manager.ts#L101)：`taskText:
  run.goal` 被烘焙进 system prompt。Anthropic 路径在 system 上打了 cache_control
  断点（[anthropic.ts:24](../../packages/runtime-ts/src/providers/anthropic.ts#L24)），但
  每个不同 goal = 完全不同的 system 前缀 = 跨 run 的 prompt cache 几乎必然全量失效。
  Claude Code 把任务目标放在 user 消息里，system prompt 跨 run 保持字节级稳定。git
  快照（[prompt-loader.ts:77-78](../../packages/runtime-ts/src/prompt-loader.ts#L77-L78)）
  和 session notes 同理注入 system，进一步放大失效。

## 3. 性能障碍清单（v4 复核）

| # | 障碍 | 位置 | 状态 |
| --- | --- | --- | --- |
| 1 | 每 token 一次事件 | agent-loop.ts | ✅ 已修（75ms 合帧） |
| 2 | runs Map 永不清理 | run-manager.ts | ✅ 已修（延迟清理） |
| 3 | bash exit≠0 自动重试 | agent-loop.ts | ✅ 已修（retryable 豁免） |
| 4 | 只读 bash 永远串行 | bash-permission.ts | ✅ 已修（read_only 档） |
| 5 | provider 重试上限 2s、无 Retry-After/jitter | configurable.ts:26 | ❌ 未修（升级为 2.2 P0） |
| 6 | 每步全量 sanitize：O(n)×每步，无增量路径 | agent-loop.ts:205 | ❌ 未修 |
| 7 | checkpoint 每步全量序列化（O(n²) IO） | run-manager.ts:104 | ❌ 新增（升级为 2.3 P0） |
| 8 | EventBus 逐事件 appendFile（每事件一次 syscall） | event-bus.ts:35 | ❌ 未修 |
| 9 | grep 纯 JS + 2000 文件/200 结果**静默**截断 | tools.ts:347,381 | ❌ 未修（无截断标记是正确性问题） |
| 10 | `bash --login -c` 每次 spawn 加载 profile | tools.ts:437 | ❌ 未修 |
| 11 | git 快照 + goal + notes 注入 system prompt | run-manager.ts:101 | ❌ 新增（prompt cache 纪律） |
| 12 | spawn_agent 恒为串行批（workspace_write 不进并发批） | agent-loop.ts:297 | ❌ 新增（多子代理委派只能一个一个来） |
| 13 | MCP 调用无 deadline | mcp.ts:16 | ❌ 新增（升级为 2.1 P0） |
| 14 | TaskCanvas 全量 mermaid 每 3 步重发 | agent-loop.ts:508 | 低优先级，量大时可合帧 |

grep 有并发读取与二进制/大文件跳过（tools.ts:352-359），工程上比 v1 时进步；但
"2000 文件后 break、200 结果后 break、输出无任何截断标记"（tools.ts:347,381-384）意味着
模型无法区分"搜完了没有匹配"与"被截断了"——在大仓库里这是正确性缺陷而非纯性能问题。

## 4. 对标顶级产品的结构性差距

### 4.1 与 Claude Code / Codex CLI 的差距清单（v4 更新）

| 能力 | 顶级产品 | SztuCode 现状 | 差距本质 |
| --- | --- | --- | --- |
| 崩溃恢复 | rollout 文件 + `--resume` 重放重建 | checkpoint 只保存，`recoverInterruptedSessions` 只降级状态 | 保存 ≠ 恢复：无 operation log、无 run.resume（v3 阶段 A 的核心） |
| 限流纪律 | Retry-After 遵从 + full jitter + 预算 | 2s 封顶退避 + 双层叠加重试 | 429 场景的行为差异是数量级的 |
| 流式中断 | Esc 中断当前流注入纠正 | steering 仅步边界消费 | 长 bash/长流期间用户纠正要等一整轮 |
| 搜索 | ripgrep 原生（SIMD/mmap） | 纯 JS 正则 + 静默截断 | 大仓库搜索速度与完整性双输 |
| MCP | 权限粒度到 `mcp__server__tool`、超时、重连 | blanket danger + 无超时 + 旧协议 | MCP 是当前权限模型的最大旁路 |
| 后台任务 | task 后台化 + 状态/输出/停止 API | spawn_agent 同步阻塞父循环 | 多子代理并行委派做不了（DAG 路径除外） |
| prompt cache | system 前缀字节级稳定 | goal/git/notes 烘焙进 system | 成本与延迟的直接差距 |
| LSP | 诊断/定义/引用/重命名 | 无 | 精确代码理解停留在文本层 |

### 4.2 值得肯定的亮点（v4 复核后仍成立）

1. **后台并行压缩**：压缩与工具执行重叠，熔断后硬丢弃退路（含极限窗口兜底），比同步
   阻塞式压缩优雅。
2. **HandoffArtifact 证据一致性校验**：coder 越界改动必须与自报 escalations 一致，用
   证据反推子代理没撒谎——超越 Claude Code 的纵深防御。
3. **offload 大输出卸载 + 分页协议**：完整度高，含路径安全。
4. **stuck/denial 双 tracker + phase 追踪**：显式干预循环，Claude Code 也无显式 denial 干预。
5. **增量 token 计数缓存**（UsageCache + 每消息 WeakMap）：token 计数已免 O(n²)，
   sanitize 尚未跟上。
6. **realpath 符号链接逃逸防护**：从目标向上找第一个存在祖先校验，姿势正确。
7. **durable checkpoint 事件关联**：sequence/operation_id/checkpoint_id 三元组使 run
   事件流可对齐——这是将来 operation log 的天然落点。

## 5. 扩展路线图

### 阶段一至三：已完成（历史存档）

| 阶段 | 内容 | 验证 |
| --- | --- | --- |
| 一（止血） | 输出修复层 / LLM 错误回注 / 压缩熔断退路 / run-manager failed 状态 + 延迟清理 / bash retryable 豁免 | 132/132 测试 |
| 二（工具基础） | Read 行号分页 / Edit 锚定 + CRLF + MultiEdit / 参数级 glob 权限 + per-workspace / bash read_only 档 / token 合帧 | 134/134 测试 |
| 三（编排决策权） | spawn_agent / Planner→DAG 闭环 / Skills 渐进披露 / ask_user_question schema | 134/134 测试 |

### 阶段四：长程能力（v4 修订优先级）

| # | 事项 | 要点 | 优先级 | 状态 |
| --- | --- | --- | --- | --- |
| 16 | run 级 checkpoint | ✅ 主体已上线（tool_batch/completed/failed 三路径 + sequence 关联）。剩余：写入节流（见 #20） | 已完成 | 已完成 |
| 20 | **checkpoint 写入节流** | 每 N 步快照或 delta 记录，hash 相同跳过；消除每步 3 次全量 IO | **P0** | 未开始 |
| 21 | **provider 重试纪律** | ProviderError 分类（status/request-id/Retry-After/billing-effect）、full jitter、全局并发预算、双层重试共享预算、上下文超限专用分支 | **P0** | 未开始 |
| 22 | **MCP 修复三件套** | per-call deadline + AbortSignal、MCP 工具接入权限系统（默认 ask，非 blanket danger）、协议升级 2025-06（resources/prompts/协商）、非文本 content 保真 | **P0** | 未开始 |
| 15 | 流式 steering | AbortSignal 分级：先中断当前 LLM 流、保留部分输出，注入用户纠正 | P1 | 未开始 |
| 18 | microcompact 分层压缩 | 轻量层只清旧 tool 输出（无 LLM 调用），重 LLM 摘要留给真正需要时；与熔断退路天然衔接 | P1 | 未开始 |
| 23 | 搜索升级 | 短期：grep 加截断标记（快修）；长期：`rg --json` 后端 + cursor/truncated 元数据 | P1 | 未开始 |
| 17 | 记忆巩固管道 | session 结束时 LLM 提炼 notes → project context.md，含用户审核闭环 | P2 | 未开始 |
| 19 | MCP 升级 | 并入 #22 | — | 未开始 |
| 24 | prompt cache 纪律 | goal 移出 system prompt 到 user 消息；git 快照/notes 移入 system-reminder 式动态段 | P2 | 未开始 |
| 25 | sanitize 增量化 | 借鉴 UsageCache 模式：消息引用未变则跳过，消除每步 O(n) 全量扫描 | P2 | 未开始 |
| 26 | conclude 容错 | conclude() 的 provider 调用纳入错误回注路径（快修，半小时工作量） | P1 | 未开始 |

#20/#21/#22 是本轮新升 P0：三者分别对应"长会话不可持续"（IO 放大）、"限流场景行为
退化"（成本与封锁风险）、"安全旁路"（MCP blanket danger）。#26 是一致性快修，建议
随手带上。

### 阶段五：Durable Run Core（承接第三版阶段 A，中期目标）

阶段四完成后，按第三版审计的阶段 A-F 推进：append-only operation log（intent/result
settle、sequence 恢复、幂等键）、`run.resume`/`run.replay` RPC、后台 task 控制面
（租约/取消树/输出分页）、policy engine 规则 AST 与审计解释、记忆巩固与评测门禁。
当前 checkpoint 事件流的 sequence/operation_id 关联是这一步的正确地基。

## 6. 总评

v1 时的核心矛盾是"可观测性生产级、韧性 demo 级"。三轮建设后，韧性从 35 升到 62，
工具与编排补到了 74-78，这个 runtime 已经是一个机制上相当完整的 Agent 原型：
它有顶级产品的大部分器官，但三个系统仍在"裸奔"——**MCP 是权限与超时模型的旁路、
provider 重试没有纪律、checkpoint 只保存不恢复**。

工程判断：当前最高杠杆不是新功能，而是 #20/#21/#22 三项"把已有防线闭合"的修复，
加上 #26 这类一致性快修。它们不动架构、风险低，但分别封住长会话 IO、限流行为、
安全旁路三个真实事故源。之后才是流式 steering 与 microcompact（体验），最后是
Durable Run Core（范式升级）。

能力数值空洞依旧：134 个测试证明机制正确性，Terminal-Bench 接入已就绪但尚无
端到端成功率/成本数据。在跑出第一批基准数字之前，本文档所有分数都只是静态代码
审计的判断，不是能力证明。
