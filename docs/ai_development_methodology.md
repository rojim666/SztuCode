# AI 辅助开发方法论 —— 基于 SztuCode 项目的实践总结

> 本文以 SztuCode 项目的真实代码和设计决策为证据基础，系统回答：
> AI 在哪些开发环节有效、如何判断 AI 代码是否可合入、如何发现 AI 的错误、
> 多方案时如何选型、以及如何保持不依赖 AI 的独立能力。

---

## 一、完整证据链：`SocketServer` 并发模型 —— "问题 → 方案 → 取舍 → 数据 → 失败 → 改进"

### 问题

SztuCode 的 daemon 是一个 TCP 服务器。当客户端发送 `session.send_message` 启动一个 agent run 时，
这个 run 可能持续数分钟（LLM 多轮对话 + 工具调用）。如果 read loop 是单线程阻塞等待 handler 返回，
那么在 run 执行期间，客户端发出的其他命令（如 `permission.respond` 审批用户操作、
`event.subscribe` 订阅事件）将全部排队等待，导致 TUI 界面假死。

**这是一个典型的"长任务阻塞短任务"并发问题。**

### 方案

在 `socket_server.py:137-139` 中，每条请求被拆成独立的 fire-and-forget task：

```python
# 每条命令独立作为 task 执行，避免长时间运行的 handler（如 session.send_message）
# 阻塞读循环，使 permission.respond 等并发命令能被及时处理
asyncio.create_task(self._handle_line(line, writer))
```

每个 `_handle_line` task 内部通过 `ContextVar(_writer_var)` 获取当前连接的 writer，
实现"同一连接上多个并发请求各自持有 writer 引用"而不需要传递参数。

### 取舍

| 维度 | 选择 | 代价 |
|------|------|------|
| **响应排序** | 不保证 request-response 顺序 | 客户端必须用 `id` 字段做关联（JSON-RPC 规范保证了这一点） |
| **任务生命周期** | fire-and-forget，不追踪 task 句柄 | 客户端断开后 handler task 继续跑到完成；无法集中 cancel |
| **取消语义** | handler task 不随 writer 关闭而取消 | agent run 在客户端断开后仍继续执行——这是有意为之（"继续完成"语义） |
| **Writer 安全** | 只有 success 路径的 `_send` 有 try/except 保护 | error 路径的 `_send` 若遇断连会抛出未捕获异常，变成 "unhandled task exception" |

**为什么取了这些取舍？** 因为 SztuCode 的会话模型是"chat 模式"——用户在 TUI 中发起对话后可以关闭窗口，
agent run 应继续执行并在下次重连时恢复。fire-and-forget + 不随 writer 关闭而取消 恰好实现了这个语义。

### 数据（验证）

这一设计通过两类测试间接验证：

1. **集成测试** `test_s5_permission_flow.py`：在 agent run 进行中发送 `permission.respond`，
   验证并发命令的响应时间（未因 run 阻塞而超时）。
2. **单元测试** `test_socket_server.py::test_broadcaster_unsubscribe_called_on_disconnect`：
   验证客户端断开后 broadcaster 正确清理订阅（说明 disconnect 路径是完整的）。

实测证据：TUI 在 agent 执行长时间 bash 命令时仍能实时渲染 `step.*` 事件流，
说明 read loop 未被阻塞。

### 失败（已发现的缺陷）

通过代码审查发现了 error-path `_send` 无异常保护的 bug（见 `socket_server.py:180-191`）：

```python
except HandlerError as e:
    await self._send(writer, make_error(req.id, e.code, str(e), e.data))  # 未保护
    return
except ValidationError as e:
    await self._send(writer, make_error(req.id, INVALID_REQUEST, "Invalid params", str(e)))  # 未保护
    return
except Exception as e:
    logger.exception("handler %s raised: %s", req.method, e)
    await self._send(writer, make_error(req.id, INTERNAL_ERROR, "Internal error"))  # 未保护
    return
```

而 success 路径（同文件 195 行）**有**保护：

