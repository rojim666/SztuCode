# SztuCode Coding Agent 评测实施指南

> 基于行业标准流程（SWE-bench 体系）+ 轨迹质量分析 + SztuCode 专项工程维度，
> 构建三层评测体系，从"能跑"到"可信赖"逐层验证。

---

## 一、为什么不能只看"测试通过"

你的项目已有 55 个单元测试 + 5 个集成测试，验证的是**功能正确性**（工具能不能调用、权限能不能拦截）。
但这些测试回答不了以下问题：

| 问题 | 现有测试能回答吗 |
|------|:---:|
| Agent 能解决真实的 GitHub issue 吗？ | 不能 |
| Agent 多步推理的路径效率如何？ | 不能 |
| Agent 会不会改坏无关文件？ | 不能 |
| 上下文压缩后信息丢失多少？ | 不能 |
| 每个任务花多少 token / 多少钱？ | 不能 |
| 同一个任务跑 5 次，结果稳定吗？ | 不能 |

**评测的目标：从"功能正确"升级到"能力可量化、过程可分析、结果可复现"。**

---

## 二、Layer 1：标准基准评测（行业对标）

### 2.1 SWE-bench —— 当前唯一权威的 Coding Agent 基准

SWE-bench 是目前业界公认的 coding agent 评测标准，核心机制：

```
1. 给 Agent 一个真实 GitHub issue 描述 + 代码仓库快照
2. Agent 自主探索代码库、定位问题、生成 patch
3. 将 patch 应用到仓库，运行项目原有的测试套件
4. FAIL_TO_PASS 测试通过 + PASS_TO_PASS 测试不回归 = "已解决"
```

#### SWE-bench 变体选择

| 变体 | 任务数 | 适用场景 | 推荐度 |
|------|--------|----------|--------|
| **SWE-bench Lite** | 300 | 快速验证、开发期迭代 | 首选起步 |
| **SWE-bench Verified** | 500 | 人工验证、黄金标准 | 正式评测 |
| SWE-bench Full | 2,294 | 全面评测、学术研究 | 成本高 |
| SWE-bench Live | 持续更新 | 防数据污染 | 进阶 |
| Multi-SWE-bench | 1,632 | 多语言（Java/TS/Go/Rust/C++） | 可选 |

**建议从 SWE-bench Lite 开始**，300 个任务可以在合理成本内完成首轮评测。

### 2.2 如何接入 SWE-bench Harness

SWE-bench 的评测流程已经标准化，你只需要实现一个函数：**输入 issue 描述 + 仓库路径，输出 unified diff patch**。

#### Step 1: 安装 SWE-bench

```bash
pip install swebench
```

#### Step 2: 拉取预构建 Docker 镜像

```bash
# 拉取 SWE-bench Lite 的实例镜像（首次约 40 分钟）
python -m swebench.harness.run_evaluation \
    --predictions_path /dev/null \
    --max_workers 8 \
    --run_id setup-pull \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --split test \
    --instance_ids astropy__astropy-12907 django__django-11099
```

#### Step 3: 编写 SztuCode 的 Harness 适配器

核心：将 SztuCode 的 agent.run 包装成 SWE-bench 要求的接口。

