<!-- # Batch: Parallel Work Orchestration -->
# 批量：并行工作编排

<!-- ## Phase 1: Research and Plan (Plan Mode) -->
## 第一阶段：研究与规划（规划模式）
<!-- 1. Understand the scope by launching Explore agents for independent research. -->
1. 通过启动 Explore 代理进行独立研究来理解范围。
<!-- 2. Decompose the work into 5-30 independent units with explicit ownership. -->
2. 将工作分解为 5-30 个具有明确所有权的独立单元。
<!-- 3. Determine the end-to-end test recipe and shared success criteria. -->
3. 确定端到端测试方案和共享成功标准。
<!-- 4. Write a plan that records dependencies, sequencing, and integration points. -->
4. 编写计划，记录依赖关系、执行顺序和集成点。
<!-- 5. Request approval before starting implementation. -->
5. 在开始实现之前请求批准。

<!-- ## Phase 2: Spawn Workers (After Plan Approval) -->
## 第二阶段：生成工作器（计划批准后）
<!-- Spawn one background agent per independent work unit using an isolated worktree. -->
使用隔离的工作树为每个独立工作单元生成一个后台代理。
<!-- Launch independent workers together so they can run concurrently. Give every -->
<!-- worker a self-contained prompt, allowed scope, expected output, and verification -->
<!-- command. Do not assign overlapping files without an explicit integration owner. -->
同时启动独立工作器，以便它们可以并发运行。为每个工作器提供自包含的提示、允许的范围、预期输出和验证命令。如果没有明确的集成负责人，不要分配重叠的文件。

<!-- ## Phase 3: Track Progress -->
## 第三阶段：跟踪进度
<!-- Track every worker until it completes or needs attention. Maintain a compact -->
<!-- status table containing the work unit, owner, state, result, and integration -->
<!-- status. Validate each result before merging it into the shared outcome, resolve -->
<!-- conflicts deliberately, and run the agreed end-to-end test recipe after -->
<!-- integration. -->
跟踪每个工作器直到它完成或需要关注。维护一个简洁的状态表，包含工作单元、负责人、状态、结果和集成状态。在将每个结果合并到共享成果之前进行验证，有意解决冲突，并在集成后运行约定的端到端测试方案。
