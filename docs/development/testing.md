# 测试指南

[返回文档中心](../README.md)

SztuCode 的测试范围应与变更风险匹配。不要把“全量测试通过”作为替代针对性测试的理由，也不要为纯文档改动运行会触发外部模型或写入大量状态的测试。

## TypeScript 主链测试

```bash
npm run typecheck
npm test
```

适用于协议、配置、工具、权限、上下文和会话存储。单个文件：

```bash
npx tsx --test packages/runtime-ts/tests/context-tools.test.ts
```

新增测试应覆盖正常路径、输入边界和关键失败路径。涉及权限时至少覆盖允许和拒绝。

## Runtime and CLI diagnostics

运行时协议和权限链路可以通过 Node 客户端验证：

```bash
npm run trace:permission
```

该命令连接本地 daemon，订阅事件，自动批准一次权限请求，并在 `run.finished` 后输出事件计数。专业 artifact Skill 的 Python helper 只按其自身文档单独验证，不属于项目测试门禁。

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
