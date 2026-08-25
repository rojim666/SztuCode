from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from sztu_code.evaluation.cli import main
from sztu_code.evaluation.harness import run_manifest
from sztu_code.evaluation.models import (
    FailureReason,
    FileChange,
    InternalTask,
    RunRecord,
    RunStatus,
    TaskCategory,
    TaskManifest,
    ValidationSpec,
)
from sztu_code.evaluation.reporting import (
    build_report,
    export_swebench_predictions,
    pass_at_k,
    render_markdown,
    write_report,
)
from sztu_code.evaluation.runners import CommandRunner, ReferenceRunner, SztuRpcRunner
from sztu_code.evaluation.tasks import (
    default_manifest_path,
    load_manifest,
    public_task_payload,
    safe_relative_path,
    select_tasks,
)


# 构造只有一个文件修改和独立验证命令的最小内部任务
def _internal_task(validation_code: str = "assert open('value.txt').read() == 'fixed\\n'") -> InternalTask:
    return InternalTask(
        id="internal.test.fixture",
        title="Fixture task",
        category=TaskCategory.GENERAL,
        prompt="Replace the old value with the fixed value.",
        workspace_files={"value.txt": "old\n"},
        validation=ValidationSpec(command=["{python}", "-c", validation_code]),
        expected_modified_files=["value.txt"],
        reference_changes=[FileChange(path="value.txt", content="fixed\n")],
    )


# 将最小任务包装为统一清单，便于各测试只关注目标行为
def _manifest(task: InternalTask | None = None) -> TaskManifest:
    return TaskManifest(
        name="test-suite",
        description="Test suite",
        tasks=[task or _internal_task()],
    )


