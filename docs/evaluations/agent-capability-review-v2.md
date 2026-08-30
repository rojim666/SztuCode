# TypeScript Runtime Agent 能力审计（第二版）

[返回文档中心](../README.md) · [上一版评审](agent-capability-review.md)

> 审计日期：2026-08-30
> 范围：packages/runtime-ts、packages/protocol、TypeScript daemon 的会话、工具、Provider、编排路径和测试。
> 性质：工程审计与路线图，不是行为契约；分数表示当前实现的生产可用度，不表示模型本身的智力。

## 结论先行

当前 TypeScript runtime 已经从“能运行的工作流原型”进入“有产品形状的 Agent 内核”，但还没有达到顶级 coding agent 的可靠性标准。最准确的判断是：**功能广度约 73 分，长程可靠性约 51 分，综合生产能力 66/100**。

它的优势不是空泛的工具数量，而是几个设计确实成立：工具失败能回注对话，模型输出截断有统一归一化，后台压缩和硬丢弃退路存在，读工具可并发，子代理有独立 session，workflow 有 DAG 校验、范围升级证据和角色交接协议。

问题也很集中：核心状态仍主要在内存里，重启不能 resume；RunManager 同时承担 composition root、持久化协调和运行控制；事件总线虽然有 trace，却没有背压和真正的批量写；权限规则已支持参数模式，但 policy 与 workspace、用户作用域仍未形成明确的策略层；MCP、skills、工具发现和模型上下文之间也还没有统一的能力注册协议。

因此，下一阶段的重点不应是继续堆工具，而应是把一次 Agent run 变成可恢复、可解释、可限流、可测量的 durable operation，然后再提升搜索、LSP、浏览器和远程执行等工具广度。

## 1. 评分卡

| 能力维度 | 旧版 | 本次 | 证据与判定 |
| --- | ---: | ---: | --- |
| 上下文管理 | 72 | **79** | ContextManager 有增量 token 缓存、后台摘要、质量门禁、熔断硬丢弃和 offload；但仍是单层摘要，sanitize 每步扫描全量消息，压缩状态不 durable。 |
| 工具系统 | 65 | **78** | Read/Edit 已有行号、分页、锚定、CRLF 和原子 MultiEdit；grep 有并发读取；缺少 ripgrep 原生后端、LSP、结构化 patch、工具搜索和统一输出 envelope。 |
| 权限与安全 | 60 | **72** | Bash 能区分 read_only，权限支持参数 glob 和 workspace 前缀；但规则解析、优先级和 deny 语义分散，缺少 hook 覆盖、三层作用域、命令 AST 和审计解释。 |
| 韧性 | 35 | **57** | LLM 错误可回注，工具有 retryable 标记，run 终态清理；但无 checkpoint、无 resume、无 Retry-After/jitter、无未知外部效果 reconciliation。 |
| 编排能力 | 55 | **74** | spawn_agent、run_workflow、planner graph 校验、DAG 并发和 handoff 已打通；但子代理是同步 tool call，缺少后台 task、优先级、资源配额、取消树和 durable scheduler。 |
| 可观测性 | 85 | **80** | 事件、usage 分类、trace、session 树和 workflow 事件完整；但每个事件仍触发 JSONL append 链，缺少 operation/attempt 稳定关联和指标聚合。 |
| 记忆系统 | 50 | **59** | global/project/session 三层、渐进披露、notes 链和分页读取可用；没有巩固管道、语义检索、冲突解决和跨会话自动提炼。 |
| 扩展生态 | 45 | **62** | skills 已做摘要常驻和按需读取，插件可按 workspace 装载；MCP 仍停在旧 initialize/tools/list，无 resources/prompts、重连和请求超时。 |
| **综合生产能力** | **58** | **66** | 交互 demo 已可信；长时间、多次重启、网络抖动、并行副作用、跨 workspace 策略仍不足以称为生产级。 |

### 评分纪律

