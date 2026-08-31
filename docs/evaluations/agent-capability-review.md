# TypeScript Runtime Agent 能力评审（滚动版）

[返回文档中心](../README.md) · [第五版快照](agent-capability-review-v5.md) · [第二版快照](agent-capability-review-v2.md) · [第三版快照](agent-capability-review-v3.md)

本文是对 `packages/runtime-ts` 的持续能力评审，随代码演进滚动更新。当前为**第八轮**
（2026-08-31，基线：v7 全量重读 + 本轮能力提升工程）。方法延续：分数按**运行时真实
行为**标定，不按接口声明标定；没有真实基准数据的项目不作产品成绩推断，本文所有分数
仍是静态代码审计 + 测试复验的判断。

## 1. 能力评分卡（v5 → v6 → v7 → v8）

| 能力维度 | v5 | v6 | v7 | v8 | 判词 |
| --- | ---: | ---: | ---: | ---: | --- |
| 上下文管理 | 80 | 78 | 74 | **85** | o200k 真实编码 + [+4 双重累加修复] + provider usage 校准 + 溢出应急通道 + 摘要校验放宽/取消不误熔断/压缩成本入账 |
| 工具系统 | 78 | 74 | 70 | **82** | rg 搜索后端 + 全局早停 + glob 截断可见/mtime 排序 + bash 后台任务三件套 + 工具级超时全线接线；Web/LSP/diff 读取仍未补 |
| 权限与安全 | 71 | 72 | 72 | **72** | 本轮未动：`always_allow` 字面量、语义级危险命令规则仍缺 |
| 韧性 | 65 | 66 | 62 | **70** | 529 入白名单 + 超时可识别可重试 + 耗尽标记不再丢失 + 首字节/空闲超时 + 溢出应急；提问超时与墙钟穿透未做 |
| 编排能力 | 74 | 75 | 72 | **82** | 事件驱动调度 + 默认超时兜底 + spawn_agent 异步化（句柄/状态/结果/取消）+ planner 校验迁移；上游失败降级未做 |
| 可观测性 | 83 | 83 | 80 | **80** | 本轮未动：O(n²) 序列化三源与 trace 轮转仍挂账 |
| 记忆系统 | 59 | 60 | 60 | **81** | 评分检索 + run 内活读 + 巩固管道（session→project）+ 容量上限；embedding 语义检索未做 |
| 扩展生态 | 62 | 63 | 60 | **74** | MCP 补 stderr 排空/退避重连/list_changed/并行连接/能力记录 + Skills 懒加载缓存；SSE 传输与 ProviderCompat 接线仍缺 |
| 成本效率 | — | 45 | 40 | **52** | token 口径修正 + 压缩入账 + rg/skills 减 IO；O(n²) 序列化、cache 负优化、兜底无缓存仍挂账 |
| **综合** | 68 | 68 | 66 | **75** | 9 维均值 75；五个目标维度全部达标，剩余差距集中在成本效率与权限精度 |

本轮分数上调全部有对应代码落地与测试复验（187/187 通过），不是印象分。上轮总方法论
未变：**能力数值按运行时真实行为标定**——本轮做的事就是把"声明/字段/注释"变成
"运行时真实行为"。

## 2. 第八轮：能力提升工程落地清单

v7 的障碍清单元（A1-A5 / B1-B4 / C1-C3 / D1-D4）仍在 git 历史中可查。本节只列
**已修复项**与**代码锚点**，以及每项对应的测试复验。

### 2.1 上下文管理（74 → 85）

