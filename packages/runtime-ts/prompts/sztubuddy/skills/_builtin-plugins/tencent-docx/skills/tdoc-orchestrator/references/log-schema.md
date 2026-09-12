# Pipeline Log Schema — 完整字段定义

> 本文件定义弹性流水线的结构化日志字段（`trace/pipeline.log`，JSON Lines）。SKILL.md 中仅展示核心字段，此处为完整定义。
>
> **与 `pipeline-state.yaml` 的分工**：
> - `pipeline.log` 记**每次路由决策**（怎么判的、走了哪条路、耗时）——面向"决策回溯"。
> - `pipeline-state.yaml` 记**流转与产物**（各 Stage 状态、产物路径）——面向"进度与产物溯源"。
> - 两者共有的 `entry` 取值以 `SKILL.md §Stage 0 → 常见预设` 表为准，本文件不重复定义其 Stage 链。

---

## 日志模板

```
[Pipeline Log] request_id=<uuid>
  entry: <入口类型>
  stage: <1|2|3>
  intent_length: <用户意图文本字符数>
  has_existing_doc: <true|false>
  context_signals: [<有值的上下文信号字段名>]
  route: <路由标签>
  decision_path: <context_signal|intent_analysis|clarification|environment_detect|user_confirmation>
  target_skill: <目标子 Skill/能力名称>
  fallback: <true|false>
  fallback_reason: <降级原因，无降级时省略>
  stage_skipped: <true|false>
  skip_reason: <跳过原因，未跳过时省略>
  duration_ms: <本 Stage 路由决策耗时>
```

---

## 字段定义

| 字段               | 类型     | 必填 | 说明                                                                                                |
| ------------------ | -------- | ---- | --------------------------------------------------------------------------------------------------- |
| `request_id`       | string   | ✅   | 唯一请求 ID，同一次请求所有 Stage 共享                                                              |
| `entry`            | enum     | ✅   | 入口类型（本 skill 承接）：full_pipeline / beautify_only（编辑类意图直接转给 `tencent-docs-routing` skill 处理，不进本 log）                                    |
| `output_docx_path` | string   | ❌   | Stage 0 写入 pipeline-state.yaml 的最终 .docx 路径（仅 Stage 0 日志建议记录）                      |
| `output_docx_user_specified` | boolean | ❌ | 是否用户显式指定输出路径（仅 Stage 0 日志建议记录）                                                |
| `stage`            | number   | ✅   | Stage 编号：1 / 2 / 3                                                                               |
| `intent_length`    | number   | ✅   | 用户意图文本长度（不记录原文，保护隐私）                                                            |
| `has_existing_doc` | boolean  | ✅   | 用户是否提供了已有文档                                                                              |
| `context_signals`  | string[] | ✅   | 有值的上下文信号字段名（如 `['expert_id', 'in_document']`）                                         |
| `route`            | string   | ✅   | 路由标签（见 SKILL.md 各 Stage 的 route 列）                                                        |
| `decision_path`    | enum     | ✅   | 决策路径：context_signal / intent_analysis / clarification / environment_detect / user_confirmation |
| `target_skill`     | string   | ✅   | 路由到的子 Skill / 能力名称                                                                         |
| `fallback`         | boolean  | ✅   | 是否为降级路由                                                                                      |
| `fallback_reason`  | string   | ❌   | 降级原因（仅 fallback=true 时填写）                                                                 |
| `stage_skipped`    | boolean  | ✅   | 本 Stage 是否被跳过（弹性入口导致）                                                                 |
| `skip_reason`      | string   | ❌   | 跳过原因（仅 stage_skipped=true 时填写）                                                            |
| `duration_ms`      | number   | ✅   | 本 Stage 路由决策耗时（毫秒）                                                                       |

---

## Entry 枚举值

本编排层承接的入口仅 `full_pipeline` / `beautify_only`，各自的 Stage 链见 `SKILL.md §Stage 0 → 常见预设`（唯一真相源），此处不重复。

> 编辑类意图（在既有 .docx 上改动/润色等）**不进本 skill、不写本 log**——识别到即直接转给 `tencent-docs-routing` skill 处理。

## Route 标签

`route` 字段由**各 Stage 的执行子 Agent** 填写，其取值由对应子 Agent 定义（见 `agents/doc-writer.md` / `agents/doc-formatter.md` / `agents/doc-converter.md`）。
本文件不枚举子 Agent 的内部 route 名，避免与子 Agent 漂移。

## Decision Path 枚举值

| 值                   | 含义                     |
| -------------------- | ------------------------ |
| `context_signal`     | 通过确定性信号直接判定   |
| `intent_analysis`    | 通过意图分析推断         |
| `clarification`      | 追问后由用户选择         |
| `environment_detect` | 通过运行环境检测         |
| `user_confirmation`  | 追问澄清后由用户确认入口 |
