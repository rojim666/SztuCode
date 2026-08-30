<!--
Use delegation examples to clarify how a primary agent should assign work to an
isolated sub-agent. A good delegation includes the complete task, relevant file
paths and constraints, expected deliverables, and a verification command. The
primary agent should wait for required results, inspect the handoff, and report
the sub-agent outcome without claiming work it did not verify.

Delegation flow:
1. Explore or plan when the task needs repository context.
2. Assign a self-contained implementation or review task.
3. Track foreground and background sub-agents until their results are available.
4. Integrate only verified results and preserve the parent task's constraints.
-->

使用委托示例来说明主代理应如何向隔离的子代理分配工作。良好的委托应包括完整任务、相关文件路径和约束、预期交付成果以及验证命令。主代理应等待所需结果，检查交接内容，并报告子代理的执行结果，不应声称已完成未经验证的工作。

委托流程：
1. 当任务需要仓库上下文时，先进行探索或规划。
2. 分配一个自包含的实现或审查任务。
3. 跟踪前台和后台子代理，直到其结果可用。
4. 仅集成经验证的结果，并保留父任务的约束条件。
