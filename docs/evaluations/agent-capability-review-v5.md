# TypeScript Runtime Agent 能力审计（第五版）

[返回文档中心](../README.md) · [第四轮滚动评审](agent-capability-review.md) · [第三版快照](agent-capability-review-v3.md)

> 审计日期：2026-08-30
> 基线：阶段五首个增量（operation lifecycle + durable replay），以当前 TypeScript runtime 代码和测试为准。
> 结论性质：静态工程审计；没有真实 benchmark 时，不声称 SWE-bench、Terminal-Bench 或竞品排名。

## 结论先行

当前 TypeScript runtime 综合生产能力仍为 **68/100**。阶段五没有带来“恢复执行”能力，而是把已有 checkpoint 快照接到一个可查询的 operation 生命周期上：run 启动/结束现在有 `operation.started`、`operation.finished`，`run.replay` 在内存事件不存在时可以从 session JSONL 回读，checkpoint 也带 `operation_id`、`sequence` 和 `checkpoint_id`。

这一步的价值是建立了 durable execution 的事实源入口，但边界必须说清：没有 `step_started`、`provider_attempt`、`tool_intent`、`tool_result`、幂等键、sequence 恢复和 `run.resume`，因此 daemon 重启后仍不能安全继续未完成 run，也不能判断外部副作用是否已经发生。

工程优先级从“保存最后一帧”推进到“记录每次操作并可判定重放”，而不是继续扩展工具数量。

## 1. 评分卡

| 能力维度 | v4 | v5 | 判定 |
| --- | ---: | ---: | --- |
| 上下文管理 | 80 | **80** | 增量 token、microcompact、增量 sanitizer 和 checkpoint 快照可用；摘要 provenance 与分层事实状态仍缺。 |
| 工具系统 | 78 | **78** | 行号 Read、锚定 Edit、MultiEdit、可见截断成立；rg/LSP/结构化 patch 仍缺。 |
| 权限与安全 | 70 | **71** | MCP 不再 blanket danger，进入可询问权限路径；正式 policy AST、deny 优先级和 shell AST 仍缺。 |
| 韧性 | 62 | **65** | operation lifecycle、磁盘 replay fallback 和 checkpoint 关联成立；没有 resume、attempt ledger 或未知效果 reconciliation。 |
| 编排能力 | 74 | **74** | DAG 和角色化子代理稳定；子代理仍同步阻塞且无 durable lease/task control plane。 |
| 可观测性 | 81 | **83** | operation 事件与 durable replay 提升了跨重启可见性；事件仍缺统一 sequence、attempt correlation 和指标聚合。 |
| 记忆系统 | 59 | **59** | notes 与三层 catalog 可用；无巩固、检索、冲突解决和审核闭环。 |
| 扩展生态 | 60 | **62** | MCP deadline、取消、协议握手和非文本 content 已改善；重连、完整 capability negotiation 与 resources/prompts 消费仍不完整。 |
| **综合生产能力** | **68** | **68** | durable replay 是基础设施进步，但未改变重启后无法安全续跑的核心限制。 |

分数代表生产机制成熟度，不代表模型智力。阶段五当前新增的 10+ 项专项测试证明局部契约，不证明进程级 crash/resume。

## 2. 阶段五已落地能力

### 2.1 Operation 生命周期

- `RunManager.start()` 发布 `operation.started`，`operation_id` 与 `run_id` 稳定关联。
- 正常和失败终态分别发布 `operation.finished`，并与 `run.finished` 保持顺序。
- 协议层已声明 operation event 类型，事件可被既有 EventBus、extension 和 session persistence 链路消费。

### 2.2 Durable replay

- `SessionStore.runEvents()` 从 session 的 run JSONL 读取并忽略损坏行，支持上限控制。
- `findRunSession()` 可按 persisted `run_ids` 反查 run 所属 session。
- `run.replay` 先读内存 EventBus，未命中时回退到 durable JSONL，daemon 重启后仍可审计已落盘事件。

### 2.3 Checkpoint 关联

- checkpoint 继续保存 tool batch、completed、failed 三类快照。
- 每个 checkpoint 具备 run 内单调 `sequence`、`operation_id`、稳定 `checkpoint_id` 和实际失败 step。
- checkpoint 已支持节流，默认每 5 步保存 tool batch，终态强制保存。

## 3. 仍未成立的能力边界