class _FakeSocketClient:
    instances: list[_FakeSocketClient] = []

    # 初始化可记录权限切换并主动投递事件的假 daemon 客户端
    def __init__(self, host: str, port: int) -> None:
        del host, port
        self.permission_modes: list[str] = []
        self.closed = False
        self._event_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self.instances.append(self)

    # 模拟建立 daemon 连接
    async def connect(self) -> None:
        return None

    # 注册评测事件回调
    def on_event(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._event_handler = handler

    # 保持事件循环存活，直到评测器在 finally 中取消任务
    async def run_event_loop(self) -> None:
        await asyncio.Event().wait()

    # 返回最小协议响应，并在 send_message 响应前制造 run.finished 竞态
    async def send_command(
        self,
        command_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if command_type == "settings.get":
            return {"settings": {"permission_mode": "normal"}}
        if command_type == "permission.set_mode":
            self.permission_modes.append(str(params["mode"]))
            return {"ok": True, "mode": params["mode"]}
        if command_type == "workspace.open":
            return {"workspace": {"workspace_id": "workspace-1"}}
        if command_type == "session.create":
            return {"session_id": "session-1"}
        if command_type == "session.send_message":
            assert self._event_handler is not None
            await self._event_handler(
                {
                    "type": "run.finished",
                    "run_id": "run-1",
                    "status": "success",
                    "steps": 2,
                }
            )
            return {"run_id": "run-1"}
        return {}

    # 记录评测器已经关闭连接
    async def close(self) -> None:
        self.closed = True


# 功能：验证随包分发的内部与 SWE-bench Lite 清单数量和来源正确
# 设计：直接走公开加载入口，覆盖 JSON、判别联合、唯一性和路径安全校验
def test_bundled_manifests_are_valid() -> None:
    internal = load_manifest(default_manifest_path("internal"))
    swebench = load_manifest(default_manifest_path("swebench-lite"))

    assert len(internal.tasks) == 10
    assert {task.category for task in internal.tasks} >= {
        TaskCategory.LONG_CONTEXT,
        TaskCategory.CROSS_LANGUAGE,
        TaskCategory.SECURITY,
        TaskCategory.COLLABORATION,
    }
    assert len(swebench.tasks) == 3
    assert {task.source for task in swebench.tasks} == {"swebench_lite"}


# 功能：验证任务工作区路径拒绝绝对路径、回退片段和 Windows 分隔符
# 设计：逐个命中三条独立安全边界，防止清单在准备阶段写出临时工作区
def test_safe_relative_path_rejects_workspace_escape() -> None:
    for unsafe in ("../secret.txt", "/tmp/secret.txt", "..\\secret.txt"):
        try:
            safe_relative_path(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe path accepted: {unsafe}")


# 功能：验证交给外部 Agent 的任务负载不会泄露 reference_changes 参考答案
# 设计：从真实内部清单取任务，检查公开字段存在且解答字段完全缺失
def test_public_task_payload_hides_reference_solution() -> None:
    task = load_manifest(default_manifest_path("internal")).tasks[0]
    payload = public_task_payload(task)

    assert payload["id"] == task.id
    assert "prompt" in payload
    assert "reference_changes" not in payload
    assert "workspace_files" not in payload


# 功能：验证 10 个内部任务重复三次后全部通过并生成稳定性与资源指标
# 设计：使用 reference runner 隔离模型随机性，集中验证 fixture、评分和聚合链路
def test_reference_runner_repeats_internal_suite() -> None:
    manifest = load_manifest(default_manifest_path("internal"))
    records = run_manifest(manifest, ReferenceRunner(), 3, 30)
    report = build_report(manifest, "reference", 3, records)

    assert len(records) == 30
    assert {record.status for record in records} == {RunStatus.PASSED}
    assert report.summary.successes == 30
    assert report.summary.success_rate == 1.0
    assert report.summary.total_modified_files > 0
    assert all(item.pass_at_k == 1.0 for item in report.task_summaries)
    assert all(item.stability == 1.0 for item in report.task_summaries)


# 功能：验证独立验证命令失败会记录 validation_failed 而不是误报 runner 错误
# 设计：让参考修改成功落盘但断言故意失败，分离执行成功和任务成功两个概念
def test_validation_failure_has_structured_reason() -> None:
    manifest = _manifest(_internal_task("raise AssertionError('still broken')"))
    record = run_manifest(manifest, ReferenceRunner(), 1, 30)[0]

    assert record.status == RunStatus.FAILED
    assert record.success is False
    assert record.failure_reason == FailureReason.VALIDATION_FAILED
    assert "still broken" in record.runner_output


# 功能：验证 command runner 修改允许范围外文件时触发 scope_violation
# 设计：用无 Shell 的当前 Python 进程同时改目标文件和新增文件，覆盖快照差异检测
def test_command_runner_detects_scope_violation() -> None:
    code = "from pathlib import Path; Path('value.txt').write_text('fixed\\n'); Path('extra.txt').write_text('x')"
    runner = CommandRunner([sys.executable, "-c", code])
    record = run_manifest(_manifest(), runner, 1, 30)[0]

    assert record.status == RunStatus.FAILED
    assert record.failure_reason == FailureReason.SCOPE_VIOLATION
    assert record.unexpected_paths == ["extra.txt"]


# 功能：验证外部 Agent 可通过指标文件上报 Token、工具调用和步数
# 设计：命令读取框架提供的环境变量写入 JSON，避免依赖真实模型或 daemon
def test_command_runner_collects_optional_metrics() -> None:
    code = (
        "from pathlib import Path; import json, os; "
        "Path('value.txt').write_text('fixed\\n'); "
        "Path(os.environ['SZTU_EVAL_METRICS_FILE']).write_text("
        "json.dumps({'input_tokens': 10, 'output_tokens': 2, 'tool_calls': 3, 'steps': 2}))"
    )
    runner = CommandRunner([sys.executable, "-c", code])
    record = run_manifest(_manifest(), runner, 1, 30)[0]

    assert record.status == RunStatus.PASSED
    assert record.metrics.input_tokens == 10
    assert record.metrics.output_tokens == 2
    assert record.metrics.tool_calls == 3
    assert record.metrics.steps == 2


# 功能：验证非法负数指标被归类为 invalid_metrics 并阻止任务误报成功
# 设计：runner 完成文件修改后写入负 Token，证明指标校验优先于验证通过
def test_command_runner_rejects_invalid_metrics() -> None:
    code = (
        "from pathlib import Path; import json, os; "
        "Path('value.txt').write_text('fixed\\n'); "
        "Path(os.environ['SZTU_EVAL_METRICS_FILE']).write_text("
        "json.dumps({'input_tokens': -1}))"
    )
    runner = CommandRunner([sys.executable, "-c", code])
    record = run_manifest(_manifest(), runner, 1, 30)[0]

    assert record.status == RunStatus.ERROR
    assert record.failure_reason == FailureReason.INVALID_METRICS


# 功能：验证 pass@k 对全失败、部分成功和必然成功样本使用正确组合公式
# 设计：选择可手算的四次两成功样本，同时覆盖两个概率边界
def test_pass_at_k_uses_finite_sample_estimator() -> None:
    assert pass_at_k(4, 0, 2) == 0.0
    assert pass_at_k(4, 2, 2) == 5 / 6
    assert pass_at_k(4, 4, 2) == 1.0


# 功能：验证同一报告可以写出 JSON、Markdown并从 JSON 无损恢复
# 设计：用单任务真实运行结果检查模型往返及人类报告关键指标而非快照全文
def test_report_roundtrip_writes_json_and_markdown(tmp_path: Path) -> None:
    manifest = _manifest()
    records = run_manifest(manifest, ReferenceRunner(), 2, 30)
    report = build_report(manifest, "reference", 2, records)

    json_path, markdown_path = write_report(report, tmp_path)
    restored = type(report).model_validate_json(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert restored == report
    assert "Success rate | 100.0%" in markdown
    assert "pass@k" in render_markdown(restored)


# 功能：验证统一 SWE-bench 运行记录可导出官方 predictions.jsonl 三字段契约
# 设计：构造未评分但已有 patch 的记录，确保框架不把生成 patch 等同于 resolved
def test_export_swebench_predictions_preserves_unscored_patch(tmp_path: Path) -> None:
    manifest = select_tasks(
        load_manifest(default_manifest_path("swebench-lite")),
        max_tasks=1,
    )
    task = manifest.tasks[0]
    record = RunRecord(
        task_id=task.id,
        source="swebench_lite",
        category=task.category,
        repetition=1,
        runner="test",
        status=RunStatus.UNSCORED,
        success=None,
        patch="diff --git a/a.py b/a.py\n",
    )
    report = build_report(manifest, "test", 1, [record])
    output = tmp_path / "predictions.jsonl"

    count = export_swebench_predictions(report, manifest, output, "test-model")
    prediction = json.loads(output.read_text(encoding="utf-8"))

    assert count == 1
    assert prediction["model_patch"] == record.patch
    assert prediction["model_name_or_path"] == "test-model"
    assert report.summary.unscored == 1
    assert report.summary.success_rate is None


# 功能：验证统一 CLI 能校验、筛选并运行内部任务生成两种报告
# 设计：直接调用库式 main 避免子进程差异，只执行两个 fixture 保持测试快速
def test_cli_runs_selected_internal_tasks(tmp_path: Path, capsys: object) -> None:
    del capsys
    output = tmp_path / "report"
    exit_code = main(
        [
            "run",
            "--suite",
            "internal",
            "--runner",
            "reference",
            "--repeat",
            "2",
            "--max-tasks",
            "2",
            "--output-dir",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["total_runs"] == 4
    assert (output / "summary.md").is_file()


# 功能：验证 RPC runner 的 auto 权限必须由调用者显式确认
# 设计：在连接 daemon 前触发参数门禁，保证测试离线且覆盖高风险默认值
def test_cli_requires_explicit_auto_permission_confirmation(tmp_path: Path) -> None:
    exit_code = main(
        [
            "run",
            "--suite",
            "internal",
            "--runner",
            "sztucode-rpc",
            "--permission-mode",
            "auto",
            "--max-tasks",
            "1",
            "--output-dir",
            str(tmp_path / "report"),
        ]
    )

    assert exit_code == 2


# 功能：验证 RPC runner 隔离并接收提前到达的事件且恢复 daemon 原权限模式
# 设计：假客户端在 send_message 返回前投递完成事件，覆盖竞态与 finally 恢复路径
def test_rpc_runner_restores_permission_mode_after_early_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeSocketClient.instances.clear()
    monkeypatch.setattr(
        "sztu_code.evaluation.runners.SocketClient",
        _FakeSocketClient,
    )
    runner = SztuRpcRunner("127.0.0.1", 9999, "auto")

    outcome = runner.run(_internal_task(), tmp_path, tmp_path / "artifacts", 5)

    client = _FakeSocketClient.instances[-1]
    assert outcome.failure_reason is None
    assert outcome.steps == 2
    assert client.permission_modes == ["auto", "normal"]
    assert client.closed is True


# 功能：验证 command runner 通过环境变量获得公开任务文件且不含参考答案
# 设计：外部命令读取 task JSON 自检字段后完成修改，覆盖真实集成边界
def test_command_runner_receives_sanitized_task_file() -> None:
    code = (
        "from pathlib import Path; import json, os; "
        "data=json.loads(Path(os.environ['SZTU_EVAL_TASK_FILE']).read_text()); "
        "assert 'reference_changes' not in data; "
        "assert Path(os.environ['SZTU_EVAL_WORKSPACE']).resolve() == Path.cwd().resolve(); "
        "Path('value.txt').write_text('fixed\\n')"
    )
    record = run_manifest(
        _manifest(),
        CommandRunner([sys.executable, "-c", code]),
        1,
        30,
    )[0]

    assert record.status == RunStatus.PASSED
    assert os.environ.get("SZTU_EVAL_TASK_FILE") is None
