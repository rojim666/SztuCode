from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sztu_code.core.config import SztuConfig
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.runner import AgentRunner
from sztu_code.core.session.model import RunStats, Session
from sztu_code.core.session.store import SessionStore

# --- mock provider -----------------------------------------------------------


class _EndTurnProvider:
    """Immediately returns end_turn; no API calls made."""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        return LlmResponse(stop_reason="end_turn", text="done")


class _LoopingProvider:
    """Always returns tool_use with an unknown tool to exhaust max_steps."""

    def __init__(self) -> None:
        self._call = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self._call += 1
        tc = ToolCallBlock(id=f"t{self._call}", name="unknown_tool", input={})
        return LlmResponse(stop_reason="tool_use", tool_calls=[tc])


class _CapturingProvider:
    # 初始化捕获型 provider，保存固定响应
    def __init__(self, response: LlmResponse) -> None:
        self.response = response
        self.messages: list[dict[str, object]] = []
        self.system: str | None = None

    # 捕获本次 LLM 调用的 messages 和 system prompt
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self.messages = [dict(m) for m in messages]
        self.system = system
        return self.response


class _SessionCompactingProvider:
    """High-water tool_use, then a compact summary, then end_turn."""

    def __init__(self) -> None:
        self._calls = 0
        self._summary = """\
## 1. Original Goal
new goal
## 2. Completed Steps
- inspected state
## 3. Key Constraints & Discoveries
- none
## 4. Current File State
- none
## 5. Remaining TODOs
- finish
## 6. Critical Data
- none
"""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self._calls += 1
        if self._calls == 1:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[ToolCallBlock(id="t1", name="unknown_tool", input={})],
                usage=UsageStats(
                    input_tokens=100_000,
                    output_tokens=10,
                    context_pct=0.9,
                ),
            )
        if run_id == "compact":
            return LlmResponse(
                stop_reason="end_turn",
                text=self._summary,
                usage=UsageStats(input_tokens=100_000, output_tokens=10),
            )
        return LlmResponse(
            stop_reason="end_turn",
            text="done",
            usage=UsageStats(input_tokens=200, output_tokens=10),
        )


class _CancelableCompactingProvider:
    def __init__(self) -> None:
        self._calls = 0
        self.compact_started = asyncio.Event()
        self.compact_cancelled = False

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        if run_id == "compact":
            self.compact_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.compact_cancelled = True
                raise

        self._calls += 1
        if self._calls == 1:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[ToolCallBlock(id="t1", name="unknown_tool", input={})],
                usage=UsageStats(
                    input_tokens=100_000,
                    output_tokens=10,
                    context_pct=0.9,
                ),
            )

        return LlmResponse(stop_reason="end_turn", text="done")


class _AsyncCompactingProvider:
    def __init__(self) -> None:
        self._calls = 0
        self.compact_started = asyncio.Event()
        self.compact_completed = asyncio.Event()
        self._summary = """\
## 1. Original Goal
finish without session
## 2. Completed Steps
- queued compaction
## 3. Key Constraints & Discoveries
- no session store
## 4. Current File State
- none
## 5. Remaining TODOs
- none
## 6. Critical Data
- none
"""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        if run_id == "compact":
            self.compact_started.set()
            # 主循环会在下一次模型请求前等待压缩完成，因此压缩必须能独立完成，
            # 不能依赖主循环的后续调用解锁
            await asyncio.sleep(0)
            self.compact_completed.set()
            return LlmResponse(
                stop_reason="end_turn",
                text=self._summary,
                usage=UsageStats(input_tokens=100_000, output_tokens=10),
            )

        self._calls += 1
        if self._calls == 1:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[ToolCallBlock(id="t1", name="unknown_tool", input={})],
                usage=UsageStats(
                    input_tokens=100_000,
                    output_tokens=10,
                    context_pct=0.9,
                ),
            )

        return LlmResponse(
            stop_reason="end_turn",
            text="done",
            usage=UsageStats(input_tokens=200, output_tokens=10),
        )


