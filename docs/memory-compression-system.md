# SztuCode 记忆与压缩系统

> 当前记忆实现位于 `packages/runtime-ts/src/memory.ts`、`packages/runtime-ts/src/session-store.ts` 和
> `packages/runtime-ts/src/run-manager.ts`，压缩实现位于 `packages/runtime-ts/src/context.ts`。本文第三层中
> 出现的 Python 类名、旧分支和旧环境变量仅作为历史设计记录，不定义当前 runtime。

## 概述

SztuCode 的 TypeScript runtime 使用三层结构：全局/项目静态记忆、会话版本化笔记和上下文压缩。

---

## 架构全景

```
┌─────────────────────────────────────────────────────────────────┐
│                      记忆与压缩三层架构                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  第一层：静态上下文记忆 (memory.ts)                                │
│    ~/.sztu/context.md  ──→  Global Context                      │
│    .sztu/context.md    ──→  Project Context                     │
│                                                                 │
│  第二层：会话笔记 (note_save 工具)                                │
│    note_save("事实")   ──→  notes.md  ──→  Session Notes        │
│                                                                 │
│  第三层：上下文压缩 (context.ts)                                  │
│    ├── 3a. 工具结果有界化              ← 每步调用前               │
│    └── 3b. 语义压缩                    ← LLM 驱动                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 第一层：静态上下文记忆

### 文件位置

| 文件 | 作用域 | 注入位置 |
|---|---|---|
| `~/.sztu/context.md` | 全局（跨项目） | system prompt 的 `Global Context` 段 |
| `<workspace>/.sztu/context.md` | 项目级 | system prompt 的 `Project Context` 段 |

### 加载流程

`RunManager` 在每次 run 开始前调用 `loadMemoryCatalog()`，同时读取全局、项目和当前 session 的
活跃笔记，形成该 run 的不可变快照。短文全文进入 system prompt；超过 2,000 字符的文档只注入
标题目录，并注册只读 `memory_read` 工具按查询或 offset 分页读取，每次最多 4,000 字符。

### 特点

- **文件级持久化**：内容跨 session 保持
- **渐进式注入**：短文内联，长文只披露索引
- **手动维护**：由用户编辑，非 agent 自动管理

---

## 第二层：会话笔记

### 核心工具：`note_save`

Agent 在 session run 中可通过 `note_save` 记录重要事实，并用 `note_update` 替代已经过时的事实。
两者都是 `workspace_write` 权限工具；`note_save` 返回稳定的 `note-...` ID，供后续更新引用。

### 数据流

```
Agent 调用 note_save("某关键发现")
  │
  ▼
SessionStore.appendNote()
  │  写入 notes.md:
  │  ## Note (2026-08-04T..., run-xxx)
  │  某关键发现
  │
  ▼
下一次 run 启动:
  │  SessionStore.readNotes() → 只读回 status: active 的版本
  │  注入 system prompt "Session memory" 段
  │  长笔记通过 memory_read 按需披露
```

### Session 目录结构

```
~/.sztu/sessions/
└── sess-<id>/
    ├── meta.json              # 会话元数据
    ├── thread.jsonl           # 完整对话消息 (NDJSON)
    ├── notes.md               # agent 记录的持久笔记
    └── runs/
        └── <run-id>.jsonl      # 该 run 的事件流
```

---

## 第三层：上下文压缩

### 3a. 工具结果截断 (`compact/budget.py`)

#### 触发位置

- **每步 LLM 调用前**：`AgentLoop.run()` 第 95-99 行
- **读取历史时**：`SessionStore.read_messages()` 第 143-148 行

#### 截断逻辑

```python
TOOL_RESULT_LIMIT = 8_000   # 超过此长度的 tool_result 触发截断
TOOL_RESULT_KEEP   = 4_000   # 保留前 N 个字符
```

```
原始: [tool_result] <30000 chars>
  ↓
截断: [tool_result] <前 4000 chars> [... 26000 chars omitted. Full output in run events.]
```

#### 特点

- **纯内存操作**：不修改磁盘文件
- **仅截断 tool_result**：text block 和 assistant 消息不受影响
- **无上下文损失**：完整内容仍在 `events.jsonl` 中可追溯
- **可配置**：通过 TOML 或环境变量调整限制值

### 3b. 语义压缩 (`compact/compactor.py`)

#### 触发方式

| 路径 | 触发条件 | 代码位置 |
|---|---|---|
| **自动** | `context_pct >= auto_threshold`（默认 0.0=禁用） | `loop.py:195-210` |
| **手动** | RPC `session.compact` 调用 | `manager.py:213-238` |

> **注意**：`CompactionConfig.auto_threshold` 默认为 `0.0`，自动压缩默认不工作。需设置 `SZTU_COMPACT_THRESHOLD=0.8` 启用。

#### 自动触发计算

```python
# loop.py:201-208
trigger_pct = response.usage.context_pct
if response.usage.input_tokens > 0 and added_estimate:
    # 修正：考虑刚追加的工具结果也会消耗上下文
    trigger_pct = (
        response.usage.context_pct
        * (response.usage.input_tokens + added_estimate)
        / response.usage.input_tokens
    )
