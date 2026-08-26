# 开发环境

[返回文档中心](../README.md)

## TypeScript 主链开发

```bash
git clone https://github.com/rojim666/SztuCode.git
cd SztuCode
npm install
```

常用命令：

```bash
npm run typecheck
npm test
npm run build
npm run test:e2e:ts
npm run test:migration
```

`typecheck` 会按依赖顺序检查 `ai`、`session`、`session-fs`、`telemetry`、`agent-core`、`protocol`、`server`、`client`、`runtime-ts`、CLI、评测和 desktop 类型。`npm test` 运行各 package 的 unit test；`test:e2e:ts` 和 `test:migration` 使用真实 TS daemon，后者额外验证旧客户端兼容、重启、fork、compaction、subagent、MCP 和桌面契约。

启动 TypeScript daemon 进行手动调试：

```bash
npm run daemon:ts
```

另一个终端中：

```bash
npm run cli:ts -- ping
npm run cli:ts -- run --goal "inspect the repository"
npm run cli:ts -- chat
```

默认连接 `127.0.0.1:7438`。新的 `@sztucode/client` 先执行 `connect()`/hello，再调用 typed RPC；断线时抛出明确的 disconnect 错误，`reconnect()` 后重新订阅并 attach。客户端只能依赖 `@sztucode/protocol` 和 daemon RPC，不能直接导入工具、Provider 或本地模型凭据。兼容性调试仍可用不发送 hello 的旧 JSON-RPC 客户端。

## Package ownership and dependency direction

修改应遵循从契约到组合入口的方向：

```text
client / cli / desktop -> protocol
server -> injected SessionRuntime（通用 transport 类型）
session-fs -> session -> ai
agent-core -> ai
runtime-ts -> server, protocol, session-fs, agent-core, telemetry
```

- `protocol` 只放可复用的 wire 类型、校验和事件契约；新增公共接口必须同步类型和测试。
- `server` 维护 transport、hello、connection state、router、LiveSessionManager、attach/detach、subscription 和 graceful shutdown；它不创建 `AgentLoop`。
- `client` 维护 TCP/NDJSON SDK、request id、idempotency key、timeout、重连和事件顺序，不绕过 daemon。
- `session`/`session-fs` 维护 SessionRuntime 接口、snapshot、branch/fork 和持久化；`runtime-ts` 的 `ServerService` 创建/打开 `AgentSession`。
- `runtime-ts` 是装配层，注入 Workspace、Permission、MCP、Skills、Git、Provider、Telemetry 和 extensions；`RunManager` 仅为旧调用方保留。

Agent 负责模型回合、工具和权限；Session 负责上下文、状态、快照和持久化；Server 负责连接与路由。子 Agent 必须拥有独立 SessionRuntime，并通过 parent session/run 关系回传事件。

## 桌面端开发

前端位于 `desktop/`，技术栈为 Vue 3、TypeScript、Vite 和 Tauri 2。

```bash
cd desktop
npm install
npm run build
npm run tauri dev
```

Rust 桥接层检查：

```bash
cd desktop/src-tauri
cargo check
```

桌面端依赖 TypeScript daemon，Tauri 启动器会运行 `packages/runtime-ts/dist/main.js`。前端开发服务器端口由 `desktop/vite.config.ts` 决定，Tauri 开发入口由 `desktop/src-tauri/tauri.conf.json` 配置。

### macOS

- 先安装 Xcode Command Line Tools：`xcode-select --install`
- 开发流程与上方相同（bash）；不要依赖 Windows 专用路径或 PowerShell 示例
- 本机打包：`cd desktop && npm run tauri build`
- 视觉测试：`npx playwright install chromium && npm run test:visual`
- 详细命令与产物路径见 [Desktop README](../../desktop/README.md)

## 模块修改清单

### 协议层

- 修改 `packages/protocol/src` 的共享类型；
- 更新 TypeScript daemon handler；
- 检查 CLI、TUI 与桌面 Client SDK；
- 重新生成 Wire Protocol；
- 添加 round-trip 和集成测试。

### 工具层

- 实现 TypeScript 参数类型和运行时校验；
- 声明静态权限或实现动态权限分类；
- 注册工具；
- 覆盖参数错误、运行失败、超时和权限拒绝；
- 验证工具不能越过工作区边界。

### UI 层

- 保持事件按 `session_id` / `run_id` 关联；
- 重连和历史 hydrate 不得产生重复状态；
- 覆盖 loading、空、失败、禁用和审批状态；
- 桌面端变更运行 TypeScript 构建与必要的视觉验证。

### 配置层

- 更新 TypeScript Settings 类型、JSON 持久化和环境变量覆盖；
- 更新 `.env.example` 和配置参考；
- 为无效类型、边界值和优先级添加测试；
- 明确是否包含凭据及其持久化方式。

### Extension 开发

daemon 从 `SZTU_EXTENSIONS` 加载 global extension，从
`SZTU_WORKSPACE_EXTENSIONS` 加载 workspace extension；后者只对对应的
workspace root 生效，两个 registry 不共享注册项。扩展通过 `activate(api)`
注册工具、Slash command、Prompt template、Resource、tool prompt
contribution 和 session event listener，并可使用 session/agent/turn/tool/
context/compact 生命周期 hook。扩展不得访问 Socket；加载、激活、工具注册
或 hook 错误必须出现在 diagnostics，hook 错误也不得结束 daemon 主循环。

新增扩展公共类型和行为时，同时添加 loader/registry、卸载、工具注册和异常
隔离测试。Extension API、Subagent/workflow DAG 和 `AgentSession` 组合入口
仍是 0.x 实验性 API，文档和协议字段可能变化。

## 数据与调试

开发时常用位置：

```text
~/.sztu/traces/runtime-ts-events.jsonl
${SZTU_DATA_DIR:-~/.sztu}/sessions/<session_id>/
```

兼容路径包含 `meta.json`、`thread.jsonl`、context、notes 和 run 事件；新的
`session-fs` backend 使用带 header 的 append-only JSONL 和 branch/fork
元数据。两者都可能包含提示词、模型响应、工具输出和 API 配置，提交 Issue
或测试夹具前必须脱敏。

## 完成标准

一项变更在满足以下条件后才适合提交：

- 行为与 Issue/PR 目标一致；
- 相关客户端和协议消费者已同步；
- 适当测试通过；
- 失败和权限路径经过验证；
- 用户文档与配置示例已更新；
- `git diff` 不包含无关生成物或本机数据。
