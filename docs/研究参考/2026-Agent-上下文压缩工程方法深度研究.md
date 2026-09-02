# 2026 Agent 上下文压缩工程方法深度研究

> 来源：https://www.datalearner.com/en/blog/agent-context-compression-deep-research
> 研究截止日期：2026-08-27
> 下载时间：2026-09-01

本文来做GPT 5.6 Sol Pro的Deep Research

**研究对象：** 长时程工具型 Agent、编码 Agent、Deep Research Agent、多轮业务 Agent 的运行时上下文管理。**核心问题：** 如何在不显著损害任务成功率、可恢复性和可审计性的前提下，降低峰值上下文、累计输入 Token、延迟以及 KV-cache 压力。

---

## 一、执行摘要

2025–2026 年的进展并不是出现了一个可以取代所有旧方案的"最强压缩算法"，而是业界逐渐形成了一套分层上下文架构。最成熟的系统不再把所有历史都塞进一个线性消息列表，也不把"压缩"简单理解为生成一段越来越短的摘要，而是把信息拆成四类：不可变原始事件、当前工作状态、近期原文、可按需恢复的外部材料。

最重要的结论如下。

1. **编码 Agent 中，先删除可再生成的旧工具输出，通常比先做 LLM 摘要更划算。** The Complexity Trap 在 SWE-agent、SWE-bench Verified 和五种模型上的结果显示，observation masking 的总成本约为原始 Agent 的一半；在 Qwen3-Coder 480B 上成本下降 52%，解决率反而提高 2.6 个百分点。原因不是摘要模型不够强，而是文件内容、终端输出和搜索结果往往占据绝大部分 Token，同时又可以通过路径、命令或查询重新获取。摘要则引入额外生成成本和事实丢失风险。
2. **"活动上下文更短"不等于"累计 Token 或总推理成本更低"。** Context Folding 把子任务放入临时分支，主线只接收返回结果，主线长度可从十万级压至约 8K；但 FoldGRPO 训练后的 Agent 会调用更多工具、搜索更多页面并生成更长轨迹。ReSum 也通过周期总结使 Agent 能继续探索，却未证明总 Token 成本一定下降。因此必须分别报告峰值上下文、累计输入、输出 Token、压缩器额外生成和墙钟延迟。
3. **滚动自由文本摘要的主要危险是不可逆信息损失和 `summary(summary)` 漂移。** 一旦旧原文被丢弃，摘要中遗漏的约束、失败原因或引用无法恢复。更稳妥的做法是保留不可变事件日志，每次压缩生成结构化状态快照；必要时从事件日志重新构建，而不是无限递归压缩旧摘要。
4. **压缩的目标应是"保留决策充分性"，而不是追求最短文本。** ACE 的结果说明，过度概括会造成 context collapse：细粒度策略、例外和失败经验被反复重写后消失。ACE 用 append/update 的小型结构化 bullet 演化 playbook，虽然它不是降低单条轨迹峰值 Token 的直接方案，却揭示了一个重要边界——高价值细节应被结构化、去重和检索，而不是一律压短。
5. **Agent 是否学会从压缩状态继续推理，与压缩器质量同样重要。** ReSum-GRPO、MEM1 和 Context Folding 都不只优化"写摘要"，而是训练 Agent 在被压缩的状态上恢复工作、决定何时分支或更新记忆。ReSum 在搜索任务中，training-free 版本较 ReAct 平均绝对提升 4.5%，经过 GRPO 后再提高 8.2%；MEM1 将递归记忆直接训练进策略，在其 QA 和 WebShop 设定中同时降低峰值 Token 和延迟。
6. **KV-cache 优化与语义压缩是两个问题。** 稳定前缀、确定性序列化和 append-only 设计可提高 cache hit、降低 prefill 成本和 TTFT，但不会解决注意力被无关内容稀释的 context rot。相反，修改早期历史的 masking 或 compaction 会使修改点之后的前缀缓存失效。生产系统必须同时设计语义保留策略和缓存边界。
7. **当前最稳健的生产组合是混合架构，而非单一方法。** 推荐顺序为：稳定可缓存前缀 → 不可变事件日志 → 旧 observation masking → 结构化工作状态 → 最近若干轮原文 → 阈值触发的语义 compaction → 外部对象存储与恢复句柄 → 按需检索 → 子 Agent/子轨迹隔离。只有在有大量训练轨迹和可验证奖励时，才值得进一步采用 ACON、ReSum-GRPO、MEM1 或 FoldGRPO。
8. **2026 年的先进方法仍有明显证据边界。** Context Folding 只有一个 36B 基座与两个任务族；Active Context Compression 的 SWE-bench Lite 实验只有 5 个样本；厂商 compaction API 多数没有公开统一 A/B 基准。它们可以指导架构，但不能把论文中的提升直接外推到客服、金融、医疗或任意企业工作流。

---

## 二、范围、定义与证据标准

### 2.1 什么算"上下文压缩"

本报告采用广义定义：任何减少模型当前可见历史、将历史替换为更短表示、把材料移出活动窗口，或让任务在多个隔离上下文之间流动的工程机制，都纳入比较。它包括：

* 硬截断和滑动窗口；
* 删除旧工具结果的 observation masking；
* 结构化状态快照和任务账本；
* LLM 语义摘要与厂商托管 compaction；
* 外部记忆、文件系统和检索；
* 子 Agent 隔离、分支轨迹折叠；
* 通过轨迹优化或强化学习得到的压缩策略；
* 稳定前缀和 KV-cache 友好序列化。

Prompt caching 本身不算语义压缩，因为模型仍然看到同样长的上下文；它只避免重复计算前缀。但它与压缩的触发方式和历史改写位置强耦合，因此必须一起讨论。

### 2.2 必须分开的四个量

很多宣传数字把不同指标混在一起，导致"压缩 90%"看起来等于"成本降低 90%"。实际至少要分开：

