# TypeScript Runtime 与 pi packages 分层对比

本文是 SztuCode TypeScript daemon 的架构设计记录。对比对象为：

- 当前实现：`packages/protocol`、`packages/runtime-ts`、`packages/cli` 以及桌面端调用边界；
- 参考实现：`F:/Learning/codinganget/pi/packages` 中的 `ai`、`agent`、`coding-agent`、`protocol`、`server`、`client` 和 `session-backends`。

本文只参考 pi 的接口和模块边界，不复制其源码，也不改变 `py-runtime`。

## 1. 当前问题

### 1.1 runtime-ts 的模块依赖关系

当前 agent、session、tool、provider 和产品编排仍集中在 `runtime-ts` 包内；但工作区已有一项进行中的边界抽取：`packages/server` 提供 `TcpNdjsonTransport`、`RpcRouter`、live-session helper 和通用 server 类型，`runtime-ts` 通过 `@sztucode/server` 使用它。因而现状是“传输/路由开始独立，应用服务仍扁平”，而不是完全没有 server package。

```text
packages/protocol      packages/server
       ^                    ^
       |                    |
       └── runtime-ts/src/server.ts (业务层同时使用两者)
   |                                                       |
   +─ EventBus                                              |
   +─ RunManager ── AgentLoop ── Context                   |
   |       |             |       └─ provider / tools        |
   |       |             +─ permissions / offload            |
   |       |             +─ EventBus                         |
   |       +─ SessionStore                                   |
   |       +─ tools / Workspace / prompts / memory            |
   +─ WorkspaceManager / GitManager / Settings               |
   +─ MCP / plugins / skills / subagents / trace              |
```

这是职责和导入关系的概念图，不是新的公共 API。具体观察如下：

- `runtime-ts/src/server.ts` 仍直接导入几乎所有基础设施（事件、运行、会话、工作区、Git、设置、技能、插件、Provider、上下文、问题、MCP、子 Agent、市场和 Trace），并负责业务方法路由、广播和事件持久化；TCP socket、NDJSON 分帧、限帧和基础 router 已抽到 `packages/server`。兼容模式仍允许现有 daemon 的首帧直接是 JSON-RPC，而新 server package 也支持可选 hello 握手。
- `packages/server` 目前自带 `RpcRequest`、`RpcResponse`、`EventEnvelope` 等类型，尚未依赖 `packages/protocol`；这形成两套协议类型。迁移时必须先建立显式 adapter 或统一到 `packages/protocol`，不能仅通过改 package dependency 强行替换，否则会改变 `id`、错误码、事件 envelope 或握手兼容性。
- `run-manager.ts` 保存所有 run 状态和 session-to-run 锁，创建 `AgentLoop`，装配 workspace/plan/memory/question 工具，构建 system prompt，管理权限，并在结束或压缩时回写 `SessionStore`。
- `agent-loop.ts` 既是模型调用循环，又负责上下文清理/压缩、工具 schema 校验、权限检查、重试、拒绝/卡死干预、offload、usage 统计、结论生成和 RuntimeEvent 发布。
- `session-store.ts` 既是 session 元数据仓库，又是消息 JSONL、模型上下文、run 事件、摘要、notes、fork、归档/置顶等文件格式的实现。它通过类型导入 `context.ts`，因此持久化模型和 agent context 已经耦合。
- `tools.ts` 同时定义 `Tool`/`ToolRegistry` 公共形状和绝大多数工作区工具工厂；它还直接依赖任务管理、bash 权限分类和 workspace/event 类型。`ToolRegistry` 没有独立的工具契约包。
- Provider 文件通过类型导入 `agent-loop.ts` 的 `ChatMessage`、`ModelProvider`、`ModelResponse`，Trace 也通过类型导入 agent/tool 类型；这使“模型抽象”和“循环实现”无法独立演进。
- `subagent.ts` 直接创建 `AgentLoop`、权限、工具、workspace、prompt 和 workflow；子 Agent 因此绕过了一个清晰的 agent runtime facade。