if trigger_pct >= self._compact_threshold:
    await self._compactor.compact(context, self._provider)
```

#### 压缩流程

```
1. notify_compacting()
   └── 发布 ContextCompactingEvent → TUI 渲染"压缩中..."

2. compact_messages()
   └── 将完整消息历史序列化为文本
   └── 附加 _COMPACT_PROMPT（6 段要求）
   └── 调用 LLM 生成摘要

3. 质量校验（4 道关卡）
   ├── 截断检查: stop_reason != "max_tokens"
   ├── 格式检查: 必须含 "## 1. Original Goal" 且 ≥ 2 个 "##" 段
   ├── 收益检查: summary_tokens < original_estimate
   └── 非空检查: summary_text 不为空白

4. 替换上下文
   └── context.messages = [
         {role: user, content: 续接消息},
         {role: assistant, content: "Understood, I'll continue from this summary."}
       ]
   └── context.compacted = True

5. 写入摘要文件
   └── summary_<timestamp>_<uuid>.md → session 目录

6. 持久化
   └── 原 thread.jsonl → thread_<ts>_<uuid>.jsonl.bak（备份）
   └── 新 thread.jsonl ← 压缩后消息对
   └── 写入失败 → 自动回滚（恢复 bak）

7. record_compaction()
   └── 发布 ContextCompactedEvent（含 original_tokens / summary_tokens）
```

#### 压缩提示词

LLM 被要求生成 6 个固定段落的摘要：

```markdown
## 1. Original Goal
用户要求 agent 完成的目标，一句话。

## 2. Completed Steps
已完成的步骤。具体列出：文件路径、执行的命令、做出的决策。

## 3. Key Constraints & Discoveries
运行中发现的影响后续决策的事实（API 限制、文件格式、用户偏好等）。

## 4. Current File State
每个创建或修改的文件：路径 + 一行描述其当前状态。

## 5. Remaining TODOs
完成原始目标仍需要做的事情，有序列表。

## 6. Critical Data
下一个 LLM 必须逐字知道的值：ID、token、错误信息、配置值。
```

#### 续接消息

压缩后，对话历史被替换为：

```
[user]
This session is being continued from a previous conversation that ran out of
context. The summary below covers the earlier portion of the conversation.

Summary:
<6 段摘要内容>

Continue the conversation from where it left off without asking the user any
further questions. Resume directly — do not acknowledge the summary, do not
recap what was happening, and do not preface with continuation text.

[assistant]
Understood, I'll continue from this summary.
```

#### 压缩持久化

```python
# store.py:173-191
def write_compacted(self, sid: str, messages: list[dict[str, Any]]) -> None:
    # 1. 备份原 thread.jsonl
    bak = session_dir / f"thread_{ts}_{uuid}.jsonl.bak"
    path.rename(bak)

    # 2. 写入压缩后消息
    with path.open("w") as f:
        for msg in messages:
            f.write(json.dumps({"ts": _now(), "role": ..., "content": ...}))

    # 3. 写入失败 → 回滚
    except Exception:
        if not path.exists() and bak.exists():
            bak.rename(path)
        raise
```

---

## 完整数据流

```
用户输入 "帮我修复这个 bug"
  │
  ▼
SessionManager.send_message()
  │  store.append_message("user", "帮我修复这个 bug")  → thread.jsonl
  │
  ▼
AgentRunner.run_and_capture()
  │  加载三层上下文:
  │    history  = store.read_messages()        → 完整对话历史
  │    notes    = store.read_notes()           → session 笔记
  │    global   = load_context_file(~/.sztu/context.md)
  │    project  = load_context_file(.sztu/context.md)
  │
  │  构建 ExecutionContext:
  │    prefill_messages = history     → context.messages 初始化
  │    session_notes    = notes       → 注入 system prompt
  │    global_context   = global      → 注入 system prompt
  │    project_context  = project     → 注入 system prompt
  │    base_system_prompt             → 分层提示词（静态规则 + git + CLAUDE.md）
  │
  ▼