```python
try:
    await self._send(writer, JsonRpcSuccess(id=req.id, result=result_data))
except (ConnectionResetError, BrokenPipeError, OSError):
    logger.debug("client disconnected before response for %s", req.method)
```

这是一个真实的缺陷：当客户端在 handler 抛出异常之后、`_send` error 响应之前断开，
error 路径的 `_send` 会因 `ConnectionResetError` 而使整个 task 崩溃，
产生 asyncio "Task exception was never retrieved" 警告。

### 改进

修复方案：将 try/except 保护提升到 `_handle_line` 的最外层，
统一保护 success 和 error 两条路径的 `_send` 调用。这处修改的影响范围很小（仅 socket_server.py），
但消除了 asyncio 未处理异常的风险。

---

## 二、AI 给出错误答案的发现与修正案例

### 场景：`INVALID_PARAMS` 错误码的"幽灵常量"

#### 问题

AI（模拟场景）在审查 `bus/envelope.py` 时建议：

> "既然定义了 `INVALID_PARAMS = -32602`，你应该在 `socket_server.py` 中用这个常量替换 `INVALID_REQUEST`，
> 让 Pydantic 参数校验失败返回 -32602 而不是 -32600，这样更符合 JSON-RPC 2.0 规范。"

这个建议听起来合理——JSON-RPC 规范确实区分了 `-32600`（Invalid Request）和 `-32602`（Invalid params）。

#### 发现过程

我没有直接采纳，而是用 `grep` 做了实际数据流追踪：

```bash
# 1. 查找 INVALID_PARAMS 的所有引用
grep -rn "INVALID_PARAMS" src/

# 2. 查找错误码 -32602 的所有实际发送点
grep -rn "\-32602" src/

# 3. 查找 HandlerError 的所有抛出点
grep -rn "HandlerError" src/
```

结果：

| 搜索结果 | 发现 |
|----------|------|
| `INVALID_PARAMS` | 只在 `envelope.py` 定义和 `bus/__init__.py` 导出，**没有任何消费方使用它** |
| `-32602` 字面量 | 出现在 `app.py` 的 8 处 `HandlerError(-32602, ...)` 中——全部是**手写的字面量**，没有引用常量 |
| `INVALID_REQUEST` | 在 `socket_server.py` 中被引用，用于请求结构校验失败（-32600） |

#### 分析结论

AI 的建议在**规范层面**是正确的——参数校验失败应该返回 -32602。
但它在**代码层面**是错误的，原因是：

1. **Handler params 校验**（`socket_server.py:182-186`）用的是 `XxxCommand.model_validate`，
   这个 ValidationError 被 catch 后发 `INVALID_REQUEST`（-32600）而非 `-32602`。
2. **Domain 校验**（`app.py` 中 8 处手动 `ValueError → HandlerError(-32602, ...)`）
   用的是硬编码的 `-32602`，完全绕过了常量定义。
3. 如果按 AI 建议"用 INVALID_PARAMS 替换 INVALID_REQUEST"，
   **JSON-RPC 请求本身的格式错误和 handler 参数校验错误将无法区分**，
   client 端的错误恢复逻辑会混乱。

#### 正确做法

不应简单替换，而应该：

1. 在 `socket_server.py` 中区分两种 ValidationError：
   - `req` 本身的 `model_validate` 失败 → `INVALID_REQUEST`（-32600）
   - handler 内部的 `params` 校验失败 → `INVALID_PARAMS`（-32602）
2. 让 `app.py` 中的所有 `HandlerError(-32602, ...)` 引用常量而非字面量

这才是符合 JSON-RPC 规范且保持错误类型语义正确的做法。

#### 教训

- AI 的建议在**抽象层面**往往是对的（应该区分错误类型）
- 但在**具体实现层面**，AI 不了解代码中已有的错误码分发路径，无法判断建议的实际影响
- **用 grep/静态分析做数据流追踪，是验证 AI 建议的最有效手段之一**

---

## 三、多方案选择：`Config` 系统的设计取舍

