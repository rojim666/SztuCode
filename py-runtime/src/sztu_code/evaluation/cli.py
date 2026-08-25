from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from sztu_code.evaluation.harness import run_manifest
from sztu_code.evaluation.models import EvaluationReport, InternalTask, TaskManifest
from sztu_code.evaluation.reporting import (
    build_report,
    export_swebench_predictions,
    render_markdown,
    write_report,
)
from sztu_code.evaluation.runners import (
    CommandRunner,
    EvaluationRunner,
    ReferenceRunner,
    SztuRpcRunner,
)
from sztu_code.evaluation.tasks import (
    default_manifest_path,
    load_manifest,
    select_tasks,
)


# 为需要任务清单的子命令添加统一筛选参数
def _add_manifest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--suite",
        choices=("internal", "swebench-lite"),
        default="internal",
        help="随包分发的任务集",
    )
    parser.add_argument("--manifest", type=Path, help="自定义版本化任务清单 JSON")
    parser.add_argument("--task-id", action="append", default=[], help="只选择指定任务")
    parser.add_argument("--max-tasks", type=int, help="最多选择多少个任务")


# 构建统一 eval 命令的子命令和安全默认值
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sztu-eval",
        description="SztuCode Coding Agent 自动化评测入口",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    validate_parser = subparsers.add_parser("validate", help="校验任务清单")
    _add_manifest_arguments(validate_parser)

    list_parser = subparsers.add_parser("list", help="列出任务")
    _add_manifest_arguments(list_parser)
    list_parser.add_argument("--json", action="store_true", help="输出 JSON")

    run_parser = subparsers.add_parser("run", help="执行任务并生成双格式报告")
    _add_manifest_arguments(run_parser)
    run_parser.add_argument(
        "--runner",
        choices=("reference", "command", "sztucode-rpc"),
        default="reference",
    )
    run_parser.add_argument(
        "--command",
        help="command runner 的 argv 字符串，不经过 Shell",
    )
    run_parser.add_argument("--repeat", type=int, default=1, help="每个任务重复次数")
    run_parser.add_argument("--timeout", type=float, default=600.0, help="单次 runner 超时秒数")
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/reports/latest"),
        help="report.json 与 summary.md 输出目录",
    )
    run_parser.add_argument(
        "--keep-workspaces",
        action="store_true",
        help="保留隔离工作区用于调试，默认自动清理",
    )
    run_parser.add_argument("--host", default="127.0.0.1", help="SztuCode daemon 地址")
    run_parser.add_argument("--port", type=int, default=7437, help="SztuCode daemon 端口")
    run_parser.add_argument(
        "--permission-mode",
        choices=("normal", "accept_edits", "auto"),
        default="accept_edits",
        help="sztucode-rpc 使用的权限模式",
    )
    run_parser.add_argument(
        "--allow-auto-permissions",
        action="store_true",
        help="显式确认仅在临时评测工作区启用 auto 权限",
    )

    report_parser = subparsers.add_parser("report", help="从 JSON 报告重建 Markdown")
    report_parser.add_argument("--input", type=Path, required=True)
    report_parser.add_argument("--output", type=Path)

    export_parser = subparsers.add_parser(
        "export-swebench", help="导出官方 SWE-bench harness predictions.jsonl"
    )
    _add_manifest_arguments(export_parser)
    export_parser.add_argument("--report", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--model-name", default="sztu-code")
    export_parser.add_argument("--repetition", type=int, default=1)
    return parser


# 加载默认或自定义清单并应用任务筛选
def _manifest_from_args(args: argparse.Namespace) -> TaskManifest:
    path = args.manifest or default_manifest_path(args.suite)
    manifest = load_manifest(path)
    task_ids = set(args.task_id) if args.task_id else None
    return select_tasks(manifest, task_ids=task_ids, max_tasks=args.max_tasks)


# 根据 CLI 参数构造 reference、外部命令或生产 daemon runner
def _runner_from_args(
    args: argparse.Namespace,
    manifest: TaskManifest,
) -> EvaluationRunner:
    if args.runner == "reference":
        if any(not isinstance(task, InternalTask) for task in manifest.tasks):
            raise ValueError("reference runner only supports the internal suite")
        return ReferenceRunner()
    if args.runner == "command":
        if not args.command:
            raise ValueError("--command is required for command runner")
        command = shlex.split(args.command, posix=os.name != "nt")
        return CommandRunner(command)
    if args.permission_mode == "auto" and not args.allow_auto_permissions:
        raise ValueError("auto permission mode requires --allow-auto-permissions")
    return SztuRpcRunner(args.host, args.port, args.permission_mode)


# 校验任务清单并打印来源和任务数量
def _validate_command(args: argparse.Namespace) -> int:
    manifest = _manifest_from_args(args)
    print(f"valid: {manifest.name} ({len(manifest.tasks)} tasks)")
    return 0


# 以表格或 JSON 列出统一任务描述
def _list_command(args: argparse.Namespace) -> int:
    manifest = _manifest_from_args(args)
    rows = [
        {
            "id": task.id,
            "source": task.source,
            "category": task.category.value,
            "title": task.title,
        }
        for task in manifest.tasks
    ]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print("ID\tSOURCE\tCATEGORY\tTITLE")
    for row in rows:
        print(f"{row['id']}\t{row['source']}\t{row['category']}\t{row['title']}")
    return 0


# 执行评测、聚合稳定性并原子交付 JSON 与 Markdown 路径
def _run_command(args: argparse.Namespace) -> int:
    manifest = _manifest_from_args(args)
    runner = _runner_from_args(args, manifest)
    workspace_root = args.output_dir / "workspaces" if args.keep_workspaces else None
    records = run_manifest(
        manifest,
        runner,
        repetitions=args.repeat,
        timeout_seconds=args.timeout,
        workspace_root=workspace_root,
    )
    report = build_report(manifest, runner.name, args.repeat, records)
    json_path, markdown_path = write_report(report, args.output_dir)
    print(f"json={json_path}")
    print(f"markdown={markdown_path}")
    print(
        f"runs={report.summary.total_runs} successes={report.summary.successes} "
        f"failures={report.summary.failures} errors={report.summary.errors} "
        f"unscored={report.summary.unscored}"
    )
    return 1 if report.summary.failures or report.summary.errors else 0


# 从机器报告重建人类可读 Markdown，便于报告模板独立演进
def _report_command(args: argparse.Namespace) -> int:
    report = EvaluationReport.model_validate_json(args.input.read_text(encoding="utf-8"))
    output = args.output or args.input.with_name("summary.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(f"markdown={output}")
    return 0


# 从统一报告导出指定重复轮次的 SWE-bench 官方预测文件
def _export_command(args: argparse.Namespace) -> int:
    manifest = _manifest_from_args(args)
    report = EvaluationReport.model_validate_json(args.report.read_text(encoding="utf-8"))
    count = export_swebench_predictions(
        report,
        manifest,
        args.output,
        args.model_name,
        repetition=args.repetition,
    )
    print(f"predictions={args.output} count={count}")
    return 0


# 解析统一命令并将可诊断输入错误转换为退出码 2
def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "validate": _validate_command,
        "list": _list_command,
        "run": _run_command,
        "report": _report_command,
        "export-swebench": _export_command,
    }
    try:
        return commands[args.subcommand](args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


# 将库式返回码转换为 console script 进程退出状态
def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
