# SztuCode 简历面试深度问答手册

> 历史复盘：本文描述早期 Python daemon + Textual 阶段，不代表当前 TypeScript daemon、Node 终端客户端和 Tauri 桌面架构。当前实现以 [架构说明](reference/architecture.md) 为准。

> 基于项目代码（`py-runtime/src/sztu_code/`）、Git 历史（50 commits, S0→S7）和设计文档，
> 逐句拆解简历描述的每个关键概念，预测面试提问并给出有代码证据的回答。

---

## 项目总述

> **SztuCode 是从零构建的本地 AI Coding Agent，面向 Claude Code、Codex 类产品的核心运行机制探索。采用"常驻 Daemon + Textual TUI 多客户端"架构，解决长任务执行、工具安全调用和复杂执行过程难以观测的问题，支持流式推理、权限审批、多 Agent 协作及 MCP 扩展。**

### Q: "从零构建"——你具体做了什么？框架选择是什么？

**答**：项目从 `Initial commit`（空仓库）起步，历经 8 个阶段（S0→S7），每阶段有明确的交付物：

| 阶段 | 提交 | 交付物 |
|------|------|--------|
| S0 | `89e6df4` | 项目骨架 + pydantic 协议契约（`bus/envelope.py`, `bus/commands.py`, `bus/events.py`） |
| S1 | `76e2992` | 单进程 Agent 循环最小闭环 |
| S2 | `1d4d6ba` | 双进程架构：TCP NDJSON 通信层 |
| S3 | `16bbe3b` | 八工具体系（read/write/edit/bash/list/task） + TUI |
| S4 | `9ffbcc4` | Session 持久化 + 分层语义记忆 |
| S5 | `7738b8f` | 工具安全：权限审批 + 失败分类 + 持久化策略 |
| S6 | `f4567c1` | 上下文压缩 + 流重试 + 分层记忆 |
| S7 | `d9544f1` | Subagent、Skills、MCP、多 Agent 编排 + Extended Thinking |

**没有用任何 Agent 框架**（如 LangChain、AutoGen、CrewAI）。核心循环（`loop.py:173` 行）全部手写。

技术栈选择：
- **语言**：Python 3.12+（async/await 原生支持）
- **协议**：JSON-RPC 2.0 + NDJSON（与 Claude Code 同款协议）
- **LLM SDK**：`anthropic` Python SDK（流式）+ 自研 OpenAI provider
- **TUI**：Textual（终端 UI 框架）
- **数据校验**：Pydantic v2（discriminated union）
- **配置**：TOML + 环境变量四级优先级

### Q: 你说"探索核心运行机制"——探索出了什么结论？

**答**：核心发现有三：

1. **Agent Loop 的本质是 "plan→act→observe" 循环，不是 DAG。**
   多步任务不需要预先规划完整的执行图——每步 LLM 看到当前状态后决定下一步。
   `loop.py:52-172` 的实现验证了这一点：没有任务图，只有 `while not context.is_done()`。

2. **长任务必须与前端解耦。**
   早期（S1）是单进程模型，TUI 关闭 = Agent 死亡。S2 引入 Daemon 后，TUI 只是"观察窗口"。
   `socket_server.py:139` 的 `asyncio.create_task` 保证了 handler 不随 client 断开而取消。

3. **安全不是"沙箱"能做好的。**
   工具安全需要多层：权限模式（`permission/mode`）、运行时审批（`PermissionManager.check_and_wait`）、
   熔断干预（`DenialTracker`）——纵深防御而非单点阻断。

### Q: "常驻 Daemon + Textual TUI 多客户端"——为什么不选 Electron/Web？

**答**：这是有意为之的约束：

- **终端原生**：目标用户是习惯终端的开发者。Textual 提供键盘驱动的交互，启动速度 < 1s。
- **多客户端共享 Session**：因为 Daemon 持有所有状态（session、run、工具注册表），
  多个 TUI 可以同时 `event.subscribe` 同一个 session，看到同一个 agent run 的实时进度。
  `ipc_broadcaster.py` 的 `_Subscription` 机制支持按 topic + scope 精确路由。
- **Desktop 客户端**：后来通过 `desktop/` 目录加上了 Electron（Tauri？）套壳，
  但核心通信仍然是 TCP NDJSON——桌面端不过是另一个 SocketClient 实例。

---

## 简历第一点：ReAct Agent Loop