1. **Replay 不是 Resume。** replay 只能回放事件，不能从最后一个安全边界重建 AgentLoop。
2. **Checkpoint 不是 operation log。** 没有 provider attempt、tool intent/result、输入摘要、输出身份和幂等键。
3. **双文件写入没有事务边界。** context snapshot 与 run event 可能一成功一失败，没有 generation、checksum 或 writer lease。
4. **失败状态仍可能产生未知外部效果。** provider 流中断或工具进程被杀时，系统不能证明副作用是否已经发生，因此不能自动重放危险调用。
5. **sequence 不可跨恢复延续。** 当前 sequence 只在单次 AgentLoop 内存中递增，重启后没有从 durable log 继续编号的规则。
6. **operation tree 尚未建立。** 子代理、workflow task 和父 run 的生命周期仍主要通过事件字段关联，没有统一 lease、取消树和终态唯一性约束。

## 4. 性能与可靠性审计

| 优先级 | 障碍 | 当前状态 | 下一步 |
| --- | --- | --- | --- |
| P0 | 缺 step/provider/tool intent-result 账本 | **未解决** | append-only operation records，settle 后写 result，危险工具默认不重放。 |
| P0 | 无 `run.resume` 与未知效果处理 | **未解决** | 增加 resume/replay/status RPC，恢复前执行幂等与外部效果审计。 |
| P0 | operation snapshot 与 context 写入非原子 | **未解决** | generation + checksum + 单 writer，最终一致性校验。 |
| P1 | checkpoint 每次仍全量 JSON 序列化 | **部分缓解** | delta log、hash 跳过、周期快照和 fsync/rename。 |
| P1 | EventBus 逐事件 append | **未解决** | 单 writer、50-100ms micro-batch、优先级和背压。 |
| P1 | Provider retry budget 未跨层共享 | **部分解决** | 全局 token bucket、fallback、billing effect 和 attempt 账本。 |
| P1 | MCP 无自动重连/capability 完整协商 | **部分解决** | reconnect/backoff、server capability snapshot、pending rejection audit。 |
| P1 | 子代理同步阻塞 | **未解决** | `task_spawn/get/output/stop`、lease、父子取消和 artifact ref。 |

阶段五验收矩阵应覆盖：provider response 前后、tool intent 前后、tool result 前后、context/event 写入前后、`kill -9`、429、连接断开、权限等待和父任务取消；指标包括恢复耗时、重复 effect 数、terminal 唯一性和审计完整性。

## 5. 与顶级 Agent 产品的差距

Claude Code、Codex CLI、Gemini CLI 和成熟 IDE Agent 的共同优势是“失败后可继续且不会悄悄重复副作用”。当前 runtime 的主要差距仍是：

- 顶级产品有 rollout/operation 级 resume；当前只有 durable replay。
- 顶级产品将 provider attempt、限流、计费和 fallback 纳入统一控制面；当前仍是局部 ProviderError 和有限重试预算。
- 顶级产品的后台任务可观察、可暂停、可取结果；当前 `spawn_agent` 仍同步等待。
- 顶级产品的代码定位依赖 ripgrep/LSP/结构化编辑；当前核心编辑仍是文本层。
- 顶级产品的权限规则可解释且按工具/参数/scope 生效；当前 MCP 已降级为可询问权限，但正式 policy engine 尚未落地。

以上是可观察机制比较，不是对竞品内部实现的断言。

## 6. 阶段五实施路线

### 5A：Operation ledger

定义 `OperationRecord`、`StepRecord`、`AttemptRecord`、`ToolIntent`、`ToolResult` 和唯一 terminal record。每条记录带 sequence、operation、step、attempt、session、workspace、idempotency_key。

### 5B：安全恢复

实现 `run.resume` 前先构建恢复判定器：已 settle 的幂等工具不可重复执行；未知效果工具进入 `needs_reconciliation`，要求读取工作区/外部状态或用户确认。

### 5C：一致性与并发

将 context generation、operation sequence 和 checksum 放在同一 commit envelope；单 writer 串行化 session metadata、context snapshot 和 event append，避免跨文件竞态。

### 5D：Task control plane

把同步子代理拆为后台 task，提供状态、进度、输出分页、停止、租约、父子取消、预算和 artifact 引用；workflow 采用 proposal → approval → execute → review → repair。

## 最终判断

阶段五已经把项目从“只能看当前进程内事件”推进到“可以从 session 文件回放已落盘 operation 生命周期”，这是正确的基础设施方向；但它还没有跨过生产 Agent 的关键门槛：**重启后安全地继续未完成工作而不重复副作用。** 下一次能力分数只有在 operation ledger、故障注入和真实 `run.resume` 验收通过后才应上调。