AgentLoop.run() — 每步循环:
  │
  │  Step 1..N:
  │
  │  [plan] 调用 LLM
  │    1. truncate_tool_results(messages)    ← 3a. 工具结果截断
  │    2. provider.chat(
  │         messages  = 截断后的消息历史
  │         system    = 分层 system prompt   ← 第一、二层记忆在此
  │         tools     = 工具 schemas
  │       )
  │
  │  [act] 执行工具
  │    context.add_assistant_message(blocks)
  │    for tool_call in response.tool_calls:
  │        result = await invoke_tool(...)
  │        context.add_tool_result(id, content)  ← 追加到 messages
  │
  │  [check] 压缩检查
  │    if context_pct >= compact_threshold:      ← 3b. 语义压缩
  │        await compactor.compact(context, provider)
  │          ├── LLM 生成摘要
  │          ├── 4 道质量关卡
  │          ├── 替换 context.messages ← [user: 续接, assistant: ack]
  │          ├── 写入 summary_*.md
  │          └── 发布 context.compacted 事件
  │
  │  [check] 终止条件
  │    if stop_reason == "end_turn" → context.mark_success()
  │    if step >= max_steps         → context.mark_failed("exceeded_max_steps")
  │
  ▼
Runner 收尾:
  │
  │  if context.compacted:
  │      store.write_compacted(session_id, context.messages)
  │      └── 原 thread.jsonl 备份，新写压缩消息对
  │  else:
  │      store.append_messages(session_id, 新增消息, run_id)
  │      └── 追加本轮新消息到 thread.jsonl
  │
  ▼
完成
```

---

## 关键配置

### TOML 配置

```toml
[compaction]
auto_threshold = 0.8       # 自动压缩阈值（0.0 = 禁用）
tool_result_limit = 8000   # 工具结果截断长度阈值
tool_result_keep = 4000    # 截断时保留的前缀长度
```

### 环境变量

```bash
SZTU_COMPACT_THRESHOLD=0.8     # 同 auto_threshold
SZTU_COMPACT_TOOL_LIMIT=8000   # 同 tool_result_limit
SZTU_COMPACT_TOOL_KEEP=4000    # 同 tool_result_keep
```

---

## 测试覆盖

### 压缩测试 (`tests/unit/test_compactor.py`) — 8 个用例

| 测试 | 验证点 |
|---|---|
| `test_compact_messages_calls_provider` | provider.chat 被调用，tool_schemas=[] |
| `test_compact_messages_returns_summary` | 返回的 summary_text 等于 provider 响应 |
| `test_compact_replaces_context_messages` | messages 替换为 2 条消息对，compacted=True |
| `test_compact_writes_summary_file` | session 目录产生 summary_*.md 文件 |
| `test_compact_publishes_event` | 发布 context.compacted 事件 |
| `test_compact_failure_preserves_context` | LLM 异常时 messages 保持不变 |
| `test_compact_messages_rejects_no_benefit` | 摘要 tokens 不小于原始时返回 None |
| `test_compact_messages_rejects_truncated_summary` | max_tokens 截断的摘要被拒绝 |

### 预算测试 (`tests/unit/test_budget.py`) — 6 个用例

| 测试 | 验证点 |
|---|---|
| `test_short_tool_result_untouched` | 7999 字符不触发截断 |
| `test_long_tool_result_truncated` | 10000 字符被截断并标记 |
| `test_exact_limit_untouched` | 恰好 8000 字符不截断 |
| `test_non_tool_result_block_untouched` | text block 不受影响 |
| `test_multiple_tool_results_independent` | 多个 tool_result 各自独立判断 |
| `test_assistant_message_untouched` | assistant 消息不截断 |

---

## 已知局限

1. **自动压缩默认禁用**：`auto_threshold = 0.0`，需用户显式配置
2. **Token 估算粗糙**：使用 `len(text) // 4` 字符估算，非真实 tokenizer
3. **仅压缩消息历史**：system prompt、tool schemas、thinking blocks 不参与压缩
4. **全量替换不可逆**：压缩后原始历史仅在 bak 文件中保留
5. **notes.md 不更新**：摘要独立存储，不与 notes 合并
6. **无渐进式压缩**：只有一刀切的语义压缩，缺少滑动窗口、重要性评分等中间策略
7. **子代理隔绝对话**：子代理创建时使用独立的 `ExecutionContext`，不继承父代理的压缩摘要
8. **无结构化记忆提取**：缺少从对话中自动提取实体/关系/决策的能力
