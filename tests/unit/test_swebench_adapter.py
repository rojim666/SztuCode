from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

# eval 不在安装包内（pyproject 仅打包 src/sztu_code），将仓库根目录加入导入路径
_SRC_ROOT = Path(__file__).resolve().parents[2]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from eval.swebench import adapter as swebench_adapter  # noqa: E402
from eval.swebench.adapter import (  # noqa: E402
    RunResult,
    SWEbenchInstance,
    TokenUsage,
    _find_local_parquet,
    build_prompt,
    get_diff_via_git,
    load_dataset,
    summarize_token_usage,
)

from sztu_code.core.bus.events import LlmUsageEvent  # noqa: E402


# 构造包含全部必需字段的最小 SWE-bench 实例
def _sample_instance() -> SWEbenchInstance:
    return SWEbenchInstance.from_dict(
        {
            "instance_id": "owner__repo-1",
            "repo": "owner/repo",
            "base_commit": "abc123",
            "problem_statement": "Fix the failing behavior.",
        }
    )


# 在临时仓库中执行 Git 命令并返回结果
def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


# 创建带有一个基线提交的本地 Git 仓库
def _create_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "--quiet")
    _run_git(repo, "config", "user.name", "SztuCode Tests")
    _run_git(repo, "config", "user.email", "tests@example.com")
    (repo / "sample.py").write_text("value = 1\n", encoding="utf-8")
    _run_git(repo, "add", "sample.py")
    _run_git(repo, "commit", "--quiet", "-m", "baseline")
    return repo


# 功能：SWEbenchInstance.from_dict 拒绝缺失任一必需字段的输入
# 设计：参数化删除四个核心字段，直接验证字典访问保留清晰的 KeyError 失败语义
@pytest.mark.parametrize(
    "missing_field",
    ["instance_id", "repo", "base_commit", "problem_statement"],
)
def test_instance_from_dict_requires_core_fields(missing_field: str) -> None:
    data = {
        "instance_id": "owner__repo-1",
        "repo": "owner/repo",
        "base_commit": "abc123",
        "problem_statement": "Fix the failing behavior.",
    }
    data.pop(missing_field)

    with pytest.raises(KeyError, match=missing_field):
        SWEbenchInstance.from_dict(data)


# 功能：SWEbenchInstance.from_dict 为所有可选字段提供空字符串默认值
# 设计：只传必需字段并逐项断言默认值，防止数据集缺少可选列时解析失败
def test_instance_from_dict_defaults_optional_fields() -> None:
    instance = _sample_instance()

    assert instance.hints_text == ""
    assert instance.test_patch == ""
    assert instance.patch == ""
    assert instance.fail_to_pass == ""
    assert instance.pass_to_pass == ""


# 功能：build_prompt 包含实例对应的仓库和问题描述
# 设计：使用最小真实实例验证动态上下文，避免只检查固定模板文本
def test_build_prompt_includes_instance_context() -> None:
    prompt = build_prompt(_sample_instance())

    assert "owner/repo" in prompt
    assert "Fix the failing behavior." in prompt


# 功能：build_prompt 明确要求定位根因、最小修改和受控测试文件变更
# 设计：断言关键约束短语，模板弱化实现纪律时测试会给出直接反馈
def test_build_prompt_includes_implementation_constraints() -> None:
    prompt = build_prompt(_sample_instance())

    assert "Identify the root cause, not just the symptom" in prompt
    assert "Make minimal, targeted changes" in prompt
    assert "Do not modify test files unless explicitly asked" in prompt


# 功能：RunResult.to_pred_dict 只输出官方 predictions 所需的三个字段
# 设计：同时填充内部遥测字段并断言完整字典相等，防止评测输出泄漏额外状态
def test_run_result_to_pred_dict_exposes_only_prediction_fields() -> None:
    result = RunResult(
        instance_id="owner__repo-1",
        model_patch="diff --git a/a.py b/a.py\n",
        model_name_or_path="sztu-code-test",
        status="success",
        steps=3,
        input_tokens=100,
    )

    assert result.to_pred_dict() == {
        "instance_id": "owner__repo-1",
        "model_patch": "diff --git a/a.py b/a.py\n",
        "model_name_or_path": "sztu-code-test",
    }


