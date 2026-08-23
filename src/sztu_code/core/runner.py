from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sztu_code.core.bus.events import (
    ChangeAppliedEvent,
    ContextInjectedEvent,
    RunFinishedEvent,
    RunStartedEvent,
)
from sztu_code.core.changes import WorkspaceChangeTracker
from sztu_code.core.compact.compactor import Compactor
from sztu_code.core.compact.offload import OffloadManager
from sztu_code.core.config import SztuConfig
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus, EventHandler
from sztu_code.core.events.writer import EventWriter
from sztu_code.core.interaction.user_questions import UserQuestionManager
from sztu_code.core.llm import create_provider
from sztu_code.core.llm.base import LLMProvider
from sztu_code.core.loop import AgentLoop
from sztu_code.core.mcp.server import McpServerManager
from sztu_code.core.memory.loader import MemoryCatalog, MemoryDocument, load_context_file
from sztu_code.core.permissions.denial_tracker import DenialTracker
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.runs import RUNS_DIR, new_run_id
from sztu_code.core.session.model import RunStats, Session
from sztu_code.core.session.store import SessionStore
from sztu_code.core.stuck_tracker import StuckLoopTracker
from sztu_code.core.subagent.registry import BackgroundTaskRegistry
from sztu_code.core.subagent.tool import AgentResultTool, SpawnAgentTool
from sztu_code.core.task.manager import TaskManager
from sztu_code.core.tools.builtin import (
    AskUserQuestionTool,
    BashTool,
    EditFileTool,
    GlobSearchTool,
    GrepSearchTool,
    ListDirTool,
    MemoryReadTool,
    NoteSaveTool,
    NoteUpdateTool,
    ReadFileTool,
    ReadRefTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    WriteFileTool,
)
from sztu_code.core.tools.registry import ToolRegistry
from sztu_code.core.trace.provider import TracingProvider
from sztu_code.core.trace.writer import TraceWriter
from sztu_code.core.workflow.tool import WorkflowRunTool
from sztu_code.core.workspace.project_profile import (
    detect_project_profile,
    render_project_profile_context,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunOutcome:
    status: str
    result: str
    reason: str | None


class AgentRunner:
    # 组装所有运行时依赖，准备执行一次完整的 agent run
    def __init__(
        self,
        config: SztuConfig,
        *,
        bus: EventBus | None = None,
        provider: LLMProvider | None = None,
        extra_handlers: list[EventHandler] | None = None,
        runs_dir: Path | None = None,
        trace: TraceWriter | None = None,
        permission_manager: PermissionManager | None = None,
        user_question_manager: UserQuestionManager | None = None,
        mcp_manager: McpServerManager | None = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._extra_handlers: list[EventHandler] = extra_handlers or []
        self._runs_dir = runs_dir or RUNS_DIR
        self._trace = trace
        self._permission_manager = permission_manager
        self._user_question_manager = user_question_manager
        self._mcp_manager = mcp_manager
        # 跨 run 共享的后台 subagent 任务注册表
        self._task_registry = BackgroundTaskRegistry()

    # 构建工具注册表，注入 TaskManager（任务工具共享同一实例）；可选注入 SpawnAgentTool
    def _build_registry(
        self,
        task_manager: TaskManager,
        *,
        session: Session | None = None,
        store: SessionStore | None = None,
        run_id: str | None = None,
        provider: LLMProvider | None = None,
        bus: EventBus | None = None,
        child_runs_dir: Path | None = None,
        session_id: str = "",
        tool_whitelist: list[str] | None = None,
        workspace_root: Path | None = None,
        parent_context: ExecutionContext | None = None,
        offload_manager: OffloadManager | None = None,
        memory_catalog: MemoryCatalog | None = None,
    ) -> ToolRegistry:
        allowed: set[str] | None = set(tool_whitelist) if tool_whitelist else None

        def _ok(name: str) -> bool:
            return allowed is None or name in allowed

        registry = ToolRegistry()
        for t in [
            ReadFileTool(workspace_root),
            BashTool(workspace_root),
            WriteFileTool(workspace_root),
            EditFileTool(workspace_root),
            ListDirTool(workspace_root),
            GlobSearchTool(workspace_root),
            GrepSearchTool(workspace_root),
        ]:
            if _ok(t.name):
                registry.register(t)
        if (
            self._user_question_manager is not None
            and session_id
            and run_id is not None
            and _ok("ask_user_question")
        ):
            registry.register(AskUserQuestionTool(self._user_question_manager, session_id, run_id))
        if memory_catalog is not None and memory_catalog.requires_reader() and _ok("memory_read"):
            registry.register(MemoryReadTool(memory_catalog))
        for t in [
            TaskCreateTool(task_manager, bus, run_id or "", session_id),
            TaskUpdateTool(task_manager, bus, run_id or "", session_id),
            TaskListTool(task_manager),
            TaskGetTool(task_manager),
        ]:
            if _ok(t.name):
                registry.register(t)
        if session is not None and store is not None and run_id is not None:
            note_tool = NoteSaveTool(store, session.id, run_id)
            if _ok(note_tool.name):
                registry.register(note_tool)
            # Phase 3b: 记忆版本化 — 支持更新旧笔记（supersedes 链）
            update_tool = NoteUpdateTool(store, session.id, run_id)
            if _ok(update_tool.name):
                registry.register(update_tool)
        # 上下文卸载回读工具：Agent 可按需获取完整工具输出（TencentDB Level 0 追溯）
        # 仅在卸载启用时注册，否则没有 ref 文件可读
        if offload_manager is not None and offload_manager.enabled and _ok("read_ref"):
            registry.register(ReadRefTool(offload_manager))
        if provider is not None and bus is not None and run_id is not None:
            runs_dir = child_runs_dir or self._runs_dir
            spawn_tool = SpawnAgentTool(
                provider=provider,
                parent_bus=bus,
                parent_run_id=run_id,
                permission_manager=self._permission_manager,
                max_steps=self._config.agent.max_steps,
                task_registry=self._task_registry,
                runs_dir=runs_dir,
                session_id=session_id,
                depth=0,
                workspace_root=workspace_root,
                parent_context=parent_context,
                session=session,
                store=store,
                budget=self._config.budget,
                wrap_up_on_max_steps=self._config.agent.wrap_up_on_max_steps,
                grace_step_on_max_steps=self._config.agent.grace_step_on_max_steps,
                stuck_max_failures=self._config.agent.stuck_max_failures,
                stuck_max_total=self._config.agent.stuck_max_total,
                tool_max_concurrency=self._config.agent.tool_max_concurrency,
                max_depth=self._config.workflow.max_depth,
            )
            if _ok("spawn_agent"):
                registry.register(spawn_tool)
            if _ok("run_workflow") and workspace_root is not None:
                registry.register(
                    WorkflowRunTool(spawn_tool, bus, run_id, workspace_root, self._config)
                )
            if _ok("agent_result"):
                registry.register(AgentResultTool(self._task_registry))
        if self._mcp_manager is not None:
            for mcp_tool in self._mcp_manager.get_tools():
                if _ok(mcp_tool.name):
                    registry.register(mcp_tool)
        return registry

    # 执行一次完整的 agent run（委托给 run_and_capture，忽略返回值）
    async def run(self, goal: str, *, run_id: str | None = None) -> None:
        await self.run_and_capture(goal, run_id=run_id)

    # 执行 agent run 并返回 RunOutcome（含最终文字结果）
    async def run_and_capture(
        self,
        goal: str,
        *,
        run_id: str | None = None,
        session: Session | None = None,
        store: SessionStore | None = None,
        system_prompt_override: str | None = None,
        tool_whitelist: list[str] | None = None,
        workspace_root: Path | None = None,
        steering_queue: asyncio.Queue[dict[str, object]] | None = None,
    ) -> RunOutcome:
        run_id = run_id or new_run_id()
        if session is not None and store is not None:
            run_path = store.runs_dir(session.id) / run_id
            history = store.read_messages(session.id)
            notes = store.read_notes(session.id)
        else:
            run_path = self._runs_dir / run_id
            history = [{"role": "user", "content": goal}]
            notes = ""
        run_path.mkdir(parents=True, exist_ok=True)

        project_root = workspace_root or Path.cwd()
        project_profile_context = ""
        try:
            project_root = project_root.resolve()
            profile = detect_project_profile(project_root)
            project_profile_context = render_project_profile_context(profile)
        except (OSError, ValueError) as error:
            logging.getLogger(__name__).warning(
                "project profile detection failed root=%s: %s", project_root, error
            )

        global_ctx = load_context_file(Path("~/.sztu/context.md").expanduser())
        project_ctx = load_context_file(project_root / ".sztu/context.md")
        memory_catalog = MemoryCatalog(
            [
                MemoryDocument("global", global_ctx, "~/.sztu/context.md"),
                MemoryDocument("project", project_ctx, ".sztu/context.md"),
                MemoryDocument("session", notes, "session/notes.md"),
            ]
        )

        task_manager = TaskManager(run_path / ".tasks")
        change_tracker: WorkspaceChangeTracker | None = None
        change_workspace_root: Path | None = None
        if workspace_root is not None:
            change_workspace_root = workspace_root.resolve()
            change_tracker = WorkspaceChangeTracker(change_workspace_root, run_path, run_id)

        bus = self._bus if self._bus is not None else EventBus()
        for h in self._extra_handlers:
            bus.subscribe(h)

        base_prompt = ""
        if not system_prompt_override:
            from sztu_code.core.prompts import build_system_prompt

            # The runner treats the current directory as the default project root for
            # profile detection, memory, and tools; use the same root for prompt
            # injection so CLAUDE.md is available even without an explicit workspace.
            base_prompt = build_system_prompt(workspace_root=project_root)

        from sztu_code.core.prompts.harness import (
            DEFAULT_PROMPT_HARNESS,
            PromptRuntimeContext,
        )

        permission_mode = (
            self._permission_manager.get_mode().value
            if self._permission_manager is not None
            else self._config.permission.mode
        )
        memory_enabled = session is not None and store is not None
        context = ExecutionContext(
            run_id=run_id,
            goal=goal,
            max_steps=self._config.agent.max_steps,
            max_budget_usd=self._config.agent.max_budget_usd,
            prefill_messages=history,
            session_notes=memory_catalog.prompt_content("session"),
            global_context=memory_catalog.prompt_content("global"),
            project_context=memory_catalog.prompt_content("project"),
            project_profile_context=project_profile_context,
            base_system_prompt=base_prompt,
            system_prompt_override=system_prompt_override,
            # Cumulative Token budgets are intentionally disabled. Usage is still
            # recorded for telemetry, while wall-clock/context/step guards remain.
            max_tokens=0,
            max_wall_clock_s=self._config.budget.max_wall_clock_s,
        )
        prefill_len = len(history)
        compactor = None  # 在 try 块外初始化，避免 UnboundLocalError

        async with EventWriter(run_path / "events.jsonl") as writer:
            writer.subscribe(bus)
            await bus.publish(RunStartedEvent(run_id=run_id, goal=goal, ts=_now()))
            cancelled = False
            try:
                try:
                    provider: LLMProvider = self._provider or create_provider(self._config)
                except SystemExit as error:
                    raise RuntimeError(str(error)) from error
                if self._trace is not None:
                    provider = TracingProvider(
                        provider,
                        self._trace,
                        include_payload=self._config.trace.include_llm_payload,
                    )
                session_id_str = session.id if session is not None else ""
                child_runs_dir = (
                    store.runs_dir(session.id)
                    if session is not None and store is not None
                    else self._runs_dir
                )
                session_dir = (
                    store.session_dir(session.id)
                    if session is not None and store is not None
                    else run_path
                )
                # 上下文卸载管理器：TencentDB Agent Memory 风格的四层递进存储
                # Level 0: refs/*.md — 完整工具输出 | Level 1: offload.jsonl — 摘要索引
                offload_manager = OffloadManager(
                    session_dir,
                    enabled=self._config.offload.enabled,
                    min_chars=self._config.offload.min_chars,
                    min_lines=self._config.offload.min_lines,
                    force_tools=frozenset(self._config.offload.force_tools),
                    summary_max_chars=self._config.offload.summary_max_chars,
                )
                registry = self._build_registry(
                    task_manager,
                    session=session,
                    store=store,
                    run_id=run_id,
                    provider=provider,
                    bus=bus,
                    child_runs_dir=child_runs_dir,
                    session_id=session_id_str,
                    tool_whitelist=tool_whitelist,
                    workspace_root=workspace_root,
                    parent_context=context,
                    offload_manager=offload_manager,
                    memory_catalog=memory_catalog,
                )
                runtime_prompt_context = PromptRuntimeContext(
                    permission_mode=permission_mode,
                    memory_enabled=memory_enabled,
                    tool_names=frozenset(tool.name for tool in registry),
                    task_text=goal,
                )
                if context.system_prompt_override:
                    context.system_prompt_override = DEFAULT_PROMPT_HARNESS.compose(
                        context.system_prompt_override, runtime_prompt_context
                    )
                else:
                    context.base_system_prompt = DEFAULT_PROMPT_HARNESS.compose(
                        context.base_system_prompt, runtime_prompt_context
                    )
                # 注册表确定后再注入工具规则，事件内容与实际 LLM system prompt 保持一致。
                injected_context = context.system_prompt(context.base_system_prompt)
                first_line = next(
                    (line.strip() for line in injected_context.splitlines() if line.strip()),
                    "",
                )[:80]
                await bus.publish(
                    ContextInjectedEvent(
                        run_id=run_id,
                        source="system",
                        label="上下文注入",
                        chars=len(injected_context),
                        preview=first_line,
                        text=injected_context,
                        ts=_now(),
                    )
                )
                compactor = Compactor(bus, session_dir, session_id_str)
                denial_tracker = DenialTracker()
                loop = AgentLoop(
                    provider,
                    registry,
                    bus,
                    permission_manager=self._permission_manager,
                    denial_tracker=denial_tracker,
                    compactor=compactor,
                    compact_threshold=self._config.compaction.auto_threshold,
                    auto_compact_min_tokens=self._config.compaction.auto_compact_min_tokens,
                    auto_compact_min_steps=self._config.compaction.auto_compact_min_steps,
                    tool_result_limit=self._config.compaction.tool_result_limit,
                    tool_result_keep=self._config.compaction.tool_result_keep,
                    session_id=session_id_str,
                    task_registry=self._task_registry,
                    offload_manager=offload_manager,
                    wrap_up_on_max_steps=self._config.agent.wrap_up_on_max_steps,
                    grace_step_on_max_steps=self._config.agent.grace_step_on_max_steps,
                    stuck_tracker=StuckLoopTracker(
                        max_failures=self._config.agent.stuck_max_failures,
                        max_total=self._config.agent.stuck_max_total,
                    ),
                    sliding_window_size=self._config.compaction.sliding_window_size,
                    compact_cooldown_steps=self._config.compaction.compact_cooldown_steps,
                    circuit_breaker_max_failures=self._config.compaction.circuit_breaker_max_failures,
                    tool_max_concurrency=self._config.agent.tool_max_concurrency,
                    pricing_provider=self._config.llm.provider,
                    pricing_model=self._config.llm.default_model,
                )
                await loop.run(context)
            except asyncio.CancelledError:
                cancelled = True
                if not context.is_done():
                    context.mark_failed("cancelled")
            except Exception:
                logging.getLogger(__name__).exception(
                    "agent run failed run_id=%s step=%d", run_id, context.step
                )
                if not context.is_done():
                    context.mark_failed("llm_error")

            if change_tracker is not None:
                changes = change_tracker.finalize()
                if changes:
                    await bus.publish(
                        ChangeAppliedEvent(
                            run_id=run_id,
                            workspace_path=str(change_workspace_root),
                            paths=[str(change["path"]) for change in changes],
                            ts=_now(),
                        )
                    )
            if compactor is not None:
                await compactor.wait_pending(cancel_pending=cancelled)
            if session is not None and store is not None:
                if context.compacted:
                    store.write_compacted(session.id, context.messages)
                else:
                    store.append_messages(session.id, context.messages[prefill_len:], run_id=run_id)
            final_stats = RunStats(
                input_tokens=context.total_input_tokens,
                output_tokens=context.total_output_tokens,
                cache_read_input_tokens=context.total_cache_read_input_tokens,
                elapsed_s=context.elapsed_s(),
                context_pct=context.last_context_pct,
            )
            if session is not None and store is not None:
                session.run_stats[run_id] = final_stats
                store.write_meta(session)
            await bus.publish(
                RunFinishedEvent(
                    run_id=run_id,
                    status=context.status,
                    reason=context.reason,
                    steps=context.step,
                    total_input_tokens=final_stats.input_tokens,
                    total_output_tokens=final_stats.output_tokens,
                    cache_read_input_tokens=final_stats.cache_read_input_tokens,
                    elapsed_s=final_stats.elapsed_s,
                    context_pct=final_stats.context_pct,
                    ts=_now(),
                )
            )

        # run 结束注销本次订阅的额外处理器，防止共享 bus 的订阅者随 run 次数无限累积
        if self._extra_handlers:
            for h in self._extra_handlers:
                bus.unsubscribe(h)

        if session is not None and store is not None:
            # Phase 3a: 等待后台异步压缩完成（compactor 为 None 时跳过）
            if compactor is not None:
                await compactor.wait_pending()
            if context.compacted:
                store.write_compacted(session.id, context.messages)
            else:
                store.append_messages(session.id, context.messages[prefill_len:], run_id=run_id)

        if cancelled:
            raise asyncio.CancelledError()

        return RunOutcome(
            status=context.status,
            result=context.result,
            reason=context.reason,
        )
