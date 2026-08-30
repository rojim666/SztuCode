# TypeScript Runtime Agent 能力评审（滚动版）

[返回文档中心](../README.md) · [第五版快照](agent-capability-review-v5.md) · [第二版快照](agent-capability-review-v2.md) · [第三版快照](agent-capability-review-v3.md)

本文是对 `packages/runtime-ts` 的持续能力评审，随代码演进滚动更新。当前为**第七轮**
（2026-08-30，基线：v6 之后的全量重读）。本轮方法升级：对 runtime 全部 44 个源文件做
第二次逐行审查（含 providers、编排、持久化、权限、MCP 全链路），并做故障路径推演。
v6 的结论是"机制完整但性能裸奔"；本轮的回答更尖锐——**除了性能裸奔，还有可靠性漏风**：
一批"看起来已经做好"的防线（重试、缓存、超时、权限提示）在细读后发现并未真正生效。
没有真实基准数据的项目不作产品成绩推断，本文所有分数仍是静态代码审计判断。

## 1. 能力评分卡（v5 → v6 → v7）

| 能力维度 | v5 | v6 | v7 | 判词 |
| --- | ---: | ---: | ---: | --- |
| 上下文管理 | 80 | 78 | **74** | 机制最完整（增量计数/后台压缩/熔断/微压缩），但 token 计数编码失配、+4 开销双重累加导致系统性高估、摘要校验过脆、溢出无应急通道 |
| 工具系统 | 78 | 74 | **70** | 行号 Read/锚定 Edit/MultiEdit 成立；Web 能力整体缺席、无工具级超时、并行写同文件无锁、glob 静默截断 |
| 权限与安全 | 71 | 72 | **72** | 参数级 glob + per-workspace + MCP 权限路径闭环；`always_allow` 存字面量使"始终允许"退化为"允许这一条"，危险命令无语义级规则 |
| 韧性 | 65 | 66 | **62** | 重试看似完备实则三个漏洞（529 不重试/超时不重试/耗尽标记丢失）；上下文溢出无应急通道；交互提问可永久挂起 |
| 编排能力 | 74 | 75 | **72** | DAG + HandoffArtifact 校验成立；波次调度气泡、`time_budget_s<=0` 永不超时、子代理同步阻塞、递归深度锁死 1 层 |
| 可观测性 | 83 | 83 | **80** | 事件总线 + telemetry span + TaskCanvas + durable replay；运行级 O(n²) 序列化三源叠加、trace 无轮转、批处理承诺是死代码 |
| 记忆系统 | 59 | 60 | **60** | 三层 catalog + 渐进披露 + notes 版本链；检索仍是子串匹配、无巩固管道、目录在 run 内冻结 |
| 扩展生态 | 62 | 63 | **60** | Skills 渐进披露 + MCP deadline/取消/权限成立；MCP stderr 死锁隐患、通知静默丢弃、ProviderCompat 全链路死代码 |
| 成本效率 | — | 45 | **40** | v6 八项之上再叠加：O(n²) 序列化三源、cache 负优化三条、推理模型参数硬伤、压缩成本不入账 |
| **综合** | 68 | 68 | **66** | 9 维均值 66；v6 的"性能裸奔"之下还有一层"防线失效"——分数下调不是苛刻，是证据密度提高了 |

v6→v7 的下调全部来自**第二次逐行审查的证据**，不是印象分。规律是：凡是有"声明/字段/
注释承诺"但"实现未接线"的地方（`background` 参数、`pendingTrace` 批处理字段、
`ProviderCompat`、`cautious` 提示段、工具级 `timeoutMs` 接口），v6 按"机制存在"计分，
v7 按"实际生效"计分。这是本轮评审的总方法论：**能力数值必须按运行时真实行为标定，
而不是按接口声明标定**。

## 2. 第七轮复审：性能与可靠性障碍深挖

本轮新发现全部有代码定位，按四个主题分组。v6 已列八项（§2.1-2.8 对应旧编号 #1-#8）
不再重复，仅在其上叠加。

### 主题 A：可靠性缺口——"看似设防，实则漏风"（本轮最高优先级）