class _FailingCompactingProvider:
    def __init__(self) -> None:
        self._calls = 0
        self.compact_started = asyncio.Event()
        self.compact_completed = asyncio.Event()
        self._summary = """\
## 1. Original Goal
survive failure
## 2. Completed Steps
- compaction drained during failure
## 3. Key Constraints & Discoveries
- main loop failed after scheduling compaction
## 4. Current File State
- none
## 5. Remaining TODOs
- inspect failure
## 6. Critical Data
- boom
"""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        if run_id == "compact":
            self.compact_started.set()
            # 新语义下主循环等压缩完成才会进入下一步（随后才失败），
            # 因此压缩分支必须能独立完成，不能等待主循环事件
            await asyncio.sleep(0)
            self.compact_completed.set()
            return LlmResponse(
                stop_reason="end_turn",
                text=self._summary,
                usage=UsageStats(input_tokens=100_000, output_tokens=10),
            )

        self._calls += 1
        if self._calls == 1:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[ToolCallBlock(id="t1", name="unknown_tool", input={})],
                usage=UsageStats(
                    input_tokens=100_000,
                    output_tokens=10,
                    context_pct=0.9,
                ),
            )

        raise RuntimeError("boom")


# --- helpers -----------------------------------------------------------------


def _config(max_steps: int = 5) -> SztuConfig:
    cfg = SztuConfig()
    cfg.agent.max_steps = max_steps
    return cfg


async def _run(
    goal: str = "test goal",
    *,
    provider: object | None = None,
    config: SztuConfig | None = None,
    tmp_path: Path,
) -> list[BaseModel]:
    collected: list[BaseModel] = []

    async def _collect(e: BaseModel) -> None:
        collected.append(e)

    cfg = config or _config()
    runner = AgentRunner(
        cfg,
        provider=provider or _EndTurnProvider(),  # type: ignore[arg-type]
        extra_handlers=[_collect],
        runs_dir=tmp_path,
    )
    await runner.run(goal)
    return collected