| 指标         | 含义                     | 典型影响                            |
| ---------- | ---------------------- | ------------------------------- |
| 峰值活动上下文    | 任一模型调用时可见的最大 Token     | 决定是否超窗、注意力稀释和单次 prefill 压力      |
| 累计输入 Token | 整条任务所有调用的输入之和          | 更接近 API 输入账单，但受 cache 计价影响      |
| 额外压缩计算     | 摘要器、检索器、反思器、训练或分支返回的开销 | 可能抵消主 Agent 的节省                 |
| 总墙钟时间      | 工具、模型、检索、压缩的端到端延迟      | 受并发、cache、外部服务影响，不能由 Token 单独推断 |

### 2.3 证据等级

* **A级：** 多模型、足够样本、公开任务与可比基线的论文实验。
* **B级：** 单一或少量模型的公开论文实验；数据可信但外推有限。
* **C级：** 厂商生产经验或正式文档，没有统一公开 A/B 数据。
* **D级：** 小样本原型或案例研究，只能证明可行性。

不同论文的模型、预算、任务和评分器不同，报告不会把彼此的成功率直接横向排名。定量对比只在各自论文的同设置基线内解释。

---

## 三、为什么长窗口没有消灭压缩需求

### 3.1 容量问题与利用问题不同

更大的 context window 解决的是"能否放进去"，不保证模型能可靠利用。Chroma 的 Context Rot 研究覆盖 18 个模型、194,480 次调用、8 种长度和 11 个 needle 位置，显示即使相关信息仍在窗口内，输入增长本身也会降低性能；干扰增加和语义相似度降低时退化更明显。它不是压缩方案评测，但说明"全部保留"并非无成本的安全选项。

工具型 Agent 的膨胀尤其严重。一次网页读取可能返回数千 Token，一次代码搜索或测试失败可能返回更多；这些 observation 被每轮重新发送。Manus 报告其典型 Agent 的输入/输出 Token 比约为 100:1，这意味着优化旧输入通常比压缩输出更有杠杆。

### 3.2 信息的价值分布极不均匀

长轨迹中的信息可分为：

* **必须永久保留：** 用户目标、硬约束、权限边界、不可撤销决策、验收标准；
* **必须保留但可结构化：** 当前计划、已完成项、关键事实、失败原因、未解决问题；
* **可移出但应可恢复：** 文件正文、网页内容、日志、截图分析、数据库结果；
* **可安全删除：** 重复状态、无价值的中间措辞、已经被新结果完全覆盖的 observation；
* **只在局部有用：** 子任务探索细节、分支中的试错。

压缩系统的核心不是"把旧消息缩短"，而是先正确分类，再为每类信息选择不同生命周期。

---

## 四、方法一：硬截断、滑动窗口与规则裁剪

### 4.1 机制与触发

硬截断在达到 Token 上限时直接移除最旧消息；滑动窗口固定保留最近 N 轮或 N Token；规则裁剪可进一步优先删除 assistant reasoning、重复系统信息或指定类型消息。Google ADK 提供 token threshold、近期事件数和带 overlap 的 turn window；LangChain/LangGraph 提供 trim、delete 和自定义过滤。

### 4.2 优点

* 无额外模型调用，延迟和费用可预测；
* 实现简单，适合作为任何系统的最后一道防溢出保护；
* 近期对话主导、旧信息自然失效的场景中效果足够；
* 规则可保证 tool-call 与 tool-result 成对保留，避免消息序列非法。

### 4.3 主要失败模式

时间顺序不是价值顺序。最早的用户约束、架构决策或身份信息可能比最近的工具噪声更重要。硬截断没有语义判断，容易造成"迟到依赖"失败：任务后期突然需要一个早期约束，但它已永久消失。截断还会形成悬空的 tool result、缺少调用参数或丢失 system/user 边界；LangChain 文档特别提醒，裁剪后仍需保持合法消息结构与工具调用配对。

### 4.4 Token、延迟、KV-cache 和审计

* **峰值 Token：** 控制最直接；上限严格。
* **累计 Token：** 会下降，但每次仍重发整个窗口。
* **延迟：** 没有摘要调用，通常最低。
* **KV-cache：** 从头删除旧内容会改变前缀；标准 prefix cache 通常无法复用删除点之后的缓存。
* **恢复性：** 若没有外部日志则为零；有事件日志时可人工或程序回填。
* **审计性：** 规则本身易审计，但被删除信息与任务失败之间的因果很难追踪。

### 4.5 适用边界

适合聊天式短任务、无长期约束的会话、低风险 MVP 和防止窗口溢出的兜底。它不应作为长时程编码、研究、财务或合规 Agent 的主记忆机制。

---

## 五、方法二：Observation Masking / Tool-result Clearing

### 5.1 机制

该方法保留用户消息、Agent 决策和工具调用句柄，但删除或占位替换旧工具输出。较安全的版本会保留：URL、文件路径、对象 ID、查询语句、命令、时间戳、内容哈希和结果摘要。需要细节时，Agent 可再次读取原对象。

Anthropic 的 server-side context editing 提供 `clear_tool_uses_20250919`：在输入超过阈值时，按时间顺序清除最旧 tool results，并用占位文本告诉 Claude 内容已被移除；可设置保留最近若干次调用、每次至少清除多少 Token、排除某些工具，也可选择连 tool inputs 一起清除。客户端仍保存完整未修改历史，因此服务端裁剪不破坏本地审计日志。

同一套 API 还提供 `clear_thinking_20251015`，可保留最近 N 个 assistant turn 的 thinking blocks，或按模型默认策略清除更旧部分。它主要调节推理连续性、窗口占用与 prompt cache 之间的权衡，不能替代对工具证据和业务状态的管理。跨模型部署时应显式设置 `keep`，因为不同 Claude 型号的默认保留行为不同。

### 5.2 为什么它经常优于 LLM 摘要

编码轨迹中最大的 Token 消费者通常是可重读的文件、命令输出和测试日志。对它们生成摘要有三重成本：先把长内容读入摘要器，再生成摘要，再承担摘要遗漏；masking 则近似零生成成本，而且保留恢复路径。

