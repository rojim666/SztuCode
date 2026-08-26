# 架构说明

[返回文档中心](../README.md)

## 系统边界

SztuCode 是本地优先的 daemon/client Agent 系统。TypeScript 与 Python 各自提供 daemon 和 CLI 入口；桌面端连接 TypeScript runtime。客户端通过 TCP 上的 NDJSON/JSON-RPC 2.0 连接，Agent 执行状态以所选 daemon 为准。

```text
Tauri Desktop / Node CLI / Eval
              │
              ▼
     @sztucode/client + @sztucode/protocol
              │ TCP / NDJSON / JSON-RPC
              ▼
     @sztucode/server (transport/router/session attach)
              │ injected SessionRuntime
              ▼
     runtime-ts RuntimeServer -> ServerService -> AgentSession
              │
     Workspace / Permission / MCP / Skills / Git / Telemetry
              │
     AgentLoop / Provider / Tools / Session persistence
```

Python runtime 是独立的平行实现，默认监听 `127.0.0.1:7437`；它不依赖 TypeScript package，但对客户端暴露相同的主要 JSON-RPC/NDJSON 语义。

### Agent、Session、Server 边界

- **Agent**：`AgentLoop`、Provider adapter 和 Tool Registry 执行模型回合、工具调用和权限请求，发布 run/step/tool 事件；不拥有 Socket，也不决定客户端连接生命周期。
- **Session**：`AgentSession` 实现一个 `SessionRuntime`，拥有上下文、生命周期、快照、分支、运行关联和持久化。Subagent/workflow child 使用独立 runtime，并带 `parent_session_id`/`parent_run_id` 关联。
- **Server**：`@sztucode/server` 只负责 Transport、连接状态、hello、RPC router、事件订阅、Session attach/detach 和优雅关闭。`RuntimeServer` 只装配依赖，`ServerService` 创建/打开 `AgentSession`；transport/server 不直接创建 `AgentLoop`。`RunManager` 只是旧调用方使用的兼容层。

## 进程与客户端

### TypeScript daemon

daemon 入口位于 `packages/runtime-ts/src/main.ts`，负责组合而不是承载传输业务：

- 加载配置、Provider、Telemetry、EventBus 和 coding-agent services；
- 将 Workspace、Permission、MCP、Skills、Git、Session backend 和扩展 registry 注入 `ServerService`；
- 用 `@sztucode/server` 启动 TCP/NDJSON transport，并注册协议路由；
- 在 shutdown 时先停止接收新请求，再关闭 transport、释放连接并等待活动 Session/后台任务。

### `sztucode` / Node CLI

npm 发布入口会启动 TypeScript daemon，并让 Node CLI 创建绑定到目标项目的会话。仓库内可使用 `npm run cli:ts -- chat`。

显式 TypeScript 命令为 `sztu-ts`，默认端口为 `7438`。

### `sztu-py` / Python CLI

Python 包入口连接 `py-runtime/src/sztu_code` 中的 Python daemon，默认端口为 `7437`。仓库内可使用 `npm run cli:py -- ...` 和 `npm run daemon:py`。

### Tauri Desktop

`desktop/` 使用 Tauri 2、Vue 3 和 TypeScript。Rust 层负责原生窗口、目录选择和受控 TCP 桥；前端负责工作区、会话、执行时间线、权限、文件预览和 Diff 审阅。

两套 runtime 使用不同的命令名和默认端口，因此可以并行安装和运行。桌面产品路径仍使用 TypeScript runtime。

## 请求与事件链路

1. `@sztucode/client` 建立 TCP，并发送 `{"type":"hello","version":1,...}`；daemon 回复 welcome、connection id 和 capabilities。
2. 旧客户端在 compatibility mode 下可以省略 hello，直接发送第一个 JSON-RPC frame；新客户端仍必须先 hello。版本不兼容返回 `hello_error` 并关闭连接。
3. 客户端调用 `event.subscribe` 选择主题，再发送带 request id、可选 idempotency key 的 JSON-RPC 命令，例如 `session.send_message`。
4. `@sztucode/server` 解析 NDJSON、校验 envelope、路由到 `ServerService`，只通过注入的 `SessionRuntime` 执行操作。
5. `AgentSession` 绑定 AgentLoop、Workspace、Permission、MCP、Skills、Git、Provider 和 Telemetry；AgentLoop 发布 run、step、tool、permission、LLM 和 change 事件。
6. server 将匹配订阅的事件包装为 `{ kind: "event", event }` NDJSON frame；响应与事件都按 `session_id`/`run_id` 关联。
7. 客户端断开时仅清理连接和 attachment；运行中的 Session 继续执行。重连后先 list/get，再 attach 并从 snapshot/history 去重 hydrate。
8. `core.shutdown` 或进程停止触发 graceful shutdown：拒绝新请求，通知/取消可取消工作，等待持久化和连接关闭；已落盘 Session 可在下一次 daemon 启动后重新打开。

命令和事件的字段定义见自动生成的 [Wire Protocol](wire-protocol.md)。

## Agent 运行时

### 上下文

Runner 组合会话消息与当前目标。上下文预算由 `packages/runtime-ts/src/context.ts` 计算；工具结果超过阈值时，`packages/runtime-ts/src/offload.ts` 将完整内容保存到当前 run 的 `refs/`，上下文保留摘要并可通过只读 `read_ref` 分页回读。写盘失败时才回退到有标记的截断；达到整体上下文阈值时再执行压缩。