1. **存在代码不等于能力成立。** run_workflow 能调用 DAG，不代表具备后台调度、崩溃恢复或任务租约。
2. **测试通过只证明局部不变量。** 当前 runtime 约有 140 个测试，覆盖 provider、workflow、权限、工具和 server contract，但没有真实 provider 故障矩阵、进程级 crash/resume 和仓库规模性能基准。
3. **没有可复现实测数据的能力不打高分。** 尚无 SWE-bench、Terminal-Bench 或长会话成本和成功率的可信 TypeScript 重新测量；旧 Python 评估不能直接外推。

## 2. 当前架构的真实形状

当前主路径仍是：

    JSON-RPC / desktop / CLI
              |
          RunManager
              |
      tools + permissions + prompts + memory + SubagentManager
              |
          AgentLoop
              |
      Provider.complete(messages, tools, callbacks)
              |
      ContextManager / EventBus / SessionStore / Workspace

AgentLoop 在一次循环中同时处理 provider 调用、上下文压缩、schema 校验、权限、重试、offload、拒绝和卡死干预、usage、事件和最终结论（packages/runtime-ts/src/agent-loop.ts:38）。

RunManager.execute() 又负责工具组装、skills、memory、子代理、prompt、session 回写和 change tracking（packages/runtime-ts/src/run-manager.ts:89）。这使第三阶段的 spawn_agent 能很快接入，但也意味着子代理创建、workflow 执行、主 run 取消和 workspace 资源没有统一的 operation 树。

AgentSession 已经提供现代 session facade，但 legacy AgentLoop 仍是主产品路径的重要组成部分；两套抽象尚未收敛。架构文档提出的 contracts、agent-core、session-core 分层仍是正确方向，但尚未落地。

## 3. 深度能力审计

### 3.1 上下文与长程任务

**已经成立**

- TokenCounter 使用 tiktoken，并缓存单消息计数；追加消息走增量快路径。
- compactWithProvider() 保留 goal、progress、decisions、open issues 和 next steps，并校验摘要长度、stop reason、token 预算和中英文标题。
- 压缩在工具执行期间后台运行，完成后合并快照期间追加的消息。
- OffloadManager 把大输出移到 run 目录，使用受限 read_ref 分页读取，且有 realpath 防逃逸。
- 摘要熔断后会调用无模型的滑窗硬丢弃，避免无限增长。

**仍然不足**

- 只有“重摘要”和“硬丢弃”两级，没有 microcompact：旧 tool output、重复日志和已解决错误不能低成本先清理。
- 每个 turn 都执行 sanitizeContextMessages()，消息数量为 n 时至少是 O(n)；长会话总体形成 O(n²) 扫描税。
- messages 是数组，后台压缩靠 snapshotLength 和 splice 合并；并发压缩、steering、tool result 交错时没有 sequence/version 不变量。
- 摘要没有事实来源、文件路径证据、完成标准或引用 ID；模型可能把无来源摘要当成高置信事实。
- run 中间步骤没有 checkpoint；进程崩溃仍会丢失最近一段可恢复状态。

判定：上下文算法已经超过多数简单开源 loop，但距 Claude Code/Codex 的长程体验仍差一个“事实化状态 + 可恢复 checkpoint”层。

### 3.2 工具系统与代码编辑

**已经成立**

- read_file 默认输出 1-based 行号，支持 offset/limit，大文件有上限提示。
- edit_file 支持行锚定、CRLF 归一化、重复匹配诊断和 MultiEdit 原子写回。
- grep_search 有二进制跳过、文件数量上限、信号中止和并发读取。
- ToolRegistry 支持别名、限制工具集合和扩展冲突检测。
- 大输出 offload 后，模型可以通过引用重新分页读取完整结果。

**关键缺口**

- grep 是 Node readFile + JavaScript RegExp，不是 ripgrep 的 SIMD、mmap 和 ignore 语义；2000 文件上限是静默截断而非可发现的分页结果。
- Edit 仍是文本替换，不理解 AST、代码块、JSON/YAML 结构、重命名引用或 patch context。
- MultiEdit 的“原子”只覆盖单进程内存到一次 write，不覆盖 crash-safe fsync/rename。
- 没有 LSP diagnostics、definition、references、rename；测试失败也没有统一的文件和行号链接。
- MCP 工具定义直接进入 registry，缺少 schema 降级、危险字段标注、超时、输出预算和 capability discovery。