The Complexity Trap 的同设置实验是目前最强的直接证据之一：

* observation masking 总成本约为 raw agent 的一半；
* Qwen3-Coder 480B 成本下降 52%，solve rate 提高 2.6 个百分点；
* hybrid 方案相对纯 masking 再省 7%，相对 LLM summarization 再省 11%。

这说明在 SWE 类任务上，"保留所有文字"可能因 context rot 反而伤害成功率。不过该结论不能直接外推到法律研究等需要逐字证据的任务。

### 5.3 失败模式

* Agent 忘记此前读取过什么，重复工具调用增多；
* 恢复句柄失效，例如网页变化、临时文件被删除或数据库快照更新；
* 删除工具输入后，无法知道旧输出由什么参数产生；
* 某段 observation 包含唯一且不可再现的错误现场，清除后无法复盘；
* 工具输出中的用户约束或安全信号没有被提升到工作状态，随正文一起消失。

因此应默认"清正文、留句柄"，对不可再现来源进行豁免，并把关键结论先提升到结构化状态。

### 5.4 KV-cache 影响

Anthropic 明确指出，清除旧 tool result 会使被清除位置之后的 cached prompt prefix 失效。因此不要每次只清几百 Token：应通过 `clear_at_least` 批量清除，使一次 cache rewrite 换来足够窗口收益。清除后形成的新前缀可在后续请求复用。这个 trade-off 在自建 masking 中同样存在。

### 5.5 综合评价

这是当前**风险最低、投入产出比最高**的第一层压缩，尤其适合代码、浏览、Shell、数据库和文档工具密集的 Agent。前提是外部材料有稳定标识、原始日志另行保存，并监控重复恢复次数。

---

## 六、方法三：结构化工作状态与任务账本

### 6.1 机制

与"把聊天总结成一段话"不同，结构化状态直接维护 Agent 继续工作所需的字段，例如：

```
goal: 用户最终目标
constraints: [硬约束与权限边界]
decisions: [已确认决策及依据]
completed: [已完成步骤与验证]
open_questions: [尚未解决的问题]
failed_attempts: [尝试、失败原因、不要重试条件]
artifacts: [路径、URL、对象ID、哈希]
next_actions: [按优先级排列的下一步]
evidence: [事实、来源、置信度]
```

Anthropic 的 context engineering 经验强调在 compaction 中保留架构决策、未解决问题、实现细节和近期文件；Manus 使用持续更新的 todo，并把文件系统当作外部上下文。两者本质上都是把"任务状态"从自然语言对话中提炼出来。

### 6.2 优点

* 字段强制覆盖关键类别，遗漏率通常低于无约束自由摘要；
* 可做 schema validation、diff、版本化和字段级审计；
* 可针对场景定制，例如编码 Agent 增加测试状态，研究 Agent 增加引文与反证；
* 支持确定性序列化，有利于稳定前缀和缓存；
* 与近期原文组合时，既保留精确细节又控制长度。

### 6.3 风险与工程复杂度

结构化不等于真实。状态更新仍可能把推测写成事实、覆盖正确旧值或忘记记录冲突。字段过少会丢细节，字段过多又退化成另一种长上下文。更新必须采用 append event + materialized view，而不是只有一个可覆盖 JSON；关键字段应记录来源和时间。

工程上还要解决并发分支合并、schema 迁移、引用完整性、敏感信息分级和冲突解决。其实现成本高于滑窗和 masking，但明显低于训练专用压缩策略。

### 6.4 推荐触发方式

不要只在窗口快满时才更新。更可靠的触发点包括：用户修改目标、完成里程碑、做出不可逆决策、工具返回关键证据、出现失败、分支结束，以及压缩前。Token 阈值只负责触发整体 compaction，不应是状态更新的唯一时机。

---

## 七、方法四：LLM 语义摘要与托管 Compaction

### 7.1 通用机制

当上下文达到阈值，模型把较旧历史转成较短的语义表示，保留近期消息原文；下一轮使用"摘要 + 近期历史"。实现可分为：

* 应用自己调用摘要模型；
* 框架中间件自动总结；
* 模型供应商返回专用 compaction item；
* 同一主模型在内部生成可读摘要块。

### 7.2 OpenAI Compaction

OpenAI Responses API 支持通过 `context_management.compact_threshold` 自动压缩，或调用 `/responses/compact` 主动生成 canonical next context。返回的是不透明、加密的 compaction item，可以通过 `previous_response_id` 或 stateless chaining 继续；`store=false` 可用于零数据保留工作流。对于 stateless 长链，官方建议可移除最近 compaction item 之前的内容以降低长尾延迟，但 `/responses/compact` 返回的 canonical items 不应再自行裁剪。

**工程影响：**

* 接入简单，供应商负责摘要格式与模型兼容性；
* 不透明 item 减少了开发者误改内部状态的风险；
* 但无法逐字段检查"保留了什么"，人类可读性和差异审计弱；
* 对特定事实的强制保留和迁移到其他模型供应商较困难；
* 官方文档没有给出跨任务的公开成功率、Token 和 cache A/B，因此应按 C 级证据看待。

### 7.3 Claude Compaction

Claude server-side compaction 使用 beta `compact-2026-01-12`，默认触发阈值 150K、最低 50K。摘要块是可读的，可通过 instructions 定制；`pause_after_compaction` 允许应用暂停，在摘要之后重新注入近期原文或自定义状态。它能与 prompt caching 结合，但 compaction 是额外采样，计费和限流需汇总 `usage.iterations`；摘要只能由原请求模型生成。有工具时摘要阶段可能偶发误调用工具，产生空 compaction block，应用需要兜底。

相对 OpenAI，它更可读、可定制、易审计；代价是应用要处理摘要质量、迭代 usage、暂停恢复和工具异常。两家的 API 目标相近，但不应仅凭"透明/不透明"断言谁的质量更高，因为都缺少公开统一基准。

### 7.4 LangChain/LangGraph 与 Google ADK