现有实现的优点是复用充分、行为集中，且已有较完整的测试；问题是边界不稳定：任何新传输、持久化后端、Agent 事件或工具 API 都可能触及 `server.ts` 和 `agent-loop.ts`，导致大范围回归。

### 1.2 五个核心职责

| 当前类型 | 实际职责 | 主要问题 |
| --- | --- | --- |
| `RuntimeServer` | 业务 JSON-RPC dispatch、客户端订阅、事件广播、run event 持久化、所有服务对象组装；通过 `@sztucode/server` 使用 TCP/NDJSON transport | transport 已开始分离，但应用服务、composition root 和旧协议兼容仍混在一个类 |
| `RunManager` | run 生命周期、取消/steer、session 忙状态、权限管理、工具和 prompt 装配、AgentLoop 启动、结果/统计回写 | 既是运行目录又是应用编排器；直接知道 SessionStore 和所有工具工厂 |
| `AgentLoop` | 单次 agent turn 循环、LLM stream、tool call、schema/permission、retry、compaction、offload、usage 和事件 | 核心算法、存储副作用和 UI/RuntimeEvent 语义耦合；Provider 类型反向依赖它 |
| `SessionStore` | session 元数据、thread/context JSONL/JSON、fork、summary、notes、run stats/events、archive/pin | 文件格式、仓库、查询和领域状态没有接口隔离；无法替换 SQLite 或内存后端而不改调用方 |
| `ToolRegistry` | 工具注册/查找、工具 schema、权限级别、调用上下文和内置 workspace/plan/task 工具工厂 | registry、工具契约、Node 文件系统能力和具体产品工具处于同一模块 |

## 2. pi 设计的可借鉴点

### 2.1 agent 与 coding-agent 分层

pi 的 `agent`（包名 `@earendil-works/pi-agent-core`）是通用、可嵌入的 agent runtime：

- `Agent` 持有 transcript、model/tool 状态、steering/follow-up 队列和生命周期订阅；
- `agent-loop` 是较低层的 turn 循环，只依赖 `pi-ai` 的消息/stream 类型和 agent 自身的类型；
- harness 目录提供 context、compaction、session storage interface、tool context、skills 和 telemetry 等可替换能力；
- session 通过 `SessionStorage`、`SessionRepo`、`SessionTree` 等接口访问，不把 JSONL/SQLite 细节写进循环。

pi 的 `coding-agent` 是产品层：组合默认 read/write/edit/bash 工具、system prompt、skills、extensions、session manager、CLI/TUI 和 RPC 入口。它依赖 agent、ai、protocol、client、tui，但通用 agent 不依赖 coding-agent。

可借鉴的边界是“核心运行时只定义协议和接口，coding-agent 再提供默认实现”，而不是照搬 pi 的命名或全部功能。

### 2.2 session backend

pi 的 agent 包只拥有存储接口和内存/JSONL 参考实现；`session-backends/sqlite-node` 单独实现 `SessionRepo`/`SessionStorage`，负责 SQLite schema、迁移、writer lease、分支缓存和搜索。通过 conformance tests，多个后端共享相同的行为验收。

对 SztuCode 的直接启示：先把当前 `SessionStore` 的文件语义提炼为小型接口，再保留 JSONL 适配器；SQLite、内存测试后端以后可以独立增加。迁移期间仍必须保持现有 `~/.sztu/sessions/<id>/meta.json`、`thread.jsonl`、`context.json` 等格式可读写。

### 2.3 server、client、protocol

- pi `protocol` 是 runtime-neutral 的 DTO、schema、编码和 framing；它不导入 Node socket，也不持有 agent 状态。
- pi `server` 只处理 listener、连接状态、握手、请求/响应、live session attach/detach、snapshot 和事件广播；通过 `PiServerService` 注入“list/create/open session”等应用能力。
- pi `client` 只依赖 protocol，使用抽象 byte transport、请求 ID 关联和独立 session lease；Node/Unix transport 通过显式子路径提供。
- `server`/`client` 的快照是权威状态，progress/event 是瞬时提示；这减少了客户端自行推断运行状态的风险。