# 功能：_find_local_parquet 优先识别数据集名称生成的标准文件名
# 设计：切换到隔离临时目录并创建唯一候选，验证相对 data 路径契约
def test_find_local_parquet_uses_standard_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    expected = Path("data/princeton-nlp_SWE-bench_Lite_test.parquet")
    alias = Path("data/swebench_lite_test.parquet")
    (tmp_path / expected).parent.mkdir()
    (tmp_path / expected).touch()
    (tmp_path / alias).touch()

    assert _find_local_parquet("princeton-nlp/SWE-bench_Lite", "test") == expected


# 功能：_find_local_parquet 在标准文件缺失时识别 SWE-bench 简写别名
# 设计：仅创建别名候选，证明回退顺序不会依赖当前仓库中的 data 文件
def test_find_local_parquet_uses_alias_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    expected = Path("data/swebench_lite_test.parquet")
    (tmp_path / expected).parent.mkdir()
    (tmp_path / expected).touch()

    assert _find_local_parquet("princeton-nlp/SWE-bench_Lite", "test") == expected


# 功能：_find_local_parquet 在没有本地候选文件时返回 None
# 设计：使用空临时目录覆盖缺失路径，避免受开发机现有数据集影响
def test_find_local_parquet_returns_none_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _find_local_parquet("princeton-nlp/SWE-bench_Lite", "test") is None


# 功能：get_diff_via_git 对没有工作区修改的本地仓库返回空补丁
# 设计：创建真实基线提交后立即取 diff，覆盖 Git fallback 的空结果契约
def test_get_diff_via_git_returns_empty_for_clean_repo(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path)

    assert get_diff_via_git(repo) == ""


# 功能：get_diff_via_git 为已跟踪文件的普通修改生成 unified diff
# 设计：修改真实临时仓库中的文本文件并检查头部与增删行，不模拟 subprocess
def test_get_diff_via_git_returns_tracked_file_changes(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path)
    (repo / "sample.py").write_text("value = 2\n", encoding="utf-8")

    patch = get_diff_via_git(repo)

    assert "diff --git a/sample.py b/sample.py" in patch
    assert "-value = 1" in patch
    assert "+value = 2" in patch

# 功能：get_diff_via_git 将未跟踪的新建文件纳入 unified diff
# 设计：在真实临时仓库中新建但不暂存文件，验证 Git fallback 返回标准新文件补丁
def test_get_diff_via_git_includes_untracked_new_file(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path)
    (repo / "new_file.py").write_text("value = 42\n", encoding="utf-8")

    patch = get_diff_via_git(repo)

    assert "diff --git a/new_file.py b/new_file.py" in patch
    assert "new file mode 100644" in patch
    assert "+value = 42" in patch