LangChain 的 `SummarizationMiddleware` 将摘要、近期消息和自定义过滤组合起来，适合需要掌控状态图的团队。Google ADK 支持 Token 阈值与 turn sliding window/overlap，可使用独立 summarizer 和自定义 prompt；若同时配置，token-based 规则优先。两者提供的是编排能力，不提供被广泛复现的压缩质量基准。

### 7.5 API 与框架能力对比

| 方案                            | 主要触发/控制                                  | 压缩产物                  | 可读与可定制                 | 恢复/审计特征                                  | 公开质量基准    |
| ----------------------------- | ---------------------------------------- | --------------------- | ---------------------- | ---------------------------------------- | --------- |
| OpenAI server-side compaction | 自动 threshold 或 /responses/compact        | 不透明加密 compaction item | 可读性低，字段控制弱             | 支持 stateful/stateless chaining；应用应另存事件日志 | 无统一公开 A/B |
| Claude server-side compaction | 默认 150K、最低 50K；可自定义 instructions         | 可读 compaction block   | 高；可暂停后回填近期原文           | 可检查摘要内容；需处理多 iteration usage 与空 block    | 无统一公开 A/B |
| Claude context editing        | Token threshold、保留次数、最少清除量、工具排除          | 被清除正文的占位符             | 规则高度可见                 | 客户端保留未修改历史；修改点后 cache 失效                 | 无统一公开 A/B |
| LangGraph/LangChain           | 中间件、trim/delete、定制 summary               | 应用自定义状态/消息            | 很高                     | 审计和恢复完全由应用负责                             | 无框架级统一基准  |
| Google ADK                    | token threshold 或带 overlap 的 turn window | summary event/近期事件    | 高；可换 summarizer/prompt | 可保留 overlap；应用负责原始会话存档                   | 无官方统一质量基准 |

选择时不应只看"自动化程度"。如果需要供应商无关迁移、字段级合规审计和可重建状态，应用层结构化方案更合适；如果目标是快速让单供应商长会话不超窗，托管 compaction 的实施成本最低。

### 7.6 自由摘要的系统性失败模式

1. **遗漏：** 摘要器不知道某个早期细节会在后期变重要。
2. **幻觉和确定性升级：** "可能"被写成"已经确认"。
3. **递归漂移：** 新摘要只读取旧摘要，错误逐轮累积。
4. **失败经验丢失：** 为追求简短而删掉"为什么不能这样做"。
5. **引用断裂：** 结论仍在，精确 URL、段落、文件行或对象版本消失。
6. **预算反转：** 短任务中摘要调用比省下的输入更贵、更慢。
7. **不可比较：** 峰值降低但总调用数上升，表面压缩率掩盖总成本。

### 7.7 安全实现原则

* 摘要应按固定 schema 写"工作状态"，而不是复述聊天；
* 永久保留原始事件日志，摘要只做物化视图；
* 给事实附来源句柄、时间和置信度；
* 保留最近若干轮原文，避免在压缩边界打断正在进行的推理；
* 周期性从原始日志重建，避免无限 `summary(summary)`；
* 用事实一致性、迟到依赖召回率和恢复调用数评估，而不只看摘要长度。

---

## 八、方法五：外部记忆、文件系统与按需检索

### 8.1 机制

外部化把大量内容移出活动窗口，保存到对象存储、文件系统、数据库、向量库或知识图谱；上下文只保留索引、短描述和恢复句柄。需要时通过关键词、embedding、图关系或元数据过滤取回少量片段。

Manus 的工程原则很实用：不要把 URL、路径、文档 ID 等可恢复句柄一起删掉；使用 append-only 状态和确定性序列化，使历史既可恢复又尽量 cache-friendly。Anthropic 则把即时加载、渐进披露和子 Agent 上下文隔离视为 context engineering 的组成部分。

### 8.2 Mem0 的证据及边界

Mem0 从对话中抽取显著记忆，进行新增、合并或删除，再按查询检索；图版本增加实体关系。在 LOCOMO 上，论文报告 LLM-as-Judge 相对 OpenAI Memory 提升约 26%，相对 full-context 的 p95 延迟降低 91%，Token 成本节省超过 90%。这是检索式长期记忆的强结果，但重点是跨会话个性化记忆，不等同于单个长任务中对工具轨迹的实时压缩；LLM-as-Judge 也会引入评估偏差。

### 8.3 失败模式

* 检索 query 没表达出真正的迟到依赖，相关材料永久"存在但不可见"；
* embedding 对精确数值、否定词、代码符号或低语义相似依赖召回不佳；
* 取回过多又造成二次 context rot；
* 外部对象更新后，句柄指向与当时不同的内容；
* 记忆合并把冲突事实错误覆盖；
* 跨租户权限过滤或敏感信息删除不完整。

因此应将向量检索与关键词、结构化过滤、时间/版本、图关系结合；对关键约束不要依赖检索，应常驻工作状态。

### 8.4 Token、延迟、KV-cache

检索显著降低活动上下文，但增加一次检索延迟和索引成本。每轮动态注入的不同片段会改变后部 prompt，静态系统前缀仍可命中 cache，动态段本身通常不能。若外部读取很慢，压缩节省可能被 I/O 抵消；应监控检索 p95、召回率和重复读取率。

---

## 九、方法六：子 Agent 隔离与 Context Folding

### 9.1 从手工隔离到可学习折叠

传统子 Agent 让不同角色在独立 context 中工作，父 Agent 只接收结果。这能隔离网页搜索、代码探索等 Token 密集过程，但通常依赖手工工作流，结果质量取决于委派 prompt 和回传格式。

Context Folding 把这个思想做成 Agent 可调用的两种动作：

* `branch(description, prompt)`：从主线程创建独立子轨迹；
* `return(message)`：结束分支，回滚到 branch 点，只把结果 message 追加到主线程。

分支内部的工具调用、观察和试错从主活动上下文中移除。论文采用 plan–execution 状态：主线做高层计划，分支做 Token 密集执行；执行态禁止嵌套分支，降低复杂度。