### 3.3 权限与安全

**已经成立**

- 工具有静态 permission，并允许 classifyPermission(params) 动态升级。
- Bash 解析命令链、管道、重定向、变量展开、路径逃逸和 git 子命令；本地只读命令返回 read_only。
- policy 支持工具级和参数 glob，权限请求有 pending、timeout、abort 生命周期和 telemetry span。
- workflow coder 的 allowed paths 与实际 changed paths 做证据一致性校验。

**仍然不足**

- PermissionManager、bash-permission、workflow scope 和 extension hook 各自判断，没有统一的可解释 rule engine。
- policy 没有完整的 deny-overrides-allow、ask rules、规则来源和版本；workspace 前缀是编码约定，不是独立 scope 模型。
- Bash 是字符串分词器，不是 shell AST。复杂 quoting、函数和 here-doc 仍可能误判；“只读”命令也可能读取工作区外隐式配置或触发网络。
- always_allow 没有绑定完整参数摘要、用户、客户端、时间、策略版本和 workspace identity。
- 扩展工具和 MCP 工具可以声明任意 schema/permission，缺少加载时 capability review 与沙箱级别。

### 3.4 韧性、取消与恢复

**当前可用**

- provider 抛错会作为 user message 回注；连续失败达到上限才终止。
- 工具可以声明 retryable: false，bash exit 非零不会被重复执行。
- run 终态会延迟清理 runs Map，保留短时间供 run.get 查询。
- AbortSignal 能传播到 provider、工具、权限等待、问题等待、压缩和子代理。

**生产级缺陷**

- run 的唯一事实仍是内存 RunState 加最终 session 回写；没有每步消息、tool intent、provider attempt 的 durable record。
- daemon 崩溃后 recoverInterruptedSessions() 只把 active session 降级为 waiting/closed，不会重建未完成 run。
- provider retry 固定封顶 2 秒，不读取 Retry-After，没有 jitter，也没有按 408、429、5xx和连接错误分类。
- provider 请求中途断开时，系统不知道外部调用是否已产生结果；自动重试可能重复计费或重复效果。
- cancel 事件、异步 execute 最终回写、session status、change tracker 和子代理终态之间没有统一 commit point。
- 没有暂停后继续、离线队列、provider fallback、预算耗尽后的降级模型和用户可见恢复策略。

这是当前最重要的能力鸿沟。顶级产品的体验不是“偶尔能跑到结尾”，而是“失败后工作仍然可继续、结果可解释、不会悄悄重复副作用”。

### 3.5 自主编排与多 Agent

**已经成立**

- spawn_agent 让模型能选择 planner、coder、tester 或 reviewer 并取得子代理证据。
- planner 输出会尝试解析并校验 WorkflowGraph。
- run_workflow 可调用 DAG orchestrator；任务有依赖、并发、超时、token budget、重试和 handoff artifact。
- 子代理有独立 session、父子 session/run 事件和权限模式。

**仍然不足**

- spawn_agent 是普通同步 tool call，主 Agent 会等待完整子代理结束；没有后台 task、progress、poll、stop、output 分页和任务租约。
- SubagentManager 在每个主 run 中创建，children 只存在内存 Map；daemon 重启后无法查看或恢复子任务。
- 主 Agent 可以调用 run_workflow，但没有 planner proposal、用户批准、资源估算、执行、审查、修复的显式状态机。
- workflow、child run、task attempt 和 parent operation 的身份关系还不够清晰。
- 子代理结果以文本或 JSON 回注，缺少共享 artifact store 和按需引用，容易重复大量上下文。

结论：编排“功能链”已通，但编排“控制平面”尚未成立。

### 3.6 Skills、MCP 和生态