```python
# eval/swebench_adapter.py
"""SztuCode -> SWE-bench 适配器

SWE-bench 的契约：
  输入: {instance_id, repo, base_commit, problem_statement}
  输出: {instance_id, model_patch: "diff --git ...", model_name_or_path}
"""
import json
import subprocess
import tempfile
from pathlib import Path


def run_sztucode_on_instance(instance: dict, workspace: str) -> dict:
    """
    用 SztuCode 的 daemon 解决一个 SWE-bench 实例。

    Args:
        instance: SWE-bench 实例（含 repo, base_commit, problem_statement）
        workspace: 临时工作目录

    Returns:
        {"instance_id": ..., "model_patch": "diff --git ...", "model_name_or_path": "sztu-code"}
    """
    repo_url = f"https://github.com/{instance['repo']}.git"
    repo_dir = Path(workspace) / instance["instance_id"]

    # 1. 克隆仓库到指定 commit
    subprocess.run(["git", "clone", repo_url, str(repo_dir)], check=True)
    subprocess.run(
        ["git", "checkout", instance["base_commit"]],
        cwd=repo_dir, check=True
    )

    # 2. 通过 SztuCode daemon 的 JSON-RPC 接口发送任务
    #    利用现有的 agent.run 命令
    prompt = f"""You are working on the repository {instance['repo']}.

Here is an issue that needs to be fixed:

{instance['problem_statement']}

Please analyze the issue, locate the problematic code, and make the necessary changes to fix it.
After making changes, verify your fix is correct."""

    # 方式 A: 通过 CLI 调用
    result = subprocess.run(
        ["sztu", "--cwd", str(repo_dir), "run", prompt],
        capture_output=True, text=True, timeout=600  # 10 分钟超时
    )

    # 方式 B: 通过 JSON-RPC 直接调用 daemon（更可控）
    # import asyncio
    # from sztu_code.core.transport.socket_client import SocketClient
    # client = SocketClient("127.0.0.1", 7437)
    # await client.connect()
    # response = await client.request("agent.run", {
    #     "prompt": prompt,
    #     "cwd": str(repo_dir),
    #     "permission_mode": "auto",  # 评测时自动批准所有操作
    # })

    # 3. 生成 diff
    diff = subprocess.run(
        ["git", "diff"],
        cwd=repo_dir, capture_output=True, text=True
    ).stdout

    return {
        "instance_id": instance["instance_id"],
        "model_patch": diff,
        "model_name_or_path": "sztu-code"
    }


def run_batch(instances: list, workspace: str, output_path: str):
    """批量运行所有实例，输出 SWE-bench 要求的 JSONL"""
    results = []
    for inst in instances:
        try:
            result = run_sztucode_on_instance(inst, workspace)
            results.append(result)
        except Exception as e:
            print(f"Failed on {inst['instance_id']}: {e}")
            results.append({
                "instance_id": inst["instance_id"],
                "model_patch": "",
                "model_name_or_path": "sztu-code"
            })

    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
```

#### Step 4: 运行评测

```bash
# 1. 加载数据集
python -c "
from datasets import load_dataset
ds = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
print(f'{len(ds)} instances')
"

# 2. 运行 SztuCode 生成预测
python eval/swebench_adapter.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --split test \
    --workspace /tmp/swebench-workspace \
    --output /tmp/preds.jsonl

# 3. 用官方 harness 评分
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --split test \
    --predictions_path /tmp/preds.jsonl \
    --max_workers 8 \
    --run_id sztucode-eval-001
```

#### Step 5: 查看结果

```bash
# 结果在 logs/sztucode-eval-001/ 下
# 关键文件：sztucode-eval-001.eval.log
# 包含每个实例的 RESOLVED / FAIL / REGRESSION 状态
```

### 2.3 HumanEval / MBPP（代码生成基线）

这两个基准测试的是**单次代码生成能力**（不需要 agent loop），适合验证你的 LLM Provider 层是否正确工作。

```python
# eval/humaneval_runner.py
from datasets import load_dataset

def run_humaneval(provider, num_samples=1):
    ds = load_dataset("openai_humaneval", split="test")
    results = []
    for item in ds:
        # 直接用 LLM 生成，不走 agent loop
        response = provider.chat([{
            "role": "user",
            "content": item["prompt"]
        }])
        results.append({
            "task_id": item["task_id"],
            "completion": response.text
        })
    return results
```

评测指标：**pass@k**（k 次采样中至少 1 次通过的概率）。

---

## 三、Layer 2：轨迹质量评测（过程分析）

SWE-bench 只看最终结果（patch 对不对），但**过程质量**决定了 agent 在生产环境中的可靠性。

### 3.1 为什么需要轨迹分析

业界研究（AgentLens、The Harness Effect）表明：

> 同一个 agent，pass@1 从 30% 到 50% 的提升，可能只是因为"少走了 3 步弯路"，
> 而不是推理能力真的提升了。轨迹质量才是可信赖的信号。

### 3.2 轨迹评测维度

你的项目已经有三层 Trace 系统（IPC / EventBus / LLM），可以直接利用。

#### 维度 1：路径效率（Path Efficiency）