### 9.2 FoldGRPO 如何训练"会折叠"的 Agent

仅提供 branch/return 工具并不足以得到好行为。FoldGRPO 在结果奖励之外加入 token-level process rewards：

* 主线超过工作窗口 50% 时，对未分支的主线 Token施加 unfolded token penalty；
* 分支偏离任务时施加 out-of-scope penalty；
* 工具调用失败时施加 failure penalty。

这样模型同时学习何时分解、在分支中保持聚焦、回传哪些信息，以及如何在短主线状态上继续规划。

### 9.3 实验结果与正确解读

论文使用 Seed-OSS-36B-Instruct、32,768 活动窗口、最多 10 个分支，在 BrowseComp-Plus（N=150）与 SWE-bench Verified（N=500）上评测：

| 方法                     | BrowseComp-Plus Pass@1 | SWE-bench Verified Pass@1 | 活动窗口/最大轨迹预算  |
| ---------------------- | ---------------------- | ------------------------- | ------------ |
| 32K ReAct              | 28.6%                  | 43.6%                     | 32K / 32K    |
| 327K ReAct             | 47.8%                  | 55.2%                     | 327K / 327K  |
| 32K Summary Agent，GRPO | 52.7%                  | 55.0%                     | 32K / 32K×10 |
| Folding Agent，FoldGRPO | **62.0%**              | **58.0%**                 | 32K / 32K×10 |

FoldGRPO 相对未训练 folding 在两任务上分别提高 20.0 和 8.8 个百分点；相对普通 GRPO 的 folding 分别再提高 5.3 和 1.6 个百分点。行为统计中，FoldGRPO 把 BrowseComp 主线降至 7,752 Token、SWE 主线降至 8,885 Token，同时处理十万级总轨迹，作者称超过 90% active-context compression。案例中 4 个分支把 107K 完整轨迹折成 6K 主线。

必须注意：训练后 Agent 的工具调用更多，难题上的输出从约 100K 增至 160K 以上。因此它证明的是**用较小工作记忆完成更长探索并提高成功率**，不是证明总 Token 或总费用下降。它还只在一个 36B 基座、两个任务族上训练和评测，且最多单层分支；多层 folding 仍是未来工作。

### 9.4 KV-cache 的独特优势

调用 return 时，系统可把 KV-cache 回滚到 branch 位置；父线程前缀与创建分支前完全相同，因此可以复用父前缀 cache，只丢弃临时分支部分。这比改写早期摘要更 cache-friendly。代价是运行时必须支持分叉/回滚、分支存储、异常恢复和审计链拼接。

### 9.5 适用与不适用场景

适合可清晰分解的深度搜索、代码库探索、多对象调查和并行分析。不适合子任务高度耦合、必须共享全部细节、无法判断完成边界，或需要逐步完整审计而运行时又没有外部轨迹存储的场景。

---

## 十、方法七：训练式上下文压缩

这类方法把"如何压缩、何时压缩、如何从压缩状态继续工作"变成可学习能力。潜在上限高，但训练数据、奖励设计和部署复杂度也最高。

### 10.1 ACON：从压缩导致的成功/失败反差中学习

ACON 同时压缩 observation 和 history。它分析两类信号：原上下文能成功而压缩后失败的轨迹，用来发现哪些信息不能删；成功轨迹中真正被后续决策使用的信息，用来提高压缩率。优化结果可以是自然语言压缩规则，并可蒸馏到较小压缩模型。

在 AppWorld、OfficeBench 和 Multi-objective QA 的 15+ step 任务中，论文报告峰值 Token 降低 26%–54%，小模型 Agent 性能提高 20%–46%，蒸馏压缩器保留教师超过 95% 的性能。以 GPT-4.1/AppWorld 为例，无压缩 accuracy 56.0、peak 9.93K；最佳 history compression 为 56.5、peak 7.33K。

其价值在于压缩规则由任务失败反推，而不是靠通用 prompt 猜测。但它需要大量原始、压缩对照轨迹和昂贵离线评测；规则容易过拟合任务分布，遇到新工具或新约束需重新优化。证据为 B 级。

### 10.2 ReSum：周期状态重建 + continuation training

ReSum 周期调用外部摘要工具，将历史压成 compact state。压缩可由系统或 Agent 触发；论文选择系统触发，因为作者认为当前 Agent 自主管理上下文仍不可靠。ReSumTool-30B 专门学习提取证据、识别缺口和指引下一步；ReSum-GRPO 在每个摘要点切分轨迹，并把最终奖励 advantage 广播到各段，使 Agent 学会从摘要状态继续推理。

在 GAIA 文本验证集 103 条、BrowseComp 与 BrowseComp-zh，基于 3B/7B/30B WebSailor、32K 窗口、最多 60 次工具调用：training-free ReSum 相对 ReAct 平均绝对提高 4.5%；ReSum-GRPO 再平均提高 8.2%，只使用 1K 训练样本。WebSailor-3B 在 BrowseComp-zh 从 8.2% 升至 20.5%；30B Agent 配专用 30B 摘要器在 BrowseComp 达到 16.0% Pass@1。专用 30B 摘要器在其设置中可超过更大的通用摘要模型。

这说明任务专用摘要器和 continuation training 很重要。但实验主要来自搜索 Agent 内部设置，部分使用 LLM judge；更长探索会增加总计算，论文没有证明总 Token 成本下降。证据为 B 级。

### 10.3 MEM1：将递归记忆写进 Agent 策略

MEM1 不外挂摘要器。每轮模型生成内部状态 `<IS_t>`，融合旧状态、新 query 和新信息；下一轮只保留最新内部状态与当前交互，裁掉更旧思维、动作和工具输出。它基于 Qwen2.5-7B Base 用 PPO 训练，并通过二维 attention mask 在动态上下文上计算有效策略梯度，从而形成近常量工作记忆。