- skills 已实现名称和描述常驻、正文按需读取，渐进披露方向正确。
- skill metadata 没有版本、依赖、冲突、适用文件类型、风险级别和验证状态。
- system prompt 每次 run 都扫描 builtin、personal、workspace、plugin roots；没有 mtime cache 或 per-session snapshot。
- skill body 作为普通文本注入，没有参数 schema、工具白名单强制或 provenance。
- MCP 客户端硬编码 2024-11-05，只支持 tools/list 和 tools/call；无 resources、prompts、notifications、重连、请求超时、取消和 capability negotiation。
- MCP 返回只保留 text content，图片、结构化 JSON、resource link 和错误 metadata 丢失。

### 3.7 会话、记忆与产品状态

- SessionStore 以 JSONL/JSON 保留历史、context、notes、run stats 和事件，兼容性好、调试容易。
- meta.json 通过 get→改→save 反复全量读写；跨进程没有 writer lease。
- context 文件整体 writeFile 替换，缺少 fsync、rename、checksum；崩溃可能留下半文件或备份泛滥。
- session history、model context、run event、workflow state 没有事务边界。
- memory 只有读取和 notes 写入，没有 session 结束后的巩固、去重、冲突解决、过期和用户审核。
- 现代 AgentSession 与 legacy AgentLoop/RunManager 并存，状态模型和事件模型存在双轨风险。

## 4. 性能障碍清单

| 优先级 | 障碍 | 位置 | 放大方式 | 解决方案 |
| --- | --- | --- | --- | --- |
| P0 | 无 checkpoint，崩溃后整段 run 重来 | agent-loop、session-store | 长任务失败成本随已完成步骤增长 | append-only operation/step/attempt records；assistant response 和 tool result settle 后 checkpoint。 |
| P0 | provider retry 不读 Retry-After 且无 jitter | providers/configurable.ts | 429 时多客户端同步重试，形成 retry storm | 状态分类、Retry-After、full jitter、重试预算和全局 token bucket。 |
| P0 | 工具和子代理没有 durable lease | subagent、workflow | 父 run 结束后可能悬挂或重复 | operation tree、取消树、task lease 和 terminal idempotency key。 |
| P1 | 每步全量 sanitize | agent-loop:202、context:55 | n 步累计 O(n²) | append 时维护 tool-call balance index，只扫描变化区间。 |
| P1 | EventBus 每事件一条 JSONL append | event-bus:35 | 每个 token/log 进入 Promise 链和文件写 | 50-100ms micro-batch、单 writer stream、优先级和背压策略。 |
| P1 | grep 纯 JS 读文件 | tools:329 | 大仓库 CPU、RSS、syscall 高且静默截断 | 优先 rg --json，回退 JS；返回 cursor、matched_files 和 truncated。 |
| P1 | prompt 每 run 扫描 instructions、git、skills | prompt-loader、skills | 每次 run 重复 IO 和 git process | workspace snapshot cache、mtime/hash 和稳定 prompt prefix。 |
| P1 | SessionStore 全量 meta/context 写回 | session-store | 高频消息造成 IO 放大和并发竞争 | append-only metadata、批量 stats、atomic rename、可选 SQLite。 |
| P1 | Read/Edit 仍以 UTF-8 文本为中心 | tools | 大文件、结构化文件和编码异常导致重试 | file capability、encoding/line map、patch/AST/LSP adapter。 |
| P2 | Windows Git Bash 使用 --login | tools:436 | 短命令启动延迟被 profile 放大 | 默认非 login shell，必要时 opt-in，或复用 worker。 |
| P2 | workflow 结果全文回注 | subagent/tool result | 多子代理使主上下文线性增长 | artifact store、结构化摘要和 task_output 分页。 |
| P2 | MCP 无超时、取消和重连 | mcp | server 卡住时 pending Promise 长期不结束 | per-call timeout、AbortSignal、reconnect/backoff 和 pending rejection。 |

### 推荐性能基准

1. 10k、100k 条消息的 append、sanitize、token estimate 延迟和 heap。
2. 1k、10k、100k 文件仓库的 rg、JS grep、glob wall time、CPU、RSS 和截断率。
3. 100、1k、10k events 的 publish-to-flush 延迟、syscall 数和丢失率。
4. 429、连接断开、kill -9、tool timeout、父任务取消下的恢复时间和重复 effect 数。

## 5. 与顶级 Agent 产品的结构差距