```python
# eval/trajectory/path_efficiency.py
"""分析 agent loop 的步数和回溯情况"""
import json
from pathlib import Path

def analyze_path_efficiency(trace_file: str) -> dict:
    """
    从 events.jsonl 中分析路径效率。

    指标：
    - total_steps: 总步数
    - unique_files_touched: 触及的不同文件数
    - edit_revert_count: 同一文件编辑后回退的次数
    - redundant_read_count: 重复读取同一文件的次数
    - efficiency_score: unique_files / total_steps（越高越好）
    """
    events = []
    with open(trace_file) as f:
        for line in f:
            events.append(json.loads(line))

    steps = [e for e in events if e.get("type") == "StepStarted"]
    tool_calls = [e for e in events if e.get("type") == "ToolCallStarted"]

    files_read = []
    files_edited = []
    for tc in tool_calls:
        if tc.get("tool_name") == "read_file":
            files_read.append(tc.get("params", {}).get("path", ""))
        elif tc.get("tool_name") in ("write_file", "edit_file"):
            files_edited.append(tc.get("params", {}).get("path", ""))

    # 重复读取
    redundant_reads = len(files_read) - len(set(files_read))

    # 回溯：编辑后又编辑同一文件（可能是在修正）
    edit_sequence = files_edited
    reverts = sum(1 for i in range(1, len(edit_sequence))
                  if edit_sequence[i] == edit_sequence[i-1])

    return {
        "total_steps": len(steps),
        "total_tool_calls": len(tool_calls),
        "unique_files_touched": len(set(files_read + files_edited)),
        "redundant_read_count": redundant_reads,
        "edit_revert_count": reverts,
        "efficiency_score": len(set(files_read + files_edited)) / max(len(tool_calls), 1),
    }
```

#### 维度 2：工具纪律（Tool Discipline）

```python
# eval/trajectory/tool_discipline.py
"""检查 agent 是否遵循"先读后写"的纪律"""
def analyze_tool_discipline(trace_file: str) -> dict:
    events = []
    with open(trace_file) as f:
        for line in f:
            events.append(json.loads(line))

    tool_calls = [e for e in events if e.get("type") == "ToolCallStarted"]

    read_before_write = 0
    write_without_read = 0

    files_read = set()
    for tc in tool_calls:
        tool = tc.get("tool_name", "")
        path = tc.get("params", {}).get("path", "")

        if tool == "read_file":
            files_read.add(path)
        elif tool in ("write_file", "edit_file"):
            if path in files_read:
                read_before_write += 1
            else:
                write_without_read += 1

    total_writes = read_before_write + write_without_read
    return {
        "read_before_write_ratio": read_before_write / max(total_writes, 1),
        "blind_write_count": write_without_read,
        "tool_call_accuracy": read_before_write / max(total_writes, 1),
    }
```

#### 维度 3：爆炸半径（Blast Radius）

```python
# eval/trajectory/blast_radius.py
"""检查 agent 是否修改了无关文件"""
def analyze_blast_radius(diff: str, expected_files: list) -> dict:
    """
    分析 git diff，检查修改范围是否超出预期。

    Args:
        diff: git diff 输出
        expected_files: 预期应该修改的文件列表
    """
    import re
    changed_files = set(re.findall(r'^diff --git a/(.+?) b/', diff, re.MULTILINE))
    expected_set = set(expected_files)

    return {
        "total_files_changed": len(changed_files),
        "expected_files_changed": len(changed_files & expected_set),
        "unexpected_files_changed": len(changed_files - expected_set),
        "unexpected_file_list": list(changed_files - expected_set),
        "blast_radius_score": len(changed_files & expected_set) / max(len(changed_files), 1),
    }
```

#### 维度 4：失败诚实度（Failure Honesty）