在 16-objective multi-hop QA 中，MEM1-QA 的 peak 为 1.04K、时间 8.70s；Qwen2.5-14B 为 3.84K、29.7s，即峰值约为后者 27.1%，时间约 29.3%。相对最佳未崩溃基线，论文报告峰值改善 1.27×、推理加速 1.78×，且只在 2-objective 训练后泛化到 16-objective。在 WebShop，MEM1 reward 70.87、peak 0.81K、2.61s；AgentLM-13B 为 70.80、2.36K、5.23s。

这是一种真正改变策略内部记忆方式的方法，适合有明确可验证奖励的 QA、数学和网页导航。问题是部署必须换成专门训练后的 Agent；递归覆盖一旦遗漏且没有外部事件日志就不可恢复，也很难解释某条事实为何消失。开放式研究、合规判断等奖励稀疏或含糊的任务不容易训练。证据为 B 级。

### 10.4 Active Context Compression：有前景但样本过小

该方法让 Focus Agent 自主写结构化 Knowledge block，并决定何时裁剪。SWE-bench Lite 的初步实验只有 N=5：总 Token 从 14.9M 降至 11.5M，减少 22.7%，准确率均为 3/5；单实例最多省 57%，另一个实例却增加 110%。它说明主动策略可能适应实例差异，也说明小样本均值会掩盖严重方差。当前只能列为 D 级原型，不能作为生产收益承诺。

---

## 十一、ACE：为什么"压得越短越好"会失败

Agentic Context Engineering（ACE）不是传统运行时压缩，而是对 context collapse 的修正。它把上下文视为持续演化的结构化 playbook，通过 Generator → Reflector → Curator 生成小型 delta bullets：新知识 append，已有知识原位更新，并用 embedding 去重。refinement 可每轮执行，也可在窗口接近上限时 lazy 执行。

这与反复全文重写的摘要有关键差异：旧策略不会仅因为下一轮总结措辞不同而整体消失；细粒度例外和失败经验可以累积。在 AppWorld 中，ReAct 平均 42.4；offline ACE 有 GT 为 59.4，无 GT 为 57.2，online ACE 无 GT 为 59.5。论文还报告相对所选强基线平均提升 10.6%。在适配成本上，offline AppWorld 的 ACE 相比 GEPA 时间下降 82.3%、rollout 减少 75.1%；online FiNER 相比 Dynamic Cheatsheet 时间下降 91.5%、费用下降 83.6%，平均适配延迟下降 86.9%。

但 ACE 会让 playbook 增长，所以它不能替代单条轨迹的 masking 或 compaction；必须结合检索、lazy refinement 和预算控制。强 Reflector 是关键依赖，无可靠反馈时错误经验会污染长期上下文；论文也显示金融任务在无 GT 时部分指标下降。HotPotQA、Game of 24 等规则简单任务不需要丰富 playbook。

ACE 对工程设计的启示是：**短期工作记忆应压缩，长期可复用知识应结构化演化；两者不能共用一段不断被改写的摘要。**

---

## 十二、KV-cache、稳定前缀与压缩的相互作用

### 12.1 什么能改善 cache

Manus 强调保持 prompt 前缀稳定、append-only 更新和确定性序列化。稳定的 system prompt、工具定义和不变任务约束应放在最前；动态检索、时间戳和随机序列化字段放后。这样服务商可复用前缀 KV-cache，降低重复 prefill 的成本和 TTFT。

### 12.2 各方法对 cache 的典型影响

| 方法              | 对 KV-cache 的影响                | 备注                    |
| --------------- | ----------------------------- | --------------------- |
| 仅追加完整历史         | 前缀最稳定，可持续命中                   | 但窗口和 context rot 持续增长 |
| 从头滑窗/硬截断        | 旧前缀整体变化，命中差                   | 实现最简单                 |
| 修改旧 observation | 从最早修改点起失效                     | 应批量清除而非频繁小清除          |
| 生成新摘要替换旧史       | compaction 边界发生 cache rewrite | 新摘要稳定后可建立新前缀          |
| 外部检索            | 静态前缀可复用，动态片段通常不可              | 检索片段应放在稳定段之后          |
| Context Folding | 可回滚到 branch 点并复用父前缀           | 临时分支 cache 被丢弃或单独保存   |
| 递归内部状态（MEM1）    | 每轮状态变化，动态段复用有限                | 静态系统前缀仍可缓存            |

OpenAI 的不透明 compaction item 是否具有额外内部 cache 优势，公开文档没有足够信息，不能推断。Claude context editing 则明确说明 clearing 会使相应位置之后的缓存失效。

### 12.3 不应把 cache 命中当成质量指标

缓存只减少重复计算，不会让模型更容易从 200K 噪声中找到关键事实。一个 99% cache hit、但充满旧日志的 prompt，仍可能比一个更短、需要重新 prefill 的结构化上下文表现差。生产优化目标应同时包含成功率、活动 Token、cache read/write Token、TTFT 和恢复次数。

---

## 十三、统一比较矩阵

评分为相对工程判断：高/中/低不是论文跨基准排名。