def _read_event_types(events_path: Path) -> list[str]:
    return [
        json.loads(line)["type"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line
    ]


# --- tests -------------------------------------------------------------------


# 功能：验证主 Agent 注册指南要求优先使用的文件与内容搜索工具
# 设计：直接构建 Registry，避免启动模型，并检查两个工具及其 Markdown schema 描述
def test_main_registry_includes_dedicated_search_tools(tmp_path: Path) -> None:
    from sztu_code.core.prompts.tool_descriptions import load_tool_descriptions
    from sztu_code.core.task.manager import TaskManager

    runner = AgentRunner(_config(), runs_dir=tmp_path / "runs")
    registry = runner._build_registry(  # noqa: SLF001
        TaskManager(tmp_path / "tasks"),
        workspace_root=tmp_path,
    )
    schemas = {str(schema["name"]): schema for schema in registry.tool_schemas()}

    assert registry.get("glob_search") is not None
    assert registry.get("grep_search") is not None
    assert schemas["glob_search"]["description"] == load_tool_descriptions()["glob_search"]
    assert schemas["grep_search"]["description"] == load_tool_descriptions()["grep_search"]


# 功能：验证 run 开始时发布携带正确 goal 的 run.started 事件
# 设计：用 extra_handlers 收集事件，而非从 events.jsonl 读取，避免文件 I/O 耦合；聚焦 runner 层的事件发布职责
async def test_run_started_event_published(tmp_path: Path) -> None:
    events = await _run(goal="my goal", tmp_path=tmp_path)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "run.started" in types
    started = next(e for e in events if e.type == "run.started")  # type: ignore[attr-defined]
    assert started.goal == "my goal"  # type: ignore[attr-defined]


# 功能：验证成功完成时发布 status=success 的 run.finished 事件
# 设计：EndTurnProvider 触发最短成功路径，聚焦 runner 层对任何终止路径都能保证发布 finished 事件
async def test_run_finished_event_published_on_success(tmp_path: Path) -> None:
    events = await _run(tmp_path=tmp_path)
    finished = next(
        (e for e in events if e.type == "run.finished"), None  # type: ignore[attr-defined]
    )
    assert finished is not None
    assert finished.status == "success"  # type: ignore[attr-defined]


# 功能：验证步数耗尽时 run.finished 携带 interrupted 状态和正确的中断原因
# 设计：LoopingProvider + max_steps=2 触发可续跑的中断路径，确认 runner 发布 finished 事件
async def test_run_finished_event_published_on_max_steps(tmp_path: Path) -> None:
    events = await _run(
        provider=_LoopingProvider(),
        config=_config(max_steps=2),
        tmp_path=tmp_path,
    )
    finished = next(e for e in events if e.type == "run.finished")  # type: ignore[attr-defined]
    assert finished.status == "interrupted"  # type: ignore[attr-defined]
    assert finished.reason == "exceeded_max_steps"  # type: ignore[attr-defined]


# 功能：验证 events.jsonl 第一行为 run.started、最后一行为 run.finished
# 设计：从 tmp_path 递归查找 events.jsonl 并按行解析，因为 events.jsonl 是 S1 的核心产物，首尾事件是完整性的最低要求；
#       显式按 utf-8 读取——EventWriter 固定 utf-8 写入，Windows 默认 gbk 会解码失败
async def test_events_jsonl_created_with_started_and_finished(tmp_path: Path) -> None:
    await _run(tmp_path=tmp_path)
    jsonl_files = list(tmp_path.rglob("events.jsonl"))
    assert len(jsonl_files) == 1
    lines = [json.loads(ln) for ln in jsonl_files[0].read_text(encoding="utf-8").splitlines() if ln]
    event_types = [e["type"] for e in lines]
    assert event_types[0] == "run.started"
    assert event_types[-1] == "run.finished"


# 功能：验证 runner 在 runs_dir 下创建以 run_id 命名的子目录并写入 events.jsonl
# 设计：检查 tmp_path 下只有一个子目录且该目录包含 events.jsonl，确认目录结构约定（runs/<run_id>/events.jsonl）
async def test_run_creates_run_subdirectory(tmp_path: Path) -> None:
    await _run(tmp_path=tmp_path)
    subdirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(subdirs) == 1
    assert (subdirs[0] / "events.jsonl").exists()


# 功能：验证通过 extra_handlers 注入的回调能收到所有事件
# 设计：注入第二个收集器，确认 extra_handlers 机制有效；这是测试代码注入 mock 观察器、生产代码接入 StdoutPrinter 的同一扩展点
async def test_extra_handlers_receive_events(tmp_path: Path) -> None:
    secondary: list[BaseModel] = []

    async def _second(e: BaseModel) -> None:
        secondary.append(e)

    cfg = _config()
    runner = AgentRunner(
        cfg,
        provider=_EndTurnProvider(),  # type: ignore[arg-type]
        extra_handlers=[_second],
        runs_dir=tmp_path,
    )
    await runner.run("goal")
    assert len(secondary) > 0


# 功能：验证 config.agent.max_steps 被正确传递给 AgentLoop，控制 LLM 调用次数上限
# 设计：用 LoopingProvider 的调用次数反推 max_steps 是否生效，不依赖内部状态检查，从行为角度验证配置传递
async def test_config_max_steps_passed_to_loop(tmp_path: Path) -> None:
    provider = _LoopingProvider()
    await _run(provider=provider, config=_config(max_steps=3), tmp_path=tmp_path)
    assert provider._call == 3


# 功能：验证配置中的工具并发上限会传递给 AgentLoop
# 设计：替换 loop.run 捕获已构造实例，直接断言 runner 不会丢失 agent 配置值
async def test_config_tool_concurrency_passed_to_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[int] = []

    async def fake_run(self: Any, context: Any) -> None:
        captured.append(self._tool_max_concurrency)
        context.mark_success()

    monkeypatch.setattr("sztu_code.core.runner.AgentLoop.run", fake_run)
    config = _config()
    config.agent.tool_max_concurrency = 2

    await _run(config=config, tmp_path=tmp_path)

    assert captured == [2]


# 功能：验证 run.started 和 run.finished 事件使用相同且非空的 run_id
# 设计：同时检查两个事件的 run_id 字段，确认 runner 在整个 run 生命周期使用同一个 run_id
async def test_run_id_embedded_in_started_event(tmp_path: Path) -> None:
    events = await _run(tmp_path=tmp_path)
    started = next(e for e in events if e.type == "run.started")  # type: ignore[attr-defined]
    finished = next(e for e in events if e.type == "run.finished")  # type: ignore[attr-defined]
    assert started.run_id == finished.run_id  # type: ignore[attr-defined]
    assert len(started.run_id) > 0  # type: ignore[attr-defined]


# 功能：验证注入外部 EventBus 时，runner 使用该 bus 而不自建，外部订阅者能收到所有事件
# 设计：显式传入 EventBus 实例并订阅收集器，确认 runner 不再内部新建 bus（否则外部订阅者收不到事件）；
#       这是 CoreApp 注入全局 bus 的核心行为，单元测试级别验证可避免集成测试的守护进程依赖
async def test_injected_bus_receives_events(tmp_path: Path) -> None:
    from sztu_code.core.events.bus import EventBus

    external_bus = EventBus()
    collected: list[object] = []

    async def collect(e: object) -> None:
        collected.append(e)

    external_bus.subscribe(collect)

    runner = AgentRunner(
        _config(),
        bus=external_bus,
        provider=_EndTurnProvider(),  # type: ignore[arg-type]
        runs_dir=tmp_path,
    )
    await runner.run("goal")

    types = [e.type for e in collected]  # type: ignore[attr-defined]
    assert "run.started" in types
    assert "run.finished" in types


# 功能：验证 session run 会从 thread.jsonl 预填带时间戳的 messages，并把 notes 注入 system prompt
# 设计：截获 LLM 入参并逐字段断言历史消息，同时确认 run 目录写到 session/runs 下
async def test_session_history_and_notes_injected(tmp_path: Path) -> None:
    from sztu_code.core.session.model import Session
    from sztu_code.core.session.store import SessionStore

    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.write_meta(session)
    store.append_message("sess-1", "user", "remember python")
    store.append_note("sess-1", "Python 3.12", "run-old")

    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    await runner.run_and_capture("remember python", run_id="run-new", session=session, store=store)

    assert len(provider.messages) == 1
    assert provider.messages[0]["role"] == "user"
    assert provider.messages[0]["content"] == "remember python"
    assert provider.messages[0]["ts"]
    assert provider.system is not None
    assert "Python 3.12" in provider.system
    assert (store.runs_dir("sess-1") / "run-new" / "events.jsonl").exists()
    assert not (tmp_path / "runs" / "run-new").exists()


# 功能：验证每次 run 都会在工作区根目录检测画像并把渲染结果注入 system prompt
# 设计：替换检测与渲染函数并用捕获型 provider 观察最终 system，避免依赖真实文件结构或模型调用
async def test_project_profile_is_injected_into_system_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    detected_roots: list[Path] = []

    # 记录检测根目录并返回最小画像替身
    def fake_detect_project_profile(root: Path) -> object:
        detected_roots.append(root)
        return object()

    monkeypatch.setattr(
        "sztu_code.core.runner.detect_project_profile", fake_detect_project_profile
    )
    monkeypatch.setattr(
        "sztu_code.core.runner.render_project_profile_context",
        lambda profile: "Language: Python\nRecommended unit test: uv run pytest",
    )
    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    outcome = await runner.run_and_capture("inspect project", workspace_root=workspace_root)

    assert outcome.status == "success"
    assert detected_roots == [workspace_root.resolve()]
    assert provider.system is not None
    assert "## Project Profile" in provider.system
    assert "Recommended unit test: uv run pytest" in provider.system


# 功能：验证 runner 的最终 system prompt 会注入工作区 CLAUDE.md
# 设计：使用捕获型 provider 观察真实 run 链路，而不是只测试提示词构建函数
async def test_claude_md_is_injected_by_runner(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "CLAUDE.md").write_text(
        "项目规则：先阅读相关代码\n",
        encoding="utf-8",
    )
    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    outcome = await runner.run_and_capture("inspect project", workspace_root=workspace_root)

    assert outcome.status == "success"
    assert provider.system is not None
    assert "## CLAUDE.md" in provider.system
    assert "项目规则：先阅读相关代码" in provider.system


# 功能：验证 runner 的最终 system prompt 会注入工作区 SZTUCODE.md
# 设计：使用捕获型 provider 观察真实 run 链路，确保桌面端/CLI 共用的底层机制生效
async def test_sztucode_md_is_injected_by_runner(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "SZTUCODE.md").write_text(
        "SztuCode 规则：修改后必须验证\n",
        encoding="utf-8",
    )
    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    outcome = await runner.run_and_capture("inspect project", workspace_root=workspace_root)

    assert outcome.status == "success"
    assert provider.system is not None
    assert "## SZTUCODE.md" in provider.system
    assert "SztuCode 规则：修改后必须验证" in provider.system


# 功能：验证未显式传入工作区时仍从当前目录读取 CLAUDE.md
# 设计：切换到临时目录运行完整链路，覆盖 CLI/TUI 默认工作区场景
async def test_claude_md_is_injected_for_default_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "CLAUDE.md").write_text("默认工作区规则\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    outcome = await runner.run_and_capture("inspect project")

    assert outcome.status == "success"
    assert provider.system is not None
    assert "## CLAUDE.md" in provider.system
    assert "默认工作区规则" in provider.system


# 功能：验证项目画像检测遇到文件系统或数据错误时不会阻断 agent run
# 设计：依次注入 OSError 和 ValueError，确认两种允许捕获的失败均保留正常 run 且不产生画像段
async def test_project_profile_detection_errors_do_not_block_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    for error_type in (OSError, ValueError):
        # 模拟检测阶段抛出可恢复的文件系统或数据异常
        def raise_detection_error(
            root: Path, error_type: type[OSError | ValueError] = error_type
        ) -> object:
            raise error_type("unreadable project metadata")

        monkeypatch.setattr(
            "sztu_code.core.runner.detect_project_profile", raise_detection_error
        )
        provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
        runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / error_type.__name__)

        outcome = await runner.run_and_capture(
            "inspect project",
            run_id=f"profile-error-{error_type.__name__}",
            workspace_root=workspace_root,
        )

        assert outcome.status == "success"
        assert provider.system is not None
        assert "## Project Profile" not in provider.system