> **为解决 Agent 在复杂任务中易中断或陷入循环的问题，设计并实现 ReAct Agent Loop，串联 LLM 流式推理、Tool Use 解析、本地工具执行和结果回注；加入步数上限、异常兜底与流式重试；最终形成可自主多轮决策的 Agent 执行闭环，避免长任务因网络异常或循环调用失控而中断。**

### Q: 解释 ReAct Loop 在你的项目中具体是怎么工作的？

**答**：核心代码在 `loop.py:52-172`。完整流程：

```
while not context.is_done():
    step += 1
    
    [intervene]  连续被拒？→ 注入干预消息强制换策略
    [plan]       调用 LLM（流式），发布 token 事件给 TUI
    [observe]    将 LLM 响应（thinking + text + tool_calls）追加到 context.messages
    [act]        遍历 tool_calls，逐个调用 invoke_tool()
                 工具结果作为 tool_result block 追加到消息历史
    [compact]    上下文使用率超阈值？→ 压缩消息历史
    [terminate]  stop_reason=end_turn → 成功 | step≥max_steps → 失败
```

关键设计决策：

1. **消息历史是完整的无状态数组**（`context.messages`）。LLM 不持有任何会话状态——
   每轮都传入完整历史。这意味着 run 可以被中断恢复、完整回放。

2. **工具调用串联执行**（非并行）。在 `loop.py:126`：
   ```python
   for tc in response.tool_calls:
       result = await invoke_tool(...)
       context.add_tool_result(tc.id, result.content, is_error=result.is_error)
   ```
   原因是 LLM 场景下工具调用通常有依赖关系（先读文件再编辑），
   并行执行会导致后一个工具在前一个工具结果不可见的情况下运行，失败率高。

3. **LLM API 错误直接终止**（不走重试），但网络中断走 `_MAX_STREAM_RETRIES=3` 次流式重试（`provider.py:98-121`）。

### Q: "流式重试"具体是怎么做的？为什么不重试所有错误？

**答**：`provider.py:98-121`：

```python
for attempt in range(1, _MAX_STREAM_RETRIES + 1):
    try:
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if attempt == 1:    # 仅第一次发布 token 事件
                    await bus.publish(LlmTokenEvent(...))
                text_parts.append(text)
            final_message = await stream.get_final_message()
        break  # 成功
    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
        if attempt == _MAX_STREAM_RETRIES:
            raise                    # 最终失败，向上传播给 AgentLoop
        await asyncio.sleep(_RETRY_BACKOFF_S[attempt - 1])  # 指数退避: 1s→2s→4s
```

设计要点：
- **只重试网络层异常**（`RemoteProtocolError`, `ReadError`, `ConnectError`）——这些是瞬时网络问题。
- **不重试 API 错误**（如 401 认证失败、429 限流）——因为是配置问题，重试不会变好。
- **重试期间不发 token 事件**（`attempt == 1` 保护）——避免 TUI 收到重复的 token 流。
- **指数退避**：1s, 2s, 4s。

### Q: "步数上限"和"异常兜底"是怎么实现的？

**答**：步数上限在 `loop.py:155-156`：

```python
elif context.step >= context.max_steps:
    context.mark_failed("exceeded_max_steps")
```

注意判断顺序：**先检查 `end_turn` 再检查 `max_steps`**。这意味着如果 LLM 恰好在最后一步完成任务（`stop_reason == "end_turn"`），标记为成功而非失败——这是有意为之的终止语义。

异常兜底有两层：

1. **LLM 调用层**（`loop.py:99-106`）：`CancelledError` 向上传播（run 被取消），其他异常标记 `"llm_error"` 并 break。
2. **工具调用层**（`invocation.py:105-258`）：工具调用 **永不抛异常**——所有错误（timeout、schema_error、runtime_error）都转换为 `ToolResult(is_error=True)`。这是关键设计：即使工具出错，agent loop 不会崩溃，LLM 看到错误结果后可以换策略。

### Q: "避免长任务因循环调用失控"——你怎么检测和阻止死循环？

**答**：三层防御（纵深防御）：

| 层级 | 机制 | 代码位置 |
|------|------|----------|
| 硬限制 | `max_steps` 步数上限（默认 20） | `loop.py:155` |
| 软熔断 | `DenialTracker`：同工具连续被拒 3 次或累计 20 次 → 注入干预消息 | `denial_tracker.py` |
| 上下文控制 | 上下文使用率超 `compact_threshold` 时自动压缩 | `loop.py:160-168` |

