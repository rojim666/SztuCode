# Pipeline State Protocol — 溯源记录参考

> 本文件是 `SKILL.md` §"Pipeline State & Log"的详细版本。
> **定位：`pipeline-state.yaml` 是本次 Pipeline 的溯源记录（audit trail），不是执行锁。**
> 每个 Stage 完成后追加写入自己的产物与决策，便于事后回溯与问题定位。
> 子 Agent 需要了解字段细节时读取本文件。

---

## Schema（v1）

```yaml
schema_version: 1
request_id: <uuid-v4>
created_at: <ISO-8601>
updated_at: <ISO-8601>

entry_type: full_pipeline | beautify_only
                          # 本编排层承接的入口仅这两种（均以 S3 doc-converter 转换收尾）
                          # ⚠️ 编辑类意图（含润色）不进本 skill——识别到即直接转给 tencent-docs-routing skill 处理
stage_chain: [1, 2, 3]    # 由 entry_type 映射，映射表见 SKILL.md §Stage 0 → 常见预设（唯一真相源）

# 最终 .docx 交付路径（Stage 0 解析为绝对路径并写入）
output_docx_path: string              # 绝对路径
output_docx_user_specified: boolean   # 溯源：用户指定 vs 编排层默认

current_stage: 0 | 1 | 2 | 3 | completed

stages:
  stage_0:
    status: pending | completed
    completed_at: null | <ISO-8601>
    decision: <entry_type>

  stage_1:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    output_path: null | "stage1/final_draft.md"
    genre: null | <string>
    expert_used: null | <string>
    route_tag: null | <string>
    critic_decision: null | PASS | DEGRADED

  stage_2:
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    route: null | html                                    # 美化恒为 html（doc-formatter 只产 html）
    html_sub: null | template | imitate
    output_path: null | "stage2/formatted-<主题>.html"    # 写实际文件名
    output_format: null | html                            # 恒为 html
    skills_invoked: []
    design_tokens_path: null | "stage2/design_tokens.json"
    fallback: false
    fallback_reason: null

  stage_3:                                              # 本编排层内 S3 = doc-converter（HTML→DOCX 转换 + present_files）
    status: pending | in_progress | completed | skipped
    started_at: null | <ISO-8601>
    completed_at: null | <ISO-8601>
    executor: null | "doc-converter"                      # 本编排层内恒为 doc-converter
    input_format: null | html                             # 恒为 html
    output_path: null | <同 output_docx_path>
    skill_used: []                                        # 有序数组：本次 S3 调用的 Skill；本编排层内恒为 ["html-to-docx"]
    present_files_opened: false                           # doc-converter 是否已调用 present_files 打开 .docx 预览（硬约束）
    fallback: false                                       # 仅 doc-converter 转换失败时为 true
    fallback_reason: null                                 # html_to_docx_failed | null

    # ⚠️ 编辑 / 对齐注入（edit_only / inject_fill）不在本 skill 内承接：
    #    识别到即直接转给 tencent-docs-routing skill 处理，
    #    由其新起独立的 request_id / pipeline-state.yaml，不在本轮内累积。

consistency_check:                 # 结束时如实留痕，不阻塞交付（见下）
  output_files_exist: null | pass | fail
  stage_chain_complete: null | pass | fail
  last_checked_at: null | <ISO-8601>
  errors: []
```

---

## 写入时机（三个节点）

溯源记录是**单写者、追加式**的——同一次请求由编排流程顺序写入，无需锁、无需原子 tmp+rename、无需启动时校验拒绝执行。

| 节点                   | 动作                                                                                                                                                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Stage 0 判定入口后** | 创建 `output/<request_id>/` 目录结构；调用 `resolve_output_docx_path.py` 取得 `output_docx_path`；写入 `schema_version / request_id / created_at / entry_type / stage_chain / current_stage / output_docx_path / output_docx_user_specified`；`stage_chain` 内各 stage 设 `pending`，不在链中的设 `skipped`                   |
| **每个 Stage 完成后**  | 更新该 stage 块（`status: completed` + `completed_at` + `output_path`(实际文件名) + 其他字段）；推进 `current_stage`（链中下一个，或 `completed`）；更新 `updated_at`；**先写 YAML 再声明 `[Stage N 完成]` 检查点** |
| **Stage 3 完成后**     | 本编排层内 S3 = **doc-converter**（HTML→DOCX 转换）：完成时写入 `stage_3.executor="doc-converter"` / `skill_used=["html-to-docx"]` / `output_path` 落盘 / `present_files_opened=true`（doc-converter 内部硬约束），`status` 置为 `completed`，本 skill 调用结束。**编辑 / 对齐注入（edit_only / inject_fill）不在本 skill 内**——识别到即直接转给 `tencent-docs-routing` skill 处理，由其新起 `request_id` / `pipeline-state.yaml` |
| **Pipeline 结束**      | 写 `consistency_check`（见下）                                                                                                                                                                                    |

