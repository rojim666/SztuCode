"""
SztuCode SWE-bench 适配器

将 SztuCode 的 agent 通过 JSON-RPC 包装成 SWE-bench 要求的接口：
  输入: {instance_id, repo, base_commit, problem_statement}
  输出: {instance_id, model_patch: "diff --git ...", model_name_or_path}

RPC 流程:
  1. permission.set_mode  → "auto"（自动批准工具调用）
  2. workspace.open       → workspace_id（指向克隆的仓库目录）
  3. session.create       → session_id（one_shot 模式，绑定 workspace）
  4. event.subscribe      → 订阅 run.* / step.* / tool.* 事件
  5. session.send_message → run_id（发送 issue 作为 goal）
  6. 等待 run.finished 事件
  7. change.diff          → 获取 agent 产生的 diff
  8. session.close         → 清理

用法:
    cd F:/Learning/codinganget/SztuCode/py-runtime
    uv run python -m eval.swebench.adapter --max-instances 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("sztucode.swebench")

# SztuCode 源码路径
SZTU_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SZTU_SRC))

from sztu_code.core.transport.socket_client import IpcError, SocketClient  # noqa: E402

# ──────────────────── 数据模型 ────────────────────

@dataclass
class SWEbenchInstance:
    """SWE-bench 实例"""
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: str = ""
    test_patch: str = ""
    patch: str = ""
    fail_to_pass: str = ""
    pass_to_pass: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> SWEbenchInstance:
        return cls(
            instance_id=d["instance_id"],
            repo=d["repo"],
            base_commit=d["base_commit"],
            problem_statement=d["problem_statement"],
            hints_text=d.get("hints_text", ""),
            test_patch=d.get("test_patch", ""),
            patch=d.get("patch", ""),
            fail_to_pass=d.get("FAIL_TO_PASS", ""),
            pass_to_pass=d.get("PASS_TO_PASS", ""),
        )


@dataclass
class RunResult:
    """单个实例运行结果"""
    instance_id: str
    model_patch: str = ""
    model_name_or_path: str = "sztu-code"
    error: str | None = None
    elapsed_seconds: float = 0.0
    steps: int = 0
    status: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    events_log: list[dict] = field(default_factory=list)

    def to_pred_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "model_patch": self.model_patch,
            "model_name_or_path": self.model_name_or_path,
        }


@dataclass
class _RunEventCollector:
    """Scope daemon events to the run currently evaluated by the adapter."""

    run_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    finished_event: dict[str, Any] | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    _pending_events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event: dict[str, Any]) -> None:
        event_run_id = str(event.get("run_id", ""))
        if not event_run_id:
            return
        if self.run_id is None:
            self._pending_events.append(event)
            return
        self._accept(event, event_run_id)

    def set_run_id(self, run_id: str) -> None:
        normalized_run_id = str(run_id)
        if not run_id or not normalized_run_id:
            raise ValueError("run_id must be non-empty")
        self.run_id = normalized_run_id
        pending_events, self._pending_events = self._pending_events, []
        for event in pending_events:
            self._accept(event, str(event.get("run_id", "")))

    def _accept(self, event: dict[str, Any], event_run_id: str) -> None:
        if event_run_id != self.run_id:
            return
        self.events.append(event)
        if event.get("type") == "run.finished":
            self.finished_event = event
            self.finished.set()


@dataclass
class TokenUsage:
    """一次运行的 LLM token 用量汇总"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


# 汇总事件流中的 llm.usage 顶层字段，缺失按 0 处理且忽略无关事件
def summarize_token_usage(events: list[dict[str, Any]]) -> TokenUsage:
    usage = TokenUsage()
    for ev in events:
        if ev.get("type") != "llm.usage":
            continue
        usage.input_tokens += ev.get("input_tokens", 0) or 0
        usage.output_tokens += ev.get("output_tokens", 0) or 0
        usage.cache_read_input_tokens += ev.get("cache_read_input_tokens", 0) or 0
        usage.cache_creation_input_tokens += ev.get("cache_creation_input_tokens", 0) or 0
    return usage


# ──────────────────── Prompt 构造 ────────────────────

def build_prompt(instance: SWEbenchInstance) -> str:
    """构造发给 SztuCode 的 goal 文本"""
    prompt = f"""You are working on the repository {instance.repo}.

Here is an issue that needs to be fixed:

{instance.problem_statement}

Please analyze the issue, locate the problematic code in the repository, and make the necessary \
changes to fix it.

Guidelines:
- Read the relevant source files first to understand the codebase structure
- Identify the root cause, not just the symptom
- Make minimal, targeted changes
- After making changes, verify your fix is correct by reading the modified files
- Do not modify test files unless explicitly asked"""
    return prompt