`DenialTracker` 是专门设计的新组件（`denial_tracker.py`），不是简单计数器：

```python
def record_denial(self, tool_name: str) -> bool:
    self._consecutive[tool_name] = self._consecutive.get(tool_name, 0) + 1
    self._total += 1
    return self.should_intervene()

def record_success(self, tool_name: str) -> None:
    self._consecutive[tool_name] = 0  # 成功即清零——AI 已改变策略
    self._intervened_this_cycle = False  # 开启新一轮干预窗口
```

关键设计：`_intervened_this_cycle` 防止同一轮重复注入干预消息（注入一次后等待 AI 响应），
而 `record_success` 重置整个周期——"一次成功调用 = AI 已经调整了策略"。

---

## 简历第二点：父子 Agent 编排

> **为支持复杂任务拆分，实现父子 Agent 编排，支持异步派生 SubAgent，并通过事件桥接、状态透传和结果回传协调子任务。最终系统支持将复杂目标拆分为独立子任务并并行/异步执行，TUI可跟踪子任务状态及最终结果。**

### Q: "父子 Agent 编排"的架构是怎样的？子 Agent 和父 Agent 共享什么、隔离什么？

**答**：核心实现在 `subagent/tool.py`（335 行）。

**共享**：
- LLM Provider（同个 API key / 模型）
- PermissionManager（统一的权限审批）
- BackgroundTaskRegistry（跨父子共享的后台任务表）

**隔离**：
- **消息历史完全隔离**：子 Agent 从空白 context 开始，只接收 `prompt` 参数中的指令
- **独立的 EventBus**：`child_bus = EventBus()`，然后通过 `_bridge` 函数桥接到父 bus
- **独立的 DenialTracker**：避免父子 agent 拒绝计数互相干扰
- **独立的 ExecutionContext**：各自的 `step`、`status`、`max_steps`

**嵌套深度限制**（`tool.py:113-118`）：
```python
if self._depth >= 2:
    return ToolResult(
        content="Subagent nesting limit (2) reached...", is_error=True
    )
```
根 agent `depth=0`，最多派生 `depth=1` 的第一层子 agent。`depth=1` 的子 agent 仍可注册 `SpawnAgentTool`，
但调用时会直接返回错误。这意味着最多 3 层（根→子→孙），防止无限递归。

### Q: "事件桥接"具体怎么实现？TUI 如何看到子 Agent 的进度？

**答**：事件桥接是子 Agent 可观测性的核心机制（`tool.py:135-138`）：

```python
child_bus = EventBus()

async def _bridge(event: BaseModel) -> None:
    await self._parent_bus.publish(event)

child_bus.subscribe(_bridge)
```

效果：**子 Agent 发布的所有事件（StepStarted、ToolCallStarted、Token 流、StepFinished）
全部被转发到父 bus**。因为 TUI 的 `event.subscribe` 订阅的是父 bus（通过 `ipc_broadcaster`），
所以在 TUI 中能实时看到子 Agent 的每一步工具调用和 token 输出。

此外还有结构化的生命周期事件：
- `SubagentStartedEvent`：子 Agent 启动（包含 `description` 用于进度展示）
- `SubagentFinishedEvent`：子 Agent 完成（包含 `status`）

### Q: 前台和后台子 Agent 有什么区别？为什么需要两种模式？

**答**：前台（`run_in_background=False`）和后台（`run_in_background=True`）的区别（`tool.py:164-176`）：

```python
if p.run_in_background:
    task = asyncio.create_task(
        self._run_background(child_loop, child_context, child_bus, child_run_path, child_run_id)
    )
    self._task_registry.register(child_run_id, task, child_context)
    return ToolResult(content=f"Subagent started in background. run_id={child_run_id}...")
# 前台模式
async with EventWriter(child_run_path / "events.jsonl") as writer:
    writer.subscribe(child_bus)
    await child_loop.run(child_context)  # 阻塞直到完成
```

| 维度 | 前台 | 后台 |
|------|------|------|
| 父 Agent 行为 | 阻塞等待子 Agent 完成 | 立即返回 run_id，继续执行 |
| 结果获取 | 返回时自带结果 | 需要通过 `agent_result(run_id)` 轮询 |
| 适用场景 | 依赖子任务结果才能继续 | 可并行的独立子任务 |
| 生命周期管理 | 随父 Agent 完成而自然结束 | 注册到 `BackgroundTaskRegistry`，daemon 退出时统一 cancel |

