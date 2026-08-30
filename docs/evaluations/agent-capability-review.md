# TypeScript Runtime Agent 能力评审

[返回文档中心](../README.md)

本文是对 `packages/runtime-ts` 的深度能力评审：以顶级 Agent 工程师视角，对照 Claude Code、
OpenAI Codex CLI、Gemini CLI 逐项打分，定位性能障碍，并给出分阶段扩展路线。评审基于对
runtime 全部 40+ 模块（agent-loop、tools、context、permissions、subagent、workflow、
providers、memory、offload、prompt 体系等）的逐行审查。

本文是**评审快照**，不是行为契约：分数与结论随代码演进失效，落地修复后应同步更新状态列。

## 1. 能力评分卡

| 能力维度 | 评分 | 一句话判词 |
| --- | --- | --- |
| 上下文管理 | 72/100 | 骨架先进（后台并行压缩、质量门禁、熔断），但熔断后无退路、无分层压缩 |
| 工具系统 | 65/100 | fail-closed 直觉好、offload 亮点，但 Read/Edit 停留在裸文本时代 |
| 权限与安全 | 60/100 | toolName 粒度 + 正则黑名单，与参数级规则引擎差一个代际 |
| 韧性（Resilience） | 35/100 | 最大短板——一次 API 抖动报废整个 run，无恢复、无错误回注 |
| 编排能力 | 55/100 | DAG 引擎工程质量高，但模型无自主委派权，是"人驱动的引擎" |
| 可观测性 | 85/100 | 事件总线、usage 三分类、trace、session 树，超出多数开源实现 |
| 记忆系统 | 50/100 | 三层架构 + 渐进披露有模有样，但无巩固管道，跨会话只读 |
| 扩展生态 | 45/100 | Skills 模型侧失明、MCP 协议陈旧、schema 直通 |
| **综合** | **58/100** | 精心打磨的原型，每个子系统都停在 60-80 分的"最后一公里"前 |

## 2. 致命缺陷（P0）

以下四项决定"demo"与"生产工具"的分水岭。

### 2.1 LLM 调用零容错

`agent-loop.ts:178` 的 `await this.provider.complete(...)` 没有任何 try/catch。Provider 抛错
一路冒泡至 `run-manager.ts:103`，run 标记失败。失败路径不调用 `replaceModelHistory`（只有
成功路径 121 行调用）——跑到第 98 步时一次网络抖动，98 步的中间结论、工具结果全部蒸发。

对比：Claude Code 的核心韧性哲学是"错误成为对话的一部分，而不是进程的终点"——API 错误
被包装为错误消息回注对话，模型可以看到并自行决策续跑。

### 2.2 Provider 行为自相矛盾

- `providers/openai.ts:53`：模型输出被 `max_tokens` 截断的 JSON 参数（高频常态）直接
  throw，一票否决整个 run。
- `providers/anthropic.ts:128`：同类错误静默容错为 `{}`，走 schema 验证失败 →
  `schema_error` 工具结果 → 模型自愈（这才是正确路径）。

同一个 runtime 两种语义，缺少统一的"模型输出修复层"。

### 2.3 压缩熔断后无退路

熔断器（连续 3 次摘要失败）触发后，无 LLM 的硬丢弃 fallback `ContextManager.compact()`
（`context.ts:218`）在主循环中从未被调用，之后上下文只能持续膨胀直到 API 硬报错。另外
摘要质量门禁的校验正则 `/goal|progress|.../i` 只认英文标题——中文摘要会被误判 invalid，
白白消耗压缩机会并累计熔断。

### 2.4 主 Agent 无自主委派能力

整个工具集中没有 Task/spawn 工具（`tools.ts:263-369` 全量核实）。子代理只能由客户端 RPC
或预构造 DAG 触发。Claude Code 的核心编排范式——模型自主决定何时委派给哪个专家子代理
——在此架构中不存在。同时 ADR-0002 声称"Planner 输出类型化 DAG"，但运行时没有
planner→WorkflowGraph 的生成管线，desktop 端提交的是硬编码静态样例。引擎造好了，燃料
管线没接。

## 3. 性能障碍清单