```python
# eval/trajectory/failure_honesty.py
"""检查 agent 失败时是否诚实报告"""
def analyze_failure_honesty(trace_file: str, was_resolved: bool) -> dict:
    """
    当任务未解决时，检查 agent 是否：
    - 承认失败（stop_reason = end_turn 且最后一轮包含"无法解决"类表述）
    - 还是伪造了一个看似正确的 diff
    """
    events = []
    with open(trace_file) as f:
        for line in f:
            events.append(json.loads(line))

    if was_resolved:
        return {"status": "resolved", "honest_failure": "N/A"}

    # 检查最后一个 assistant 消息
    last_assistant = None
    for e in reversed(events):
        if e.get("type") == "AssistantResponse":
            last_assistant = e.get("content", "")
            break

    # 简单启发式：检查是否包含失败/不确定的表述
    honesty_markers = ["cannot", "unable", "could not", "not sure",
                       "无法", "不确定", "未能", "不确定是否"]
    is_honest = any(m in (last_assistant or "").lower() for m in honesty_markers)

    return {
        "status": "failed",
        "honest_failure": is_honest,
        "fabricated_diff": not is_honest,
        "final_message": last_assistant[:200] if last_assistant else "",
    }
```

### 3.3 利用 SztuCode 的 Trace 系统

你的项目已经实现了三层 Trace，可以直接复用：

```python
# SztuCode 的 trace 系统已经记录了：
# - IPC 层：所有 JSON-RPC 请求/响应
# - EventBus 层：所有事件（StepStarted, ToolCallStarted, TokenEvent 等）
# - LLM 层：每次 LLM 调用的完整请求和响应

# trace 文件位置：~/.sztu/sessions/<session_id>/events.jsonl
# 可以直接用上面的分析函数处理这些文件
```

---

## 四、Layer 3：工程维度评测（SztuCode 专项）

这一层针对 SztuCode 的核心工程特性，验证你的架构设计是否真的有效。

### 4.1 Agent Loop 鲁棒性

| 指标 | 测量方法 | 目标 |
|------|----------|------|
| 流式重试成功率 | 注入网络异常，统计重试后成功恢复的比例 | > 90% |
| 熔断触发率 | 在 SWE-bench 运行中统计 DenialTracker 干预次数 | < 5% |
| max_steps 终止率 | 统计因步数上限终止的任务比例 | < 20% |
| 工具异常恢复率 | 工具返回 is_error=True 后，下一步是否换策略 | > 70% |

```python
# eval/engineering/loop_robustness.py
"""评测 Agent Loop 的鲁棒性"""
async def evaluate_loop_robustness(runner, test_cases: list) -> dict:
    results = {
        "max_steps_termination": 0,
        "denial_intervention": 0,
        "llm_error_termination": 0,
        "tool_error_recovery": 0,
        "total_runs": 0,
    }

    for case in test_cases:
        context = await runner.run_and_capture(case["prompt"], case["cwd"])
        results["total_runs"] += 1

        if context.status == "failed":
            if "exceeded_max_steps" in (context.fail_reason or ""):
                results["max_steps_termination"] += 1
            elif "llm_error" in (context.fail_reason or ""):
                results["llm_error_termination"] += 1

        # 从 trace 中提取 denial 干预和工具错误恢复
        # ...

    return {
        "max_steps_rate": results["max_steps_termination"] / results["total_runs"],
        "llm_error_rate": results["llm_error_termination"] / results["total_runs"],
        "denial_intervention_rate": results["denial_intervention"] / results["total_runs"],
    }
```

### 4.2 上下文治理

| 指标 | 测量方法 | 目标 |
|------|----------|------|
| compact 压缩比 | 压缩前 token 数 / 压缩后 token 数 | > 3:1 |
| 信息保留率 | 压缩后 agent 是否能继续完成任务（完成率对比） | 压缩前后完成率差 < 10% |
| 水位检测准确性 | compact 触发时 actual context_pct 与 threshold 的偏差 | < 5% |

### 4.3 权限安全

| 指标 | 测量方法 | 目标 |
|------|----------|------|
| 越界拦截率 | 构造 CWD 外文件访问用例，统计拦截比例 | 100% |
| 误审批率 | 构造危险命令（rm -rf 等），统计被批准的比例 | 0% |
| AUTO 模式安全性 | AUTO 模式下是否仍拦截 deny_patterns | 100% 拦截 |

### 4.4 成本效率

| 指标 | 测量方法 | 目标 |
|------|----------|------|
| Token / Task | 每个 SWE-bench 实例消耗的 token 总量 | < 50K tokens |
| $ / 成功任务 | 总 API 花费 / 解决的实例数 | 对标同类 agent |
| 步数 / 任务 | 平均每个任务消耗的 agent loop 步数 | < 15 步 |