### Q: `agent_result` 工具怎么知道子 Agent 结束了？轮询不是低效吗？

**答**：`agent_result` 不是轮询——它是按需查询（`tool.py:311-334`）。LLM 在需要结果时才调用一次：

```python
task, context = entry
if not task.done():
    return ToolResult(content="still running")
```

设计理念：LLM 在 agent loop 中被问到"需要工具调用吗"时才调用 `agent_result`，
不是在后台做 busy-polling。这种 "pull-based" 模型比 "push-based callback" 更简单，
且与 LLM 的 turn-based 交互模式天然匹配。

---

## 简历第三点：Daemon-TUI 通信层

> **为保证任务执行不受前端生命周期影响，基于 JSON-RPC 2.0、TCP/NDJSON 构建常驻 Daemon 与 TUI 的通信层，实现事件订阅、断线重连及共享 Session；最终 Agent 执行与前端解耦，TUI 退出或重连都不会中断后台任务，这样就支持多个客户端查看同一任务会话。**

### Q: 为什么选 JSON-RPC 2.0 + TCP/NDJSON？WebSocket 不是更合适吗？

**答**：几个判断：

1. **JSON-RPC 2.0** 是 Claude Code 同款协议——项目目标是探索其核心运行机制，协议对齐降低理解成本。
2. **NDJSON**（换行分隔 JSON）比 WebSocket frame 更简单——不需要帧头、不需要 upgrade 握手，
   只需要 `readline()` + `json.loads()`。64MB frame 限制（`_MAX_LINE_BYTES = 64 * 1024 * 1024`）足以承载 MCP 大文件工具结果。
3. **TCP 而非 Unix domain socket**：跨平台一致性（此项目运行在 Windows 上）。
4. **WebSocket 的缺点**：需要 HTTP upgrade、需要处理 ping/pong、浏览器生态的复杂性对 daemon-to-TUI 通信是多余的。

### Q: "TUI 退出不会中断后台任务"——技术上怎么实现的？

**答**：核心在 `socket_server.py:139` 的一行代码：

```python
asyncio.create_task(self._handle_line(line, writer))
```

这是"fire-and-forget"模式：
- `read_loop` 持续读取新请求行
- 每个请求（包括 `session.send_message` 触发的长时间 agent run）作为独立 task 运行
- **task 的生命周期不绑定到 writer 的生命周期**

当 TUI 断开时（writer close）：
1. `read_loop` 因 EOF 退出 → `finally` 块清理 writer → broadcaster 取消该 writer 的订阅
2. **但 handler task 继续运行**——因为在 `_handle_connection` 的 finally 中只 close 了 writer，
   没有 cancel 任何 task（甚至没有追踪 task 句柄）

这导致一个"副作用"：agent run 在客户端断开后仍继续执行——但这恰好是 chat 模式的期望行为：
用户关闭 TUI，agent 继续工作；用户重连 TUI 后 `session.resume` 恢复会话。

### Q: "断线重连"具体怎么做？重连后历史消息会不会丢？

**答**：TUI 的重连逻辑在 `tui/app.py` 的 `_socket_loop` 中：

```python
while True:
    try:
        client = SocketClient(host, port)
        await client.connect()
        client.on_event(self._handle_event)
        await client.run_event_loop()
    except (ConnectionRefusedError, OSError):
        await asyncio.sleep(2)  # 退避 2 秒
        continue
```

重连后恢复会话的流程：
1. `event.subscribe` 向 daemon 重新订阅事件
2. `session.resume` 恢复指定 session
3. Daemon 的 `_subscribe_handler` 支持**历史回放**（`app.py` 的 `_replay_events`）——扫描 `events.jsonl`，
   将匹配的过去事件以 `EventPushEnvelope` 形式推给新连接的客户端

消息历史存储在 `~/.sztu/sessions/<session_id>/thread.jsonl` 中（`session/store.py`），
由 daemon 持有——TUI 不需要本地缓存，重连后从 daemon 拉取完整历史。

### Q: 多个客户端怎么"看到同一个任务会话"？事件怎么路由？

**答**：`ipc_broadcaster.py` 的订阅模型：

