"""
SWE-bench 多实例跟踪运行脚本
追踪每个实例的步数、Token 使用、缓存命中率、压缩触发情况
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# 添加源码路径
_PY_RUNTIME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PY_RUNTIME_ROOT / "src"))
sys.path.insert(0, str(_PY_RUNTIME_ROOT))

from eval.swebench.adapter import (
    SWEbenchInstance,
    build_prompt,
    clone_repo,
    get_diff_via_git,
    load_dataset,
)

from sztu_code.core.transport.socket_client import IpcError, SocketClient

logger = logging.getLogger("swebench.tracked")


async def run_instance_tracked(
    instance: SWEbenchInstance,
    repo_dir: Path,
    host: str = "127.0.0.1",
    port: int = 7437,
    timeout: int = 900,
) -> dict:
    """
    运行单个 SWE-bench 实例并返回详细跟踪数据
    """
    result = {
        "instance_id": instance.instance_id,
        "repo": instance.repo,
        "steps": 0,
        "status": "",
        "error": None,
        "elapsed_seconds": 0.0,
        "has_patch": False,
        "patch_length": 0,
        # Token 指标
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "max_context_pct": 0.0,
        # 每步详情
        "step_details": [],
        # 压缩事件
        "compaction_events": [],
        # 离线事件
        "offload_events": [],
    }

    start_time = time.time()
    client = SocketClient(host, port)

    run_finished = asyncio.Event()
    run_final_status = {"status": "", "steps": 0, "run_id": ""}

    async def on_event(event: dict) -> None:
        etype = event.get("type", "")

        if etype == "run.finished":
            run_final_status["status"] = event.get("status", "unknown")
            run_final_status["steps"] = event.get("steps", 0)
            run_final_status["run_id"] = event.get("run_id", "")
            run_finished.set()

        elif etype == "llm.usage":
            usage = event.get("usage", {}) if "usage" in event else event
            step = event.get("step", -1)
            step_info = {
                "step": step,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read": usage.get("cache_read_input_tokens", 0),
                "cache_creation": usage.get("cache_creation_input_tokens", 0),
                "context_pct": usage.get("context_pct", 0.0),
                "model": event.get("model", ""),
            }
            result["step_details"].append(step_info)
            result["total_input_tokens"] += step_info["input_tokens"]
            result["total_output_tokens"] += step_info["output_tokens"]
            result["total_cache_read_tokens"] += step_info["cache_read"]
            result["total_cache_creation_tokens"] += step_info["cache_creation"]
            result["max_context_pct"] = max(result["max_context_pct"], step_info["context_pct"])

        elif etype == "tool.call_started":
            tool_name = event.get("tool_name", "")
            if tool_name == "compact":
                result["compaction_events"].append({
                    "step": event.get("step", -1),
                    "ts": event.get("ts", ""),
                })
            elif tool_name == "read_ref":
                result["offload_events"].append({
                    "step": event.get("step", -1),
                    "ts": event.get("ts", ""),
                })

    try:
        await client.connect()
    except (ConnectionRefusedError, OSError) as e:
        result["error"] = f"Cannot connect to daemon: {e}"
        result["elapsed_seconds"] = time.time() - start_time
        return result

    loop_task = asyncio.create_task(client.run_event_loop())

    try:
        await client.send_command("permission.set_mode", {"mode": "auto"})

        ws_result = await client.send_command("workspace.open", {
            "path": str(repo_dir.resolve())
        })
        workspace_id = ws_result.get("workspace", {}).get("workspace_id", "")

        await client.send_command("event.subscribe", {
            "topics": ["run.*", "step.*", "tool.*", "llm.usage"],
            "scope": "global",
        })

        prompt = build_prompt(instance)
        sess_result = await client.send_command("session.create", {
            "mode": "one_shot",
            "title": instance.instance_id,
            "workspace_id": workspace_id,
        })
        session_id = sess_result.get("session_id", "")

        send_result = await client.send_command("session.send_message", {
            "session_id": session_id,
            "content": prompt,
        })
        run_id = send_result.get("run_id", "")

        try:
            await asyncio.wait_for(run_finished.wait(), timeout=timeout)
        except TimeoutError:
            result["error"] = f"Timeout after {timeout}s"
            try:
                await client.send_command("run.cancel", {"run_id": run_id})
            except Exception:
                pass

        result["status"] = run_final_status["status"]
        result["steps"] = run_final_status["steps"]

        # 获取 diff
        if run_final_status["status"] in ("success", "max_steps", "cancelled", "interrupted"):
            try:
                diff_result = await client.send_command("change.diff", {
                    "workspace_id": workspace_id,
                })
                patch = diff_result.get("diff", "")
                result["has_patch"] = bool(patch)
                result["patch_length"] = len(patch)
            except IpcError:
                patch = get_diff_via_git(repo_dir)
                result["has_patch"] = bool(patch)
                result["patch_length"] = len(patch)

        # 清理
        try:
            await client.send_command("session.close", {"session_id": session_id})
        except Exception:
            pass

    except IpcError as e:
        result["error"] = f"RPC error: {e}"
    except Exception as e:
        result["error"] = f"Unexpected: {e}"
        logger.exception("Unexpected error")
    finally:
        result["elapsed_seconds"] = time.time() - start_time
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        await client.close()

    return result


def print_instance_summary(r: dict, idx: int, total: int) -> None:
    """打印单个实例的跟踪摘要"""
    print(f"\n{'─'*72}")
    print(f"[{idx}/{total}] {r['instance_id']}")
    print(f"  Repo: {r['repo']}")
    print(f"{'─'*72}")

    status_emoji = "✅" if r["has_patch"] else ("⚠️" if r["error"] else "❌")
    try:
        print(f"  Status: {status_emoji} {r['status']} | Steps: {r['steps']} | Time: {r['elapsed_seconds']:.0f}s")
    except UnicodeEncodeError:
        print(f"  Status: {r['status']} | Steps: {r['steps']} | Time: {r['elapsed_seconds']:.0f}s")

    if r["error"]:
        print(f"  ERROR: {r['error']}")
        return

    total_in = r["total_input_tokens"]
    total_out = r["total_output_tokens"]
    cache_read = r["total_cache_read_tokens"]
    cache_create = r["total_cache_creation_tokens"]

    # 缓存命中率（total_input_tokens 为未缓存净输入，分母需加回缓存读，与前端公式同口径）
    billed_in = total_in + cache_read
    cache_hit_pct = (cache_read / billed_in * 100) if billed_in > 0 else 0.0
    # 每次步骤平均 token
    avg_in_per_step = total_in / max(r["steps"], 1)
    avg_out_per_step = total_out / max(r["steps"], 1)

    print(f"  Tokens: {total_in:,} in / {total_out:,} out")
    print(f"  Cache:  {cache_read:,} read / {cache_create:,} created")
    print(f"  Cache Hit Rate: {cache_hit_pct:.1f}%")
    print(f"  Avg/Step: {avg_in_per_step:,.0f} in / {avg_out_per_step:,.0f} out")
    print(f"  Max Context: {r['max_context_pct']*100:.1f}%")
    print(f"  Compactions: {len(r['compaction_events'])} | Offloads: {len(r['offload_events'])}")

    # 步数分布（每 10 步统计一次）
    if r["step_details"]:
        step_tokens = [s["input_tokens"] for s in r["step_details"]]
        print(f"  Token range/step: {min(step_tokens):,} - {max(step_tokens):,}")

        # 缓存变化趋势：前 5 步 vs 后 5 步
        if len(r["step_details"]) >= 10:
            first5_cache = sum(s["cache_read"] for s in r["step_details"][:5])
            first5_in = sum(s["input_tokens"] for s in r["step_details"][:5])
            last5_cache = sum(s["cache_read"] for s in r["step_details"][-5:])
            last5_in = sum(s["input_tokens"] for s in r["step_details"][-5:])
            first5_rate = (first5_cache / first5_in * 100) if first5_in > 0 else 0
            last5_rate = (last5_cache / last5_in * 100) if last5_in > 0 else 0
            print(f"  Cache rate (first 5 steps): {first5_rate:.1f}%")
            print(f"  Cache rate (last 5 steps):  {last5_rate:.1f}%")

        # Context pct 趋势
        ctx_pcts = [s["context_pct"] for s in r["step_details"] if s["context_pct"] > 0]
        if len(ctx_pcts) >= 2:
            print(f"  Context pct: {ctx_pcts[0]*100:.1f}% -> {ctx_pcts[-1]*100:.1f}% (start -> end)")


def print_final_report(results: list[dict]) -> None:
    """打印最终汇总报告"""
    n = len(results)
    if n == 0:
        return

    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["error"]]
    interrupted = [r for r in results if r["status"] in ("interrupted", "max_steps", "token_budget_exhausted", "wall_clock_exceeded")]
    patched = [r for r in results if r["has_patch"]]

    print(f"\n{'='*72}")
    print(f"FINAL REPORT — {n} instances")
    print(f"{'='*72}")

    print("\n  Outcomes:")
    print(f"    Success:      {len(successful)}/{n}")
    print(f"    Interrupted:  {len(interrupted)}/{n}")
    print(f"    Failed:       {len(failed)}/{n}")
    print(f"    Has Patch:    {len(patched)}/{n}")

    # 步数统计
    all_steps = [r["steps"] for r in results if not r["error"]]
    if all_steps:
        print("\n  Steps:")
        print(f"    Min:    {min(all_steps)}")
        print(f"    Max:    {max(all_steps)}")
        print(f"    Avg:    {sum(all_steps)/len(all_steps):.1f}")
        print(f"    Median: {sorted(all_steps)[len(all_steps)//2]}")
        over_100 = sum(1 for s in all_steps if s >= 100)
        print(f"    >=100:  {over_100}/{len(all_steps)}")

    # Token 统计
    all_in = [r["total_input_tokens"] for r in results if not r["error"]]
    all_out = [r["total_output_tokens"] for r in results if not r["error"]]
    if all_in:
        print("\n  Tokens:")
        print(f"    Total Input:  {sum(all_in):,}")
        print(f"    Total Output: {sum(all_out):,}")
        print(f"    Avg Input:    {sum(all_in)/len(all_in):,.0f}")
        print(f"    Max Input:    {max(all_in):,}")
        over_budget = sum(1 for t in all_in if t >= 500_000)
        print(f"    >=500K budget: {over_budget}/{len(all_in)}")

    # 缓存统计
    all_cache = [r["total_cache_read_tokens"] for r in results if not r["error"]]
    if all_cache:
        cache_rates = []
        for r in results:
            if not r["error"] and r["total_input_tokens"] > 0:
                rate = r["total_cache_read_tokens"] / r["total_input_tokens"] * 100
                cache_rates.append(rate)
        if cache_rates:
            print("\n  Cache Hit Rate:")
            print(f"    Min:    {min(cache_rates):.1f}%")
            print(f"    Max:    {max(cache_rates):.1f}%")
            print(f"    Avg:    {sum(cache_rates)/len(cache_rates):.1f}%")
            print(f"    Median: {sorted(cache_rates)[len(cache_rates)//2]:.1f}%")

    # 压缩事件
    total_compactions = sum(len(r.get("compaction_events", [])) for r in results)
    total_offloads = sum(len(r.get("offload_events", [])) for r in results)
    print(f"\n  Compactions: {total_compactions} | Offloads: {total_offloads}")

    # 时间统计
    all_time = [r["elapsed_seconds"] for r in results]
    print("\n  Time:")
    print(f"    Total:  {sum(all_time):.0f}s ({sum(all_time)/60:.1f}min)")
    print(f"    Avg:    {sum(all_time)/len(all_time):.0f}s")

    # 预算被触发的情况
    budget_triggers = []
    for r in results:
        reasons = []
        if r["status"] == "max_steps":
            reasons.append("max_steps")
        if r["status"] == "token_budget_exhausted":
            reasons.append("token_budget")
        if r["status"] == "wall_clock_exceeded":
            reasons.append("wall_clock")
        if reasons:
            budget_triggers.append(f"    {r['instance_id']}: {', '.join(reasons)}")
    if budget_triggers:
        print("\n  Guardrail Triggers:")
        for bt in budget_triggers:
            print(bt)
    else:
        print("\n  Guardrail Triggers: None (all completed naturally)")

    print(f"\n{'='*72}")


async def main_async(
    instance_ids: list[str],
    workspace: Path,
    host: str = "127.0.0.1",
    port: int = 7437,
    timeout: int = 900,
) -> None:
    """主异步函数"""
    # 加载数据集
    instances_data = load_dataset("princeton-nlp/SWE-bench_Lite", "test")
    instance_map = {d["instance_id"]: d for d in instances_data}

    # 选择实例
    selected = []
    for iid in instance_ids:
        if iid in instance_map:
            selected.append(instance_map[iid])
        else:
            logger.warning(f"Instance not found: {iid}")

    if not selected:
        logger.error("No valid instances to run")
        return

    total = len(selected)
    logger.info(f"Running {total} instances with tracking...")
    logger.info(f"Daemon: {host}:{port} | Timeout: {timeout}s")
    logger.info(f"Workspace: {workspace}")

    all_results = []

    for i, inst_data in enumerate(selected):
        instance = SWEbenchInstance.from_dict(inst_data)
        logger.info(f"\n[{i+1}/{total}] {instance.instance_id}")
        logger.info(f"  Repo: {instance.repo} @ {instance.base_commit[:10]}")

        # 克隆
        try:
            repo_dir = clone_repo(instance, workspace)
        except Exception as e:
            logger.error(f"  Clone failed: {e}")
            all_results.append({
                "instance_id": instance.instance_id,
                "repo": instance.repo,
                "status": "clone_failed",
                "error": str(e),
                "steps": 0,
                "elapsed_seconds": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cache_read_tokens": 0,
                "total_cache_creation_tokens": 0,
                "max_context_pct": 0,
                "has_patch": False,
                "patch_length": 0,
                "step_details": [],
                "compaction_events": [],
                "offload_events": [],
            })
            continue

        # 运行
        result = await run_instance_tracked(
            instance, repo_dir, host=host, port=port, timeout=timeout
        )
        all_results.append(result)

        # 实时打印摘要
        print_instance_summary(result, i + 1, total)

    # 最终报告
    print_final_report(all_results)

    # 保存详情 JSON
    detail_path = workspace / "tracked_run_detail.json"
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"\nDetailed results saved to: {detail_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SWE-bench 多实例跟踪运行")
    parser.add_argument(
        "--instance-ids", default="",
        help="逗号分隔的 instance_id 列表"
    )
    parser.add_argument(
        "--workspace", default="eval/reports/tracked-workspace",
        help="工作目录"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7437)
    parser.add_argument("--timeout", type=int, default=900, help="每个实例超时（秒）")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 默认 5 个多样性实例
    if args.instance_ids:
        instance_ids = [x.strip() for x in args.instance_ids.split(",") if x.strip()]
    else:
        instance_ids = [
            "django__django-11011",          # Django ORM fix, medium
            "sympy__sympy-12481",            # SymPy math, moderate
            "psf__requests-1963",            # Requests small change
            "scikit-learn__scikit-learn-10297",  # ML bug fix
            "astropy__astropy-12907",        # Astro fix
        ]

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    asyncio.run(main_async(
        instance_ids=instance_ids,
        workspace=workspace,
        host=args.host,
        port=args.port,
        timeout=args.timeout,
    ))


if __name__ == "__main__":
    main()