比较对象取 Claude Code、OpenAI Codex CLI、Gemini CLI 和一流 IDE Agent 的公开能力形态。这里比较工程机制和用户可观察行为，不声称复制其内部实现。

| 能力 | 顶级产品共同特征 | 当前 runtime | 差距 |
| --- | --- | --- | --- |
| 代码定位 | 行号、快速搜索、结构化诊断，读写闭环 | 行号 Read、文本 Edit、JS grep | 缺 ripgrep、LSP、AST 和统一位置引用。 |
| 权限 | 工具、参数、scope、deny/ask/allow 优先级，决策可解释 | 工具级、部分参数 glob、workspace 前缀 | 缺正式 policy engine、规则来源和 hook override。 |
| 错误恢复 | 网络、限流、上下文和工具错误都成为可处理状态 | LLM 错误回注，有限 retry | 缺 Retry-After、fallback、checkpoint 和未知效果处理。 |
| 会话恢复 | 任务可继续，中间状态可恢复 | 重启后只恢复 session 可见状态 | 缺 run/step/attempt durable log 和 resume。 |
| 流式交互 | 中途 steering、取消 generation、后台任务 progress | step 边界 steering，token 已合帧 | 缺 generation-level steering 和 task observer。 |
| 子代理 | 自主 fan-out，可观察、暂停、取结果 | spawn_agent 同步调用，DAG 可执行 | 缺后台 task control plane、租约和 artifact refs。 |
| 工具发现 | 核心工具常驻，其余延迟发现 | 大多数工具随 run registry 提供 | 缺 capability catalog、ToolSearch 和 schema 版本。 |
| 上下文 | microcompact、摘要、事实引用、稳定 cache prefix | 摘要、滑窗、offload | 缺分层压缩、provenance 和 checkpoint-aware cache。 |
| 记忆 | 会话结束提炼、项目偏好、可搜索可审查 | notes 和三层文本读取 | 缺巩固、检索、过期、冲突和用户批准。 |
| MCP | resources/prompts、重连、取消、schema 转换 | tools/list 和 tools/call | 协议能力和错误处理落后一代。 |
| 成本控制 | token、时间、并发、模型路由和失败预算 | usage 和部分 token budget | 缺全局限流、重试预算、fallback 和 operation 成本预算。 |

## 6. 分阶段扩展路线

### 阶段 A：Durable Run Core

目标：任何已接受的 prompt 在进程崩溃后都能恢复为“未开始、继续中、已完成或明确失败”，不重复已结算效果。

1. 定义 OperationRecord、StepRecord、AttemptRecord、ToolIntent、ToolResult 和 OperationTerminal。
2. 以 append-only JSONL 先实现，不立即引入 SQLite；每条记录带 sequence、operation、step、attempt、workspace 和 session。
3. provider response 完整 settle 后再分类；tool call 先写 intent，再执行，再写 result。
4. crash recovery 处理 unknown external effect：默认不自动重放危险工具，回注“结果未知”并要求读回确认。
5. 增加 run.resume、run.replay 和 operation status；保留 7438 JSON-RPC 兼容。

验收：kill -9 注入覆盖 provider 前后、tool intent 前后、tool result 前后和 session write 前后；恢复不重复成功的幂等工具，未知效果有 audit。

### 阶段 B：Provider Control Plane

1. 统一 ProviderError：status、retryable、retry_after_ms、request_id、billing_effect、partial_response。
2. Retry-After + full jitter + per-provider budget + global concurrency/token bucket。
3. 分别处理连接超时、读超时、DNS、429、5xx、上下文超限、schema 和认证错误。
4. 支持显式 fallback policy；fallback 必须记录在 operation 中。
5. 将 provider facade 从 agent-loop 提出到 contracts，切断反向类型依赖。

### 阶段 C：Tool Plane 2.0

1. 用 rg --json 替换大多数 JS grep，返回 cursor、truncated 和 matched_files。
2. 引入 ToolEnvelope：status、output、artifact_ref、locations、warnings、retry_policy 和 side_effect_class。
3. 增加 LSP diagnostics、definition、references；Edit 失败返回精确位置和建议 patch。
4. 将 Read/Edit 的文本行映射、编码和结构化 patch 抽成 capability adapter。
5. MCP 工具进入 catalog，支持延迟加载和 schema 版本。

