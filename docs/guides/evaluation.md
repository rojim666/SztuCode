# SztuCode Coding Agent 评测指南

[返回文档中心](../README.md)

`npm run eval` 是统一的 TypeScript 评测入口。它负责加载版本化任务、为每次运行创建隔离工作区、调用可替换
runner、执行独立验证，并同时生成机器可读 JSON 与人类可读 Markdown 报告。

评测结果区分三件事：

- runner 是否正常完成；
- 任务验证是否通过；
- SWE-bench patch 是否经过官方 harness 评分。

只生成 patch 的 SWE-bench 运行会标为 `unscored`，不会被统计成成功。

## 环境准备

TypeScript 评测主链不需要 Python 环境，不调用真实模型 API，也不需要 Docker：

```bash
npm install
npm run eval -- validate --manifest packages/evaluation/tasks/internal-v1.json
```

使用 `sztucode-rpc` runner 时，需要先按[配置参考](../getting-started/configuration.md)配置模型并启动
daemon：

```bash
npm run build
npm run daemon
```

SWE-bench 的最终评分必须使用官方 Docker harness。官方文档建议准备 x86_64 环境、Docker、至少
120 GB 可用磁盘和 16 GB 内存。普通 CI 不运行这一步。

## 快速开始

列出任务：

```bash
npm run eval -- list --manifest packages/evaluation/tasks/internal-v1.json
```

用离线 reference runner 验证 10 个内部任务，每个重复三次：

```bash
npm run eval -- run --manifest packages/evaluation/tasks/internal-v1.json --repeat 3 --output-dir tmp/eval/internal-reference
```

输出目录包含：

```text
tmp/eval/internal-reference/
├── report.json   # 完整运行记录、聚合指标和失败原因
└── summary.md    # 面向人类的指标表和稳定性汇总
```

reference runner 只证明任务 fixture、验证器、指标聚合和报告链路可复现，不代表模型能力分数。

## Runner

| Runner | 用途 | 外部依赖 | 评分语义 |
| --- | --- | --- | --- |
| `reference` | 验证内部任务和评测框架 | 无 | 运行独立验证命令 |
| `command` | 接入任意外部 Agent | 用户提供命令 | 内部任务由验证命令评分 |
| `sztucode-rpc` | 通过 daemon 运行 SztuCode | daemon 与模型配置 | 内部任务评分；SWE-bench 仅产出 patch |

### SztuCode daemon runner

默认使用 `accept_edits` 权限。全自动评测如需运行命令，可以显式启用仅限临时评测工作区的
`auto` 模式：

```bash
npm run eval -- run \
  --suite internal \
  --runner sztucode-rpc \
  --permission-mode auto \
  --allow-auto-permissions \
  --repeat 3 \
  --timeout 600 \
  --output-dir tmp/eval/internal-agent
```

缺少 `--allow-auto-permissions` 时命令会在连接 daemon 前拒绝执行。runner 会先保存 daemon 当前
权限模式，并在成功、失败或超时后的清理阶段恢复。权限模式在 daemon 内是全局状态，因此不要让
评测与其他会话并发共享同一 daemon，自动化环境应使用专用实例。默认工作区位于系统临时目录，
运行结束自动删除；只有显式传入 `--keep-workspaces` 才会保留到报告目录。

### 外部命令 runner

command runner 直接执行解析后的 argv，不经过 Shell：

```bash
npm run eval -- run \
  --suite internal \
  --runner command \
  --command "node path/to/agent_adapter.mjs" \
  --output-dir tmp/eval/custom-agent
```

外部进程从环境变量取得契约：

| 环境变量 | 内容 |
| --- | --- |
| `SZTU_EVAL_TASK_FILE` | 不含参考答案的公开任务 JSON |
| `SZTU_EVAL_WORKSPACE` | 本次运行的隔离工作区绝对路径 |
| `SZTU_EVAL_METRICS_FILE` | 可选过程指标 JSON 输出路径 |

可选指标文件格式：

```json
{
  "input_tokens": 1200,
  "output_tokens": 240,
  "cache_read_input_tokens": 300,
  "cache_creation_input_tokens": 0,
  "tool_calls": 8,
  "steps": 4
}
```

字段必须是非负整数。缺失字段按零处理；非法指标会把本次运行标记为 `invalid_metrics`。
command runner 是接入接口，不是操作系统沙箱；只应运行受信任的本地适配器。框架会隔离任务目录、
隐藏参考答案并检查修改范围，但不能阻止任意外部进程访问其本来就拥有权限的其他路径。

## 任务格式

任务清单是 `schema_version: "1.0"` 的 JSON 文件。统一字段包括：

- `id`：稳定且唯一的任务标识；
- `source`：`internal` 或 `swebench_lite`；
- `category`：`long_context`、`cross_language`、`security`、`collaboration` 或 `general`；
- `title`、`prompt`、`tags`：给 Agent 和报告使用的任务描述。

