# ADR-0002：结构化多智能体 DAG、交接与范围升级

- 状态：Proposed
- 日期：2026-08-07
- 关联：[Issue #18](https://github.com/rojim666/SztuCode/issues/18)

## 背景

现有 Subagent 能独立运行并转发事件，但 Planner、Coder、Tester 和 Reviewer 之间依赖父模型用自然语言协调。并发、重试、失败传播和交接格式没有统一约束；Coder 的职责范围也只存在于提示词中。

## 决策

在 daemon 内新增确定性 `WorkflowOrchestrator`：Planner 输出类型化 DAG，调度器只启动依赖已经成功的任务，并要求每个角色返回 `HandoffArtifact`。Tester 产物必须含命令、输出和结论；Reviewer 必须根据 Diff、测试和安全证据返回 `accept` 或 `return`。

Coder 的 `allowed_paths` 通过文件工具动态分级。范围内调用是 `workspace_write`；范围外调用升级为 `danger_full_access`，交给已有 Permission Manager。用户批准或启用 `auto` 后允许执行并把升级路径写入交接事件；拒绝或审批超时则不执行。工作区根目录边界始终不可越过。

并发、深度、Token、墙钟和重试由显式预算控制。全部 `workflow.*` 事件进入现有 EventBus，因此自动持久化到 run 事件文件、IPC 和统一 Trace。

## 替代方案

- 只用角色提示词协调：实现简单，但无法可靠验证失败传播、预算和写入范围。
- 对 Coder 越界无条件拒绝：边界清晰，但与项目已有的人在回路和 `auto` 权限语义冲突。
- 为工作流单独建立日志：会造成 Trace 分裂，客户端也需要两套回放逻辑。

## 后果

- 工作流行为可以用无模型的确定性测试覆盖，并可从 Trace 重建。
- 多 Agent 会增加 Token 和墙钟成本，评测必须同时报告质量证据与资源消耗。
- `auto` 模式能够批准角色范围升级，使用者需要把它限制在可信、可恢复的工作区。
- 后续安全扫描闭环可直接作为 Reviewer 的必需证据，而无需改变交接协议。
