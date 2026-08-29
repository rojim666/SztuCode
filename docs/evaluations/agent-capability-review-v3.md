# TypeScript Runtime Agent 能力审计（第三版）

[返回文档中心](../README.md) · [第二版评审](agent-capability-review-v2.md)

> 审计日期：2026-08-30
> 范围：`packages/runtime-ts`、`packages/protocol`、TypeScript daemon 的运行、持久化、工具、Provider、编排和测试路径。
> 方法：以提交 `9f6d228`（durable checkpoint）为基线，结合代码证据和故障路径审查；没有真实基准数据的项目不作产品成绩推断。

## 结论先行

当前 runtime 的综合生产能力调整为 **68/100**（第二版 66）。这次提升来自 checkpoint、原子 context 替换、失败路径保存 partial messages，以及本轮新增的 checkpoint `sequence`/`operation_id`/`checkpoint_id` 关联和真实失败 step；但它只解决了“最近状态可以被保存”，没有解决“未完成 operation 可以在重启后继续”。

最容易被误读的边界是：`run.checkpoint` 是摘要事件，`context.json` 是最新快照，两者不是完整 durable operation log。当前 daemon 启动时的 `recoverInterruptedSessions()` 仍只改变 session 状态，不会重建 run。因此长任务的核心风险仍然是重复执行、未知外部效果和无法解释的恢复。

工程优先级应从“继续增加工具”转为建立可恢复 operation 内核，再将 Provider 控制面、工具执行面和多 Agent 调度面接到同一棵 operation tree 上。

## 1. 评分卡

| 能力 | v2 | v3 | 判定依据 |
| --- | ---: | ---: | --- |
| 上下文管理 | 79 | **80** | 增加 checkpoint 后上下文可保存；仍有每步全量 sanitize、两级压缩和无 provenance 摘要。 |
| 工具系统 | 78 | **78** | 行号 Read、锚定 Edit、原子 MultiEdit 成立；grep/LSP/结构化 patch 仍缺。 |
| 权限与安全 | 72 | **72** | 参数 glob 和 workspace policy 已有；规则优先级、解释和 shell AST 尚未统一。 |
| 韧性 | 57 | **62** | tool batch、completed、failed 可落盘，partial messages 可保存；无 step/attempt 账本、resume 或未知效果 reconciliation。 |
| 编排能力 | 74 | **74** | DAG 和角色化子代理可执行；子代理仍是同步调用，缺 durable task control plane。 |
| 可观测性 | 80 | **81** | checkpoint 增加状态可见性；事件仍逐条 append，缺稳定 operation/attempt correlation。 |
| 记忆系统 | 59 | **59** | 三层 catalog 和 notes 可用；无巩固、检索、冲突与用户审核闭环。 |
| 扩展生态 | 62 | **62** | skills 渐进披露已成立；MCP 仍只有基础 tools 能力。 |
| **综合生产能力** | **66** | **68** | 交互和短任务可信度提升；重启、网络抖动、并行副作用仍是高风险。 |

分数含义是当前实现的生产可用度，不是模型智力。现有测试只能证明局部契约；尚无进程级 kill、真实 429、仓库规模搜索和长会话成本基准。

## 2. Checkpoint 正确性审计

### 已解决

- `AgentLoop` 在 tool batch、正常完成和失败路径调用 `onCheckpoint`。
- `RunManager` 保存去除 system message 后的模型上下文，并追加 `run.checkpoint`。
- `SessionStore.replaceModelHistory()` 使用固定 `.bak`、临时文件和 `rename()`，避免无限时间戳备份。
- 失败路径尝试保存 `partialMessages`，降低多步工作完全蒸发的概率。
- 每个 checkpoint 现在带 run 内单调 `sequence`，并以 `operation_id` 与 `checkpoint_id` 建立稳定关联。
- 失败 checkpoint 使用 AgentLoop 的当前 step，不再固定写入 `step: 0`；专项测试覆盖 Provider 连续失败路径。

### 尚未解决

1. **不是 operation log。** 没有 `operation_started`、`step_started`、`provider_attempt`、`tool_intent`、`tool_result`、`operation_finished`，也没有 sequence、attempt、结果身份和幂等键。
2. **序列仍只覆盖 checkpoint。** 当前 sequence 是单次 AgentLoop 内的 checkpoint 序列，不覆盖 provider attempt、tool intent/result，也没有从持久化记录恢复后续编号。
3. **没有统一 commit point。** context 写入和 run event 写入是独立文件操作，可能一方成功、另一方失败；没有 generation、checksum 或单 writer lease。
4. **不能 resume。** `recoverInterruptedSessions()` 不读取 checkpoint 重建运行；当前不存在 `run.resume`/`run.replay` RPC。
5. **新增 IO 回归。** 每个 tool batch 都可能完整序列化模型上下文，长会话产生 O(n²) 写入和序列化成本。

因此当前成熟度是“可恢复快照（Level 1.5）”，不是“可重放 operation（Level 3）”。

## 3. 顶级产品对照后的关键缺口

Claude Code、Codex CLI、Gemini CLI 和成熟 IDE Agent 的共同用户体验不是工具数量，而是：失败后可继续、权限可解释、后台任务可观察、结果可引用、成本可控制。当前 runtime 仍缺：