| 方法                  | 峰值 Token 控制 | 累计 Token 潜力 | 质量风险         | 可恢复性       | 人类可读/审计           | KV-cache 友好度 | 实现成本 | 最适场景           |
| ------------------- | ----------- | ----------- | ------------ | ---------- | ----------------- | ------------ | ---- | -------------- |
| 硬截断/滑窗              | 高           | 中           | 高            | 低，除非有日志    | 高（规则清楚）           | 低            | 低    | 短会话、兜底         |
| Observation masking | 高           | 高           | 低至中          | 高，若留句柄     | 高                 | 中偏低          | 低至中  | 编码、浏览、Shell    |
| 结构化工作状态             | 中至高         | 高           | 中            | 高，若有事件日志   | 高                 | 中至高          | 中    | 长任务通用基座        |
| 自由文本摘要              | 高           | 中           | 中至高          | 低至中        | 高                 | 中            | 中    | 低风险通用会话        |
| 厂商托管 compaction     | 高           | 中           | 中            | 取决于供应商/API | OpenAI 低、Claude 高 | 未统一披露        | 低    | 快速接入单供应商       |
| 外部记忆 + 检索           | 高           | 高           | 召回失败风险       | 高          | 高                 | 中            | 中至高  | 跨会话、知识密集       |
| 子 Agent 隔离          | 高           | 不确定         | 回传遗漏         | 高，若保存子轨迹   | 高                 | 高            | 中    | 可分解并行任务        |
| Context Folding     | 很高          | 不一定降低       | 分支/return 遗漏 | 高，若保存完整树   | 很高                | 很高           | 高    | 超长研究、SWE       |
| ACON                | 高           | 高           | 分布迁移         | 高，若外存原轨迹   | 中至高               | 取决于实现        | 高    | 有大量回放数据的产品     |
| ReSum-GRPO          | 高           | 不一定降低       | 摘要与续推双重风险    | 中          | 高                 | 中            | 很高   | 长程搜索 Agent     |
| MEM1                | 很高          | 高           | 递归状态不可逆      | 低，除非外存     | 低至中               | 中偏低          | 很高   | 可验证奖励的专用 Agent |
| ACE playbook        | 不是主目标       | 中           | 错误经验污染       | 高          | 高                 | 中            | 高    | 跨任务策略积累        |

---

## 十四、按场景选型

### 14.1 编码 Agent

首选 observation masking：旧文件正文、搜索结果和测试日志可移除，但保留路径、命令、测试名、diff、失败原因和 git 状态。常驻结构化状态应包含需求、架构决策、已改文件、验证命令、失败尝试和未解决问题。对大型代码库探索可使用子 Agent 或 folding。不要把未提交 diff 仅存于摘要；它应存在真实工作树和事件日志中。

### 14.2 Deep Research / 浏览 Agent

应把"结论"和"证据"分离：工作状态保存问题树、候选结论、冲突和下一步；外部证据库存 URL、标题、访问时间、原文片段和内容哈希。网页正文可 masking，但引用句柄不能丢。ReSum 或 folding 适合多轮搜索；最终写作前应执行一次证据回填和引用核验，而不能只依赖摘要。

### 14.3 客服与企业流程 Agent

最近对话原文应保留，用户身份、权限、承诺、工单状态和政策依据进入结构化字段；旧知识库结果可清除并按需重查。跨会话偏好可用 Mem0 类记忆，但必须提供删除、纠错、租户隔离和来源追踪。高风险承诺不可由模型摘要覆盖原记录。

### 14.4 金融、医疗、法律与合规

压缩只能生成工作视图，不能替代证据档案。所有决策相关原文、版本和审计链必须外存；关键数值和否定条件常驻结构化状态，且做 deterministic validation。优先 masking 可再获取材料，谨慎使用自由摘要；自动 compaction 前后应运行事实一致性检查。模型生成的内部状态不能作为唯一记录。

### 14.5 多 Agent 系统

每个 Agent 应有最小局部上下文，父 Agent 只接收结构化交付物；同时保存父子任务 ID、委派 prompt、来源和完整子轨迹。共享一段不断增长的群聊会抵消隔离收益。若采用 folding，应限制嵌套深度、定义超时/异常 return，并处理分支间事实冲突。

---

## 十五、推荐的生产架构

```
稳定且可缓存的系统前缀
        │
        ├── 用户目标、硬约束、权限、安全策略
        │
        ├── 结构化工作状态（可版本化、带来源）
        │
        ├── 最近 N 轮原文
        │
        └── 按需检索的外部片段

不可变事件日志 ──> 状态构建器/压缩器 ──> 当前活动上下文
       │                         │
       ├── 文件、URL、对象 ID     ├── observation masking
       ├── 全量工具输入/输出       ├── 阈值 compaction
       └── 分支/子 Agent 全轨迹    └── 恢复与引用回填
```

### 15.1 建议的执行顺序

1. **先测量再压缩。** 记录每种消息类型的 Token、重复率、cache hit、p50/p95 延迟和成功率。
2. **先做无损外部化。** 所有原始工具结果、文件版本和网页证据进入事件/对象存储。
3. **删除可再生成的大对象。** 默认清旧 observation，保留恢复句柄和关键结论。
4. **建立结构化工作状态。** 把目标、约束、决策、失败和下一步从对话中独立出来。
5. **保留近期原文。** 在摘要边界后留足连续上下文，避免打断当前思路。
6. **达到高水位才做语义 compaction。** 使用滞回阈值，例如 70% 触发、压到 35%–45%，避免频繁重写和 cache 抖动。
7. **定期从原始日志重建。** 不允许无限递归 `summary(summary)`。
8. **复杂子任务使用隔离上下文。** 先从静态委派开始，有充足训练数据再考虑 FoldGRPO。
9. **把压缩策略纳入 eval。** 每次模型、工具、schema 或 prompt 变更都回放长轨迹。

### 15.2 建议的默认保留策略

* 永不自动删除：原始用户目标、权限、安全约束、不可逆决策、审计 ID；
* 有条件删除：旧工具正文、长日志、重复文件内容、已失效检索片段；
* 删除前提升：唯一错误现场、关键数值、引用、失败原因；
* 永远留句柄：URL、路径、查询、命令、对象 ID、版本、哈希；
* 近期保留：最近 3–8 个有效 turn 或一个完整任务阶段，而不是机械消息条数。

---

## 十六、评测方案：怎样知道压缩没有把 Agent 变笨

### 16.1 核心指标

| 维度   | 建议指标                                                     |
| ---- | -------------------------------------------------------- |
| 任务质量 | 成功率、Pass@1、部分完成率、人工验收率                                   |
| 上下文  | 峰值活动 Token、平均活动 Token、压缩比                                |
| 成本   | 累计 uncached input、cache read/write、output、压缩器 Token、工具费用 |
| 延迟   | TTFT、单轮 p50/p95、任务 p50/p95、压缩暂停时间                        |
| 信息保持 | 迟到依赖召回率、关键约束保持率、事实矛盾率、引用可恢复率                             |
| 行为   | 重复工具调用率、恢复调用次数、无效循环率、分支完成率                               |
| 稳定性  | 摘要漂移率、不同随机种子方差、超窗率、空 compaction 率                        |
| 审计   | 每个结论的来源覆盖率、状态 diff 可解释率、事件日志完整率                          |