# ──────────────────── Git 操作 ────────────────────

def clone_repo(instance: SWEbenchInstance, workspace: Path) -> Path:
    """克隆仓库到指定 commit"""
    repo_dir = workspace / instance.instance_id.replace("/", "__")

    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
    # 若首次未删干净（如 .git 残留），重试；仍失败则抛出明确错误
    if repo_dir.exists() and any(repo_dir.iterdir()):
        shutil.rmtree(repo_dir)

    repo_url = f"https://github.com/{instance.repo}.git"
    logger.info(f"  Cloning {instance.repo} @ {instance.base_commit[:8]}...")

    # 浅拷贝元数据 + 按需拉取 blob，显著加快大仓库克隆；checkout 需要的提交历史仍会拉取
    subprocess.run(
        [
            "git", "clone", "--quiet", "--filter=blob:none",
            "--single-branch", repo_url, str(repo_dir),
        ],
        check=True,
        timeout=600,
    )
    subprocess.run(
        ["git", "checkout", "--quiet", instance.base_commit],
        cwd=repo_dir,
        check=True,
        timeout=60,
    )
    return repo_dir


def get_diff_via_git(repo_dir: Path) -> str:
    """直接通过 git diff 获取变更（备选方案）"""
    result = subprocess.run(
        ["git", "diff"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    patches = [result.stdout]

    untracked_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    for file_path in untracked_result.stdout.splitlines():
        new_file_result = subprocess.run(
            ["git", "diff", "--no-index", "--", "/dev/null", file_path],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if new_file_result.returncode in (0, 1):
            patches.append(new_file_result.stdout)

    return "".join(patches)


# ──────────────────── RPC 调用 ────────────────────

async def run_instance_via_rpc(
    instance: SWEbenchInstance,
    repo_dir: Path,
    host: str = "127.0.0.1",
    port: int = 7437,
    timeout: int = 600,
) -> RunResult:
    """
    通过 JSON-RPC 调用 SztuCode daemon 完成单个实例

    流程: workspace.open → session.create → send_message → 等待 → change.diff
    """
    result = RunResult(instance_id=instance.instance_id)
    start_time = time.time()
    client = SocketClient(host, port)

    # 收集的事件
    collector = _RunEventCollector()

    async def on_event(event: dict[str, Any]) -> None:
        collector.record(event)
        event_type = event.get("type", "")
        if collector.run_id != str(event.get("run_id", "")):
            return

        # 日志关键事件
        if event_type == "step.started":
            logger.info(f"    [step {event.get('step')}] planning...")
        elif event_type == "tool.call_started":
            tool = event.get("tool_name", "")
            logger.info(f"    [tool] {tool}")
        elif event_type == "tool.call_failed":
            err = event.get("error_message", "")
            logger.warning(f"    [tool] FAIL: {err}")

    try:
        await client.connect()
    except (ConnectionRefusedError, OSError) as e:
        result.error = f"Cannot connect to daemon: {e}"
        result.elapsed_seconds = time.time() - start_time
        return result

    # 启动事件循环
    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())

    try:
        # 1. 设置权限模式为 auto
        await client.send_command("permission.set_mode", {"mode": "auto"})
        logger.info("  Permission mode: auto")

        # 2. 打开 workspace
        ws_result = await client.send_command("workspace.open", {
            "path": str(repo_dir.resolve())
        })
        workspace_id = ws_result.get("workspace", {}).get("workspace_id", "")
        logger.info(f"  Workspace: {workspace_id}")

        # 3. 订阅事件
        await client.send_command("event.subscribe", {
            "topics": ["run.*", "step.*", "tool.*", "llm.usage"],
            "scope": "global",
        })

        # 4. 创建 session（绑定 workspace）
        prompt = build_prompt(instance)
        sess_result = await client.send_command("session.create", {
            "mode": "one_shot",
            "title": instance.instance_id,
            "workspace_id": workspace_id,
        })
        session_id = sess_result.get("session_id", "")
        logger.info(f"  Session: {session_id}")

        # 5. 发送消息（goal）
        send_result = await client.send_command("session.send_message", {
            "session_id": session_id,
            "content": prompt,
        })
        raw_run_id = send_result.get("run_id")
        if not raw_run_id:
            raise ValueError("daemon returned an empty run_id")
        run_id = str(raw_run_id)
        collector.set_run_id(run_id)
        logger.info(f"  Run started: {run_id}")

        # 6. 等待 run.finished
        try:
            await asyncio.wait_for(collector.finished.wait(), timeout=timeout)
        except TimeoutError:
            result.error = f"Timeout after {timeout}s"
            # 尝试取消
            try:
                await client.send_command("run.cancel", {"run_id": run_id})
            except Exception:
                pass

        finished_event = collector.finished_event or {}
        result.status = finished_event.get("status", "")
        result.steps = finished_event.get("steps", 0)
        result.events_log = collector.events

        # 提取 token usage（顶层字段，缺失按 0）
        usage = summarize_token_usage(collector.events)
        result.input_tokens = usage.input_tokens
        result.output_tokens = usage.output_tokens
        result.cache_read_input_tokens = usage.cache_read_input_tokens
        result.cache_creation_input_tokens = usage.cache_creation_input_tokens

        # 7. 获取 diff
        if result.status in ("success", "max_steps", "cancelled"):
            try:
                diff_result = await client.send_command("change.diff", {
                    "workspace_id": workspace_id,
                })
                result.model_patch = diff_result.get("diff", "")
            except IpcError as e:
                logger.warning(f"  change.diff failed: {e}")
                # 备选：直接 git diff
                result.model_patch = get_diff_via_git(repo_dir)

        if not result.model_patch:
            # 尝试 git diff 作为 fallback
            result.model_patch = get_diff_via_git(repo_dir)

        if not result.model_patch:
            result.error = result.error or "No patch generated"

        # 8. 清理 session
        try:
            await client.send_command("session.close", {"session_id": session_id})
        except Exception:
            pass

    except IpcError as e:
        result.error = f"RPC error: {e}"
    except Exception as e:
        result.error = f"Unexpected: {e}"
        logger.exception("Unexpected error")
    finally:
        result.elapsed_seconds = time.time() - start_time
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        await client.close()

    return result


# ──────────────────── 数据集加载 ────────────────────

def _find_local_parquet(dataset_name: str, split: str) -> Path | None:
    """定位本地 SWE-bench parquet（含常见别名），不存在返回 None"""
    candidates = [
        Path(f"data/{dataset_name.replace('/', '_')}_{split}.parquet"),
        Path(f"data/swebench_{dataset_name.split('/')[-1].replace('SWE-bench_', '').lower()}_"
             f"{split}.parquet"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_dataset(dataset_name: str, split: str = "test") -> list[dict]:
    """加载 SWE-bench 数据集：优先本地 parquet → HuggingFace → 本地 JSON"""
    parquet_path = _find_local_parquet(dataset_name, split)
    if parquet_path is not None:
        import pyarrow.parquet as pq

        table = pq.read_table(parquet_path)
        logger.info(f"从本地 parquet 加载 {table.num_rows} 行: {parquet_path}")
        return table.to_pylist()
    try:
        from datasets import load_dataset as hf_load
        ds = hf_load(dataset_name, split=split)
        return list(ds)
    except ImportError:
        logger.error("需要安装 datasets: uv run pip install datasets")
        sys.exit(1)
    except Exception as e:
        logger.error(f"加载数据集失败: {e}")
        logger.info("尝试从本地 JSON 文件加载...")
        local_path = Path(f"data/{dataset_name.replace('/', '_')}_{split}.json")
        if local_path.exists():
            with open(local_path) as f:
                return json.load(f)
        raise


# ──────────────────── 批量运行 ────────────────────

async def run_batch_async(
    instances: list[dict],
    workspace: Path,
    output_path: str,
    host: str = "127.0.0.1",
    port: int = 7437,
    timeout: int = 600,
) -> None:
    """批量运行所有实例"""
    results: list[RunResult] = []
    total = len(instances)

    for i, inst_data in enumerate(instances):
        instance = SWEbenchInstance.from_dict(inst_data)
        logger.info(f"\n[{i+1}/{total}] {instance.instance_id}")
        logger.info(f"  Repo: {instance.repo} @ {instance.base_commit[:10]}")

        # 克隆仓库
        try:
            repo_dir = clone_repo(instance, workspace)
        except Exception as e:
            logger.error(f"  Clone failed: {e}")
            results.append(RunResult(
                instance_id=instance.instance_id,
                error=f"Clone failed: {e}",
            ))
            continue

        # 通过 RPC 运行
        result = await run_instance_via_rpc(
            instance, repo_dir, host=host, port=port, timeout=timeout
        )
        results.append(result)

        if result.model_patch:
            status_str = result.model_patch[:50] + "..."
        else:
            status_str = f"FAIL: {result.error}"
        logger.info(
            f"[{i+1}/{total}] {instance.instance_id} -> "
            f"{'PATCHED' if result.model_patch else 'FAILED'} "
            f"({result.elapsed_seconds:.1f}s, {result.steps} steps)"
        )
        if result.model_patch:
            logger.info(f"  Patch preview: {status_str}")

        # 实时写入（防崩溃丢失数据）
        workspace_dir = Path(output_path).parent
        workspace_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for r in results:
                f.write(json.dumps(r.to_pred_dict()) + "\n")

        # 保存详细结果
        detail_path = output_path.replace(".jsonl", "_detail.jsonl")
        with open(detail_path, "a") as f:
            f.write(json.dumps({
                "instance_id": result.instance_id,
                "status": result.status,
                "steps": result.steps,
                "elapsed_seconds": result.elapsed_seconds,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cache_read_input_tokens": result.cache_read_input_tokens,
                "cache_creation_input_tokens": result.cache_creation_input_tokens,
                "error": result.error,
                "has_patch": bool(result.model_patch),
                "patch_length": len(result.model_patch),
            }) + "\n")

    # 汇总
    patched = sum(1 for r in results if r.model_patch)
    failed = sum(1 for r in results if r.error)
    total_time = sum(r.elapsed_seconds for r in results)
    logger.info(f"\n{'='*60}")
    logger.info(f"Total: {total} | Patched: {patched} | Failed: {failed}")
    logger.info(f"Total time: {total_time:.1f}s | Avg: {total_time/max(total,1):.1f}s/task")
    if any(r.input_tokens for r in results):
        total_in = sum(r.input_tokens for r in results)
        total_out = sum(r.output_tokens for r in results)
        logger.info(f"Tokens: {total_in:,} in / {total_out:,} out")
    logger.info(f"Predictions: {output_path}")
    logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="SztuCode SWE-bench 适配器")
    parser.add_argument(
        "--dataset", default="princeton-nlp/SWE-bench_Lite",
        help="SWE-bench 数据集名称"
    )
    parser.add_argument("--split", default="test", help="数据集 split")
    parser.add_argument("--max-instances", type=int, default=None, help="最多运行多少个实例")
    parser.add_argument(
        "--instance-ids", default="",
        help="逗号分隔的 instance_id 列表，只运行这些",
    )
    parser.add_argument(
        "--workspace", default="eval/reports/swebench-workspace",
        help="工作目录（存放克隆的仓库）"
    )
    parser.add_argument(
        "--output", default="eval/reports/preds.jsonl",
        help="输出预测文件路径"
    )
    parser.add_argument("--host", default="127.0.0.1", help="daemon 地址")
    parser.add_argument("--port", type=int, default=7437, help="daemon 端口")
    parser.add_argument("--timeout", type=int, default=600, help="每个实例超时（秒）")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    # 清空之前的详细结果
    detail_path = args.output.replace(".jsonl", "_detail.jsonl")
    if Path(detail_path).exists():
        Path(detail_path).unlink()

    # 加载数据集
    logger.info(f"Loading dataset: {args.dataset} ({args.split})")
    instances = load_dataset(args.dataset, args.split)
    logger.info(f"Loaded {len(instances)} instances")

    if args.instance_ids:
        wanted = {item.strip() for item in args.instance_ids.split(",") if item.strip()}
        instances = [inst for inst in instances if inst["instance_id"] in wanted]
        logger.info(f"Filtered to {len(instances)} requested instances")
    if args.max_instances:
        instances = instances[:args.max_instances]
        logger.info(f"Limited to {len(instances)} instances")

    # 运行评测
    asyncio.run(run_batch_async(
        instances=instances,
        workspace=workspace,
        output_path=args.output,
        host=args.host,
        port=args.port,
        timeout=args.timeout,
    ))

    # 提示下一步
    run_id = time.strftime("%Y%m%d-%H%M%S")
    logger.info("\nNext step — run official harness to score:")
    logger.info(
        f"  uv run python -m swebench.harness.run_evaluation \\\n"
        f"    --dataset_name {args.dataset} \\\n"
        f"    --split {args.split} \\\n"
        f"    --predictions_path {args.output} \\\n"
        f"    --max_workers 4 \\\n"
        f"    --run_id sztucode-{run_id}"
    )


if __name__ == "__main__":
    main()