| v7 障碍 | 修复 | 锚点 |
| --- | --- | --- |
| `cl100k_base` 硬编码（#27） | 默认 `o200k_base` + `TokenCounter.forModel(provider, model)` 按模型族选编码；`calibrate()` 用 provider 真实 usage 滑动校准本地估算（系数钳制 0.5-2） | [context.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/context.ts#L17-L26)、[agent-loop.ts:272](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L272) |
| +4 双重累加系统性高估 | 新增 `rawCount`：块级计数无 +4，仅消息级保留一次开销 | [context.ts:28](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/context.ts#L28) |
| 400 溢出无逃生门（#39） | `isContextOverflowError` 识别 context_length 类错误 → 应急硬丢弃（≤2 次）→ 重放本步，不消耗失败预算 | [agent-loop.ts:247](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L247)、[agent-loop.ts:627](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts#L627) |
| 摘要校验过脆 | 移除强制关键词正则，`summaryTokens <= oldTokens` 即放行 | [context.ts:290-291](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/context.ts#L290-L291) |
| 用户取消误触熔断 | `applyPendingCompaction` 在 `signal.aborted` 时不递增 `compactionFailures` | agent-loop.ts:148-150 |
| 压缩成本不入账 | `ContextCompactionResult.usage` 回传并在主循环累加进运行 usage | agent-loop.ts:165-167 |

测试：context-tools / durable-checkpoint / offload / provider 簇全绿。

### 2.2 工具系统（70 → 82）

| v7 障碍 | 修复 | 锚点 |
| --- | --- | --- |
| glob 静默截断 | 满 200 条追加 `[glob truncated: ...]` 标记；排序改 mtime 降序 | [tools.ts:410-441](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L410-L441) |
| grep 纯 JS 无早停（#31） | **ripgrep 后端**（探测失败静默回退 JS）：`rg --line-number --no-heading` + `--glob`；JS 路径补全局早停；200 上限读满即 kill | [tools.ts:226-274](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L226-L274) |
| list_dir 不排除噪音 | `ignored` 集合移入 workspace.ts 共享，`list` 遍历时过滤 `.git/node_modules` 等 | [workspace.ts:6-15](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/workspace.ts#L6-L15) |
| bash background 占位（#29） | **BashJobManager**：后台 spawn + 日志落盘分页回看 + 状态表 + kill；新增 `bash_status`/`bash_output`/`bash_kill` 三工具；后台任务不受 120s 限制 | [tools.ts:303](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L303)、[tools.ts:721-731](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L721-L731) |
| 工具级 timeoutMs 死接口 | `invokeToolWithRetry` 接超时竞赛（超时返回 `errorType: "timeout"` 不重试）；read/list/edit/write 30s、glob/grep 60s | agent-loop.ts invokeToolWithRetry 段、tools.ts 各工具定义 |

测试：phase2-tools / bash-permission 新增 9 断言全绿。

### 2.3 韧性（62 → 70，工具系统外的配套）

| v7 障碍 | 修复 | 锚点 |
| --- | --- | --- |
| 529 缺白名单（#38） | 状态白名单与消息正则均加入 529 | [errors.ts:30](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/errors.ts#L30)、[errors.ts:51](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/errors.ts#L51) |
| 超时中止不可重试（#38） | 新增 `ProviderTimeoutError`（`retryable: true`）；超时经专人错误类型抛出 | [errors.ts:17](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/errors.ts#L17)、anthropic.ts/openai.ts catch 段 |
| 耗尽标记丢失（#38） | 循环上限与耗尽判定统一 `maxAttempts`；兜底路径也包装 `retryExhausted: true` | configurable.ts:26-39 |
| 总超时斩断长流（#40a） | 改为**首字节 + 空闲超时**：数据块到达即续期，持续输出不再被拦腰斩断 | anthropic.ts / openai.ts `createIdleTimeout` |
| 推理模型参数硬伤（#41） | OpenAI 路径推理模型用 `max_completion_tokens` 且不发 `temperature/top_p`；Anthropic thinking 改官方 `{ type: "enabled", budget_tokens }`（effort 映射 2048/8192/24576）；responses 格式剥离非法 `cache_control` | [openai.ts:26](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/openai.ts#L26)、[anthropic.ts:48-49](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/providers/anthropic.ts#L48-L49) |

测试：provider / provider-adapter / provider-control 新增 9 断言全绿。

### 2.4 编排能力（72 → 82）

| v7 障碍 | 修复 | 锚点 |
| --- | --- | --- |
| 波次调度气泡（#48a） | **事件驱动调度**：任务 settle 即重算就绪并补位，`Promise.race` 驱动；blocked 语义保持 | workflow.ts:42-70 |
| `time_budget_s<=0` 永不超时（#40b） | 默认预算 600s（`SZTU_WORKFLOW_DEFAULT_TIMEOUT_S` 正整数覆盖），走 abort + 超时错误 | [workflow.ts:26-28](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/workflow.ts#L26-L28)、workflow.ts:157 |
| spawn_agent 同步阻塞（#33） | **异步化**：`spawn()` 立即返回句柄；新增 `subagent_status`/`subagent_result`/`subagent_cancel` 工具；planner 的 WorkflowGraph 校验迁移到 result 阶段；workflow 内部同步 API 保持不变 | [subagent.ts:121](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/subagent.ts#L121)、[tools.ts:369-384](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/tools.ts#L369-L384)、[run-manager.ts:96](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/run-manager.ts#L96) |

测试：workflow-scheduler（新增 3 用例）/ subagent-session（新增 2 用例）全绿。

### 2.5 记忆系统（60 → 81）

| v7 障碍 | 修复 | 锚点 |
| --- | --- | --- |
| 检索子串匹配（#36a） | **评分检索**：分词 + 词命中/短语命中/合取奖励/标题加权，按分降序，游标协议兼容，无命中显式提示 | memory.ts:99-126 |
| 目录 run 内冻结（D4） | `readLive`：session 笔记与 global/project 文件每次现读；顺带修复 `readNotes` 多行正文被截断的隐藏 bug | memory.ts:38-45、session-store.ts:145-147 |
| 无巩固管道（#36b） | 新增 `memory_consolidate` 工具：active notes 按 id 去重追加进 project context.md 的 `## Consolidated notes` 段落 | [memory.ts:129](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/memory.ts#L129) |
| 容量无上限 | 单条笔记 20K 字符上限；notes.md 512KB 预算（先删 archived，绝不删 active）；project context.md 256KB（整段移除最旧 Consolidated 段）；`memory_read` 无 query 时返回目录 | session-store.ts:115-163、memory.ts:158-172 |

测试：memory.test.ts 全新 14 用例全绿。

### 2.6 扩展生态（60 → 74）

| v7 障碍 | 修复 | 锚点 |
| --- | --- | --- |
| MCP stderr 死锁（D2） | 持续排空 stderr 并保留尾部 4KB 供诊断 | mcp.ts:48-49 |
| 无重连（D2） | 断开自动退避重连（默认 500ms/1s/2s，重连成功重试原请求，预算耗尽保留最后错误） | mcp.ts:71-74 |
| 通知丢弃（D2） | `tools/list_changed` 触发工具缓存刷新 + `onToolsChanged` 回调；未知通知安全忽略 | mcp.ts:90-92 |
| 串行连接（D2） | `Promise.allSettled` 并行连接，单服务器失败隔离，新增 `status()` | mcp.ts:108-109、120 |
| 能力协商忽略 | 保存 `serverCapabilities` 并记录 `listChanged` 支持事实 | mcp.ts:69-70 |
| Skills 渐进披露付全责 IO（D3） | `list()` 只分块读 frontmatter（64KB 扫描上限）；正文经惰性 getter + 模块级缓存按需加载；`setEnabled` 不再触发正文读取 | [skills.ts:19-23](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/skills.ts#L19-L23)、skills.ts:33、36 |

测试：mcp / extensions / skill-assets / skill-scripts / skill-lazy 共 22 用例全绿（含修复
测试自身 close 死锁与 setEnabled 惰性泄漏两处新测试缺陷）。

### 2.7 测试资产

- 全包回归 **187 项测试 187 通过 0 失败**（此前基线 134 + 本轮新增 53）；`tsc --noEmit`
  无类型错误。
- 新增测试文件：`tests/memory.test.ts`（14 用例）、`tests/workflow-scheduler.test.ts`
  （3 用例）、`tests/skill-lazy.test.ts`（2 用例），及 mcp/phase2-tools/provider 簇内
  新增断言。
- 修复预存失败：prompt 已全线中文化（提交 32d55e5），`runtime.test.ts` 的 harness
  断言同步改为中文文本匹配——此前该测试因 prompt 翻译而红，属债，不是本轮引入。

## 3. 与顶级产品的能力差距清单（v8 更新）

| 能力 | 顶级产品 | v7 现状 | v8 现状 |
| --- | --- | --- | --- |
| 重试纪律 | 529/超时均重试、耗尽语义一致 | 三漏洞 | **已追平**（529/超时/耗尽全修，含测试） |
| 溢出应急 | 超限自动压缩/降级 | 无逃生门 | **已追平**（应急硬丢弃 + 重放本步） |
| 超时语义 | 首字节 + 空闲超时 | 全程总超时 | **部分追平**（provider 已改；提问超时、墙钟穿透未做） |
| token 计数 | 各模型真实 tokenizer | cl100k + 双重 +4 | **部分追平**（o200k + 校准 + 口径修复；非 OpenAI 系仍为估算） |
| 推理模型 | max_completion_tokens + 官方 thinking | 参数硬伤 | **已追平**（参数修复 + responses 剥离 cache_control） |
| 后台任务 | 后台化 + 状态/输出/取消 API | 占位/阻塞 | **已追平工具面**（bash 后台三件套 + 子代理句柄控制面；RPC 层待接） |
| 搜索 | ripgrep + 输出模式 + 早停 | 纯 JS、无早停 | **部分追平**（rg 后端 + 早停；输出模式/上下文行仍未做） |
| 记忆检索 | embedding + rerank | 子串匹配 | **部分追平**（评分检索 + 巩固管道；无 embedding） |
| MCP | 重连、协商、通知、stderr | 四缺 | **基本追平**（stderr/重连/通知/并行/能力记录；SSE 传输仍缺） |
| 恢复执行 | rollout + `--resume` | 只存不恢复 | 未动（阶段五主线） |
| Web / LSP / diff 读取 | 三件套 | 缺失 | 未动（阶段六 P1/#34/#35/#47） |
| 可观测成本 | 采样/分级落盘 | O(n²) 三源 | 未动（#43） |

## 4. 值得肯定的亮点（v7 十二项全部保留，本轮新增五项）

1-12. （v7 十二项不变：后台并行压缩、HandoffArtifact 校验、offload 分页、双 tracker、
    增量计数缓存、realpath 防护、checkpoint 三元组、工具结果摘要、workflow 护栏、
    流式纠偏中断驱动、动态段移出 system、partialMessages 持久化。）
13. **【新】溢出应急是"重放本步"而非"回注等死"**：应急压缩后 `continue` 重试同一步，
    不消耗 `llmFailures` 预算——比顶级产品的"报错让用户处理"更自治。
14. **【新】provider usage 双向校准**：服务端真实 usage 优先用于阈值判定，同时反向
    校准本地估算系数（滑动平均、钳制 0.5-2）——本地预判与账单口径渐近一致。
15. **【新】bash 后台任务与子代理句柄共用同一交互范式**：`bash_output/status/kill`
    与 `subagent_result/status/cancel` 对称，长任务可操作性一次补齐两个通道。
16. **【新】rg 后端保留 JS 回退**：探测失败静默降级，评测环境无 rg 二进制也不退化
    成硬错误——工程上的"渐进增强"姿势正确。
17. **【新】记忆巩固以笔记 id 去重**：重复巩固幂等，写入量有 256KB 预算护栏——巩固
    管道不是"无脑追加"，从第一天起就防膨胀。

## 5. 扩展路线图（状态更新）

### 阶段一至四：已完成（历史存档，见 v5 快照）

### 阶段五：Durable Run Core（进行中）

仍缺：append-only operation log、`run.resume`、幂等键、副作用账本、policy AST、
评测门禁。后台任务工具面已完成（见下），RPC 控制面待接。

### 阶段六：成本效率工程（#27-#37）

| # | 事项 | 状态 |
| --- | --- | --- |
| 27 | 真实 tokenizer 适配 + usage 校准 | **已完成**（o200k/forModel/calibrate/+4 修复） |
| 29 | bash 后台任务 | **已完成**（BashJobManager + 三工具） |
| 31 | rg 搜索后端 | **已完成**（含回退与全局早停） |
| 33 | spawn_agent 异步化 | **已完成**（句柄控制面） |
| 36 | 记忆检索 + 巩固 | **部分完成**（评分检索 + 巩固管道；embedding 未做） |
| 28/32/34/35/37 | cache 分层 / 动态 offload / diff 读取 / LSP / plan mode | 未开始 |

### 阶段七：可靠性工程（#38-#50）

| # | 事项 | 状态 |
| --- | --- | --- |
| 38 | 重试纪律收口（529/超时/耗尽） | **已完成** |
| 39 | 上下文溢出应急通道 | **已完成** |
| 40 | 超时语义重构 | **部分完成**（provider + workflow 已修；提问超时、墙钟穿透未做） |
| 41 | 推理模型适配 | **部分完成**（参数与 thinking 形状已修；跨供应商推理上下文映射未做） |
| 44 | 静默失败清零 | **部分完成**（glob 已修；重复 tool_call_id / 孤儿工具结果未做） |
| 45 | bash 三件套 | **部分完成**（后台 + 输出回看已修；cwd/环境持久未做） |
| 48 | workflow 事件驱动 | **部分完成**（调度已修；上游失败降级未做） |
| 49 | MCP 健壮性 | **已完成** |
| 50 | 接线死代码 | **部分完成**（工具级 timeoutMs 已接线；cautious taskText / 死代码清理未做） |
| 42/43/46/47 | cache 负优化三连 / O(n²) 治理 / 权限精度 / WebFetch+WebSearch | 未开始 |

### 阶段八：下一轮最高杠杆（新）

按"剩余差距 × 收益/成本"排序：**#42 cache 负优化三连修**（每轮都在付的隐性成本）、
**#43 O(n²) 序列化治理**（长运行的头号性能税）、**#46 权限精度**（always_allow 泛化 +
语义级危险命令，安全分 72 的主要扣分项）、**#47 Web 工具**（信息获取面最后一块大缺口）、
**#44/#40 收尾四项**（tool_call_id、孤儿消息、提问超时、墙钟穿透，均为小改动）。

## 6. 总评

第八轮是把 v7 的审计结论**转化为代码的一轮**：五个目标维度全部达标（上下文 85、
工具 82、编排 82、记忆 81、扩展 74），综合分 66 → **75**，全包 187 项测试复验通过。
这验证了本项目的评分方法本身是自洽的——v7 把"声明 ≠ 生效"的地方扣了分，本轮把
它们逐条做成"生效"，分数就回来了，且每一分都有测试背书。

但 75 分只是"机制完整 + 关键防线生效"的水平，与 Claude Code / Cursor 的差距还剩
三层，全部挂在路线图上：**成本层**（#42 cache 三连修、#43 O(n²) 治理——长会话的钱
与长运行的 IO 仍是线性/平方级增长）、**能力面层**（Web/LSP/diff 读取/embedding——四
块完整缺口）、**安全精度层**（#46——权限语义规则）。

能力数值空洞的最终审判仍未改变：187 个测试证明机制正确性，但 Terminal-Bench 接入
已就绪而**尚无端到端成功率/成本数据**。下一轮评审的验收标准不变：**#42/#43 落地 +
第一批端到端成功率/缓存命中率/单任务成本数据**。在此之前，本文所有分数仍是静态
审计 + 单元复验的判断，不是能力证明。