# 功能：get_diff_via_git 同时保留修改、删除和新建文件，并忽略被 Git ignore 的文件
# 设计：在真实临时仓库中构造多类变更，验证补丁可应用且调用前后 Git 状态保持不变
def test_get_diff_via_git_includes_all_supported_changes(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path)
    (repo / "deleted.py").write_text("deleted = True\n", encoding="utf-8")
    (repo / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    _run_git(repo, "add", "deleted.py", ".gitignore")
    _run_git(repo, "commit", "--quiet", "-m", "add deletion fixture")

    (repo / "sample.py").write_text("value = 2\n", encoding="utf-8")
    (repo / "new_file.py").write_text("value = 42\n", encoding="utf-8")
    (repo / "deleted.py").unlink()
    (repo / "ignored.tmp").write_text("ignore me\n", encoding="utf-8")
    status_before = _run_git(repo, "status", "--porcelain=v1").stdout

    patch = get_diff_via_git(repo)

    assert "diff --git a/sample.py b/sample.py" in patch
    assert "-value = 1" in patch
    assert "+value = 2" in patch
    assert "diff --git a/new_file.py b/new_file.py" in patch
    assert "new file mode 100644" in patch
    assert "+value = 42" in patch
    assert "diff --git a/deleted.py b/deleted.py" in patch
    assert "deleted file mode 100644" in patch
    assert "ignored.tmp" not in patch
    assert _run_git(repo, "status", "--porcelain=v1").stdout == status_before

    patch_path = tmp_path / "model.patch"
    patch_path.write_text(patch, encoding="utf-8")
    apply_target = tmp_path / "apply-target"
    _run_git(tmp_path, "clone", "--quiet", str(repo), str(apply_target))
    _run_git(apply_target, "apply", str(patch_path))

    assert (apply_target / "sample.py").read_text(encoding="utf-8") == "value = 2\n"
    assert (apply_target / "new_file.py").read_text(encoding="utf-8") == "value = 42\n"
    assert not (apply_target / "deleted.py").exists()

# 功能：load_dataset 存在本地 Parquet 时优先返回本地数据且不调用远程加载器
# 设计：注入最小 pyarrow 与 datasets 内存模块，验证读取参数并以未调用断言阻止下载路径
def test_load_dataset_prefers_local_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    parquet_path = Path("data/princeton-nlp_SWE-bench_Lite_test.parquet")
    (tmp_path / parquet_path).parent.mkdir()
    (tmp_path / parquet_path).touch()
    rows = [{"instance_id": "owner__repo-1"}]
    table = SimpleNamespace(num_rows=1, to_pylist=Mock(return_value=rows))
    read_table = Mock(return_value=table)
    remote_load = Mock(side_effect=AssertionError("remote dataset loader must not be called"))
    fake_pyarrow = ModuleType("pyarrow")
    fake_parquet = ModuleType("pyarrow.parquet")
    fake_datasets = ModuleType("datasets")
    setattr(fake_pyarrow, "parquet", fake_parquet)
    setattr(fake_parquet, "read_table", read_table)
    setattr(fake_datasets, "load_dataset", remote_load)
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pyarrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", fake_parquet)
    monkeypatch.setitem(sys.modules, "datasets", fake_datasets)

    result = load_dataset("princeton-nlp/SWE-bench_Lite", "test")

    assert result == rows
    read_table.assert_called_once_with(parquet_path)
    remote_load.assert_not_called()


# 功能：多个 llm.usage 事件按顶层字段正确累计输入、输出与缓存 token
# 设计：构造两个与 LlmUsageEvent 形状一致的事件，断言四类 token 分别相加，覆盖 issue 根因场景
def test_sums_top_level_usage_across_multiple_events() -> None:
    events = [
        {
            "type": "llm.usage", "run_id": "r1", "ts": "t1",
            "input_tokens": 100, "output_tokens": 10,
            "cache_read_input_tokens": 50, "cache_creation_input_tokens": 5,
        },
        {
            "type": "llm.usage", "run_id": "r2", "ts": "t2",
            "input_tokens": 200, "output_tokens": 20,
            "cache_read_input_tokens": 60, "cache_creation_input_tokens": 6,
        },
    ]
    usage = summarize_token_usage(events)
    assert usage.input_tokens == 300
    assert usage.output_tokens == 30
    assert usage.cache_read_input_tokens == 110
    assert usage.cache_creation_input_tokens == 11


# 功能：缺失字段按 0 处理，不抛出异常
# 设计：事件只带部分字段，断言其余字段为 0，验证 get 默认值兜底路径
def test_missing_fields_default_to_zero() -> None:
    events = [{"type": "llm.usage", "run_id": "r1", "input_tokens": 7}]
    usage = summarize_token_usage(events)
    assert usage.input_tokens == 7
    assert usage.output_tokens == 0
    assert usage.cache_read_input_tokens == 0
    assert usage.cache_creation_input_tokens == 0


# 功能：字段显式为 None 时按 0 处理，不抛出异常
# 设计：事件序列化可能带 None 空值，or 0 兜底保证加法恒为 int
def test_none_fields_default_to_zero() -> None:
    events = [
        {
            "type": "llm.usage", "run_id": "r1", "ts": "t1",
            "input_tokens": None, "output_tokens": None,
            "cache_read_input_tokens": None, "cache_creation_input_tokens": None,
        },
    ]
    usage = summarize_token_usage(events)
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_input_tokens == 0
    assert usage.cache_creation_input_tokens == 0


# 功能：非 llm.usage 事件（即使带相似字段名）不影响统计
# 设计：混入 run.finished / tool.* 事件并携带 input_tokens 字段，断言全零，防止类型误判
def test_ignores_non_usage_events() -> None:
    events = [
        {"type": "run.finished", "run_id": "r1", "status": "success", "input_tokens": 999},
        {"type": "tool.call_started", "tool_name": "bash", "input_tokens": 1},
        {"type": "step.started", "step": 1},
    ]
    usage = summarize_token_usage(events)
    assert usage == TokenUsage()


# 功能：空事件列表返回全零汇总
# 设计：无事件是最简输入，断言 dataclass 相等即可覆盖默认值
def test_empty_events_yield_zero_usage() -> None:
    assert summarize_token_usage([]) == TokenUsage()


# 功能：直接消费 LlmUsageEvent 模型序列化产物，与现行协议字段保持一致
# 设计：用真实 pydantic 模型 model_dump 喂给函数，字段改名或形状变化时此测试会失败，
#      防止模型升级后统计静默归零
def test_consumes_lm_usage_event_serialization() -> None:
    ev = LlmUsageEvent(
        run_id="r1",
        input_tokens=42,
        output_tokens=7,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=1,
        context_pct=0.5,
        model="test-model",
        ts="t1",
    )
    usage = summarize_token_usage([ev.model_dump()])
    assert usage.input_tokens == 42
    assert usage.output_tokens == 7
    assert usage.cache_read_input_tokens == 3
    assert usage.cache_creation_input_tokens == 1


# 功能：交错事件只保留当前 run，且其他 run 的完成事件不能唤醒等待
# 设计：先记录未绑定 run_id 的混合事件，再绑定当前 run 并继续交错记录，验证日志和 token 统计均已隔离
def test_run_event_collector_filters_interleaved_events() -> None:
    collector = swebench_adapter._RunEventCollector()
    collector.record({
        "type": "run.finished", "run_id": "other", "status": "success", "steps": 99,
    })
    collector.record({"type": "step.started", "run_id": "current", "step": 1})
    collector.record({"type": "llm.usage", "run_id": "other", "input_tokens": 900})
    collector.record({
        "type": "tool.call_started", "run_id": "current", "tool_name": "bash",
    })
    collector.record({
        "type": "llm.usage", "run_id": "current", "input_tokens": 12, "output_tokens": 3,
    })

    collector.set_run_id("current")
    assert not collector.finished.is_set()

    collector.record({
        "type": "run.finished", "run_id": "other", "status": "failure", "steps": 100,
    })
    assert not collector.finished.is_set()

    collector.record({
        "type": "run.finished", "run_id": "current", "status": "success", "steps": 2,
    })

    assert collector.finished.is_set()
    assert collector.finished_event == {
        "type": "run.finished", "run_id": "current", "status": "success", "steps": 2,
    }
    assert [event["run_id"] for event in collector.events] == ["current"] * 4
    usage = summarize_token_usage(collector.events)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 3


# 功能：run_id 返回前到达的当前完成事件不会丢失
# 设计：缓存当前和其他 run 的完成事件，绑定后只重放当前 run 的事件并立即设置完成信号
def test_run_event_collector_replays_current_finished_event_after_binding() -> None:
    collector = swebench_adapter._RunEventCollector()
    current_finished = {
        "type": "run.finished", "run_id": "current", "status": "failure", "steps": 4,
    }
    collector.record(current_finished)
    collector.record({
        "type": "run.finished", "run_id": "other", "status": "success", "steps": 8,
    })

    assert not collector.finished.is_set()
    collector.set_run_id("current")

    assert collector.finished.is_set()
    assert collector.finished_event == current_finished
    assert collector.events == [current_finished]


# 功能：当前 run 的所有终止状态都能结束等待，其他 run 的同名状态不能结束等待
# 设计：参数化覆盖 SWE-bench 适配器接受的四种 run.finished 状态
@pytest.mark.parametrize("status", ["success", "failure", "cancelled", "max_steps"])
def test_run_event_collector_accepts_all_terminal_statuses(status: str) -> None:
    collector = swebench_adapter._RunEventCollector()
    collector.set_run_id("current")

    collector.record({
        "type": "run.finished", "run_id": "other", "status": status, "steps": 8,
    })
    assert not collector.finished.is_set()

    collector.record({
        "type": "run.finished", "run_id": "current", "status": status, "steps": 3,
    })

    assert collector.finished.is_set()
    assert collector.finished_event is not None
    assert collector.finished_event["status"] == status
    assert collector.finished_event["steps"] == 3


# 功能：无法归属 run 的事件不会污染日志，也不会结束当前等待
# 设计：当前 run 已绑定时记录缺少 run_id 的完成和 token 事件，断言均被忽略
def test_run_event_collector_ignores_events_without_run_id() -> None:
    collector = swebench_adapter._RunEventCollector()
    collector.set_run_id("current")

    collector.record({"type": "run.finished", "status": "success", "steps": 1})
    collector.record({"type": "llm.usage", "input_tokens": 50})

    assert collector.events == []
    assert not collector.finished.is_set()


# 功能：空的 RPC run_id 不会被转换成可用的字符串 ID
# 设计：空字符串和 JSON null 都必须拒绝，防止无效 ID 接收其他事件
@pytest.mark.parametrize("run_id", ["", None])
def test_run_event_collector_rejects_empty_run_id(run_id: str | None) -> None:
    collector = swebench_adapter._RunEventCollector()

    with pytest.raises(ValueError, match="run_id must be non-empty"):
        collector.set_run_id(run_id)  # type: ignore[arg-type]


# 功能：RPC 适配器只用当前 run 的完成事件、日志和 token 生成结果
# 设计：假的 SocketClient 先发送其他 run 的完成事件，返回当前 run_id 后再发送当前事件，全程不连接 daemon 或网络
@pytest.mark.asyncio
async def test_run_instance_via_rpc_ignores_other_run_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_finished = {
        "type": "run.finished", "run_id": "other", "status": "failure", "steps": 99,
    }
    current_events = [
        {"type": "step.started", "run_id": "current", "step": 1},
        {
            "type": "llm.usage",
            "run_id": "current",
            "input_tokens": 12,
            "output_tokens": 3,
        },
        {
            "type": "run.finished",
            "run_id": "current",
            "status": "success",
            "steps": 2,
        },
    ]

    class FakeSocketClient:
        def __init__(self, host: str, port: int) -> None:
            del host, port
            self._handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None
            self._message_sent = asyncio.Event()

        async def connect(self) -> None:
            pass

        async def close(self) -> None:
            pass

        def on_event(
            self,
            handler: Callable[[dict[str, Any]], Awaitable[None]],
        ) -> None:
            self._handler = handler

        async def run_event_loop(self) -> None:
            await self._message_sent.wait()
            await asyncio.sleep(0.01)
            assert self._handler is not None
            for event in current_events:
                await self._handler(event)
            await asyncio.Event().wait()

        async def send_command(
            self,
            method: str,
            params: dict[str, Any],
        ) -> dict[str, Any]:
            del params
            if method == "workspace.open":
                return {"workspace": {"workspace_id": "workspace-1"}}
            if method == "session.create":
                return {"session_id": "session-1"}
            if method == "session.send_message":
                assert self._handler is not None
                await self._handler(other_finished)
                self._message_sent.set()
                return {"run_id": "current"}
            if method == "change.diff":
                return {"diff": "diff --git a/file.py b/file.py\n"}
            return {"ok": True}

    monkeypatch.setattr(swebench_adapter, "SocketClient", FakeSocketClient)
    instance = swebench_adapter.SWEbenchInstance(
        instance_id="owner__repo-1",
        repo="owner/repo",
        base_commit="abc123",
        problem_statement="Fix the failing behavior.",
    )

    result = await swebench_adapter.run_instance_via_rpc(
        instance,
        tmp_path,
        timeout=1,
    )

    assert result.status == "success"
    assert result.steps == 2
    assert result.events_log == current_events
    assert result.input_tokens == 12
    assert result.output_tokens == 3
