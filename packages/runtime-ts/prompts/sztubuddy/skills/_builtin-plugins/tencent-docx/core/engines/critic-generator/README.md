# Critic-Generator Engine 参数字典

> 本文档是 `critic-generator/engine.md` 的**配套参数文档**，回答 Expert 作者的两个问题：
> 1. 本引擎**可以通过哪些旋钮控制**？（§二 参数清单）
> 2. 我的场景**该传什么值**？（§三 场景模板 / §四 反模式）
>
> **使用方式**：Expert 在自己的 SKILL.md 里，在需要调用本引擎的 Phase 中**显式声明参数**。引擎协议本身不含参数值，只负责按传入参数执行状态机。

---


## 二、参数清单

### 2.1 完整参数总览

| 参数 | 类型 | 必填 | 默认值 | 一句话语义 |
| --- | --- | --- | --- | --- |
| `draft` | string | ✅ | — | 待审文本（章节 / 全文 / 已重写稿） |
| `rubrics_files` | list | ✅ | — | 评分尺规文件路径清单（定义维度与评分标准） |
| `scope` | enum | ✅ | — | 审查范围：`section` / `full` / `revision` |
| `max_loops` | int | ❌ | `2` | 允许的 REVISE 轮次上限 |
| `loop_index` | int | ❌ | `0` | 当前轮次（由调用方维护并传入） |
| `pass_score` | number | ❌ | `75` | 维度通过阈值（score < pass_score 即算扣分） |
| `min_issues` | int | ❌ | `2` | 强制否定配额：至少 N 个维度扣分 |
| `min_instructions` | int | ❌ | `3` | 强制指令配额：至少 M 条改进指令 |
| `profile` | object | ❌ | `null` | 需求画像（文档类型/受众/风格/规模），用于盲审包 |
| `source_facts` | list | ❌ | `[]` | Phase 2 搜索素材清单（标题+来源+Tier），用于盲审包 |
| `prev_instructions` | list | ❌ | `[]` | 上一轮 P0 扣分指令（scope=revision 时必填） |
| `report_path` | string | ❌ | `output/critic/{title}_critic_r{loop}.md` | 评审报告落盘路径 |

### 2.2 每个参数详解

#### `draft` — 待审文本
- **作用**：进入 Step ① Isolate 时的核心输入
- **写法**：Markdown 或纯文本；若为 section 则只传该章节内容
- **禁止**：塞入推理过程、内部注释、生成时的思考链

#### `rubrics_files` — 评分尺规
- **作用**：Step ② LoadRubrics 要加载的尺规文件路径清单
- **关键约定**：**引擎本身不定义评分维度**，维度完全由 rubrics 文件决定
- **典型内容**：
  - L1：`references/quality-framework.md`（通用 7 维）
  - L2：`references/anti-patterns.md` + `references/terms-library.md`（领域反模式 + 术语库）
- **空列表视为违约**：至少传 1 份，加载失败即中断状态机

#### `scope` — 审查范围
- **作用**：告知引擎本次审查的粒度，影响 Challenge 配额策略
- **取值**：
  - `"section"` → 审查单个章节/段落，配额可适度降低
  - `"full"` → 审查全文，完整配额，强制否定全维度
  - `"revision"` → 定向复审前一轮扣分点，只审 `prev_instructions` 涉及维度

#### `max_loops` — REVISE 轮次上限
- **作用**：防止 Expert 和引擎反复调用进入死循环
- **取值**：
  - `1` → 一次审查即止，不允许 REVISE（快速任务）
  - `2` → 允许 1 次重写 → 二轮验收（默认，适合大多数场景）
  - `3` → 允许 2 次重写（高质量领域专家，如 L2 法律合同）

#### `loop_index` — 当前轮次
- **作用**：Expert 维护并传入，引擎据此判断是否该进入 DEGRADED
- **首次调用传 `0`**；重写后再次调用传 `1`、`2`…
- **注意**：`loop_index >= max_loops` 且仍有 P0 时，引擎返回 `DEGRADED`

#### `pass_score` — 维度通过阈值
- **作用**：Step ③ Score 判定某维度是否算"扣分"
- **取值指南**：
  - 60–70：宽松（兜底场景，允许瑕疵）
  - 75：默认（L1 通用写作）
  - 80–85：严格（L2 领域专家）
  - 90+：极严（合同/法律/医疗等高风险场景）
- **量纲对齐**：若 rubrics 用 1–5 分制，`pass_score` 应写为 3、4、4.5 等；若 100 分制则直接写 75、85

#### `min_issues` — 强制扣分配额
- **作用**：防止"全部通过"，要求至少 N 个维度未满分
- **取值**：
  - `scope=section`：建议 1–2
  - `scope=full`：建议 2–3
  - `scope=revision`：建议 1

#### `min_instructions` — 强制指令配额
- **作用**：防止"没啥好改的"，要求至少产出 M 条具体改进指令
- **取值**：
  - `scope=section`：2–3
  - `scope=full`：3–5
  - `scope=revision`：1–2

#### `profile` — 需求画像
- **作用**：盲审包的一部分，提供受众/风格上下文
- **典型结构**：
  ```yaml
  type: "report"
  subtype: "调研报告"
  audience: "中层管理"
  style: "商务书面体"
  industry: "AI"
  size: "7000字"
  ```
- **可选**：若 Expert 的 Phase 1 已产出此画像，建议传入

#### `source_facts` — 可查证素材
- **作用**：盲审包的一部分，供 Score 核验事实溯源
- **结构**：沿用 Research Extract 五元组（`fact / source / tier / dimension / timestamp`）或精简版（`title / source / tier`）
- **用途**：Score 审查"数据溯源率"时，需要知道哪些素材是权威源

#### `prev_instructions` — 上轮扣分指令
- **作用**：`scope=revision` 时必填，告知引擎"这次只审哪些点"
- **典型结构**：上一轮 Critic 报告里 P0 指令的原样 YAML
- **配合**：Expert 重写完后再调用引擎时，同时传入 `prev_instructions` 和 `loop_index+1`

#### `report_path` — 评审报告路径
- **作用**：Step ⑥ Report 的输出文件路径
- **默认值**：`output/critic/{title}_critic_r{loop}.md`（变量由引擎展开）
- **建议按 loop 区分**：第一轮 `_r0.md`、二轮 `_r1.md`，保留历史轨迹
