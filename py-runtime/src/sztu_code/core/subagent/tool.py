from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from sztu_code.core.agents.loader import AgentProfile, AgentProfileLoader
from sztu_code.core.bus.events import SubagentFinishedEvent, SubagentStartedEvent
from sztu_code.core.config import BudgetConfig
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.events.writer import EventWriter
from sztu_code.core.loop import AgentLoop
from sztu_code.core.runs import new_run_id
from sztu_code.core.skills.loader import SkillLoader
from sztu_code.core.stuck_tracker import StuckLoopTracker
from sztu_code.core.subagent.registry import (
    BackgroundTaskRegistry,
    BackgroundTaskStatus,
)
from sztu_code.core.tools.base import BaseTool, ToolResult
from sztu_code.core.tools.builtin.bash import BashTool
from sztu_code.core.tools.builtin.edit_file import EditFileTool
from sztu_code.core.tools.builtin.glob_search import GlobSearchTool
from sztu_code.core.tools.builtin.grep_search import GrepSearchTool
from sztu_code.core.tools.builtin.list_dir import ListDirTool
from sztu_code.core.tools.builtin.note_save import NoteSaveTool
from sztu_code.core.tools.builtin.read_file import ReadFileTool
from sztu_code.core.tools.builtin.task_create import TaskCreateTool
from sztu_code.core.tools.builtin.task_get import TaskGetTool
from sztu_code.core.tools.builtin.task_list import TaskListTool
from sztu_code.core.tools.builtin.task_update import TaskUpdateTool
from sztu_code.core.tools.builtin.write_file import WriteFileTool
from sztu_code.core.tools.registry import ToolRegistry
from sztu_code.core.workflow.scope import ScopeAuditLog

if TYPE_CHECKING:
    from sztu_code.core.llm.base import LLMProvider
    from sztu_code.core.permissions.manager import PermissionManager
    from sztu_code.core.session.model import Session
    from sztu_code.core.session.store import SessionStore

_profile_loader = AgentProfileLoader()
_skill_loader = SkillLoader()


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SpawnAgentParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # invoke_tool 会剥离时间线标题 description，故此处须有默认值否则经循环调用必报 schema_error
    description: str = ""
    prompt: str
    run_in_background: bool = False
    subagent_type: str = ""
    skill: str = ""
    # 以下字段供工作流组合工具设置，不暴露在普通模型工具 schema 中
    allowed_paths: list[str] | None = None
    allowed_tools: list[str] | None = None
    max_tokens: int = 0
    max_wall_clock_s: int = 0
    scope_audit: Any = None