**A1. 重试白名单缺 529、超时中止永不重试、耗尽标记会丢失**
（[errors.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/errors.ts#L22)、[errors.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/errors.ts#L40-L44)、[configurable.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/configurable.ts#L26-L33)）

- 可重试状态白名单 `[408,425,429,500,502,503,504]` 不含 **529**（Anthropic
  overloaded_error 官方要求重试）——过载直接失败并消耗主循环失败预算。
- 总超时经 `controller.abort()` 触发（[anthropic.ts:23](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/anthropic.ts#L23)），
  抛出的 AbortError 消息不含 "timeout" 字样，`retryableProviderError` 的消息正则判为
  不可重试——**最该重试的场景（慢/挂起）恰好永不重试**。
- 重试循环封顶 `min(10, max_retries)` 但耗尽判定用原始 `max_retries`；当
  `max_retries > 10` 时循环在 attempt=10 退出且**不带 `retryExhausted` 标记**，
  `agent-loop.ts:238` 的防放大保护失效，错误被当普通失败回注对话。

**A2. 上下文溢出（400）无应急通道**
（[agent-loop.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L239-L246)）

400 不可重试，主循环只做"错误回注让模型继续"——上下文已经超限，回注只会再次超限，
连续失败 3 次（`maxLlmFailures`）后整个 run 终止。**没有"检测到 context_length 类
错误 → 立即硬丢弃/紧急压缩"的逃生门**。这是成功率维度最便宜也最痛的补丁。

**A3. 超时语义全链路错误**
（[anthropic.ts:23](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/anthropic.ts#L23)、[openai.ts:105](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/openai.ts#L105)、[workflow.ts:136-138](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/workflow.ts#L136-L138)、[questions.ts:8](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/questions.ts)）

- Provider 只有一个覆盖**整个流式过程**的总超时（默认 120s，定时器在 `finally` 才清除）：
  持续输出超 120s 的长任务流被拦腰斩断；服务端挂起但连接不断时也只能干等。**应改为
  首字节超时 + 空闲（chunk 间隔）超时**，而不是全局墙钟。
- `time_budget_s <= 0` 时 workflow 的 timeout 是 `new Promise(() => {})`——**永不超时**；
  叠加子代理同步阻塞，一个挂死的子任务可无限期卡住整个父 run。
- `ask_user_question` 的 Promise 只能由用户应答或 run 取消解决，前端掉线即**永久挂起**，
  无单问题超时。
- 墙钟预算只在步头检查（[agent-loop.ts:179](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L179)），
  单个长工具可任意超出。

**A4. 静默失败三例——"错误自信"的源头**

1. `glob_search` 满 200 条后静默停止，无任何截断标记
   （[tools.ts:317-322](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L313-L322)）——与 `grep_search` 的
   显式标记不一致，模型以为搜完了。
2. 重复 `tool_call_id` 的结果互相覆盖、回注时静默跳过，造成 tool_use 无配对结果
   （[agent-loop.ts:340](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L340)、[agent-loop.ts:484-485](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L484-L485)）。
3. 孤儿 `tool` 消息在 Anthropic 方向被静默丢弃，会话拼接/恢复场景下内容无声消失
   （[anthropic.ts:51](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/anthropic.ts#L51)）。

**A5. 防线"声明了但没接线"清单**（接口存在 ≠ 能力存在）

| 声明 | 现实 | 位置 |
| --- | --- | --- |
| bash `background` 参数 | schema 注明 "not yet supported"，实现完全不消费 | [tools.ts:411](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L411) |
| EventBus 批处理 | `pendingTrace`/`traceBatchScheduled` 声明后零使用 | [event-bus.ts:15-16](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/event-bus.ts#L15-L16) |
| `ProviderCompat`（网关差异修正） | 定义与消费点齐全，唯一构造点从不传 `compat` | [openai.ts:10-11](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/openai.ts#L10-L11)、configurable.ts:22-23 |
| 工具级 `timeoutMs` 接口 | 机制存在于执行层，但无任何工具设置 | tools.ts:29 |
| `cautious` 谨慎操作提示段 | 依赖 `taskText`，两个调用方都未传，永不注入 | [prompt-harness.ts:29](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/prompt-harness.ts#L29) |
| `READ_ONLY_COMMANDS`/`DANGEROUS_PATH_PATTERNS` | 定义后无调用点，历史残留 | tools.ts:127-145 |
| TaskCanvas `export()` | 无调用方，画布数据从未持久化 | task-canvas.ts:212-223 |

### 主题 B：成本效率——v6 八项之上的新增量

**B1. 运行级 O(n²) 序列化的第三个源头**
（[trace.ts:15](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/trace.ts#L15)、[agent-loop.ts:267](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L267)、[event-bus.ts:35](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/event-bus.ts#L35)）

v6 只点了 EventBus 逐事件 `appendFile`。本轮确认这是**三源叠加**：
`TracingProvider` 每步把完整 messages + 全部 tool schemas 落盘（`includePayload` 默认
true）；checkpoint 每步把整个消息数组浅拷贝并全量重写 `context.json` + `.bak` 复制
（[session-store.ts:70](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/session-store.ts#L70)）；EventBus 逐事件追加。
再叠加 TaskCanvas 每步全量渲染 Mermaid 进事件流（第 k 步输出 O(k)）、`summary_tokens`
每步把所有历史摘要重新分词（[agent-loop.ts:258](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L258)）——
**长运行的磁盘写入量与 CPU 是步数的平方级**。另：`session.history` RPC 每次都全量读入
并逐行解析所有 `runs/*.jsonl`（session-store.ts:82-86），会话越长每次历史请求越慢。

**B2. Prompt cache 的三条负优化**（v6 只说了"单层"，漏了这三条）

1. **OpenAI 风格自动前缀缓存被首条动态 user 消息破坏**：git 快照 + memory 被放在
   历史最前的 user 消息（[run-manager.ts:103-105](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/run-manager.ts#L103-L105)）。
   OpenAI 自动前缀缓存包含消息前缀，该消息每次运行都变——除 system+tools 外的前缀
   永远命中不了。（Anthropic 侧已正确地把它们移出 system，见亮点节。）
2. **兜底路径丢失缓存配置**：`providerFromEnvironment`（configurable.ts:42-50）构造的
   provider 不带 `cacheControl`——评测与无配置场景**全程无缓存**。
3. **Responses API 携带非法 `cache_control`**：responses 格式的 tools 定义保留了
   chat 路径生成的 `cache_control` 字段（[openai.ts:137](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/openai.ts#L137)），
   严格网关可能直接拒绝。

**B3. 推理模型兼容性硬伤**
（[openai.ts:137](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/openai.ts#L137)、[anthropic.ts:27](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/anthropic.ts#L27)）

- chat completions 用 `max_tokens` 而非 `max_completion_tokens`：o1/o3/gpt-5 类推理模型
  拒绝 `max_tokens`（且常拒绝 `temperature`）——推理模型在 OpenAI 兼容路径上基本不可用。
- Anthropic thinking 参数发送 `thinking: { type: "adaptive" }` + `output_config`，**不是
  官方 Messages API 形状**（官方为 `thinking: { type: "enabled", budget_tokens }`），
  可能被 400 拒绝或静默忽略——推理能力实际不可靠。
- 跨供应商切换时推理上下文丢失：thinking 块归一化到 OpenAI 时被丢弃，
  `reasoning_content` 发往 Anthropic 时不携带。
- 压缩摘要输入把 thinking 块文本一并计入（[context.ts:92](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/context.ts#L92)），
  浪费摘要调用的输入预算。

**B4. 成本核算系统性低估**：压缩调用的 `response.usage` 只用于摘要校验，从不累加进
运行 `usage`（context.ts:267）；内置模型目录为空（`BUILTIN_PROFILES = []`，
[model-profiles.ts:11](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/model-profiles.ts#L11)），
默认 `context_window: 128_000` 一刀切，无 tokenizer/缓存/多模态能力字段——报表里的
成本与窗口都不是真值。

### 主题 C：工具系统——与顶级产品的能力面对比

**C1. 工具面缺口清单**（对照 Claude Code 逐项核对）

| 能力 | 顶级产品 | 本项目 |
| --- | --- | --- |
| Web 获取/搜索 | WebFetch + WebSearch | **完全缺失**（无任何 web 工具） |
| bash 后台任务 | 后台化 + 输出持久化 + 状态/取消 | `background` 占位、64KB 头截断后丢失、无回看 |
| bash cwd/环境持久 | 会话级持久 | 每次固定 `workspace.root`、环境不持久（[tools.ts:441-455](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L441-L455)） |
| 搜索 | ripgrep + 输出模式（files/count/-C/multiline） | 纯 JS 逐文件 readFile，单一输出格式，无上下文行 |
| glob | 按 mtime 排序 + 截断提示 | 字母序 + 静默截断 |
| Read | 图片/多模态 + git diff-aware | 纯 utf8 文本、不感知 git |
| Edit 反馈 | 结构化 diff/行号 | 仅返回 "applied N edit(s)"，且 CRLF 被隐式归一为 LF |
| LSP / Notebook | diagnostics/定义/引用；NotebookEdit | 均缺失 |
| 工具级超时 | 每工具独立超时 | 仅 bash 有（120s 上限），其余只受全局 signal |
| 写并发保护 | 文件级串行化 | 并行批内对同文件的 `edit_file`/`write_file` 无锁 |

**C2. 搜索路径的三个实现细节**：`grep_search` 无全局早停（200 条上限只在汇总阶段截断，
已找够后其余文件的 IO 照付，[tools.ts:364-385](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L364-L385)）；
`walkFiles` 目录级串行递归（文件级有 8 并发、目录级没有）；`globRegexCache` 无上限
无淘汰（tools.ts:47）。`list_dir` 不排除 `.git/node_modules`（workspace.ts:42-56），
200 条配额轻易被 `.git` 吃掉。

**C3. 权限分类器的精度局限**：`sed`/`awk` 整体被视为只读，但 `sed -i` 实际写文件
（[bash-permission.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/bash-permission.ts#L3-L6)）；
`isDangerousCommand` 只匹配路径/变量六类模式，无 `rm -rf`、`git push -f`、`chmod 777`
等语义级规则；`always_allow` 保存的是当前参数**字面量**（[permissions.ts:48-49](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/permissions.ts#L48-L49)），
不做通配泛化——对参数多变的工具，"始终允许"退化为"允许这一条"。

### 主题 D：编排与生态的新发现

**D1. 波次调度气泡**：每波 `await Promise.all(ready...)` 等最慢任务结束才重新计算就绪
（[workflow.ts:44-54](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/workflow.ts#L44-L54)）——先完成的任务空出的并发槽位立即闲置，吞吐低于真实并发上限。
上游失败则下游全部标 `blocked` 终止，无跳过/降级路径。

**D2. MCP 三个隐患**（[mcp.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/mcp.ts)）：
stdio 子进程 `stderr: "pipe"` 但无人读取——服务器日志写满管道缓冲即**死锁**；
服务器串行逐个连接，多服务器启动延迟线性叠加；无 id 的通知被静默丢弃，
`tools/list_changed` 永远无法感知（工具列表冻结在首次 `listTools`）。

**D3. Skills 渐进披露的隐性代价**：`SkillLoader.list()` 对每个 SKILL.md 读全文并解析
正文（[skills.ts:13-16](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/skills.ts#L13-L16)），而 `buildSystemPrompt` 每 run 调用、`skill` 工具每次调用又全量
`list()`——**想省的正文 IO 在索引阶段就全付了**，且无缓存。

**D4. 记忆目录在 run 内冻结**：`loadMemoryCatalog` 只在 run 启动时读一次
（[memory.ts:44-48](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/memory.ts#L44-L48)），同一 run 内先 `note_save` 后 `memory_read` 看不到刚写的内容；
`DenialTracker` 总数干预被自锁——`intervenedThisCycle` 置位后到下次成功前，即使总数
持续超 20 也不再干预（[denial-tracker.ts:20-25](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/denial-tracker.ts#L20-L25)）。

## 3. 与顶级产品的能力差距清单（v7 更新）

| 能力 | 顶级产品 | SztuCode 现状 | 差距本质 |
| --- | --- | --- | --- |
| 重试纪律 | 529/超时均重试、耗尽语义一致 | 529 缺白名单、超时不重试、耗尽标记可丢失 | 最该重试的场景恰好不重试 |
| 溢出应急 | 上下文超限自动压缩/降级 | 400 → 错误回注 → 三连败终止 | 无逃生门，成功率直接损失 |
| 超时语义 | 首字节 + 空闲超时 | 全程总超时；工作流可永不超时；提问可永久挂起 | 长流被斩断、挂起无人管 |
| token 计数 | 各模型真实 tokenizer | `cl100k_base` 硬编码 + 双重 +4 高估 | 压缩判据系统性有偏 |
| prompt cache | 历史分层 breakpoint + 稳定前缀工程 | 单层 + 三条负优化 + 兜底路径无缓存 | 长会话成本线性增长 |
| 推理模型 | max_completion_tokens + 官方 thinking 形状 | max_tokens 被拒、thinking 形状非标准 | 推理模型路径基本不可用 |
| 后台任务 | task/bash 后台化 + 状态/输出/取消 API | bash background 占位、spawn_agent 同步阻塞 | 长任务可操作性缺失 |
| 恢复执行 | rollout + `--resume` 重放 | checkpoint 只存不恢复 | 保存 ≠ 恢复 |
| 搜索 | ripgrep + 输出模式 + 早停 | 纯 JS 逐文件、无早停、glob 静默截断 | 大仓库速度与可信度双输 |
| Web 能力 | WebFetch + WebSearch | 无 | 信息获取面整块缺失 |
| LSP | diagnostics/定义/引用/重命名 | 无 | 精确代码理解停留在文本层 |
| 可观测成本 | 采样/分级落盘 | 运行级 O(n²) 三源序列化、trace 无轮转 | 长运行越跑越慢越贵 |
| MCP | 重连、协商分支、通知、stderr 处理 | 一次性连接、通知丢弃、stderr 死锁隐患 | 生态健壮性差距 |
| 流式中断 | Esc 中断当前流注入纠正 | 已实现中断驱动纠偏（本轮确认） | 此项已追平，移出差距清单 |

## 4. 值得肯定的亮点（v6 九项复核后仍成立，新增三项）

1. **后台并行压缩**：压缩与工具执行重叠，熔断后硬丢弃退路，比同步阻塞式优雅。
2. **HandoffArtifact 证据一致性校验**：coder 越界改动必须与自报 escalations 一致——
   超越 Claude Code 的纵深防御。
3. **offload 大输出卸载 + 分页协议**：完整度高，含 realpath 路径安全（`offload.ts:73-82`）。
   （遗留瑕疵：`read_ref` 每页全文件读取再 slice，offload.ts:97-98。）
4. **stuck/denial 双 tracker + phase 追踪**：显式干预循环，Claude Code 也无显式
   denial 干预。
5. **增量 token 计数缓存**（UsageCache + 每消息 WeakMap）：免 O(n²)，`context.ts:202-238`。
6. **realpath 符号链接逃逸防护**：从目标向上找第一个存在祖先校验，姿势正确。
7. **durable checkpoint 事件关联**：sequence/operation_id/checkpoint_id 三元组是
   operation log 的天然落点。
8. **工具结果轻量摘要**：bash/grep/read 的摘要规则分层保真，比"全文截断"聪明。
9. **workflow 循环护栏**：token_budget + review_decision + max_retries，DAG 不会无限烧钱。
10. **【新】流式纠偏是中断驱动而非轮询**：`combineSignals` 把 steering signal 并入生成
    signal（[agent-loop.ts:222](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L222)），打断当前流 → 保存半截输出 → 注入纠偏 → 继续，
    这一条已追平顶级产品（v6 曾列为差距，本轮复核后撤销）。
11. **【新】git/memory 动态段已移出 Anthropic system 前缀**：作为首条 user 消息注入
    （[run-manager.ts:103-105](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/run-manager.ts#L103-L105)，注释明确 "Volatile workspace state belongs after the
    cacheable system prefix"）——对 Anthropic 是正确的缓存工程，只是对 OpenAI 风格
    前缀缓存反而有害（见 B2，需要按 provider 分流）。
12. **【新】失败路径也持久化部分对话**：`partialMessages` 挂到错误上由 RunManager 落盘
    （[run-manager.ts:111-115](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/run-manager.ts#L111-L115)），多步工作成果不会因一次失败蒸发。

## 5. 扩展路线图

### 阶段一至四：已完成（历史存档，见 v5 快照）

### 阶段五：Durable Run Core（进行中）

`run.replay` 可回退磁盘 JSONL，checkpoint 已有关联三元组。仍未完成：append-only
operation log、`run.resume`、幂等键、副作用账本、后台 task 控制面、policy AST、
记忆巩固与评测门禁。

### 阶段六：成本效率工程（v6 提出）

事项 #27-#37 保持原优先级不变（真实 tokenizer、cache 分层、bash 后台、run.resume、
rg、动态 offload、spawn_agent 异步、diff 读取、LSP、语义记忆、plan mode）。
本轮补充证据：#28 的范围要扩大——除历史断点外还需修 B2 三条负优化；#27 要顺带
修 +4 双重累加（[context.ts:21](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/context.ts#L21) 与 :175）。

### 阶段七：可靠性工程（本轮新增，与阶段六并列为最高杠杆）

阶段六修"每次调用多贵"，阶段七修"关键时刻会不会倒"。两者互不依赖、可并行。

| # | 事项 | 要点 | 优先级 | 状态 |
| --- | --- | --- | --- | --- |
| 38 | **重试纪律收口** | 529 入白名单；超时中止改抛可识别的 TimeoutError 并纳入可重试；耗尽判定与循环上限统一，`retryExhausted` 不再丢失 | **P0** | 未开始 |
| 39 | **上下文溢出应急通道** | 识别 `context_length`/400 类错误 → 立即硬丢弃或紧急压缩后重放本步，替代"回注等死" | **P0** | 未开始 |
| 40 | **超时语义重构** | provider 改首字节 + 空闲超时；`time_budget_s<=0` 给默认上限；`ask_user_question` 加单问题超时；墙钟预算穿透到工具执行中 | **P0** | 未开始 |
| 41 | **推理模型适配** | OpenAI 路径 `max_completion_tokens` + 参数清洗（借道接线 ProviderCompat）；Anthropic thinking 改官方形状；跨供应商推理上下文映射 | **P0** | 未开始 |
| 42 | **cache 负优化三连修** | 动态首条 user 消息按 provider 分流（OpenAI 风格后置或并入 system 尾部）；`providerFromEnvironment` 带上缓存配置；剥离 responses 格式的 `cache_control` | **P0** | 未开始 |
| 43 | **O(n²) 序列化治理** | TracingProvider 改增量/采样落盘；checkpoint 增量化（或降频 + 摘要）；实现 EventBus 批处理（字段已声明）；TaskCanvas 事件改引用式；trace 轮转 + 启动尾部读取 | P1 | 未开始 |
| 44 | **静默失败清零** | glob 截断标记；重复 `tool_call_id` 显式报错；孤儿工具结果降级为文本而非丢弃 | P1 | 未开始 |
| 45 | **bash 三件套** | cwd/环境持久会话 + 输出落盘回看 + `background` 落地（与 #29 合并实施） | P1 | 未开始 |
| 46 | **权限精度提升** | `always_allow` 自动泛化为通配规则；`sed -i`/`rm -rf`/`push -f` 语义级规则；危险命令分级提示 | P1 | 未开始 |
| 47 | **WebFetch + WebSearch 工具** | 补齐信息获取面（fetch 带超时/大小上限/正文抽取；search 走可配置后端） | P1 | 未开始 |
| 48 | **workflow 调度改事件驱动** | 任务完成即补位（消除波次气泡）；上游失败支持跳过/降级策略 | P2 | 未开始 |
| 49 | **MCP 健壮性** | stderr 排空、退避重连、通知处理（list_changed）、并行连接、能力协商分支 | P2 | 未开始 |
| 50 | **接线既有死代码** | `cautious` 段传入 `taskText`；工具级 `timeoutMs` 逐工具设置；清理或接线 `READ_ONLY_COMMANDS`/`DANGEROUS_PATH_PATTERNS` | P2 | 未开始 |

#38-#42 是阶段七 P0：五项全部是"修已有防线"而非"加新器官"，改动面小、风险低，
直接作用于成功率与长任务存活率。与阶段六 P0（#27-#30）合并后共九项，构成本项目
当前最高杠杆的改造集——**先让已有能力真实生效，再谈扩展**。

## 6. 总评

v6 的结论是"机制完整度 7 成、成本效率 4 成半"。本轮第二次逐行审查后，这个判断要再
修正一层：**机制完整度本身也要打折**——一批防线停留在"声明/字段/注释"层面而没有
接线（A5 清单），重试与超时这两个韧性核心组件各有三个实锤漏洞（A1、A3），上下文
溢出这个必然发生的故障没有逃生门（A2）。

工程判断随之更新：最高杠杆从"阶段六四项"扩展为"**阶段六 + 阶段七的九个 P0**"。
阶段七五项（#38-#42）是本轮的直接产物，特征是**不加功能、只修防线**：529 与超时的
重试、400 的应急、超时语义、推理模型参数、缓存负优化——每一项都是几十行级的改动，
换来的却是"该重试时真的会重试、该降级时真的会降级、推理模型真的能用、缓存真的命中"。

能力数值空洞依旧：134 个测试证明机制正确性，但 Terminal-Bench 接入已就绪而**尚无
端到端成功率/成本数据**。本轮暴露的可靠性漏洞（尤其 529 不重试、溢出无应急、超时
斩断长流）恰恰是只有真实压测才能量化的——在跑出第一批基准数字之前，本文所有分数
仍只是静态代码审计的判断。下一轮评审的验收标准已经明确：**#38-#42 落地 + 第一批
端到端成功率/缓存命中率/单任务成本数据**，三者齐备才谈得上把分数从"审计判断"改为
"能力证明"。
