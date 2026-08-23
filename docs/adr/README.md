# 架构决策记录

[返回文档中心](../README.md)

Architecture Decision Record（ADR）用于记录难以从代码本身还原的重大技术决策，包括背景、约束、选择、替代方案和后果。

## 何时需要 ADR

以下变化通常需要先提交 ADR：

- 修改 daemon 与客户端的进程或传输边界；
- 引入新的持久化格式或破坏性数据迁移；
- 修改公共 IPC、扩展或 Provider 兼容策略；
- 改变权限模型、信任边界或凭据存储方式；
- 引入影响多个模块的新框架或基础设施；
- 推翻已经记录的架构决策。

局部实现细节、可逆重构和普通依赖升级通常不需要 ADR。

## 状态

- `proposed`：正在讨论，尚未采用；
- `accepted`：已接受，应按该决策实现；
- `superseded`：被后续 ADR 替代；
- `deprecated`：仍可见，但不再推荐；
- `rejected`：讨论后未采用，用于保留取舍背景。

## 编号与命名

按四位数字递增：

```text
0001-short-decision-title.md
0002-another-decision.md
```

复制 [ADR-0000 模板](0000-template.md)，填写所有相关部分，并在 PR 中与实现一起评审。替代旧决策时，在新旧 ADR 中互相链接。

## 决策索引

| ADR | 状态 | 决策 |
| --- | --- | --- |
| [ADR-0001](0001-daemon-client-separation.md) | Accepted | daemon 与客户端采用分离架构 |
| [ADR-0002](0002-structured-multi-agent-workflow.md) | Proposed | 结构化多智能体 DAG、交接与范围升级 |
| [ADR-0003](0003-lazy-prompt-catalog-and-harness.md) | Accepted | 提示词统一目录与按需运行时注入 |