内部任务还定义初始文件、验证命令、允许修改的路径和 reference runner 使用的参考修改：

```json
{
  "id": "internal.example.boundary",
  "source": "internal",
  "title": "Fix a boundary condition",
  "category": "general",
  "prompt": "Fix can_retry without editing the verifier.",
  "tags": ["typescript"],
  "workspace_files": {
    "retry.mjs": "export const canRetry = (attempt, limit) => attempt < limit;\n",
    "verify.mjs": "import assert from 'node:assert/strict';\nimport { canRetry } from './retry.mjs';\nassert.equal(canRetry(1, 1), true);\n"
  },
  "validation": {
    "command": ["node", "verify.mjs"],
    "timeout_seconds": 10
  },
  "expected_modified_files": ["retry.mjs"],
  "reference_changes": [
    {"path": "retry.mjs", "content": "export const canRetry = (attempt, limit) => attempt <= limit;\n"}
  ]
}
```

验证命令直接使用 Node 执行 TypeScript/JavaScript fixture；评测调度器和内部任务均由 TypeScript/Node 运行。所有清单路径必须使用 `/`，绝对路径、`..` 和
Windows 反斜杠会在创建工作区前被拒绝。公开任务文件不会包含 `workspace_files` 或
`reference_changes`，外部 Agent 无法通过 runner 契约读取参考答案。

随包提供的清单位于：

- `packages/evaluation/tasks/internal-v1.json`：10 个离线任务；
- `packages/evaluation/tasks/swebench-lite-smoke.json`：3 个固定 SWE-bench Lite 实例。

可用 `--manifest path/to/tasks.json` 加载自定义清单，并用 `--task-id` 或 `--max-tasks` 筛选。
内部任务的验证命令会被直接执行，因此自定义清单也必须来自可信来源。

## 指标定义

| 指标 | 定义 |
| --- | --- |
| Success rate | `passed / scored runs`；错误算失败，`unscored` 不进入分母 |
| pass@k | 有限重复样本下至少一次成功的组合估计 `1 - C(n-c,k) / C(n,k)` |
| Stability | 成功/失败两类中占多数结果的比例；全部一致为 1 |
| Tokens | runner 报告的 input + output；缓存 Token 单独保留，不重复相加 |
| Duration | 单次工作区准备、Agent 执行和独立验证的墙钟时间 |
| Tool calls | runner 观察或上报的工具调用总数 |
| Modified files | 内部任务用内容快照、Git 任务用 `git status` 计算的变更文件数 |
| Failure reason | setup、runner、timeout、validation、scope、metrics 等结构化分类 |

每个任务重复执行由 `--repeat N` 控制。报告同时保留每次原始记录和每任务均值/标准差，方便比较
不同模型、上下文策略或 runner。

## SWE-bench Lite 小样本

先让 SztuCode 在三个固定实例上生成 patch：

```bash
npm run eval -- run \
  --suite swebench-lite \
  --runner sztucode-rpc \
  --permission-mode auto \
  --allow-auto-permissions \
  --max-tasks 3 \
  --output-dir tmp/eval/swebench-smoke
```

这一步会克隆公开仓库并调用真实模型，必须显式执行。生成的运行记录仍是 `unscored`。随后导出
官方预测格式：

```bash
npm run eval -- export-swebench \
  --suite swebench-lite \
  --report tmp/eval/swebench-smoke/report.json \
  --output tmp/eval/swebench-smoke/predictions.jsonl \
  --model-name sztu-code
```

最后使用官方 Docker harness：

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --split test \
  --predictions_path tmp/eval/swebench-smoke/predictions.jsonl \
  --instance_ids astropy__astropy-12907 astropy__astropy-14182 astropy__astropy-14365 \
  --max_workers 1 \
  --run_id sztucode-smoke
```

官方 harness 通过 Docker 应用 patch、执行 `FAIL_TO_PASS` 和 `PASS_TO_PASS` 测试并判定是否
resolved。参见 [SWE-bench Harness Reference](https://www.swebench.com/SWE-bench/reference/harness/)。

## 报告再生成

Markdown 模板可以独立于评测重新生成：

```bash
npm run eval -- report \
  --input tmp/eval/internal-agent/report.json \
  --output tmp/eval/internal-agent/summary.md
```

`report.json` 可能包含 patch 和有界 runner 输出。公开报告前仍应检查其中是否包含外部仓库内容、
个人路径或敏感信息；评测工作区、缓存和大型 Docker 产物不得提交。

## 运行时边界

评测调度器、报告生成器和 SWE-bench patch 导出均由 `packages/evaluation` 的 TypeScript 实现负责。官方 SWE-bench Docker harness 仍按其上游要求使用 Python 命令，但这不属于 SztuCode 的运行时。