| # | 障碍 | 位置 | 影响 |
| --- | --- | --- | --- |
| 1 | 每 token 一次 EventBus 事件：对象分配 + `toISOString()` + 串行扩展分发 | `agent-loop.ts:178` | 高吞吐流式纯税；Claude Code 做 token 缓冲合帧 |
| 2 | 每步全量 sanitize：O(n) 每步跑一遍，n 步累计 O(n²)；token 计数有增量缓存但 sanitize 没有 | `agent-loop.ts:171` | 长会话每步无谓 CPU 开销 |
| 3 | runs Map 永不删除：cancel 也只改 status，RunState 永久驻留 | `run-manager.ts:28` | 长驻 daemon 内存泄漏 |
| 4 | 重试上限 2 秒且不读 Retry-After：正则匹配错误消息判断可重试性，无 jitter | `providers/configurable.ts:25` | 429 限流窗口 30-60 秒，2 秒重试等于自杀式风暴 |
| 5 | `bash --login -c`：每次 spawn 加载 profile | `tools.ts:396` | Windows Git Bash login shell 启动开销显著 |
| 6 | grep 是纯 JS 逐行：对比 Claude Code 调 ripgrep（SIMD/mmap/并行）；2000 文件静默截断 | `tools.ts:329` | 大仓库搜索既慢又不完整 |
| 7 | 只读 bash 永远串行：`classifyBashPermission` 最高只返回 `workspace_write` | `bash-permission.ts:14` | 3 个并行 `rg` 查询被迫串行 |
| 8 | bash exit≠0 被自动重试：测试失败的 errorType 是 `runtime_error`，落入可重试集合 | `agent-loop.ts:506` | 非幂等命令重复执行风险 |
| 9 | meta.json 读改写：每条消息全量 get→改→save | `session-store.ts:64` | 高频对话 IO 放大 |
| 10 | git 快照每 run 重拍进 system prompt | `run-manager.ts:98` | 破坏跨 run 的 prompt cache 前缀稳定性 |

## 4. 对标顶级产品的结构性差距

### 4.1 与 Claude Code 的差距清单

| 能力 | Claude Code | SztuCode | 差距本质 |
| --- | --- | --- | --- |
| Read 工具 | `cat -n` 行号 + offset/limit 分页 | 裸文本、无行号、2MB 后不可读 | 空间定位基础设施缺失——grep 反而有 `file:line` 格式 |
| Edit 体系 | 精确匹配 + 行号锚定 + MultiEdit + 失败诊断 | 纯精确匹配、无原子性、CRLF 无缓解 | edit 成功率被 read 拖累，两个工具互相拖后腿 |
| 权限规则 | `Bash(git diff:*)` 参数级 glob + 三层作用域 | toolName 粒度 + 全局共享 policy.toml | `always_allow write_file` 后跨项目全局静默放行 |
| 流式中断 | 流式期间可 Esc 注入 steering | 仅步边界消费（`agent-loop.ts:166`） | 长 bash 执行期间用户纠正指令要等一整轮 |
| 会话恢复 | `--resume` / rollout 重放 | `recoverInterruptedSessions` 只是降级为 waiting_for_input | 崩溃时刻中间消息不在任何持久化介质里 |
| Prompt cache | 增量断点管理 | 仅 system 尾 + 最后一个工具打点，压缩后前缀突变全量失效 | 成本与延迟的直接差距 |
| 子代理 | Task tool fan-out + 模型可见的 agent 描述 | 模型不知道任何子代理存在 | 编排决策权在人在模型，是范式差异 |
| system-reminder | 文件变更提醒、todo 注入、上下文水位 | `system-reminders/` 5 个模板零接线 | 模型对压缩完全无感知 |

### 4.2 值得肯定的亮点

以下设计达到或超过 Claude Code 的水准：

1. **后台并行压缩**（`agent-loop.ts:76-98`）：压缩与工具执行重叠，藏进 LLM 等待工具 IO 的
   空窗期，比 Claude Code 的同步阻塞式压缩更优雅。
2. **HandoffArtifact 证据一致性校验**（`workflow.ts:167-172`）：coder 越界改动路径必须与
   自报 escalations 完全一致，用证据反推子代理没撒谎，超越 Claude Code 的纵深防御。
3. **offload 大输出卸载 + 分页协议 + 路径安全**：Claude Code"临时文件 + 占位指针"的等价
   物且实现完整。
4. **stuck/denial 双 tracker 干预**：Claude Code 官方也没有显式的 denial-loop 干预。
5. **realpath 符号链接逃逸防护**（`workspace.ts:20-38`）：从目标向上找第一个存在的祖先做
   校验，正确的姿势。

## 5. 扩展路线图

按投入产出比排序，阶段一不修，其他一切都是沙上建塔。

### 阶段一：止血（韧性支柱）

| # | 事项 | 要点 | 状态 |
| --- | --- | --- | --- |
| 1 | 统一输出修复层 | 新增 `providers/output-normalization.ts`：`parseToolArguments` 宽容解析（malformed JSON → 空对象 → schema_error 回注 → 模型自愈）；`normalizeStopReason` 把 `length`/`max_tokens` 统一映射为 `max_tokens`，不再伪装成 `end_turn` | 已完成 |
| 2 | LLM 错误回注对话 | `agent-loop.ts` 主循环 LLM 调用包 try/catch：错误转为 user 消息回注（含 attempt 计数与原因），`maxLlmFailures`（默认 3）内模型自行续跑，达到上限诚实上抛；错误对象携带 `partialMessages`，RunManager 失败路径持久化已积累对话 | 已完成 |
| 3 | 压缩熔断退路 | LLM 摘要连续失败 `compactCircuitBreaker`（默认 3）次后熔断，退化为 `ContextManager.compact()` 无模型硬丢弃；滑窗保留不足时退到极限窗口（仅保留最近 1 turn）保证止血；门禁正则支持中文标题（目标/进展/决策/未决/下一步） | 已完成 |
| 4 | 修 run-manager 两个 bug | 终态 run 经 `scheduleRunCleanup` 延迟 60s 清理（unref timer），runs Map 不再永久驻留；catch 分支状态改为 `failed` 并与 `run.finished` 事件一致，`RunGetResult` 协议类型同步扩展 | 已完成 |
| 5 | bash 重试豁免 | `Tool` 接口新增 `retryable` 字段，bash 标记 `retryable: false`——exit≠0 是业务结果且命令可能非幂等，不自动重试 | 已完成 |

