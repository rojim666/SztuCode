# 贡献指南

[返回文档中心](README.md)

欢迎通过代码、测试、文档、设计和评测参与。先完成一个可验证的小改动，不需要先读完所有架构文档或安装整个项目。

## 1. 选任务，确定范围

- **小修直接 PR**：错别字、文档补充、已有行为的小范围修复不强制先开 Issue。在 PR 中说明问题与验证方法即可。
- **已有 Issue 先留言**：说明要做的部分和简短方案，检查认领/关联 PR，避免重复。范围明确且无人处理时无需等批准；范围有争议或涉及公共接口、安全、存储格式时先讨论。
- **大改先 Issue**：新功能、架构调整或研究实验先写清问题、范围、验收条件和风险；达成范围共识后再实现。较大的 Epic 拆成能独立验证的 PR。

可以从 [good first issue](https://github.com/rojim666/SztuCode/labels/good%20first%20issue) 或 [help wanted](https://github.com/rojim666/SztuCode/labels/help%20wanted) 找任务。没有合适标签也可选一个小问题。认领不是硬性截止承诺；做不完请留言交接，连续 14 天无进展时维护者可重新开放认领。

遵守 [行为准则](CODE_OF_CONDUCT.md)。安全漏洞、权限绕过和凭据泄漏不要公开报告，按 [安全政策](SECURITY.md) 处理。

## 2. 建分支，只装需要的环境

没有仓库写权限时先在 GitHub Fork，再克隆自己的 Fork；已有权限也请用分支提交 PR，不直接推 main。

```bash
# 将 YOUR_ACCOUNT 替换为自己的 GitHub 账号
git clone https://github.com/YOUR_ACCOUNT/SztuCode.git
cd SztuCode
git remote add upstream https://github.com/rojim666/SztuCode.git
git fetch upstream
git switch -c docs/short-description upstream/main
```

有写权限者可克隆原仓库并从 `origin/main` 建分支。默认目标是 `main`，Issue 明确指定其他基线时遵从该基线。分支名用 `docs/`、`fix/`、`feat/` 或 `test/` 加简短描述即可，Issue 编号可选。

### 按目录选环境

| 修改范围 | 环境与入口 |
| --- | --- |
| 文档、Issue/PR 模板 | Node.js 20+，根目录 `npm ci`；无需模型 Key、Rust 或启动 daemon |
| Python Agent、daemon、CLI、评测 | Python 3.12 或 3.13、uv；根目录 `uv sync --project py-runtime --frozen` |
| TypeScript 运行链、协议、Node CLI | Node.js 20+；根目录 `npm ci` 和 `npm ci --prefix desktop`（根类型检查包含 desktop） |
| 桌面工作台 | 上述 TS 环境，加 Python/uv 并执行 `uv sync --project py-runtime --frozen`（桌面启动/构建会准备文档解析 runtime）；原生 Tauri 另需 Rust、系统依赖，见 [Desktop README](../desktop/README.md) |

当前默认产品运行时是 `py-runtime/src/sztu_code`；`packages/` 与 `desktop/` 是仍可运行的 TypeScript 桌面链。新增 Agent 产品能力优先落在 Python，不要误把 Skill 中的 Python helper 当成主运行时。目录边界见 [仓库地图](development/repository-layout.md)，编码约定见 [AGENTS.md](../AGENTS.md)。

## 3. 修改与验证

一次 PR 解决一个问题，不夹带无关重构或全仓格式化。修 Bug 补复现测试；新增行为覆盖正常、错误和权限拒绝路径。检查按影响范围选择，不要求纯文档贡献跑所有测试。

| 改动 | 本地验证 |
| --- | --- |
| 所有改动 | `git diff --check`；检查 diff 无密钥、缓存、私有内容或未脱敏日志 |
| 文档和模板 | `npm run docs:links`；预览 Markdown，模板改动检查 YAML 结构 |
| Python 运行时 | 在 `py-runtime/` 执行 `uv run ruff check src tests`、`uv run mypy src`，以及相关 `uv run pytest tests/...`；核心生命周期/权限改动扩大到相关集成测试 |
| TS 运行链 | 根目录 `npm run typecheck`、`npm test`、`npm run build`；协议/会话改动补对应集成验证 |
| TS 协议 | 上述检查外，运行 `npm run docs:protocol`，提交对应生成文档并核对消费者 |
| 桌面 UI | TS 检查与 `npm run build --prefix desktop`；相关 unit/visual 测试，提供截图；Rust 变更在 `desktop/src-tauri` 运行 `cargo check` |

命令细节见 [测试指南](development/testing.md)。仅改文档不代表 CI 自动跳过代码检查，仍需查看 PR 的实际检查结果。失败时记录命令、错误与是否能在基线复现；不要删测试、弱化断言或绕过合并门禁。环境缺失导致未运行的检查写明原因，不能写成通过。真实模型评测需明确成本和凭据，不是首次贡献的前提。

## 4. 提交 PR，完成 Review

```bash
git add <本次修改的文件>
git commit -s -m "docs: simplify contributor workflow"
git push -u origin HEAD
```

`-s` 添加 [DCO 1.1](https://developercertificate.org/) 的 `Signed-off-by`，表示你有权按项目许可证提交贡献，不转让著作权。提交信息说明具体意图，Conventional Commits 风格推荐但不额外增加格式流程。

在 GitHub 向 `rojim666/SztuCode` 的 `main` 提交 PR：

1. 用模板说明**改了什么、为什么、如何验证、剩余风险**。有关联 Issue 就链接；只有完整满足验收时才用 `Closes #编号`。
2. 已完成的改动可直接 Ready for review；还在实现或希望提前讨论时使用 Draft，不强制每个 PR 先走 Draft。
3. 回应 Review，更新必要的测试、文档和截图。需要同步基线时处理冲突，不强推覆盖他人的提交。
4. 由维护者检查范围、验证结果和安全/兼容性后合并，遵守仓库要求的 CI、Review 和 CODEOWNERS 规则；贡献者不必自行找齐所有 Reviewer。

不合并含凭据/私有内容、削弱安全边界、验收不明确或未解释失败检查的改动。协议、持久化、并发和权限变化尤其需要对应模块的审查。维护者可要求拆分过大的 PR。

## 卡住时

在 Issue 或 PR 留下：你想完成什么、已做什么、具体错误、需要什么帮助。贴脱敏信息即可，不必先写长报告。流程之外的设计背景按需查阅 [路线图](ROADMAP.md)、[架构决策](adr/README.md) 和 [开发文档](development/development.md)。