SztuCode 的配置系统（`config.py`）面临一个经典选择：

### 方案 A：用 Pydantic 做配置模型 + 自动校验

**优点**：代码少，类型安全，schema 自动生成文档
**缺点**：错误信息是 Pydantic 格式的（"1 validation error for SztuConfig..."），对非 Python 用户不友好；TOML 中的 typo key 可能被 silently ignore（Pydantic 默认 ignore extra）

### 方案 B：手写 dataclass + 逐字段校验（实际采用）

**优点**：每个字段的错误信息完全可控、中文友好、typo key 检测（unknown key → SystemExit）
**缺点**：`_apply_toml` 和 `_apply_env` 两个函数加起来约 400 行，代码冗长

### 选择依据

看实际代码（`config.py:173-176`）：

```python
def _apply_toml(config: SztuConfig, data: dict[str, Any]) -> None:
    unknown = set(data.keys()) - {"core", "logging", "agent", "llm", "trace", "permission", "compaction", "mcp"}
    if unknown:
        raise SystemExit(f"Unknown top-level config keys: {', '.join(sorted(unknown))}")
```

这个选择的核心依据是 **fail-fast with actionable error messages**。

SztuCode 的 daemon 是一个需要自行配置的后台服务。用户写 `[core]` 写成了 `[Core]`（大小写错误）
——Pydantic 方案会 silent ignore，用户困惑"为什么我的 host 没生效"；
手写方案直接退出并提示 `Unknown top-level config keys: Core`，5 秒定位问题。

**这恰好符合项目 CLAUDE.md 中"Config file is silently skipped if absent; unknown keys cause a hard exit"的设计意图。**

手写校验的行数虽然多，但代码结构是机械的重复模式——每个 section 都是"检查 unknown keys → 逐字段校验类型 → setattr"。
这种代码 AI 生成质量很高（模式单一），人工审查也很容易（扫一眼类型检查即可）。

**结论：选择方案 B 不是因为它"更好"，而是因为它符合这个项目的用户体验约束（非 Python 用户 + 需要明确错误提示）。**
如果这是一个内部微服务的 Python SDK，我可能选方案 A。

---

## 四、独立解释核心代码：`AgentLoop.run()` 逐行分析

以下是 `loop.py:52-172` 的"plan→act→observe"主循环，我将逐段解释其设计意图。

### Phase 1: 熔断干预（line 59-82）

```python
if self._denial_tracker is not None and self._denial_tracker.should_intervene():
    msg = self._denial_tracker.intervention_message()
    context.messages.append({"role": "user", "content": msg})
```

**设计意图**：当 LLM 连续多次尝试执行被用户拒绝的工具时（如反复尝试 `rm -rf /`），
不直接终止 run，而是注入一条干预消息强制 LLM 换策略。这是一种**软熔断**：给 LLM 第二次机会，
但不让它无限重试。

`DenialInterventionEvent` 的发布（line 65-81）确保 TUI 能渲染"熔断已触发"的视觉提示。

### Phase 2: Plan（line 85-98）

```python
response = await self._provider.chat(
    messages=context.messages,
    tool_schemas=self._registry.tool_schemas(),
    ...
)
```

**设计意图**：每次迭代都把**完整**消息历史发给 LLM。这是"stateless loop"模型——
LLM 不持有任何会话状态，所有上下文都在 `context.messages` 中。
这使得 run 可以被完整回放（replay）、可以被中断后恢复（只需重放消息历史）。

API 错误（除了 CancelledError）标记为 `"llm_error"` 并退出循环——不做重试，
因为 LLM API 错误通常是凭证/配额问题，重试无意义。

### Phase 3: Observe + Act（line 109-148）

```python
for tool_call in response.tool_calls:
    tool_call.input = self._registry.enrich_tool_input(tool_call.name, tool_call.input)
```

先补齐工具调用的时间线标题（如 bash 命令没有 description 时自动生成中文描述），
这样事件流中的 `ToolCallStartedEvent` 就携带人类可读的标题。