阶段一验证：`packages/runtime-ts` 全量测试 132/132 通过（含熔断退路、LLM 错误回注、retryable 豁免、failed 状态持久化等新增用例），`tsc --noEmit` 零错误。

### 阶段二：补齐工具基础设施

| # | 事项 | 要点 | 状态 |
| --- | --- | --- | --- |
| 6 | Read 加行号 + offset/limit 分页 | `cat -n` 格式，是 Edit 成功率的先决条件 | 未开始 |
| 7 | Edit 加行号锚定 + CRLF 归一化 | 失败时提示重 read；考虑 MultiEdit 原子批量编辑 | 未开始 |
| 8 | 权限规则升级为参数级 | `write_file(/src/**)`、`bash(git diff:*)` 的 glob 规则 + per-workspace 作用域 | 未开始 |
| 9 | bash 分类增加 read_only 档 | `bash-permission.ts` 已实现只读命令白名单（`cat/ls/rg/...`）与只读 git 子命令白名单（`status/diff/log/...`），`classifyBashPermission` 动态降级为 `read_only` 进并发批；危险语法（路径逃逸/展开/重定向/sudo）保持 `danger_full_access` | 已完成 |
| 10 | 流式 token 合帧 | 50-100ms 缓冲窗口批量发事件，消灭每 token 事件风暴 | 未开始 |

### 阶段三：把编排决策权交给模型

| # | 事项 | 要点 | 状态 |
| --- | --- | --- | --- |
| 11 | 实现 Task 工具 | 主 Agent 可 spawn 子代理（复用 SubagentManager，加 `dispatch_agent` 工具），agent 描述注入 system prompt，结果截断后作为 tool_result 回注——单点投入回报最大的架构升级 | 未开始 |
| 12 | Planner→DAG 管线 | planner 角色输出结构化 WorkflowGraph（复用现有校验器），打通 ADR-0002 承诺的闭环 | 未开始 |
| 13 | Skills 模型侧接线 | name + description 常驻 system prompt + Skill 工具按需读全文（渐进披露），激活 23 个内置技能 | 未开始 |
| 14 | ask_user_question 补全 schema items | 结构化提问的 UI 可靠性因缺 items 定义落空 | 未开始 |

### 阶段四：长程能力

| # | 事项 | 要点 | 状态 |
| --- | --- | --- | --- |
| 15 | 流式 steering | AbortSignal 分级：先中断当前 LLM 流、保留部分输出，注入用户纠正 | 未开始 |
| 16 | run 级 checkpoint | 每 N 步持久化 messages 快照，崩溃后可 resume；事件流已在落盘，缺的只是重放重建 | 未开始 |
| 17 | 记忆巩固管道 | session 结束时 LLM 提炼 notes → project context.md；接线已存在但 reference-only 的 CLAUDE.md 创建 prompt | 未开始 |
| 18 | microcompact 分层压缩 | 轻量层只清旧 tool 输出（无 LLM 调用），重 LLM 摘要只留给真正需要时 | 未开始 |
| 19 | MCP 升级 | 2025-06 协议版本、resources/prompts 能力、schema 降级转换、重连与超时 | 未开始 |

## 6. 总评

这套 runtime 的核心矛盾是：可观测性达到了生产级（85 分），韧性却停留在 demo 级（35 分）。
对 Claude Code 内部机制的逆向理解相当深入（后台压缩、渐进披露、offload、证据校验都是明显
借鉴并部分超越的痕迹），但当前形态下，任何一次上游 API 异常都会把用户数小时的 agent 工作
变成一次性赌博——而这恰恰是 Claude Code/Codex 从"demo"跨入"生产工具"的那道分水岭。

评测文档自己承认（`evaluations/multi-agent-workflow.md`）："不能声称旧 Python 阶段记录的五
场景成本、成功率已经由当前实现重新证明"——当前项目没有任何可信的能力数值，这本身就是
最大的能力空洞。

执行顺序建议：先做阶段一的 5 项止血（涉及文件少、风险低、收益直接），再做阶段二第 6/7 项
（Read/Edit 行号体系），然后是阶段三第 11 项的 Task 工具——那是这套系统从"优秀的工作流
执行引擎"进化为"自主多 Agent 系统"的关键一跃。