```python
# eval/engineering/cost_efficiency.py
"""评测成本效率"""
def calculate_cost_metrics(run_results: list) -> dict:
    """
    Args:
        run_results: 每个任务的运行结果，含 token 使用量和解决状态
    """
    total_input_tokens = sum(r["input_tokens"] for r in run_results)
    total_output_tokens = sum(r["output_tokens"] for r in run_results)
    total_cost = sum(r["cost_usd"] for r in run_results)
    resolved = sum(1 for r in run_results if r["resolved"])

    return {
        "avg_tokens_per_task": (total_input_tokens + total_output_tokens) / len(run_results),
        "avg_input_tokens": total_input_tokens / len(run_results),
        "avg_output_tokens": total_output_tokens / len(run_results),
        "avg_steps": sum(r["steps"] for r in run_results) / len(run_results),
        "cost_per_resolved": total_cost / max(resolved, 1),
        "total_cost": total_cost,
    }
```

### 4.5 子 Agent 编排效率

| 指标 | 测量方法 | 目标 |
|------|----------|------|
| 子 Agent 调用率 | 需要子 agent 的任务中实际使用了子 agent 的比例 | 视任务而定 |
| 子 Agent 结果可用率 | 子 agent 返回的结果被父 agent 采纳的比例 | > 60% |
| 并行加速比 | 后台子 agent 的并行执行 vs 串行执行的时间比 | > 1.5x |

---

## 五、稳定性评测（多次运行方差）

Agent 的输出是非确定性的（LLM 采样），同一个任务跑多次结果可能不同。

```python
# eval/stability.py
"""评测 agent 的运行稳定性"""
async def evaluate_stability(runner, task: dict, n_runs: int = 5) -> dict:
    """
    对同一任务运行 n 次，统计结果分布。

    关键指标：
    - pass@1: 单次通过率
    - pass@k: k 次中至少 1 次通过的概率
    - 方差: 结果的稳定性
    """
    results = []
    for i in range(n_runs):
        context = await runner.run_and_capture(task["prompt"], task["cwd"])
        # 检查是否解决
        resolved = check_resolved(task, context)
        results.append({
            "run": i,
            "resolved": resolved,
            "steps": context.step,
            "status": context.status,
        })

    passed = sum(1 for r in results if r["resolved"])

    # pass@k 计算
    from math import comb
    n, c, k = n_runs, passed, 1
    pass_at_k = 1 - comb(n - c, k) / comb(n, k) if n - c < k else 1.0

    return {
        "pass_at_1": passed / n_runs,
        "pass_at_k": pass_at_k,
        "variance": sum(1 for r in results if r["resolved"]) / n_runs,
        "step_variance": statistics.variance([r["steps"] for r in results]) if n_runs > 1 else 0,
        "runs": results,
    }
```

---

## 六、评测报告模板

```markdown
# SztuCode Evaluation Report

## 基本信息
- 评测日期: YYYY-MM-DD
- Agent 版本: sztu-code vX.X.X
- LLM 模型: claude-sonnet-4-20250514
- 评测集: SWE-bench Lite (300 tasks)

## Layer 1: 标准基准结果
| 指标 | 结果 |
|------|------|
| Resolved Rate | XX/300 = XX.X% |
| Fail (tests not passed) | XX |
| Regression (broke other tests) | XX |
| No Patch (agent 未生成 diff) | XX |

## Layer 2: 轨迹质量
| 指标 | 平均值 |
|------|--------|
| 平均步数 | XX.X |
| 平均工具调用数 | XX.X |
| 读后写比例 | XX.X% |
| 爆炸半径得分 | XX.X% |
| 失败诚实度 | XX.X% |

## Layer 3: 工程维度
| 指标 | 结果 |
|------|------|
| max_steps 终止率 | XX.X% |
| 熔断触发率 | XX.X% |
| compact 触发次数 | XX |
| 平均 Token / Task | XX,XXX |
| 成本 / 成功任务 | $X.XX |

## 稳定性（抽样 20 个任务，每个跑 5 次）
| 指标 | 结果 |
|------|------|
| pass@1 | XX% |
| pass@5 | XX% |
| 步数方差 | XX.X |

## 失败模式分析
| 失败类型 | 占比 | 示例 |
|----------|------|------|
| 错误诊断（修了症状没修根因） | XX% | ... |
| 正确修复但位置错误 | XX% | ... |
| 上下文耗尽 | XX% | ... |
| 编辑执行错误 | XX% | ... |
| 测试盲区（修了但破坏了其他测试） | XX% | ... |

## 对标
| Agent | SWE-bench Lite | SWE-bench Verified |
|-------|:---:|:---:|
| SztuCode (本项目) | XX% | XX% |
| Claude Sonnet 4.5 | - | 77.2% |
| GPT-4 Turbo | - | 38.0% |
| OpenHands | - | 35% |
```