```python
if response.stop_reason == "tool_use":
    for tc in response.tool_calls:
        result = await invoke_tool(...)
        context.add_tool_result(tc.id, result.content, is_error=result.is_error)
```

工具调用串联执行（非并行）。这是一个有意为之的简化——并行工具调用在 LLM 场景下
失败率很高（后续工具依赖前一个工具的输出），且错误恢复更复杂。

`max_tokens` 中途截断的处理（line 140-149）是一个**防御性边界条件**：
当 LLM 输出在生成 tool_call JSON 过程中被截断时，不导致消息历史不平衡（assistant 有 tool_use 而缺少对应的 tool_result），
而是注入合成错误结果，让对话可以继续。

### Phase 4: 终止判断（line 151-156）

```python
if response.stop_reason == "end_turn":
    context.result = response.text or ""
    context.mark_success()
elif context.step >= context.max_steps:
    context.mark_failed("exceeded_max_steps")
```

**end_turn 优先于 max_steps** 的判断顺序（先检查 end_turn 再检查 max_steps）是有意为之：
如果 LLM 在最后一步刚好完成任务（end_turn），不应标记为失败。

### Phase 5: 自动压缩（line 160-168）

```python
if (
    not context.is_done()
    and response.stop_reason == "tool_use"
    and self._compactor is not None
    and self._compact_threshold > 0
    and response.usage is not None
    and response.usage.context_pct >= self._compact_threshold
):
    await self._compactor.compact(context, self._provider)
```

只有在"run 还将继续"（not is_done + stop_reason == tool_use）且"上下文使用率超过阈值"时才触发压缩。
默认 `compact_threshold = 0.0`（禁用），只有用户显式配置后才启用。
这是保守的默认值——自动压缩有信息丢失风险，不如让用户手动 `/compact`。

---

## 五、总结：AI 辅助开发的方法论

### 1. AI 适用的环节

| 环节 | 为什么适合 | SztuCode 中的例子 |
|------|------------|-------------------|
| 样板代码生成 | 模式固定，AI 产出接近手写 | `config.py` 中 8 个 section 的逐字段校验（重复模式） |
| 代码审查 | AI 扫 diff 找低级错误比人眼快 | 发现 `socket_server.py` error-path `_send` 无异常保护 |
| 测试用例生成 | AI 擅长穷举边界路径 | `test_tool_retry.py` 覆盖了指数退避的各种失败组合 |
| 文档/注释生成 | 从代码反向生成说明 | `enrich_tool_input` 自动补齐时间线标题（替代手动写） |

### 2. AI 不适用的环节

| 环节 | 为什么不适合 | 替代做法 |
|------|-------------|----------|
| 架构决策 | AI 不了解团队、运维、roadmap | 手写 trade-off 分析，参考项目现有模式 |
| 安全敏感代码 | AI 可能生成"看着对但可绕过"的代码 | 必须逐行审查 + OWASP 对照 |
| 性能关键路径 | 瓶颈需要 profiling，AI 只能猜 | 先 profiling，再针对性优化 |
| 跨层一致性 | AI 不追踪数据流 | 用 grep/dataflow 分析验证 AI 建议 |

### 3. 保持独立能力的核心原则

1. **你能不能在空白文件里从零写出核心逻辑？** — 以 `loop.py` 为例，你需要理解 plan→act→observe 循环的每一步语义，而不仅仅是"知道调用 chat API"。

2. **你能不能读懂 AI 生成的代码并判断它对不对？** — 以 `INVALID_PARAMS` 为例，AI 的建议在规范层面正确但在代码层面错误。你需要用 grep 验证数据流，而非盲信建议。

3. **你能不能在没有 AI 提示的情况下定位到 bug 所在的模块？** — 以 `socket_server.py` error-path bug 为例，线索是"asyncio unhandled task exception"日志 + 异常堆栈指向 `_handle_line`。你需要能独立追踪。

**底线：AI 是杠杆，你对结果负全责。AI 生成的代码，审查标准应该比手写代码更严，而不是更松。**
