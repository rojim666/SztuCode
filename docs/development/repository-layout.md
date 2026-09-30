# 仓库目录地图

[返回文档中心](../README.md)

## 从哪里开始

根目录只保留项目入口、包管理、构建配置和开发约定。先看根 `README.md`，查详细资料进入 [文档中心](../README.md)，定位维护脚本进入 [脚本索引](../../scripts/README.md)。

默认运行链是 **Python**：`npm run daemon` / `npm run cli -- ping`，监听 `127.0.0.1:7437`。
桌面工作台连接 **TypeScript**：`npm run daemon:ts` / `npm run cli:ts -- ping`，监听 `127.0.0.1:7438`。
两者是独立实现，不能把一条链的模块或测试当作另一条链已交付的能力。

## 产品代码与入口

- `py-runtime/`：默认 daemon、Agent Loop、bus、CLI、TUI、评测和 Python 测试。
- `packages/`：TS workspace，包含 AI 适配、Agent 内核、协议、客户端、服务端、会话、遥测、runtime、CLI 和评测。
- `desktop/`：Tauri + Vue 工作台，连接 TS daemon。
- `prompt-studio/`：提示词开发工作台。
- `website/`：网站项目。
- `npm/`：发布分发目录；不作为临时输出目录。
- `scripts/`：构建、文档、导入、验收和诊断脚本。
- `tests/`：仓库级场景；模块测试也分布在各 runtime/package 内。

## 文档分类

- `docs/getting-started/`：安装和配置。
- `docs/development/`：开发、测试、文档与仓库布局规则。
- `docs/reference/`：协议、架构、提示词、插件和实现参考。
- `docs/guides/`、`docs/operations/`：专题用法及运维。
- `docs/evaluations/`：注明日期和验证方式的能力快照；最新入口见文档中心。
- `docs/architecture/`、`docs/adr/`：设计说明和决策。
- `docs/plans/`、`docs/superpowers/`：提案和实施计划；存在文件不代表已经实现。
- `docs/office-agent/`：Office 专题资料和验收资产。
- `docs/releases/`：发布记录。
- `docs/archive/`：旧方案、旧提示词及阶段报告。
- `docs/研究参考/`：外部研究资料。

根 `AGENT.md`、`AGENTS.md`、`CLAUDE.md` 保留原位置供开发工具读取；贡献、安全和行为准则的根入口也保留。

## 本地状态和生成产物

`node_modules/`、`.venv/`、`dist/`、缓存目录是依赖或生成产物；`.sztu/`、`data/` 和工具自己的隐藏目录可能保存本地会话或状态。整理时不按“看起来多余”删除它们。

一次性日志、截图、临时报告使用已忽略的 `tmp/`。不要将个人运行日志放在根目录或提交真实密钥。

## 本次整理记录（2026-09-30）

- 根目录 7 个窗口诊断脚本移至 `scripts/diagnostics/windows/`；2 个已入库输出移至其 `archive/`。
- 根目录 3 个本地日志移至 `tmp/diagnostics/2026-09-30/`，保留原文件。
- 插件和记忆说明移至 `docs/reference/`；旧提示词、记忆方案、技术报告及 TS 迁移方案移至 `docs/archive/`。
- 合并方法论、面试复盘、外部工具说明及系统提示词 HTML 的重复副本。权威副本分别是 `guides/ai-assisted-development.md`、`archive/interview-notes.md`、`archive/claw-code-tool-system.md`、`reference/system-prompts.html`。存在正文差异的桌面方案单独归档，没有覆盖旧方案。
- 修正文档中心的失效路径。英文索引链接到实际存在的中文资料，不指向未创建的翻译。

移动前后核对产品源码、配置和资源文件的 SHA-256；本次整理不更改核心代码，也保留整理前已有的工作区修改。
已入库文件的原位置可通过 Git 历史追溯；本地日志按上述路径取回。调整文档后执行 `npm run docs:links`。