### 阶段 D：Permission Policy Engine

1. 统一为 deny > ask > allow > mode default；subject 从 command、path、file、url 等字段标准化提取。
2. scope 区分 builtin、user、workspace、session、run；记录来源、版本、创建者和时间。
3. Bash 使用 parser 或安全 token model，无法证明只读时 fail-closed。
4. hooks 可返回 allow、ask、deny，但必须记录 override 原因。
5. 前端提供“为什么询问或拒绝”的解释事件。

### 阶段 E：Autonomous Task Plane

1. 新增 task_spawn、task_get、task_list、task_output、task_stop。plan tools 负责计划，task tools 负责执行 operation。
2. 每个 task 有 parent operation、role、model、priority、token/time budget、allowed tools、workspace scope、lease 和 terminal state。
3. 主 Agent 可并发 fan-out，但受全局并发和 token budget 限制；结果以 artifact reference 返回。
4. planner 先返回 proposal，模型或用户批准后执行 DAG；reviewer/tester 结果成为 graph gate。
5. 子任务支持暂停、恢复、重试和 crash reconciliation。

### 阶段 F：Memory、Skills、MCP 和评测闭环

1. session 结束时提炼 notes，按事实、偏好、决策、未决事项分类；写入前去重、冲突检测并允许审核。
2. skill metadata 增加版本、依赖、风险、适用范围、允许工具和 provenance；正文加载建立 hash cache。
3. MCP 升级 resources/prompts、capability negotiation、取消、超时、重连和结构化 content。
4. system prompt 建立稳定 prefix cache；项目指令、技能目录、工具 catalog、git snapshot 分层缓存。
5. 建立 SWE-bench Lite、Terminal-Bench 精选任务、网络故障、长会话和多 agent 成本报告。

## 7. 架构落地顺序

不要直接重写 AgentLoop。推荐用兼容 facade 渐进迁移：

    现有 RunManager / AgentLoop
              |
      OperationCoordinator
              |
        Agent Core Facade
              |
      Durable Session Backend

1. 先提取 contracts：消息、provider response/error、tool envelope 和 operation IDs。
2. 在现有 RunManager 外包一层 coordinator，只追加记录，不改变事件和 RPC。
3. 给 provider/tool 增加 intent/settle boundary，先覆盖只读和幂等工具。
4. 建立 crash/recovery conformance suite，再迁移写工具和子代理。
5. 最后把 RunManager 降为兼容 facade，将组合逻辑移至 coding-agent service。

## 8. 必须避免的错误路线

- 不要先增加几十个工具来掩盖无 resume 的核心问题。
- 不要用更长 prompt 代替 durable state；摘要不是日志，模型记忆不是事实库。
- 不要把所有工具标为可重试；副作用必须有 idempotency key 或读回校验。
- 不要未经 benchmark 就宣称 JS grep、EventBus 或 session IO 优化有效。
- 不要把 planner JSON 解析成功等同于 DAG 生产可用；必须包含 proposal、approval、execution、review 和 recovery。
- 不要在没有协议版本和迁移策略时直接替换 JSONL、7438 JSON-RPC 或桌面事件字段。

## 9. 最终判断

SztuCode TypeScript runtime 已具备一个认真 Agent 产品的骨架，尤其是工具安全、压缩、offload、事件和角色化 workflow；阶段二和阶段三也确实提升了“模型能完成什么”。但顶级 Agent 的分水岭在于“长任务失败后还能否可靠继续”，而不是工具列表是否更长。

当前最大的投资回报来自 durable operation/recovery、provider control plane、统一权限策略和后台 task plane。完成阶段 A-D 后，综合生产能力预计可从 66 提升到 78-82；完成阶段 E-F 并用真实 benchmark 校准后，才有资格讨论 85+。

在此之前，任何 SWE-bench 成功率、成本或“接近 Claude Code/Codex”的表述都应标注为未由当前 TypeScript runtime 重新证明。