### 16.2 必做的对照组

至少比较：full context、固定滑窗、observation masking、结构化状态 + masking、语义 compaction，以及最终混合方案。不要只与"完全不管理上下文"的弱基线比较。所有组使用相同模型、工具、最大行动数、温度和终止条件；分别给出成功率、峰值和累计 Token。

### 16.3 专门构造的压缩压力测试

* **迟到依赖：** 在第 1 轮给出约束，第 30 轮才需要；
* **相似干扰：** 放入多个近似数字、文件名或人名；
* **失败记忆：** 前期尝试已证明无效，观察后期是否重复；
* **引用恢复：** 摘要后要求给出原 URL、段落或文件行；
* **目标变更：** 中途修改需求，检查旧目标是否错误残留；
* **不可再现 observation：** 临时网页或一次性日志，验证豁免机制；
* **分支合并：** 两个子 Agent 给出冲突结论，检查父状态如何保留分歧；
* **cache 抖动：** 高频小压缩与低频批量压缩对 TTFT/费用的影响。

### 16.4 上线门槛示例

生产团队可设定：相对 full-context 成功率下降不超过 1–2 个百分点；关键约束保持率 ≥99%；引用可恢复率 ≥99%；p95 活动 Token 至少下降 40%；压缩器额外费用不超过节省输入费用的 20%；重复工具调用增幅不超过 10%。具体阈值应按业务风险调整，不是通用行业标准。

---

## 十七、2026 年趋势判断

1. **从"压缩文本"转向"管理状态"。** 压缩器会越来越像数据库物化视图维护器：字段化、版本化、带来源、可重建。
2. **从固定阈值转向价值感知触发。** Token 高水位仍是安全阀，但里程碑、决策、失败、分支完成等语义事件会成为主要触发。
3. **从外挂摘要器转向 joint optimization。** ReSum、MEM1、ACON、FoldGRPO 说明压缩与 continuation policy 将联合训练。
4. **树形轨迹会替代单一线性历史。** 研究和编码任务天然有分支；未来会出现多层 folding、分支 cache 管理和冲突合并。
5. **可恢复压缩会成为高风险系统的默认要求。** 删除正文但保留句柄、原始事件不可变、摘要可重建，比单一"聪明摘要"更可靠。
6. **成本报告会更严格。** 只报 active context compression 将不再足够；必须同时披露累计 Token、额外模型调用、cache write/read 和端到端延迟。
7. **压缩安全将形成独立 eval 类别。** 迟到依赖、否定条件、引用完整性、敏感信息删除和跨租户隔离会成为标准测试。

---

## 十八、最终建议

如果今天建设一个通用长时程 Agent，不建议从训练专用压缩模型开始。最合理的路径是：

1. 用不可变事件日志保证所有信息可恢复；
2. 对旧工具输出做 observation masking，保留恢复句柄；
3. 维护带来源的结构化工作状态，并保留近期原文；
4. 在高水位做低频、批量语义 compaction；
5. 对外部材料按需检索，对可分解探索使用隔离子上下文；
6. 通过长轨迹回放评测迟到依赖、引用、失败记忆和总成本；
7. 只有当任务稳定、奖励可验证且数据充足时，才投资 ACON/ReSum/MEM1/FoldGRPO。

一句话概括：**把"原始事实"存下来，把"当前状态"写清楚，把"可再生成的正文"移出去，把"局部探索"隔离开；压缩应当可恢复、可评测，而不是只追求一段更短的摘要。**

---

## 十九、一手来源

### 厂商与框架文档

1. Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).
2. Anthropic, [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction).
3. Anthropic, [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing).
4. OpenAI, [Compaction guide](https://developers.openai.com/api/docs/guides/compaction).
5. Manus, [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-Agents-Lessons-from-Building-Manus).
6. LangChain, [Short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory).
7. Google Agent Development Kit, [Context compaction](https://adk.dev/context/compaction/).

### 论文与实验

1. JetBrains Research et al., [The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management](https://arxiv.org/html/2508.21433), 2025.
2. ACON, [Training-Free and Learnable Agent Context Optimization](https://arxiv.org/html/2510.00615), 2025.
3. ByteDance Seed et al., [Scaling Long-Horizon LLM Agent via Context-Folding](https://arxiv.org/abs/2510.11967), 2025; [project page](https://context-folding.github.io/).
4. ReSum, [ReSum: Unlocking Long-Horizon Search Intelligence via Context Summarization](https://arxiv.org/html/2509.13313), arXiv v3, 2026-03-26.
5. MEM1, [Learning to Synergize Memory and Reasoning for Efficient Long-Horizon Agents](https://arxiv.org/html/2506.15841), 2025; [project page](https://mit-mi.github.io/mem1-site/).
6. Mem0, [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/html/2504.19413), 2025.
7. Active Context Compression, [Active Context Compression: Autonomous Memory Management in LLM Agents](https://arxiv.org/html/2601.07190), 2026.
8. ACE, [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models](https://arxiv.org/html/2510.04618v1), 2025.
9. Chroma Research, [Context Rot: How Increasing Input Tokens Impacts LLM Performance](https://www.trychroma.com/research/context-rot), 2025.

### 证据边界声明

* 厂商文档用于确认 API 行为与生产建议，不代表存在公开、可复现的质量提升基准。
* 论文数据按作者报告复述；不同论文之间没有统一模型、任务、预算和评分器，不能直接横向排名。
* Context Folding 的"10×/90%+"指活动主上下文，不代表总生成 Token 或总费用等比例下降。
* MEM1 的多目标 QA 指标与一般单题 accuracy 口径不同，本文只做同论文基线内解释。
* Active Context Compression 只有 N=5，应视为原型证据。
* 研究截止 2026-08-27；此后 API beta 名称、阈值、定价或论文版本可能变化。