默认卸载阈值为 2,000 字符或 50 行，`bash`、`grep_search` 和 `glob_search` 始终卸载。可通过 `SZTU_OFFLOAD_ENABLED`、`SZTU_OFFLOAD_MIN_CHARS` 和 `SZTU_OFFLOAD_MIN_LINES` 调整。

`task_create`、`task_update`、`task_list` 和 `task_get` 由 TypeScript `TaskManager` 提供。任务以 JSON 保存在当前 run 目录中，进程重启后仍可恢复；主 Agent 和声明这些工具的子 Agent 使用相同契约。

多 Agent workflow 使用与普通 Agent 相同的 `run.cancel` 和 `run.get` 控制面。取消信号会传播到所有正在执行的子任务，并将尚未调度的任务标记为 `cancelled`；daemon 关闭时也会取消活动 workflow。

Prompt Harness 从 `prompts/content/*/index.json` 加载原子提示，并按实际注册工具、权限模式、记忆能力与任务风险动态组合。标记为 `reference-only` 的提示不会进入模型上下文，避免向 Agent 声明运行时并不存在的 IDE、Hook 或沙箱能力。

模型生成的工具参数不会因 TypeScript 类型声明而被假定可信。AgentLoop 在权限审批和调用前按工具 JSON Schema 做运行时校验；缺失字段、错误类型、非法枚举和越界数值会作为 `schema_error` 写入 trace，并反馈给模型修正。

### 工具

内置工具通过 Tool Registry 注册。工具参数在调用边界校验，运行时根据工具类型和具体输入计算权限：

- `read_only`：读取、列表和搜索；
- `workspace_write`：受工作区约束的写入和编辑；
- `danger_full_access`：Shell 等高风险能力。

工具返回统一的成功、输出和错误分类，调用链通过事件对客户端可见。

### 权限

Permission Manager 结合当前模式、持久化策略、工具权限和用户响应决定是否执行。审批状态通过 `permission.*` 事件广播，响应使用 `permission.respond`。

### Skills、Subagents 与 MCP

- Skills 从项目、用户和内置目录发现，通过描述匹配或显式调用注入工作流。
- Subagent 使用独立 run ID 和受限角色执行子任务，结果回填父运行。
- MCP 将外部 stdio/TCP Server 的能力适配为统一工具。

### Planner、Coder、Tester、Reviewer 工作流

`run_workflow` 先让只读 Planner 输出含依赖、负责人、完成条件和文件范围的结构化 DAG，再由 daemon 调度器按依赖执行 Coder、Tester 和 Reviewer：

- Coder 只获得读写文件工具，不获得 Shell；范围内编辑走普通写权限，越过 Planner 分配范围时升级为 `danger_full_access`。`normal`/`accept_edits` 会请求用户审批，`auto` 直接放行，批准后的范围升级写入交接证据；
- Tester 只读工作区并独立运行命令，必须提交命令、关键原始输出和结论；
- Reviewer 只读 Diff、测试和安全证据，必须给出 `accept` 或 `return`；
- DAG 调度器统一限制并发、嵌套深度、Token、墙钟和重试预算，并把失败、取消和超时传播到依赖任务与父工作流；
- `workflow.*` 事件与其他 EventBus 事件共用 `events.jsonl`、IPC 和 daemon Trace，TUI 与桌面时间线均可回放任务和交接证据。

范围升级仍受工作区根目录约束；`auto` 不允许写出当前 workspace。

## 数据持久化

主要本地数据：

| 路径 | 所有者 | 内容 |
| --- | --- | --- |
| `~/.sztu/sessions/` | Session Store | 会话、消息、notes、runs 和事件 |
| `~/.sztu/workspaces.json` | Workspace Manager | 最近和归档工作区 |
| `~/.sztu/runtime-settings.json` | Settings Store | Provider、模型、端点、凭据和权限模式 |
| `~/.sztu/model-profiles.json` | Model Profile Store | 模型列表与当前 profile ID |
| `~/.sztu/traces/runtime-ts-events.jsonl` | EventBus | runtime 事件 trace |

会话与 trace 可能包含源码、提示词和模型响应，应按敏感数据处理。

## 关键不变量

- 协议边界使用类型化模型，不让客户端猜测字段。
- daemon 是任务状态的唯一事实来源；客户端状态必须可从历史和事件恢复。
- 工作区工具不得越过已解析的工作区根目录。
- 高风险动作必须经过权限策略，模式切换不能绕过底层分类。
- 角色分配范围不是第二套静态沙箱；越界必须进入权限升级并留下 Trace 证据。
- 事件关联键和顺序必须足够支持断线重连、去重和回放。
- 生成的 Wire Protocol 必须与代码保持同步。

## 扩展入口

| 目标 | 主要位置 |
| --- | --- |
| 新命令/事件 | `packages/protocol/`、`packages/runtime-ts/src/server.ts`、客户端 SDK |
| 新工具 | `packages/runtime-ts/src/tools.ts` |
| 新 Provider | `packages/runtime-ts/src/providers/` |
| 新权限规则 | `packages/runtime-ts/src/permissions.ts` |
| 新 Skill | `.sztu/skills/`、`~/.sztu/skills/` 或内置 Skills |
| 新 Agent 角色 | `packages/runtime-ts/src/subagent.ts` |
| 新 MCP 接入 | `packages/runtime-ts/src/mcp.ts` 与 JSON 配置 |

实现细节和提交标准见 [开发环境](../development/development.md) 与 [贡献指南](../CONTRIBUTING.md)。