> `stage_chain` 的取值由 `entry_type` 决定，映射表以 `SKILL.md §Stage 0 → 常见预设` 为唯一真相源，本文件不重复定义。

### Stage 3 写入规则（单一执行者 doc-converter）

本编排层内 Stage 3 只有一个执行者 **doc-converter**（HTML→DOCX 转换 + present_files 打开预览），写入行为如下：

| 场景                          | executor            | skill_used            | 硬约束                                                          | status 推进节奏                                                     |
| ----------------------------- | ------------------- | --------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------- |
| 转换 + 预览（S3）             | `"doc-converter"`   | `["html-to-docx"]`    | 拿到 .docx **必须**立即 `present_files` 打开预览 → 记 `present_files_opened=true` | doc-converter 完成即 `completed`，本 skill 调用结束   |

> **编辑 / 对齐注入不在本 skill 内**：命中 `edit_only` / `inject_fill` 时，本 skill 不介入 Stage 3——识别到即直接转给 `tencent-docs-routing` skill 处理（由其新起独立的 `request_id` / `pipeline-state.yaml`），不在本轮 `stage_3` 内累积写入。因此本文件的 S3 写入是**单写者一次性收尾**（`doc-converter` 完成即 `completed`），无需锁、无中间态。
>
> **`fallback` 归属**：仅 `doc-converter` 转换失败时置 `true`（`fallback_reason=html_to_docx_failed`）；其他失败模式不在本编排层内出现。
>
> **`present_files_opened` 硬约束**：doc-converter 拿到 .docx 后**必须**立即调用 `present_files` 工具打开预览，并在 pipeline-state.yaml 中置 `present_files_opened=true`；未开预览即声明完成 = S3 未完成（详见 `agents/doc-converter.md` §6 纪律约束 3）。

---

## 输出目录规范

Pipeline 中间产物落在 `output/<request_id>/` 下；最终 .docx 交付路径由顶层 `output_docx_path` 决定。

```
<workspace>/output/<request_id>/
├── pipeline-state.yaml              # 溯源记录（含 output_docx_path）
├── stage1/
│   └── final_draft.md               # Stage 1 创作产物（标准 Markdown）
├── stage2/
│   ├── design_tokens.json           # design-token 输出（html-template / html-imitate）
│   └── formatted-<主题>.html        # 美化产物
├── stage3/
│   └── <文件名>.docx                # 仅当 output_docx_user_specified=false 时落在此目录
├── working/                         # 临时文件（结束后可清理）
└── trace/
    └── pipeline.log                 # 结构化日志（JSON Lines）
```

### 输出路径规范（`output_docx_path`）

Stage 0 调用 `scripts/wb/local/resolve_output_docx_path.py`，将返回的 `output_docx_path` / `output_docx_user_specified` 写入 yaml；doc-converter 原样使用。

```bash
python3 <plugin_root>/scripts/wb/local/resolve_output_docx_path.py \
  --workspace <workspace> --request-id <request_id> \
  [--user-path "<路径>"] [--filename "<主题>.docx"]
```

用户指定路径 → `--user-path`；未指定 → `--filename` + `--request-id`。`stage_3.output_path` 与顶层 `output_docx_path` 同值。脚本参数与错误码见脚本文件头。

### 命名规则

1. `stage1/final_draft.md` 用固定名。
2. **`stage2` 的 HTML 允许带主题后缀**（如 `formatted-文化东方.html`）。`output_path` 必须写**实际生成的文件名**，不得写占位固定名——否则溯源路径与磁盘不符（这是历史 bug）。
3. **`stage3` 的 .docx 路径由 `output_docx_path` 决定**（Stage 0 脚本 resolve）。
4. 图片资源放 `stage2/images/`，HTML 中用相对路径。
5. Trace 文件放 `trace/`，与产物分离。

---

## consistency_check（结果留痕，非阻塞）

Pipeline 结束时（`current_stage = completed`）做一次**如实检查**并记录，用于溯源，**不阻塞交付**：

```
1. 对 stages 中每个非 null 的 output_path，实际检查文件是否存在且非空
   （`stage_3` 以顶层 `output_docx_path` 绝对路径为准）
   → 全部存在：output_files_exist = pass；否则 = fail 并把缺失路径写入 errors
2. 检查 stage_chain 中每个 stage 是否都为 completed
   → 是：stage_chain_complete = pass；否则 = fail 并记录缺失 stage
3. 写 last_checked_at
4. 无论 pass/fail 都交付最终产物；fail 仅作为溯源信息保留在 errors
```

> ⚠️ 检查必须**真实 stat 文件**，不得在路径与磁盘不符时仍报 `pass`（历史上出现过 `output_path` 写固定名而实际文件带主题后缀、却报 pass 的情况）。
