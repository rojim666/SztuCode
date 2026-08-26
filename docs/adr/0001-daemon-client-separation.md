# ADR-0001：daemon 与客户端采用分离架构

[返回 ADR 索引](README.md)

- 状态：Accepted
- 日期：2026-08-04
- 决策者：SztuCode 维护者
- 关联：[README 架构说明](../../README.md#系统架构)、[Wire Protocol](../reference/wire-protocol.md)

## 背景

AI Coding Agent 的一次任务可能持续数分钟，期间会产生模型流式输出、工具调用、权限审批、会话持久化和执行 Trace。若 Agent Loop 与界面运行在同一进程，客户端关闭或界面故障会直接中断任务，也难以让 TUI、桌面端和 CLI 共享一致的运行状态。

项目需要同时满足：

- 长任务不依赖单个客户端窗口的生命周期；
- 多种客户端复用同一套 Agent、权限和会话语义；
- IPC 消息能够验证、记录和回放；
- 客户端可以在任务运行期间继续发送审批、取消和查询命令；
- 默认只向本机提供服务，不把工作区控制接口暴露到网络。

## 决策

SztuCode 采用持久 daemon 与多个客户端分离的架构：

- `@sztucode/protocol` 定义 JSON-RPC/NDJSON、事件、Session 和 Workflow 的共享契约；`@sztucode/client` 是只调用 daemon RPC 的 typed SDK；desktop、CLI 和评测 runner 都通过它或兼容 transport 接入。
- `@sztucode/server` 提供 TCP/NDJSON transport、hello handshake、connection state、RPC router、LiveSessionManager、attach/detach、订阅和 graceful shutdown。它依赖注入的 `SessionRuntime`/`PiSessionRuntime`，不创建 `AgentLoop`。
- `packages/runtime-ts` 的 `RuntimeServer` 只装配依赖；`ServerService` 创建/打开 `AgentSession`，再注入 Workspace、Permission、MCP、Skills、Git、Provider、Telemetry 和 Session backend。`RunManager` 作为旧 desktop/CLI/test 调用方的兼容层暂时保留。
- Agent 负责模型回合、工具和权限；Session 负责上下文、生命周期、snapshot、branch/fork 和持久化；Server 负责连接、路由、事件投递和 attach 状态。子 Agent 使用独立 SessionRuntime，并通过 parent session/run 关联。
- 客户端与 daemon 继续通过 TCP 上的 NDJSON 传输 JSON-RPC 2.0；新客户端首帧为 `hello`，包含协议版本和能力，随后可订阅事件。`runtime-ts` 开启 compatibility mode，旧客户端可以跳过 hello 直接发送首个 JSON-RPC frame，既有 method、envelope、事件名和错误码保持不变。
- 第一版只扩展现有 TCP + NDJSON 传输，不同时引入 CBOR；二进制协议若未来需要，必须通过新的协商能力和兼容测试单独引入。
- 默认监听 `127.0.0.1:7438`，不以远程多用户服务为当前目标；Python daemon 是默认端口 `7437` 的平行实现，不是 TypeScript package 的依赖。

客户端可以提供不同交互体验，但不得绕过 daemon 的权限、工作区和会话边界。新增用户可见能力如需改变 IPC，必须先更新类型化协议，再更新各客户端。

## 备选方案

### 单进程、单界面 Agent

实现简单，早期调试成本低，但界面生命周期会控制任务生命周期，不利于恢复、并发控制和多客户端复用。随着权限审批和会话持久化加入，该方案会产生重复实现和状态不一致。

### 将核心能力实现为远程 HTTP 云服务

便于集中部署和多人访问，但会扩大认证、租户隔离、代码上传、合规和运维范围。项目当前强调本地优先，也不具备承诺公共服务安全性的资源条件。

### 客户端直接调用模型，daemon 只执行工具

可以减少 daemon 对模型协议的关注，但会把对话历史、工具调用配对、上下文压缩和 Trace 分散到不同客户端，无法保证一致的 Agent 语义。

## 后果

### 正面

- 客户端退出后，任务和会话可以继续存在并在重连后恢复；
- 所有客户端复用统一的权限、工具、上下文和模型接入；
- 客户端 SDK 提供 request timeout、request id、idempotency key、明确的断连错误和 reconnect；
- Session snapshot 与 append-only session entries 让 list/get/attach 可以从磁盘恢复，连接断开不会取消活动 Session；
- IPC、EventBus 和 LLM 三层数据可以独立观察和回放；
- 客户端可以专注交互，而核心行为可以通过无界面测试验证。

### 负面与成本

- 必须维护进程启动、端口占用、断连、重连和版本兼容；
- 新能力通常需要同时修改协议、daemon 和至少一个客户端；
- 异步并发和事件顺序比单进程调用更复杂；
- 本地 TCP 接口本身成为需要持续审查的安全边界。

### 风险与缓解

- 默认只监听 loopback 地址，避免直接暴露到局域网或公网；
- 协议边界验证 envelope 和关键参数，未知或非法请求返回明确错误；
- 工作区、权限和工具约束只在 daemon 中作最终判定；
- 通过集成测试覆盖真实 daemon 启动、IPC 往返、审批和会话流程；
- 协议模型变更后生成并检查参考文档，减少客户端契约漂移。
- 兼容路径保留 legacy `SessionStore` 目录；组合路径使用 `@sztucode/session-fs` 的 typed JSONL、branch/fork 元数据和原子写入，并提供迁移适配器。
- 扩展只由 daemon 按 global/workspace scope 加载（`SZTU_EXTENSIONS`、`SZTU_WORKSPACE_EXTENSIONS`）；加载、注册和 hook 失败写 diagnostics，单个扩展错误不能结束主循环。

## 验证

- daemon 运行期间，客户端能够订阅事件并发送其他命令；
- 客户端断开和重连不会破坏已持久化会话；
- CLI、TUI 和桌面端对同一命令与事件使用一致协议；
- 集成测试使用真实 daemon 进程验证 IPC 边界；
- 协议生成脚本检查参考文档与模型保持同步。
- `npm run test:e2e:ts` 和 `npm run test:migration` 使用真实 daemon 验证 hello/compatibility、事件顺序、最终 snapshot、断线重连、重启和 desktop contract。

## 后续工作

- 定义正式的协议兼容性和版本协商策略；当前 hello version 仅为最小握手，compatibility mode 仍是迁移桥接；
- 强化本地 IPC 客户端身份和未授权访问防护；
- 为 daemon 与桌面端建立稳定的联合发布流程；
- 将 `AgentSession` composition、Subagent/workflow DAG、Extension API 和部分 typed server/client API 从实验性状态推进到稳定契约。