---

## 七、推荐实施路径

### Phase 1: 基础验证（1-2 周）

1. **搭建 SWE-bench Lite 评测环境**
   - 安装 Docker + swebench
   - 拉取 SWE-bench Lite 的预构建镜像
   - 编写 SztuCode 的 Harness 适配器

2. **跑通 10 个实例**
   - 先跑 10 个任务验证流程正确
   - 检查 patch 生成、测试执行、结果聚合是否正常

3. **完成 SWE-bench Lite 全量评测**
   - 300 个任务，预计 20-40 小时
   - 获取 Resolved Rate 基线

### Phase 2: 轨迹分析（1 周）

1. **收集所有任务的 trace 文件**
2. **运行轨迹分析脚本**
3. **定位失败模式**：是诊断错误？上下文耗尽？还是工具使用不当？
4. **针对性优化**：根据失败模式调整 prompt、工具描述或 loop 参数

### Phase 3: 全面对标（1-2 周）

1. **运行 SWE-bench Verified (500 tasks)**
2. **运行稳定性测试**（抽样 20-30 个任务，每个跑 5 次）
3. **运行工程维度评测**
4. **生成完整评测报告**

### Phase 4: 自定义任务集（持续）

1. **从自己的项目中收集真实任务**
2. **构建包含以下类型的任务集**：
   - Bug 修复（5-7 个）
   - 功能添加（5-7 个）
   - 重构任务（3-5 个）
   - 测试生成（3-5 个）
   - 架构/脚手架（2-3 个）
3. **定义二元成功标准**（不是"代码正确"，而是"通过这 5 个测试用例"）

---

## 八、关键注意事项

### 8.1 评测时的权限配置

SWE-bench 评测时需要 **AUTO 模式**（自动批准所有工具调用），否则人工审批会阻塞评测流程。

```python
# 在 SztuCode daemon 启动时设置权限模式
# 或在 agent.run 请求中指定 permission_mode: "auto"
```

### 8.2 成本控制

SWE-bench Lite (300 tasks) 的预估成本：
- 每个任务平均 30K-50K tokens
- 300 tasks × 40K tokens × $0.003/1K = ~$36-$60
- 建议先用 10 个任务估算成本，再决定是否全量运行

### 8.3 数据污染

如果你的 LLM 训练数据中包含了 SWE-bench 的 issue 或解决方案，评测结果会被高估。
解决方法：
- 使用 SWE-bench Live（持续更新的数据集）
- 使用 SWE-bench Pro（有私有测试集）
- 在报告中注明可能的污染风险

### 8.4 Harness 效应

研究表明，同一个模型 + 不同的 harness（工具配置、prompt 模板、重试策略）可以产生
10-20% 的分数差异。因此：
- 评测时固定所有配置
- 记录完整的运行环境（模型版本、温度、max_steps 等）
- 对比其他 agent 时，确保是在相同条件下

---

## 九、参考资源

- [SWE-bench 官方仓库](https://github.com/SWE-bench/SWE-bench)
- [SWE-bench Leaderboard](https://www.swebench.com/)
- [SWE-bench Verified 介绍](https://openai.com/index/introducing-swe-bench-verified/)
- [agent-eval-harness](https://github.com/dragonstyle/agent-eval-harness) - 通用 agent 评测框架
- [Trae Agent 评测实现](https://github.com/bytedance/trae-agent/blob/main/evaluation/README.md) - 字节跳动的参考实现
- [AgentLens 论文](https://arxiv.org/abs/2507.00724) - 轨迹级评测方法论
- [The Harness Effect 论文](https://arxiv.org/abs/2509.00275) - Harness 对评测结果的影响
