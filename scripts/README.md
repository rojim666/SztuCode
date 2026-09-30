# 开发与维护脚本

从仓库根目录执行脚本。入口命令以根 `package.json` 为准；脚本不是 Agent 运行时模块。

## 构建与资源

- `prepare-plugin-assets.js`、`prepare-skill-assets.js`：准备桌面分发资源。
- `import-workbuddy.mjs`：导入提示词资源。
- `cleanup-desktop-processes.js`：桌面进程清理工具，执行前阅读其影响范围。

## 文档与诊断

- `check_markdown_links.ts`：`npm run docs:links`。
- `gen_protocol_doc.ts`：`npm run docs:protocol`。
- `trace_permission_flow.ts`：`npm run trace:permission`。
- [Windows 窗口诊断](diagnostics/windows/README.md)：截图、窗口尺寸与圆角探测；原根目录临时脚本集中在这里。

## 评测与验收

- `runtime_ts_e2e.ts`：`npm run test:e2e:ts`，本地 mock 模型及真实 TS daemon。
- `migration_validation.ts`：迁移验证脚本，当前没有同名根 npm script。
- `eval-semantic-search.ts`：`npm run eval:semantic`。
- `run-tbench.mjs`：`npm run bench:tbench` / `npm run bench:tbench:ts`。
- `eval-office-baseline.mjs`、`generate-office-report.mjs`：Office 基线及报告。
- `bench-jev-context.ts`、`eval-jev-retrieval.ts`：Jev 实验评测。

新增一次性诊断脚本放入 `diagnostics/`；本地日志和截图放入已忽略的 `tmp/`。供 package、CI 或发布流程调用的现有脚本保持原路径。