SztuCode 当前协议是 TCP loopback 上的 JSON-RPC 2.0 + NDJSON，且桌面端、CLI 和测试已经依赖它。因此可借鉴的是注入式 server service、transport-neutral client 和 authoritative state 原则；不能直接把 CBOR/长度前缀或握手协议替换进现有端口。

## 3. 推荐 packages 目录

推荐先在现有仓库中增加逻辑边界，再按需要拆成独立 npm package。第一阶段不要求移动全部文件：用 facade 和 type-only imports 逐步迁移。

```text
packages/
  protocol/                 # 现有 JSON-RPC/NDJSON DTO、事件和 workflow schema
  runtime-contracts/        # 新：agent/session/tool/provider/event 的 Node-neutral TypeScript 接口
  agent-core/               # 新：AgentLoop、turn 状态、compaction、retry、steering
  tool-runtime/             # 新：Tool、ToolRegistry、schema、ToolContext、权限分类接口
  session-core/             # 新：Session、SessionRepo/Storage、消息/分支/统计接口
  session-backend-jsonl/    # 新：兼容当前 ~/.sztu/sessions 文件布局的适配器
  provider-runtime/         # 新：ModelProvider facade 和 anthropic/openai/configurable adapters
  coding-agent/             # 新：workspace/plan/memory/skills/MCP/subagent/prompt 产品组合
  server/                   # 已有：TCP/NDJSON transport、router、live-session helper；继续保持 transport-neutral 扩展边界
  daemon-server/            # 后续：runtime service composition 和旧 JSON-RPC method handlers
  client/                   # 可选：从 cli/src/client.ts 抽出 transport-neutral JSON-RPC client
  runtime-ts/               # 兼容 facade/daemon entry；7438、NDJSON、现有 exports 保持不变
  cli/                      # 现有 CLI，依赖 client 和 protocol，不直接构造 AgentLoop
```

如果维护成本不允许新增这么多 package，最小可行版本是保留 `runtime-ts` package，按上述名称建立 `src/{contracts,agent,tools,session,providers,coding,server}` 子目录；依赖方向和测试边界必须相同。

## 4. 推荐依赖方向

依赖应从稳定契约指向实现，禁止下层反向导入 composition root：

```text
protocol  <── runtime-contracts
                 ↑       ↑       ↑
              agent-core tool-runtime session-core
                 ↑       ↑       ↑
          provider-runtime  session-backend-jsonl/sqlite
                 \       |       /
                  coding-agent
                       ↑
                 daemon-server ── client ── cli/desktop
```

具体规则：

1. `protocol` 不依赖 runtime-ts、Node socket、SessionStore 或桌面端。
2. `runtime-contracts` 只放 type/interface、错误码和跨实现的纯值；不得导入 `server.ts`。
3. `agent-core` 依赖 `runtime-contracts`、`provider-runtime` 的接口和 `tool-runtime` 的接口；不得依赖 SessionStore 具体类、WorkspaceManager 或 JSON-RPC。
4. `tool-runtime` 可以依赖 workspace capability interface 和 protocol 的权限类型，但不得依赖 AgentLoop；工具通过 `ToolContext` 回调事件/权限。
5. `session-core` 只定义会话领域和 repository/storage 接口；backend 依赖它，agent-core 只依赖接口。
6. `provider-runtime` 定义 `ModelProvider`、消息和 usage facade；Anthropic/OpenAI adapter 实现接口，不能从 `agent-loop.ts` 反向取得类型。
7. `coding-agent` 是唯一组合默认工具、prompt、memory、skills、MCP、subagents 和 workspace 的产品层。
8. `daemon-server` 依赖 protocol、coding-agent 的 service facade 和 session backend；传输适配器只负责字节/行读取，不能直接操作 AgentLoop。
9. `client` 只依赖 protocol；`cli`/desktop 依赖 client，不依赖 daemon 内部类。
10. 允许 type-only 依赖，但不允许通过 barrel export 形成运行时回环；每个 package 的 `index.ts` 只导出稳定公共接口。

### 4.1 当前循环依赖和风险