# 功能：验证真实工作区画像会进入 Agent prompt，且 package script 正文不会被注入。
# 设计：用捕获型 provider 观察真实检测和渲染后的 system prompt，锁定推荐命令与不执行脚本正文的边界。
async def test_workspace_project_profile_is_injected_into_agent_context(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text(
        json.dumps({"name": "web", "scripts": {"build": "unsafe-build --all"}}),
        encoding="utf-8",
    )
    provider = _CapturingProvider(LlmResponse(stop_reason="end_turn", text="done"))
    runner = AgentRunner(_config(), provider=provider, runs_dir=tmp_path / "runs")

    await runner.run_and_capture("inspect", run_id="run-profile", workspace_root=workspace)

    assert provider.system is not None
    assert "## Project Profile" in provider.system
    assert "Detected Project Profile" in provider.system
    assert "npm run build" in provider.system
    assert "advisory only" in provider.system
    assert "unsafe-build --all" not in provider.system


# 功能：验证桌面端收到 run.finished 时本轮耗时与 token 已经持久化
# 设计：在完成事件订阅器中立即读取 meta，锁定先落盘再广播的时序契约
async def test_session_stats_persisted_before_finished_event(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
        run_ids=["run-new"],
    )
    store.write_meta(session)
    store.append_message(session.id, "user", "hello", run_id="run-new")
    persisted_at_finish: list[tuple[RunStats | None, float]] = []

    async def capture_finished(event: BaseModel) -> None:
        if event.type == "run.finished":  # type: ignore[attr-defined]
            persisted_at_finish.append((
                store.read_meta(session.id).run_stats.get("run-new"),
                event.elapsed_s,  # type: ignore[attr-defined]
            ))

    provider = _CapturingProvider(
        LlmResponse(
            stop_reason="end_turn",
            text="done",
            usage=UsageStats(input_tokens=120, output_tokens=30),
        )
    )
    runner = AgentRunner(
        _config(),
        provider=provider,
        extra_handlers=[capture_finished],
        runs_dir=tmp_path / "runs",
    )

    await runner.run_and_capture("hello", run_id="run-new", session=session, store=store)

    assert len(persisted_at_finish) == 1
    persisted, finished_elapsed = persisted_at_finish[0]
    assert persisted is not None
    assert persisted.input_tokens == 120
    assert persisted.output_tokens == 30
    assert persisted.elapsed_s == finished_elapsed


# 功能：验证自动压缩后摘要会覆盖写入 thread，而不是按旧 prefill 长度切片丢弃
# 设计：历史超过两条时触发压缩，运行结束应能在 thread 中读到摘要和后续消息
async def test_auto_compact_writes_summary_to_thread(tmp_path: Path) -> None:
    cfg = _config()
    cfg.compaction.auto_threshold = 0.8
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.write_meta(session)
    store.append_message("sess-1", "user", "old goal")
    store.append_message("sess-1", "user", "new goal with enough history")

    runner = AgentRunner(
        cfg,
        provider=_SessionCompactingProvider(),  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )
    await runner.run_and_capture(
        "new goal",
        run_id="run-compact",
        session=session,
        store=store,
    )
    # Phase 3a: 等待异步压缩完成（后台 Task 需要事件循环调度）
    messages = store.read_messages("sess-1")
    assert messages[0]["role"] == "user"
    assert "Original Goal" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    event_types = [
        json.loads(line)["type"]
        for line in (store.runs_dir("sess-1") / "run-compact" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert "context.compacted" in event_types
    assert event_types.index("context.compacted") < event_types.index("run.finished")
    assert event_types[-1] == "run.finished"


async def test_cancelled_run_cancels_pending_compaction(tmp_path: Path) -> None:
    cfg = _config()
    cfg.compaction.auto_threshold = 0.8
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.write_meta(session)
    store.append_message("sess-1", "user", "old goal")
    store.append_message("sess-1", "user", "new goal with enough history")

    provider = _CancelableCompactingProvider()
    runner = AgentRunner(
        cfg,
        provider=provider,  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )
    task = asyncio.create_task(
        runner.run_and_capture(
            "new goal",
            run_id="run-cancel",
            session=session,
            store=store,
        )
    )

    await provider.compact_started.wait()
    # 压缩触发起，主循环在下一次模型请求前会等待压缩完成（wait_pending），
    # 因此此刻主任务阻塞在 wait_pending——直接取消整个 run 即可覆盖
    # "取消运行时连带取消挂起压缩"的路径
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert provider.compact_cancelled is True
    event_types = [
        json.loads(line)["type"]
        for line in (store.runs_dir("sess-1") / "run-cancel" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert "context.compacted" not in event_types
    assert event_types[-1] == "run.finished"


async def test_run_without_session_waits_for_pending_compaction(tmp_path: Path) -> None:
    cfg = _config()
    cfg.compaction.auto_threshold = 0.8
    provider = _AsyncCompactingProvider()
    runner = AgentRunner(
        cfg,
        provider=provider,  # type: ignore[arg-type]
        runs_dir=tmp_path,
    )

    outcome = await runner.run_and_capture("new goal", run_id="run-no-session")

    assert outcome.status == "success"
    assert provider.compact_started.is_set()
    assert provider.compact_completed.is_set()
    run_path = tmp_path / "run-no-session"
    assert len(list(run_path.glob("summary_*.md"))) == 1
    event_types = _read_event_types(run_path / "events.jsonl")
    assert "context.compacted" in event_types
    assert event_types.index("context.compacted") < event_types.index("run.finished")
    assert event_types[-1] == "run.finished"


async def test_failed_run_waits_for_pending_compaction(tmp_path: Path) -> None:
    cfg = _config()
    cfg.compaction.auto_threshold = 0.8
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.write_meta(session)
    store.append_message("sess-1", "user", "old goal")
    store.append_message("sess-1", "user", "new goal with enough history")

    provider = _FailingCompactingProvider()
    runner = AgentRunner(
        cfg,
        provider=provider,  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )

    outcome = await runner.run_and_capture(
        "new goal",
        run_id="run-failure",
        session=session,
        store=store,
    )

    assert outcome.status == "failed"
    assert outcome.reason == "llm_error"
    assert provider.compact_started.is_set()
    assert provider.compact_completed.is_set()
    messages = store.read_messages("sess-1")
    assert "Original Goal" in messages[0]["content"]
    event_types = _read_event_types(store.runs_dir("sess-1") / "run-failure" / "events.jsonl")
    assert "context.compacted" in event_types
    assert event_types.index("context.compacted") < event_types.index("run.finished")
    assert event_types[-1] == "run.finished"


# 功能：验证 session run 中注册了 note_save，工具调用会写入 notes.md
# 设计：mock provider 第一步请求 note_save、第二步 end_turn，覆盖 runner→registry→tool invocation 的完整路径
async def test_session_registers_note_save_tool(tmp_path: Path) -> None:
    from sztu_code.core.session.model import Session
    from sztu_code.core.session.store import SessionStore

    class _NoteProvider:
        # 初始化调用计数器，用于返回两步响应
        def __init__(self) -> None:
            self.calls = 0

        # 第一步请求 note_save，第二步返回 end_turn
        async def chat(
            self,
            messages: list[dict[str, object]],
            tool_schemas: list[dict[str, object]],
            bus: EventBus,
            run_id: str,
            *,
            step: int = 0,
            system: str | None = None,
            usage_estimator: object | None = None,
        ) -> LlmResponse:
            self.calls += 1
            if self.calls == 1:
                return LlmResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        ToolCallBlock(
                            id="note-1",
                            name="note_save",
                            input={"content": "Use Python 3.12"},
                        )
                    ],
                )
            return LlmResponse(stop_reason="end_turn", text="noted")

    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.append_message("sess-1", "user", "remember")

    runner = AgentRunner(_config(max_steps=3), provider=_NoteProvider(), runs_dir=tmp_path)
    await runner.run_and_capture("remember", run_id="run-1", session=session, store=store)

    assert "Use Python 3.12" in store.read_notes("sess-1")