```python
@dataclass
class _Subscription:
    sub_id: str
    writer: asyncio.StreamWriter
    topics: list[str]       # fnmatch glob patterns, e.g. "step.*", "tool.*"
    scope: str              # "global" | "run:<run_id>"
```

- `topics`：按事件类型过滤（glob 匹配）——TUI 通常订阅 `["*"]`（全量）
- `scope`：按 run 过滤——`"global"` 接收所有 run 的事件，`"run:abc123"` 只接收特定 run

当事件发布时，broadcaster 遍历所有订阅，对每个匹配的订阅写入 `EventPushEnvelope`。
两个 TUI 各有一个独立的 writer 在 `_subscriptions` 中，所以同一事件会被写到两个 TCP 连接上。

---

## 简历第四点：MCP 与上下文压缩

> **为扩展 Agent 的外部能力并控制长任务上下文成本，接入 MCP Client，实现外部工具发现、异步调用、超时取消；同时实现上下文水位检测与摘要压缩；最终扩展系统 Agent 对外部工具和数据源的接入能力，同时在长任务中控制上下文长度，保留目标、关键决策及必要工具结果。**

### Q: MCP Client 是怎么接入的？stdio 和 TCP 两种 transport 怎么选择？

**答**：MCP 接入有完整的连接管理（`mcp/client.py` + `mcp/server.py` + `mcp/tool.py`）：

**连接**（`McpClient`）：
- **stdio**：`asyncio.create_subprocess_exec` 启动子进程，通过 stdin/stdout NDJSON 通信。
  关键细节：**后台 drain stderr**（`_drain_stderr` 协程）——防止 MCP server 的 stderr 管道缓冲区满导致子进程阻塞。
- **TCP**：`asyncio.open_connection`，与 TCP MCP server 通信。

**握手**（`client.py:73-79`）：
```python
async def _initialize(self) -> None:
    await self._call("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "sztu-code", "version": "0.1"},
    })
    await self._notify("notifications/initialized", {})
```

**工具注册**（`server.py:36-38`）：
```python
def register_tools(self, registry: ToolRegistry) -> None:
    for tool in self._tools:
        registry.register(tool)
```

MCP 工具与内置工具在同一个 `ToolRegistry` 中，LLM 看到的是统一的 `tool_schemas()` 列表。
**LLM 不知道也不应该知道工具来自 MCP 还是内置**——这是正确的抽象。

### Q: "超时取消"怎么做的？MCP server 卡住了怎么办？

**答**：两层超时保护：

1. **每次 `_read_line` 有 30s 超时**（`client.py:203`）：
   ```python
   data = await asyncio.wait_for(self._reader.readline(), timeout=30.0)
   ```

2. **每次工具调用有 120s 总超时**（`invocation.py:197-198`）：
   ```python
   result = await asyncio.wait_for(tool.invoke(runtime_params), timeout=timeout)
   ```

超时后返回 `ToolResult(is_error=True, error_type="timeout")`——**不抛异常**——LLM 看到错误可以换工具。

关闭 MCP server 时的安全处理（`client.py:120-145`）：
- stdio: `terminate()` → `wait(5s)` → 超时则 `kill()`
- TCP: close writer → `wait_closed()`

### Q: "上下文水位检测"——怎么知道什么时候该压缩？

**答**：水位检测在 `loop.py:160-168`：

```python
if (
    not context.is_done()
    and response.stop_reason == "tool_use"    # run 还将继续（有工具调用）
    and self._compactor is not None
    and self._compact_threshold > 0           # 默认 0 = 禁用
    and response.usage is not None
    and response.usage.context_pct >= self._compact_threshold
):
    await self._compactor.compact(context, self._provider)
```

触发条件精确且保守：
- `not context.is_done()`：只在 run 继续时压缩（不要在最后一步浪费 token 做压缩）
- `stop_reason == "tool_use"`：确保压缩结果 `[user_summary, assistant_ack]` 对下一次 LLM 调用是合法的消息交替
- `compact_threshold` 默认 0.0（禁用）——自动压缩有信息丢失风险，项目倾向让用户手动 `/compact`

### Q: 压缩的摘要包含哪些内容？压缩后的消息历史是什么结构？

**答**：摘要提示词（`compactor.py:18-45`）要求 LLM 输出 6 个结构化段落：

