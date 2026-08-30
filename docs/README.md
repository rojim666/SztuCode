# SztuCode 文档中心

这里汇总 SztuCode 的使用、开发、架构、运维和历史资料。根目录 [README](../README.md) 用于快速了解和启动项目；详细规则以本目录中的现行文档为准。

## 新用户

| 文档 | 适合解决的问题 |
| --- | --- |
| [安装与启动](getting-started/installation.md) | 如何准备环境、安装依赖并启动 TUI 或桌面端 |
| [配置参考](getting-started/configuration.md) | 如何配置模型、daemon、权限、压缩和日志 |
| [运维手册](operations/runbook.md) | 如何管理 daemon、查看日志和排查常见故障 |

## 贡献者

| 文档 | 适合解决的问题 |
| --- | --- |
| [贡献指南](CONTRIBUTING.md) | Issue、分支、编码、提交和 Pull Request 的完整流程 |
| [社区行为准则](CODE_OF_CONDUCT.md) | 协作边界、问题报告与执行原则 |
| [项目路线图](ROADMAP.md) | 当前版本目标、研究方向和明确非目标 |
| [开发环境](development/development.md) | 本地开发环境、常用命令和模块修改约束 |
| [测试指南](development/testing.md) | 单元、集成、协议和桌面端测试如何选择与运行 |
| [文档规范](development/documentation.md) | 文档放置、链接、生成文件和归档规则 |
| [安全策略](SECURITY.md) | 漏洞报告渠道、敏感信息和 Agent 安全边界 |

## 设计与参考

| 文档 | 状态 | 说明 |
| --- | --- | --- |
| [架构说明](reference/architecture.md) | 现行 | daemon、客户端、运行链路和数据持久化 |
| [架构决策记录](adr/README.md) | 现行 | 重大技术决策、背景和替代方案 |
| [Wire Protocol](reference/wire-protocol.md) | 自动生成 | JSON-RPC 命令、事件和 Schema |
| [系统提示词架构](reference/system-prompts.html) | 参考 | 分层提示词结构的可视化说明 |
| [评估指南](guides/evaluation.md) | 指南 | SWE-bench 与轨迹质量评估方法 |
| [Terminal-Bench 评测指南](guides/terminal-bench.md) | 指南 | 通过 Harbor 接入 Terminal-Bench 的运行、模型与成本控制 |
| [多智能体工作流现状](evaluations/multi-agent-workflow.md) | 现行 | TypeScript DAG、角色化子 Agent 与当前验证边界 |
| [Agent 能力评审](evaluations/agent-capability-review.md) | 评审快照 | Runtime 各项能力打分、性能障碍与分阶段扩展路线 |
| [Agent 能力审计（第二版）](evaluations/agent-capability-review-v2.md) | 评审快照 | 阶段二、三落地后的重新评分、性能瓶颈、顶级产品差距和 durable 路线 |
| [Agent 能力审计（第三版）](evaluations/agent-capability-review-v3.md) | 评审快照 | Durable checkpoint 落地后的边界审计、性能回归、故障矩阵和 operation 恢复路线 |
| [AI 辅助开发方法论](guides/ai-assisted-development.md) | 指南 | 使用 AI 开发时的验证、审查与取舍 |

## 历史资料

`archive/` 中的内容用于保存设计过程和阶段性复盘，可能包含过时的架构、数量、路径或技术选型，不能作为当前实现依据：

- [桌面工作台早期方案](archive/desktop-workbench-plan.md)
- [外部 Claw-Code 工具系统参考](archive/claw-code-tool-system.md)
- [阶段性面试复盘](archive/interview-notes.md)

## 文档状态约定

- **现行**：与当前代码契约保持一致，修改相关行为时必须同步更新。
- **指南**：提供推荐流程，允许随实践持续完善。
- **自动生成**：由脚本生成，不接受手工编辑。
- **历史资料**：只用于背景理解，不定义当前行为。

发现文档与实现不一致时，请以可执行代码和测试为证据，同时提交文档修正。具体规则见 [文档规范](development/documentation.md)。