- `context.ts -> type agent-loop.ts` 与 `agent-loop.ts -> context.ts` 是当前已存在的类型环。迁移时将 `ChatMessage`、`ModelInvocation`、`ContentBlock` 移到 `runtime-contracts`，用 `import type` 保留零运行时环。
- `agent-loop.ts -> tools.ts -> task-manager/bash-permission/workspace/event-bus` 使核心循环绑定 Node 工作区。应把 `Tool`/`ToolRegistry`/`ToolContext` 提出，具体 workspace 工具留在 coding-agent/tool-runtime adapter。
- Provider `-> type agent-loop.ts`、Trace `-> type agent-loop.ts/tools.ts` 会把模型和观测层锁定在循环实现。应将 provider/trace DTO 放进 contracts/provider-runtime，Trace 通过 event sink 注入。
- `run-manager.ts -> AgentLoop + SessionStore + prompt + memory + tools`，而 `memory.ts -> SessionStore`，形成应用编排与持久化的回环风险。RunManager 应拆成 `RunCoordinator`（生命周期）和 `AgentFactory`（组合），session 只经 repository interface 使用。
- `server.ts -> RunManager/SessionStore/SubagentManager` 并由这些对象向上发布 EventBus，扩展 RPC 时容易把 server 变成新的全局依赖。采用 `RuntimeService` 注入和 handler 表，server 不被下层导入。
- 迁移中若同时更换 JSONL schema、事件字段、协议 framing 或 session busy 语义，会出现桌面端无法连接、重复消息、run 状态丢失和旧会话不可读。必须先做 facade，再做后端替换；禁止把 pi 的 CBOR/握手协议直接套到 7438。
- `SessionStore` 当前用文件追加写且 `get()` 读取完整 `meta.json`；并发写、进程重启、部分文件和跨平台路径是后端替换时的风险。每个 backend 需要锁/原子提交策略及 conformance tests。

## 5. 分阶段迁移顺序与验收标准

迁移按“契约先行、行为不变、一次只移动一个边界”执行。每阶段都保留旧入口，避免桌面端和 py-runtime 受到影响。

### 阶段 0：基线和依赖守护

**工作**：记录当前 RPC 方法/事件、session 文件样例、7438 NDJSON 行为和测试基线；增加依赖图检查规则（至少禁止新代码从 contracts/agent-core 导入 server）。

**验收**：

- `npx tsc -p packages/protocol/tsconfig.json --noEmit` 通过；
- `npx tsc -p packages/runtime-ts/tsconfig.json --noEmit` 通过；
- `npx tsx --test packages/runtime-ts/tests/runtime.test.ts packages/runtime-ts/tests/server.test.ts` 通过；
- 桌面 contract 测试仍能发现并覆盖全部现有 handler；
- 7438、JSON-RPC 2.0、NDJSON、7437 py-runtime 均未改动。

### 阶段 1：提取 runtime-contracts 和 provider facade

**工作**：将 `ChatMessage`、tool call/result、usage、`ModelProvider`、`ModelInvocation`、Agent progress/event sink 等类型移出 `agent-loop.ts`；Provider adapter 改为依赖 facade。保留旧路径 re-export。

**验收**：

- agent-loop、context、provider、trace 不再形成运行时循环；依赖检查确认只存在 type-only 兼容导出；
- OpenAI/Anthropic/configurable provider 测试和 trace 测试通过；
- 旧的 `runtime-ts/src/agent-loop.ts` 导入路径和 `ModelProvider` 类型仍可编译；
- 无协议字段、事件名称或 provider 配置行为变化。

### 阶段 2：提取 tool-runtime 与 Agent Core

**工作**：把 `Tool`、`ToolRegistry`、schema 校验、ToolContext、权限分类接口提取；把 AgentLoop 的 turn/compaction/retry/steering 保留在 agent-core；workspace/plan/task/memory 工具改为 coding-agent 工厂。

**验收**：

- agent-core 可用内存 fake provider、fake tool 和 fake event sink 做无 Node 文件系统测试；
- 现有工具 schema 错误、权限拒绝、重试、offload、卡死干预、max-step conclusion 测试全部通过；
- `ToolRegistry` 的公共类型有显式 TypeScript 声明和测试；
- `RunManager` 仍能产生相同 run/step/tool/permission 事件。

