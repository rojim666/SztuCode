# Office Agent 能力基线

审计基准：2026-09-05，依据当前仓库代码与测试；文档/接口声明不等于可用功能。

| 能力 | 代码证据 | 接入状态 | 已有测试 | 限制 |
|---|---|---|---|---|
| Office 文档解析 | `packages/runtime-ts/src/document-parser/`；`document-parser.test.ts` 覆盖 PDF、DOCX、XLSX | 已接入 TS runtime 的 `parse_document` 工具 | `npm test -- ...document-parser...` | PPTX 测试明确断言 unsupported；未见 DOC/XLS/ODS 运行实现 |
| Office 文档生成 | 全仓未发现 runtime 的 DOCX/PPTX 生成器或 RPC 方法 | 未实现 | 无生成端到端测试 | 只能把生成列为评测未实现，不能伪造通过 |
| Excel/CSV 分析 | XLSX 解析器可读表格；`read_file` 支持文本 | 部分可用（解析，不含分析编排/图表输出） | XLSX parser 单测 | CSV 没有专用解析/统计/图表产物协议 |
| 多资料检索 | `workspace-indexer`、`lexical-index`、`hybrid-search`、`semantic-search` 测试；文档解析器未接入索引证据 | 部分可用 | 对索引/搜索有单测 | 尚未证明 Office 二进制内容进入索引；需以实际 fixture 验证 |
| 浏览器 | `packages/runtime-ts/src/browser-mcp*` 与 `browser-mcp.test.ts`；桌面有 Browser inspector | 有工具提供者（MCP 可选） | browser MCP 单测 | 依赖 MCP provider/配置；离线评测默认不启用 |
| 电脑控制 | 仅发现桌面 UI/桥接代码与 computer-use skill；未发现 runtime 内置 Windows 控制 provider | 未确认/未实现 | 未发现可证明 provider 的 runtime 集成测试 | 不能把 UI 存在视为可执行控制能力 |
| Checkpoint/续跑 | `agent-loop.ts` `onCheckpoint`；`durable-checkpoint.test.ts`；session/run JSONL | 已接入持久化 checkpoint | durable checkpoint 单测 | 测试证明写入与单调 ID；未证明跨进程自动 resume 或幂等恢复 |
| Skills 安装/分发 | Python `skills/loader.py` 有 install/list/set-enabled；TS 有 skill tests 与 bundled skills | Python 可安装；TS 有加载/运行资产 | `test_skill_loader.py`、`skill-install/skill-assets/skill-lazy` 等 | 两条链行为不完全同步；分发包/签名/依赖锁定未形成发布验收 |
| Agent 执行路径 | 默认 Python daemon（`AGENT.md`）；TS daemon `packages/runtime-ts` 端口 7438；桌面连 TS | 双运行时并存，默认产品路径为 Python | Python/TS 各自 runner、session、provider 测试 | 新办公行为按约定优先 TS，但生产默认仍 Python；跨链结果不可直接等同 |
| 协议/桌面连接 | `packages/protocol` JSON-RPC 2.0 NDJSON；desktop service 连接 runtime | 已接入 | protocol/server/client/desktop-contract 测试 | 办公产物与授权交付尚无稳定协议类型 |
| CI | `.github/workflows/` 与 package scripts（typecheck/test/build） | 基础 CI 可运行 | 由 workflow 执行现有检查 | 未见办公 fixture job、真实模型隔离 job 或产物验收 job |