# 在隔离的冷启动上下文中派生子 agent，支持前台阻塞和后台并行两种模式
class SpawnAgentTool(BaseTool):
    name = "spawn_agent"
    description = (
        "Spawn an isolated sub-agent to handle a self-contained sub-task. "
        "The sub-agent starts with a clean context containing only the provided prompt — "
        "it does not inherit the current conversation history. "
        "Use run_in_background=true to run in parallel; retrieve result later with agent_result."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "3-5 word task description shown in progress display",
            },
            "prompt": {
                "type": "string",
                "description": (
                    "Complete task description including all context the sub-agent needs. "
                    "The sub-agent cannot see the parent conversation, so be explicit."
                ),
            },
            "run_in_background": {
                "type": "boolean",
                "description": "When true, returns immediately with a run_id; use agent_result to poll.",  # noqa: E501
            },
            "subagent_type": {
                "type": "string",
                "description": "Agent role profile (coder/tester/reviewer/planner/explore/plan/executor). Leave empty for coder.",  # noqa: E501
            },
            "skill": {
                "type": "string",
                "description": "Optional Agent Skill name to apply to the sub-agent at spawn time.",
            },
        },
        "required": ["description", "prompt"],
    }
    params_model = SpawnAgentParams

    # 构造 SpawnAgentTool；depth=0 表示根 agent，最大允许嵌套深度为 2
    def __init__(
        self,
        provider: LLMProvider,
        parent_bus: EventBus,
        parent_run_id: str,
        permission_manager: PermissionManager | None,
        max_steps: int,
        task_registry: BackgroundTaskRegistry,
        runs_dir: Path,
        session_id: str,
        depth: int = 0,
        workspace_root: Path | None = None,
        parent_context: ExecutionContext | None = None,
        session: Session | None = None,
        store: SessionStore | None = None,
        budget: BudgetConfig | None = None,
        wrap_up_on_max_steps: bool = True,
        grace_step_on_max_steps: bool = True,
        stuck_max_failures: int = 2,
        stuck_max_total: int = 0,
        tool_max_concurrency: int = 4,
        max_depth: int = 2,
        owner_run_id: str = "",
    ) -> None:
        self._provider = provider
        self._parent_bus = parent_bus
        self._parent_run_id = parent_run_id
        self._permission_manager = permission_manager
        self._max_steps = max_steps
        self._task_registry = task_registry
        self._runs_dir = runs_dir
        self._session_id = session_id
        self._depth = depth
        self._workspace_root = workspace_root
        self._parent_context = parent_context
        self._session = session
        self._store = store
        self._budget = budget
        self._wrap_up_on_max_steps = wrap_up_on_max_steps
        self._grace_step_on_max_steps = grace_step_on_max_steps
        self._stuck_max_failures = stuck_max_failures
        self._stuck_max_total = stuck_max_total
        self._tool_max_concurrency = tool_max_concurrency
        self._max_depth = max_depth
        # owner_run_id：所属 root run。嵌套 spawn 时从父 tool 继承，保证整个后代树的
        # 终态事件都路由回 root sink。为空时回退为 parent_run_id（root tool 自身场景）。
        self._owner_run_id = owner_run_id or parent_run_id

    # 派生子 agent，前台时阻塞直到完成并返回结果，后台时立即返回 run_id
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = SpawnAgentParams.model_validate(params)

        if self._depth >= self._max_depth:
            return ToolResult(
                content=(
                    f"Subagent nesting limit ({self._max_depth}) reached; "
                    "cannot spawn further subagents."
                ),
                is_error=True,
                error_type="runtime_error",
            )

        # 空 subagent_type 默认使用 coder 角色
        subagent_type = p.subagent_type or "coder"
        profile: AgentProfile | None = _profile_loader.load(subagent_type)
        # 子 agent 步数：角色显式配置优先，否则继承父传入值
        child_max_steps = self._max_steps
        if profile is not None and profile.max_steps > 0:
            child_max_steps = profile.max_steps

        # 解析并合并 skill：角色白名单非空时 union，否则只合并系统提示不缩窄工具集
        skill_name = (p.skill or (profile.skill if profile else "")).strip()
        skill = _skill_loader.resolve(skill_name) if skill_name else None
        role_prompt = (profile.system_prompt if profile else "").strip()
        allowed_tools: set[str] | None = (
            set(profile.allowed_tools) if profile and profile.allowed_tools else None
        )
        skill_prompt = ""
        if skill is not None:
            if allowed_tools is not None:
                allowed_tools |= set(skill.allowed_tools)
            skill_prompt = _skill_loader.render_prompt(skill, p.prompt).strip()
        if p.allowed_tools is not None:
            workflow_tools = set(p.allowed_tools)
            allowed_tools = (
                workflow_tools if allowed_tools is None else allowed_tools & workflow_tools
            )
        # 子代理继承静态基础规则 + 角色提示 + 技能 + 后台身份段
        from sztu_code.core.prompts.system_prompt import build_static_base

        identity = (
            f"You are a background sub-agent of type `{subagent_type}`. Work only on the "
            "delegated task, use only the tools available to you, do not ask the user questions, "
            "and finish with a concise result."
        )
        system_prompt = "\n\n".join(
            part for part in (build_static_base(), role_prompt, skill_prompt, identity) if part
        )

        # 非 normal 权限模式使用独立 PermissionManager，避免污染父 session 缓存
        child_permission_manager = self._permission_manager
        if profile is not None and profile.permission_mode != "normal":
            from sztu_code.core.permissions.manager import PermissionManager as ChildPM
            from sztu_code.core.permissions.policy import PermissionMode

            child_permission_manager = ChildPM(mode=PermissionMode(profile.permission_mode))

        from sztu_code.core.prompts.harness import (
            DEFAULT_PROMPT_HARNESS,
            PromptRuntimeContext,
        )

        child_permission_mode = (
            child_permission_manager.get_mode().value
            if child_permission_manager is not None
            else "normal"
        )
        child_run_id = new_run_id()
        child_context = ExecutionContext(
            run_id=child_run_id,
            goal=p.prompt,
            max_steps=child_max_steps,
            project_profile_context=(
                self._parent_context.project_profile_context
                if self._parent_context is not None
                else ""
            ),
            system_prompt_override=system_prompt or None,
            max_tokens=(
                p.max_tokens if p.max_tokens > 0 else self._budget.max_tokens if self._budget else 0
            ),
            max_wall_clock_s=(
                p.max_wall_clock_s
                if p.max_wall_clock_s > 0
                else self._budget.max_wall_clock_s
                if self._budget
                else 0
            ),
        )

        child_bus = EventBus()

        # 将子 bus 所有事件桥接到父 bus，TUI 据此渲染嵌套进度
        async def _bridge(event: BaseModel) -> None:
            await self._parent_bus.publish(event)

        child_bus.subscribe(_bridge)

        child_registry = self._build_child_registry(
            child_bus,
            child_run_id,
            profile,
            allowed_tools=allowed_tools,
            child_context=child_context,
            permission_manager=child_permission_manager,
            child_max_steps=child_max_steps,
            allowed_paths=p.allowed_paths,
            scope_audit=p.scope_audit if isinstance(p.scope_audit, ScopeAuditLog) else None,
        )
        child_context.system_prompt_override = DEFAULT_PROMPT_HARNESS.compose(
            system_prompt,
            PromptRuntimeContext(
                permission_mode=child_permission_mode,
                tool_names=frozenset(tool.name for tool in child_registry),
                task_text=p.prompt,
            ),
        )
        # 子 agent 使用独立的 DenialTracker，避免父子 agent 拒绝计数互相干扰
        from sztu_code.core.permissions.denial_tracker import DenialTracker

        child_loop = AgentLoop(
            self._provider,
            child_registry,
            child_bus,
            permission_manager=child_permission_manager,
            denial_tracker=DenialTracker(),
            session_id=self._session_id,
            task_registry=self._task_registry,
            wrap_up_on_max_steps=self._wrap_up_on_max_steps,
            grace_step_on_max_steps=self._grace_step_on_max_steps,
            stuck_tracker=StuckLoopTracker(
                max_failures=self._stuck_max_failures,
                max_total=self._stuck_max_total,
            ),
            tool_max_concurrency=self._tool_max_concurrency,
        )

        await self._parent_bus.publish(
            SubagentStartedEvent(
                run_id=child_run_id,
                parent_run_id=self._parent_run_id,
                description=p.description or "Subagent task",
                ts=_now(),
            )
        )

        child_run_path = self._runs_dir / child_run_id
        child_run_path.mkdir(parents=True, exist_ok=True)

        if p.run_in_background:
            # 登记到父 run 的 pending 集合，父 loop 结束回合前会等待其完成
            if self._parent_context is not None:
                self._parent_context.pending_background_run_ids.add(child_run_id)
            task: asyncio.Task[None] = asyncio.create_task(
                self._run_background(
                    child_loop, child_context, child_bus, child_run_path, child_run_id
                )
            )
            # 注册时记录所有权（parent_run_id 直接父 + owner_run_id root owner），
            # 使取消可递归遍历后代树，且终态事件按 owner 路由到 root sink
            self._task_registry.register(
                child_run_id, self._parent_run_id, task, child_context,
                owner_run_id=self._owner_run_id,
            )
            return ToolResult(
                content=(
                    f"Subagent started in background. run_id={child_run_id}. "
                    f"Use agent_result(run_id='{child_run_id}') to retrieve result."
                ),
                metadata={"run_id": child_run_id, "status": "running"},
            )

        async with EventWriter(child_run_path / "events.jsonl") as writer:
            writer.subscribe(child_bus)
            await child_loop.run(child_context)

        await self._parent_bus.publish(
            SubagentFinishedEvent(
                run_id=child_run_id,
                parent_run_id=self._parent_run_id,
                status=child_context.status,
                ts=_now(),
            )
        )

        if child_context.status == "success":
            return ToolResult(
                content=child_context.result or "Subagent completed with no text output.",
                metadata=self._context_metadata(child_context),
            )
        return ToolResult(
            content=(
                child_context.result
                or f"Subagent failed (status={child_context.status}, reason={child_context.reason})"
            ),
            is_error=True,
            error_type="runtime_error",
            metadata=self._context_metadata(child_context),
        )

    # 提取子运行 ID、状态、预算用量和耗时，供组合工作流做全局预算核算
    def _context_metadata(self, context: ExecutionContext) -> dict[str, object]:
        return {
            "run_id": context.run_id,
            "status": context.status,
            "reason": context.reason or "",
            "tokens": context.total_tokens(),
            "elapsed_s": context.elapsed_s(),
        }

    # 后台任务协程：写事件文件，运行 loop，发布完成事件。
    # 终态事件只发布一次：registry.mark_terminal 在并发完成/取消竞争中只有首个赢家胜出，
    # 取消不得覆盖先到的完成结果。
    async def _run_background(
        self,
        loop: AgentLoop,
        context: ExecutionContext,
        bus: EventBus,
        run_path: Path,
        run_id: str,
    ) -> None:
        try:
            async with EventWriter(run_path / "events.jsonl") as writer:
                writer.subscribe(bus)
                await loop.run(context)
        except asyncio.CancelledError:
            # 取消到达时仍需终结记录；只有赢得 mark_terminal 的路径发布终态事件
            self._publish_terminal(run_id, context, cancelled=True)
            raise
        except Exception as exc:  # noqa: BLE001 — 后台任务异常需转为 failed 终态
            self._publish_terminal(run_id, context, detail=str(exc))
            raise
        else:
            self._publish_terminal(run_id, context)

    # 登记终态到 registry：mark_terminal 赢家由 registry 的 on_terminal 回调
    # 发布 SubagentFinishedEvent，使事件发布不依赖本协程是否已执行。
    # cancelled 用 CANCELLED，不复用 FAILED，避免把取消误判为失败。
    def _publish_terminal(
        self,
        run_id: str,
        context: ExecutionContext,
        *,
        cancelled: bool = False,
        detail: str = "",
    ) -> None:
        if cancelled:
            self._task_registry.mark_terminal(
                run_id, BackgroundTaskStatus.CANCELLED, reason=detail or "cancelled"
            )
        elif context.status == "success":
            self._task_registry.mark_terminal(
                run_id, BackgroundTaskStatus.COMPLETED, detail=context.result
            )
        else:
            fail_reason = detail or context.reason or context.status
            self._task_registry.mark_terminal(
                run_id, BackgroundTaskStatus.FAILED, reason=fail_reason
            )

    # 构造子 registry；基于合并后的白名单过滤工具，深度允许时注册嵌套 SpawnAgentTool
    def _build_child_registry(
        self,
        child_bus: EventBus,
        child_run_id: str,
        profile: AgentProfile | None,
        *,
        allowed_tools: set[str] | None = None,
        child_context: ExecutionContext | None = None,
        permission_manager: PermissionManager | None = None,
        child_max_steps: int = 0,
        allowed_paths: list[str] | None = None,
        scope_audit: ScopeAuditLog | None = None,
    ) -> ToolRegistry:
        from sztu_code.core.task.manager import TaskManager

        allowed: set[str] | None = allowed_tools

        def _allowed(name: str) -> bool:
            return allowed is None or name in allowed

        registry = ToolRegistry()
        _all_tools = [
            ReadFileTool(self._workspace_root),
            BashTool(self._workspace_root),
            WriteFileTool(self._workspace_root, allowed_paths, scope_audit),
            EditFileTool(self._workspace_root, allowed_paths, scope_audit),
            ListDirTool(self._workspace_root),
            GrepSearchTool(self._workspace_root),
            GlobSearchTool(self._workspace_root),
        ]
        for t in _all_tools:
            if _allowed(t.name):
                registry.register(t)

        child_task_manager = TaskManager(self._runs_dir / child_run_id / ".tasks")
        for t in [
            TaskCreateTool(child_task_manager, child_bus, child_run_id, self._session_id),
            TaskUpdateTool(child_task_manager, child_bus, child_run_id, self._session_id),
            TaskListTool(child_task_manager),
            TaskGetTool(child_task_manager),
        ]:
            if _allowed(t.name):
                registry.register(t)

        if self._session is not None and self._store is not None:
            note_tool = NoteSaveTool(self._store, self._session.id, child_run_id)
            if _allowed(note_tool.name):
                registry.register(note_tool)

        if self._depth + 1 < self._max_depth:
            nested = SpawnAgentTool(
                provider=self._provider,
                parent_bus=child_bus,
                parent_run_id=child_run_id,
                permission_manager=permission_manager,
                max_steps=child_max_steps if child_max_steps > 0 else self._max_steps,
                task_registry=self._task_registry,
                runs_dir=self._runs_dir,
                session_id=self._session_id,
                depth=self._depth + 1,
                workspace_root=self._workspace_root,
                parent_context=child_context,
                session=self._session,
                store=self._store,
                budget=self._budget,
                wrap_up_on_max_steps=self._wrap_up_on_max_steps,
                grace_step_on_max_steps=self._grace_step_on_max_steps,
                stuck_max_failures=self._stuck_max_failures,
                stuck_max_total=self._stuck_max_total,
                tool_max_concurrency=self._tool_max_concurrency,
                max_depth=self._max_depth,
                owner_run_id=self._owner_run_id,
            )
            if _allowed("spawn_agent"):
                registry.register(nested)
            if _allowed("agent_result"):
                registry.register(AgentResultTool(self._task_registry))

        return registry