```markdown
## 1. Original Goal        # 一句话复述原始目标
## 2. Completed Steps       # 已完成步骤（含文件路径、命令、决策）
## 3. Key Constraints       # 关键约束与发现（API 限制、文件格式等）
## 4. Current File State    # 每个文件路径 + 一行状态描述
## 5. Remaining TODOs       # 有序待办清单
## 6. Critical Data         # 必须逐字保留的值（ID、token、错误信息）
```

压缩后的消息历史被**就地替换**为两行（`compactor.py:83-86`）：
```python
context.messages = [
    {"role": "user", "content": result.summary_text},
    {"role": "assistant", "content": "Understood, I'll continue from this summary."},
]
```

这样的好处是：后续 LLM 调用看到的 `[user: summary, assistant: "Understood..."]`
形成一个合法的 turn，LLM 可以从这个 checkpoint 继续工作。

Token 估算不做精确计算（太慢），而是用 **字符数 / 4** 的粗略近似（`compactor.py:113-114`）：
```python
original_estimate = sum(len(str(m.get("content", ""))) for m in messages) // 4
```

### Q: 如果压缩本身失败怎么办？LLM 返回空摘要怎么办？

**答**：`compactor.py:135-143` 做了完整的兜底：

```python
try:
    response = await provider.chat(...)
except Exception:
    logger.exception("compactor: LLM call failed, skipping compaction")
    return None                          # 压缩失败 → 返回 None，不改变消息历史

summary_text = response.text.strip()
if not summary_text:
    logger.warning("compactor: LLM returned empty summary, skipping compaction")
    return None                          # 空摘要 → 返回 None，不改变消息历史
```

**压缩失败 → 不压缩，继续执行**。这是一种 "fail-open" 策略——宁可让上下文继续膨胀（最终可能超 token 限制），
也不能因为压缩失败而丢失消息历史。

---

## 高频追问：跨简历点的综合问题

### Q: 这个项目的最大技术挑战是什么？你怎么解决的？

**答**：最大挑战是 **Agent Loop 的鲁棒性**——在以下所有条件下都不能崩溃：

1. LLM API 瞬时故障（网络断开）
2. 工具执行超时或抛异常
3. LLM 陷入拒绝循环（反复尝试被拒操作）
4. 上下文无限增长
5. 用户中途断开 TUI 连接

每一层都有独立对策（见下表），且每个对策都是"优雅降级"而非"崩溃退出"：

| 失败场景 | 对策 | 降级行为 |
|----------|------|----------|
| LLM 网络故障 | 流式重试（最多 3 次，指数退避） | 3 次后标记 `llm_error`，不崩溃 |
| 工具超时 | `asyncio.wait_for` + ToolResult(is_error=True) | LLM 看到错误消息，换策略 |
| 工具异常 | 所有异常 catch → ToolResult(is_error=True) | 同上 |
| 拒绝循环 | DenialTracker 熔断 → 注入干预消息 | 给 LLM 第二次机会 |
| 上下文膨胀 | 水位检测 → 自动压缩 | 压缩失败 → 不压缩，继续运行 |
| 客户端断开 | fire-and-forget task | run 继续执行，重连后可恢复 |

### Q: 如果重新设计，你会改变什么？

**答**：三个"如果重来"：

1. **Config 系统**：手写 TOML 校验（`config.py` ~490 行）虽然错误信息友好，但扩展性差。
   会考虑用 pydantic-settings + 自定义 validator，在保持错误信息质量的同时减少代码量。

2. **工具并行执行**：当前串联执行工具（`for tc in tool_calls: await`）。对于无依赖的工具调用
   （如并行读取两个文件），可以并发执行以减少 wall-clock 时间。但需要处理失败隔离——一个工具超时不能影响另一个。

3. **Error 路径 `_send` 未保护**（`socket_server.py`）：早该在 `_handle_line` 最外层统一 try/except，
   而非仅在 success 路径保护。这是一个应该在 code review 中发现的低级遗漏。

### Q: 你做这个项目最大的收获是什么？

**答**：理解了一个定理：**Agent 系统的能力 = LLM 能力 × 工具广度 × 循环鲁棒性。**

- LLM 能力是外部给定的（选模型）
- 工具广度靠 MCP + 内置工具扩展
- **循环鲁棒性完全靠工程实现**——这是项目花时间最多的地方：重试、超时、熔断、压缩、权限、事件追踪

一个"demo 能跑"的 Agent 和一个"生产可部署"的 Agent，差距不在 LLM 调用那段代码（10 行），
而在所有异常路径的处理（200 行）。SztuCode 证明了这一点。