- provider attempt 账本、Retry-After/full jitter、fallback 和 billing effect 分类；
- `task_spawn/get/output/stop` 后台任务协议、租约、取消树和资源配额；
- ripgrep 原生搜索、LSP diagnostics/definition/references/rename、结构化 patch；
- deny/ask/allow 优先级明确的 policy engine、规则来源和审计解释；
- microcompact、事实来源/文件证据/引用 ID，以及稳定 prompt prefix cache；
- MCP resources/prompts、能力协商、超时、取消、重连和非文本 content 保真；
- session 结束后的记忆巩固、语义检索、冲突解决、过期和用户批准。

这不是声称其他产品的内部实现完全相同，而是按可观察的工程能力比较；本项目没有实测 benchmark 时，不应声称 SWE-bench 或 Terminal-Bench 排名。

## 4. 性能障碍与验证矩阵

| 优先级 | 障碍 | 影响 | 首选修复 |
| --- | --- | --- | --- |
| P0 | 快照替代 operation log | 崩溃后重跑，副作用可能重复 | append-only record + intent/result settle + resume |
| P0 | retry 无 Retry-After/jitter/分类 | 429 retry storm、重复计费 | ProviderError、预算、token bucket、fallback |
| P0 | 子代理无 durable lease | 悬挂、重复、父子状态不一致 | operation tree、task lease、terminal idempotency |
| P1 | 每步全量 sanitize 和 context write | 长会话 O(n²) CPU/IO | 增量索引、delta log、每 N 步快照、hash 跳过 |
| P1 | EventBus 逐事件 append | syscall、尾延迟和背压放大 | 单 writer、50-100ms micro-batch、优先级丢弃策略 |
| P1 | JS grep 读全文件 | 大仓库 CPU/RSS 高、截断不透明 | `rg --json` 后端，cursor/matched_files/truncated |
| P1 | prompt/skills/session 全量扫描写回 | 每 run 和每消息重复 IO | mtime/hash cache、批量 stats、writer lease |
| P2 | MCP 无超时/取消/重连 | server 卡死形成永久 pending | per-call deadline、AbortSignal、backoff |

故障注入必须覆盖：provider response 前后、tool intent 前后、tool result 前后、context 写入前后、event 写入前后、`kill -9`、429、连接断开、权限等待、父任务取消。每个场景都要检查：是否重复外部效果、恢复耗时、最终状态唯一性、审计记录完整性。

建议先建立四组基准：10k/100k 消息的 sanitize 与 heap；1k/10k/100k 文件的 `rg` 与 JS fallback；100/1k/10k events 的 publish-to-flush 与 syscall；上述故障矩阵的恢复时间和重复 effect 数。没有这些数字前，任何“性能接近顶级产品”的结论都不可靠。

## 5. 逐步扩展路线

### 阶段 A：Durable Run Core（下一优先级）

定义 `OperationRecord`、`StepRecord`、`AttemptRecord`、`ToolIntent`、`ToolResult`、`OperationTerminal`。先用 append-only JSONL，每条记录带 sequence、operation、step、attempt、session、workspace。provider settle 后写 attempt；工具先写 intent，再执行，再写 result；未知外部效果默认不自动重放，而是要求读回确认。增加 `run.resume`、`run.replay` 和 operation status。

验收标准：kill 注入后成功幂等工具不重复，未知效果有明确 audit，任何终态只有一个 terminal record，恢复后能继续未完成步骤。

### 阶段 B：Provider Control Plane

统一错误分类（HTTP status、retry-after、request id、partial response、billing effect），加入 full jitter、provider/global budget、并发 token bucket、上下文超限专用分支和显式 fallback 记录。将 facade 从 AgentLoop 提出，避免循环承担策略与执行。

### 阶段 C：Tool Plane 2.0

以 `rg --json`、LSP、结构化 patch 和统一 output envelope 为核心；所有结果带 cursor、truncated、artifact ref、位置证据和 schema version。MultiEdit 进一步采用 fsync/rename 或 patch journal，明确 crash 语义。

### 阶段 D：Permission Policy Engine

建立 allow/ask/deny 的正式规则 AST，固定 deny-overrides-allow、作用域（global/project/workspace/session）、来源、版本和审计解释；Bash 解析升级为 shell AST，MCP/extension 工具加载时执行 capability review。

### 阶段 E：Autonomous Task Plane

把同步 `spawn_agent` 拆成后台 task API，支持状态、进度、输出分页、停止、租约、父子取消、优先级、并发/预算配额和 artifact 引用。workflow 采用 proposal → approval → execute → review → repair 状态机。

### 阶段 F：Memory、Skills、MCP 与评测闭环

增加稳定 prompt cache、skill 版本/依赖/冲突/风险/provenance、MCP capability negotiation/resources/prompts/reconnect，构建长会话、权限、恢复、成本和仓库规模的持续评测门禁。

## 6. 不应采取的路线

- 不要用更多工具数量掩盖没有 resume 的基础缺陷。
- 不要把 JSONL 快照称为事务；没有 sequence/checksum/lease 就不能宣称 crash-safe。
- 不要在无基准数据时发布竞品成绩或“接近 Claude Code/Codex”的结论。
- 不要让模型自行决定 retry、危险重放和跨 workspace 权限；这些必须由 runtime policy 控制。

## 最终判断

本项目已经具备可信的 Agent loop、工具契约和 DAG 原型，阶段二、三的功能建设是有效的；durable checkpoint 是正确的第一步，但它暴露了真正的下一道门槛：**从保存最后一帧，升级到记录并恢复整个 operation。** 在完成阶段 A 并用故障注入证明不重复副作用之前，项目应定位为“高级 Agent runtime 原型”，而不是顶级生产 coding agent。
