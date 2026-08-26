# 测试指南

[返回文档中心](../README.md)

SztuCode 的测试范围应与变更风险匹配。不要把“全量测试通过”作为替代针对性测试的理由，也不要为纯文档改动运行会触发外部模型或写入大量状态的测试。

## TypeScript 主链测试

```bash
npm run typecheck
npm test
npm run test:e2e:ts
```

`npm run typecheck` 覆盖所有 TypeScript package、runtime、CLI、评测和
desktop 类型；根目录 `npm test` 运行 `server`、`client`、`telemetry`、
`runtime-ts`、`evaluation` 的 unit test。需要覆盖每个 workspace 时运行：

```bash
npm run test --workspaces --if-present
```

这些测试适用于协议、配置、工具、权限、上下文和会话存储。单个文件：

```bash
npx tsx --test packages/runtime-ts/tests/context-tools.test.ts
npx tsx --test packages/server/tests/*.test.ts
npx tsx --test packages/client/tests/*.test.ts
npx tsx --test packages/telemetry/tests/*.test.ts
```

`test:e2e:ts` 构建并启动真实 TypeScript daemon，再通过 TCP/NDJSON 客户端
验证请求、事件和最终 snapshot；不要用 mock router 替代 daemon 边界。

新增测试应覆盖正常路径、输入边界和关键失败路径。涉及权限时至少覆盖允许和拒绝。

## Runtime and CLI diagnostics

运行时协议和权限链路可以通过 Node 客户端验证：

```bash
npm run trace:permission
```

该命令连接本地 daemon，订阅事件，自动批准一次权限请求，并在 `run.finished` 后输出事件计数。专业 artifact Skill 的 Python helper 只按其自身文档单独验证，不属于项目测试门禁。

## Agent/Session/Server 迁移验证

迁移验证优先启动真实 TypeScript daemon 子进程，并使用本地 mock LLM、MCP TCP 服务和旧式原始 RPC 客户端。套件覆盖以下 15 类场景：

| 场景 | 断言重点 |
| --- | --- |
| 旧客户端 -> 新 daemon | 不发送 hello 仍可使用旧 envelope、method 和错误码。 |
| 新客户端 -> compatibility daemon | hello、版本能力和后续 RPC 可用。 |
| session create/list/get | response 与持久化 Session snapshot 一致。 |
| prompt 流式事件 | 事件顺序、`session_id`/`run_id` 和最终状态。 |
| steer/follow-up | 活跃 run 接收 steer，后续消息不丢失。 |
| tool permission | request/respond 顺序、允许和拒绝路径。 |
| tool failure | tool error 被记录，Agent/daemon 主循环仍可继续。 |
| abort | run 进入 aborted/cancelled，Session snapshot 收敛。 |
| daemon 重启 | 运行/已落盘 Session 可 list/get/attach，事件不重复。 |
| session fork | branch/fork 元数据与父子历史隔离。 |
| context compaction | compact 事件在 turn/run 事件之间顺序正确。 |
| subagent | child session、`parent_run_id`、映射事件和最终结果。 |
| MCP tool | 外部 MCP 调用、结果和失败诊断。 |
| desktop contract | desktop 使用的 method、事件名称和字段保持兼容。 |
| Python runtime 隔离 | Python daemon/CLI 的 ping 或 compileall 不受 TS 变更影响。 |

每个失败必须输出 `request_id`、`session_id`、`run_id`（若已分配）和 daemon
stderr；测试同时断言事件顺序和最终 Session snapshot。运行命令：

```bash
npm run test:migration
```

失败信息包含 `request_id`、`session_id`、`run_id`，同时保留 daemon 输出，便于定位协议、会话或运行级回归。
若环境没有 `uv`/`pytest`，Python 场景会明确降级为标准库 `compileall` 隔离检查；具备 Python 测试依赖时执行真实 ping 集成测试。

## 协议一致性

```bash
npm run typecheck
```

协议变更从 `packages/protocol/src` 开始，并同步 runtime、CLI 和桌面消费者。

## 文档链接

```bash
npm run docs:links
```

该命令检查根目录 Markdown 与 `docs/**/*.md` 的本地相对链接是否有效。移动或重命名文档后应运行，规则见[文档规范](documentation.md)。

## 桌面端

```bash
cd desktop
npm run build

cd src-tauri
cargo check
```

根目录的 `npm run typecheck` 已包含 `tsc -p desktop/tsconfig.json --noEmit`。
桌面 contract 变更至少运行 `npm run build --prefix desktop`，并在需要时执行
`npm run test:unit` 与 Playwright 视觉测试。

## Python runtime

Python runtime 是独立实现，不依赖 `packages/runtime-ts`。在具备 `uv` 的环境
运行：

```bash
cd py-runtime
uv run ruff check src tests
uv run mypy src
uv run pytest
```

TS 文档或 package 测试不能替代 Python 测试；迁移套件只验证两条 runtime 的
协议和进程边界。

视觉测试入口为：

```bash
cd desktop
npx playwright install chromium
npm run test:visual
```

默认使用 Playwright 安装的 Chromium，不向 `launchOptions` 写入硬编码本机路径。如需覆盖，可设置环境变量 `PLAYWRIGHT_CHROMIUM_PATH` 指向浏览器可执行文件。不要把个人绝对路径提交进仓库。

轻量配置单元测试：

```bash
cd desktop
npm run test:unit
```

UI 变更应验证至少一个常规桌面宽度和一个窄窗口，重点检查文本溢出、权限卡、时间线、Diff 页面和空/错误状态。macOS 上还应确认系统 traffic lights 与导航按钮不重叠。

## 评估

Agent 任务质量评估与普通回归测试用途不同。无需模型凭据的基础设施门禁为：

```bash
npm run eval -- validate --manifest packages/evaluation/tasks/internal-v1.json
npm run eval -- run --manifest packages/evaluation/tasks/internal-v1.json --repeat 3 --output-dir tmp/eval
```

真实 daemon、外部 command runner、SWE-bench 和指标语义见
[评估指南](../guides/evaluation.md)。评估报告可能含 patch、外部仓库内容或个人路径，不应默认提交。

## PR 中报告验证结果

建议写明实际执行结果，而不是只写“tests passed”：

```text
Validation
- npm run typecheck
- npm test
- npm run build
- npm run build --prefix desktop

Not run
- full integration suite: change does not touch daemon behavior
```