### 阶段 3：提取 session-core 和 JSONL backend

**工作**：定义 `SessionRepo`/`SessionStorage`、metadata、message、history、fork、summary、stats 接口；将现有 `SessionStore` 改成 `session-backend-jsonl` 实现，旧类作为 facade。为内存后端和 JSONL 后端共享 conformance suite。

**验收**：

- 新建、读取、列表、归档、置顶、关闭、fork、history、context、summary、notes、run stats 行为与现有测试一致；
- 旧目录中的 meta/thread/context/runs 文件可读，写入仍为兼容 JSON/JSONL；
- daemon 重启后 session 可恢复，部分/空目录不会破坏 `session.list`；
- session busy、steer、cancel 和 `client_message_id` 去重语义不变；
- 不引入 SQLite 作为默认后端，不改 py-runtime。

### 阶段 4：coding-agent/application facade

**工作**：建立 `CodingAgentService`/`RunCoordinator`，集中组合 workspace、prompt、skills、MCP、memory、subagents、permissions 和 session repository；`RunManager` 逐步变为兼容 facade。将 subagent/workflow 通过 service 接口创建 agent，而非直接 new AgentLoop。

**验收**：

- one-shot、chat、subagent、workflow、question、permission、change tracking 和 model profile 流程通过现有集成测试；
- workflow DAG、范围升级和交接证据事件不变；
- server 不再直接导入具体工具工厂或 prompt/memory 实现；
- 关闭 daemon 能取消 run/workflow 并等待资源释放。

### 阶段 5：daemon-server/client 分离

**工作**：在已有 `packages/server` 的 transport/router/live-session 抽取基础上，继续把 `RuntimeServer` 的业务方法、事件持久化和 service composition 提取为 daemon-server facade；用注入的 service handler 处理业务。将 `packages/cli/src/client.ts` 提取为可复用 client facade，桌面端继续使用同一 JSON-RPC wire contract。现有兼容模式（无 hello 的 JSON-RPC 首帧）必须保留，hello 握手只能作为显式新模式。

**验收**：

- 真实 TCP 集成测试覆盖 parse error、invalid request、unknown method、超大 frame、并发请求、事件订阅、断开和关闭；
- 7438 默认端口、loopback 默认 host、NDJSON 每行一个 JSON-RPC envelope 完全保持；
- 桌面端 contract 测试、CLI chat、run replay 和 session reconnect 通过；
- client 不导入 daemon 内部模块；
- `packages/server` 的独立 typecheck/test 通过，且 `@sztucode/server` 不反向依赖 `runtime-ts`；
- pi 的 CBOR/length-prefix 仅作为未来可选 transport，不进入本阶段。

### 阶段 6：可选后端和发布收敛

**工作**：在 session-core conformance 通过后，评估 SQLite backend、搜索和 writer lease；完善 package exports、独立 typecheck/test 和构建产物。最后再考虑是否把子目录拆成独立 npm packages。

**验收**：

- JSONL 与可选 SQLite 后端通过同一 conformance suite；
- 旧会话迁移有备份、回滚和文档，默认仍可使用 JSONL；
- 所有新增公共接口有 `.d.ts` 类型、单元测试和兼容性说明；
- 根目录、runtime-ts、protocol、cli、desktop 的 typecheck/test 均通过；
- 发布包仍包含 desktop 所需 `main.js`、prompts、agents 和 skills 资源。

## 6. 结论与非目标

推荐的目标形态是：`protocol` 定义线协议，`runtime-contracts` 定义运行时接口，`agent-core` 执行通用循环，`session-core` 隔离持久化，`coding-agent` 组合产品能力，`daemon-server` 提供现有 JSON-RPC/NDJSON 服务，`client` 为 CLI/桌面复用客户端。

迁移不是一次性重写，也不要求复制 pi 的完整 agent harness、CBOR protocol、TUI 或 SQLite schema。首要目标是降低循环依赖和替换成本，同时保持 SztuCode 当前行为：TypeScript daemon 仍在 7438 提供 loopback NDJSON/JSON-RPC，桌面端继续以它为事实来源，Python runtime 继续独立运行在 7437。
