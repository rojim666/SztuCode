# 贡献指南

[返回文档中心](README.md)

感谢你参与 SztuCode。项目欢迎代码、测试、文档、设计、评测和问题分析等贡献。为了让学习型协作仍然保持可维护性，所有改动都应通过公开 Issue、分支、Pull Request 和 Review 留下可复现记录。

## 开始之前

请先阅读：

- [README](../README.md)：项目定位、架构和运行方式；
- [路线图](ROADMAP.md)：当前版本目标与非目标；
- [行为准则](CODE_OF_CONDUCT.md)：社区协作边界；
- [安全政策](SECURITY.md)：安全问题的非公开报告方式；
- [架构决策记录](adr/README.md)：重要技术决策及其背景。

普通缺陷和功能建议请先创建或认领 Issue。安全漏洞、密钥泄漏或可被利用的权限绕过不得提交公开 Issue，请按安全政策私下报告。

## 开发环境

基础开发需要：

- Git；
- Node.js 20+；
- 可选：Rust stable 和系统依赖，用于桌面端开发。部分 artifact Skill 会按需调用 Python helper，但不属于项目主链依赖。

克隆并安装主运行时依赖：

```bash
git clone https://github.com/rojim666/SztuCode.git
cd SztuCode
npm install
```

运行基础检查：

```bash
npm run typecheck
npm test
npm run build
```

如果修改了协议，必须从 `packages/protocol/src` 更新共享类型并核验所有消费者：

```bash
npm run typecheck
```

桌面端开发：

```bash
cd desktop
npm install
npm run build
npm run test:visual

cd src-tauri
cargo check
```

视觉测试可能需要本机安装 Playwright 浏览器。

## 选择和认领任务

推荐新贡献者从带有 [`good first issue`](https://github.com/rojim666/SztuCode/labels/good%20first%20issue) 标签的任务开始；需要社区协助但范围较大的任务使用 [`help wanted`](https://github.com/rojim666/SztuCode/labels/help%20wanted)。

认领前请在 Issue 下留言，说明准备采取的方案和预计完成时间。维护者确认后再开始实现，避免多人重复工作。若连续 14 天没有进展说明，Issue 可以重新开放认领。

一个适合进入开发的 Issue 应至少包含：

- 可复现的问题或明确的用户价值；
- 有边界的工作范围；
- 可验证的验收标准；
- 已知依赖、风险或非目标。

较大的 Epic 应先拆分为可独立 Review 的子任务。不要在一个 PR 中同时完成无关重构、功能开发和界面改版。

## 分支流程

默认从目标基线分支创建短生命周期分支。当前长期开发分支或默认合并分支以 GitHub 仓库设置和对应 Issue 为准；不确定时先在 Issue 中确认。

建议分支命名：

```text
feat/<issue-id>-short-name
fix/<issue-id>-short-name
docs/<issue-id>-short-name
test/<issue-id>-short-name
refactor/<issue-id>-short-name
```

示例：

```bash
git fetch origin
git switch <base-branch>
git pull --ff-only
git switch -c feat/12-lsp-tool
```

提交 PR 前，将分支更新到最新基线并自行处理冲突。不要对已供他人使用的共享分支强制推送；确需整理个人 PR 分支时，也应先确认不会覆盖协作者提交。

## 编码和测试要求

- 遵循现有模块边界和代码风格，不为单一用例引入不必要抽象。
- TypeScript 代码必须通过严格类型检查和对应测试。
- 新增或修改行为必须配套测试；修复缺陷时优先先补复现用例。
- 测试范围与风险匹配：协议、权限、会话和 Agent Loop 变更需要相应集成验证。
- 新工具必须声明输入模型、权限级别、失败语义和测试。
- 不在代码、测试、日志、截图或 Issue 中提交 API Key、Token、个人信息和私有仓库内容。
- 用户可见的桌面端改动应验证构建，并在 PR 中提供截图或录屏。
- 注释只解释不明显的约束和决策，不重复代码本身。

仓库级编码约定以 [AGENT.md](../AGENT.md) 为准。

## 提交信息

推荐使用简洁的 Conventional Commits 风格：

```text
feat: add workspace symbol search
fix: prevent permission cache bypass
docs: add contributor setup guide
test: cover context compaction fallback
refactor: isolate provider message conversion
```

每个提交应表达一个完整意图，并保持可构建、可测试。避免使用“update”“fix bug”等无法说明改动目的的信息。生成文件应和对应源模型修改放在同一 PR 中。

本项目采用 [Developer Certificate of Origin 1.1](https://developercertificate.org/) 的贡献声明方式。提交时添加 Signed-off-by：

```bash
git commit -s -m "feat: add workspace symbol search"
```

签署表示你有权按项目许可证提交该贡献，不代表转让著作权。

## Pull Request 流程

1. 先关联 Issue，确认范围和验收标准。
2. 创建分支并完成最小、聚焦的实现。
3. 在本地运行与改动相关的检查和测试。
4. 推送分支并创建 Draft PR，尽早暴露设计问题。
5. 填写 PR 模板，说明动机、方案、风险、验证结果和界面证据。
6. CI 通过且实现稳定后标记 Ready for review。
7. 回应 Review 时说明处理方式；不同意建议时提供代码或测试依据。
8. 至少一名有对应模块所有权的 Reviewer 批准后合并。

维护者可以要求拆分过大的 PR。以下情况通常不会合并：

- 没有关联问题或无法说明用户价值；
- 验收标准不可验证；
- 降低权限、安全或数据保护边界；
- 新行为没有测试，且未说明无法测试的原因；
- 包含密钥、生成缓存、大型构建产物或无关格式化改动；
- 绕过失败检查或删除测试来获得通过。

## Review 标准

Reviewer 重点检查：

- 行为是否满足 Issue，而不是只检查代码能否运行；
- 协议、权限、持久化和并发语义是否保持兼容；
- 失败路径是否可恢复、可观察且不会误报成功；
- 测试是否覆盖关键边界和回归风险；
- 文档、协议和界面是否与实现同步；
- 改动范围是否聚焦，是否影响无关文件。

Review 是共同承担质量责任，不是对贡献者能力的评价。所有反馈应针对代码、行为和证据。

## 获取帮助

环境问题或实现讨论优先放在对应 Issue 或 Pull Request 中，方便后续贡献者检索。涉及安全、隐私或凭据的信息按 [SECURITY.md](SECURITY.md) 私下沟通。