class AgentResultParams(BaseModel):
    run_id: str


# 查询后台 subagent 的执行状态和最终结果
class AgentResultTool(BaseTool):
    name = "agent_result"
    description = (
        "Retrieve the result of a background sub-agent previously started with spawn_agent. "
        "Returns 'still running' if the sub-agent has not yet completed."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "description": "The run_id returned by spawn_agent(run_in_background=true)",
            },
        },
        "required": ["run_id"],
    }
    params_model = AgentResultParams

    # 初始化，持有共享的后台任务注册表
    def __init__(self, task_registry: BackgroundTaskRegistry) -> None:
        self._task_registry = task_registry

    # 查询指定 run_id 的后台任务状态，返回结果或错误。
    # 区分 unknown / running / completed / cancelled / failed / reclaimed：终态结果首次读取后回收。
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = AgentResultParams.model_validate(params)
        query = self._task_registry.consume_result(p.run_id)
        if query.status is BackgroundTaskStatus.RUNNING:
            if query.reason == "unknown":
                return ToolResult(
                    content=(
                        f"Unknown run_id: {p.run_id}. "
                        "Only background subagents can be queried."
                    ),
                    is_error=True,
                    error_type="runtime_error",
                )
            return ToolResult(content="still running")
        if query.status is BackgroundTaskStatus.COMPLETED:
            return ToolResult(content=query.result_text)
        if query.status is BackgroundTaskStatus.CANCELLED:
            return ToolResult(
                content=query.result_text or "Subagent was cancelled.",
                is_error=True,
                error_type="runtime_error",
            )
        if query.status is BackgroundTaskStatus.FAILED:
            return ToolResult(
                content=query.result_text or "Subagent failed.",
                is_error=True,
                error_type="runtime_error",
            )
        # reclaimed：结果已被消费或过期回收，与 unknown 的拼写错误可区分
        return ToolResult(
            content=(
                f"Result for run_id {p.run_id} is no longer available "
                f"({query.reason or 'reclaimed'})."
            ),
            is_error=True,
            error_type="runtime_error",
        )
