from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from sztu_code.core.config import SztuConfig
from sztu_code.core.events.bus import EventBus
from sztu_code.core.subagent.tool import SpawnAgentTool
from sztu_code.core.tools.base import BaseTool, ToolResult
from sztu_code.core.workflow.model import (
    HandoffArtifact,
    WorkflowGraph,
    WorkflowLimits,
    WorkflowTask,
)
from sztu_code.core.workflow.orchestrator import WorkflowOrchestrator, WorkflowTaskError
from sztu_code.core.workflow.scope import (
    ScopeAuditLog,
    normalize_workspace_relative,
    path_is_allowed,
)

_CODER_TOOLS = [
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "grep_search",
    "glob_search",
]


class WorkflowRunParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goal: str
    allowed_paths: list[str]
    completion_criteria: list[str]


# 从模型输出中提取首个完整 JSON 对象，兼容意外附带的代码围栏或说明文字
def _extract_json_object(content: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("role output did not contain a JSON object")


# 计算分配范围内文件内容摘要，用于识别 Coder 的实际变更而非依赖自述
def _scope_snapshot(workspace_root: Path, scopes: list[str]) -> dict[str, str]:
    files: set[Path] = set()
    root = workspace_root.resolve()
    for raw_scope in scopes:
        scope = normalize_workspace_relative(raw_scope)
        if any(marker in scope for marker in "*?["):
            candidates: Iterable[Path] = root.glob(scope)
        else:
            target = root / scope
            candidates = target.rglob("*") if target.is_dir() else [target]
        for candidate in candidates:
            if not candidate.is_file() or ".git" in candidate.parts:
                continue
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            files.add(candidate)
    snapshot: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return snapshot


# 比较执行前后摘要并返回新增、修改或删除的工作区相对路径
def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


class SpawnRoleExecutor:
    # 绑定通用 Subagent 入口与工作区，按角色契约生成独立执行提示
    def __init__(
        self,
        spawn_tool: SpawnAgentTool,
        workspace_root: Path,
        workflow_id: str,
    ) -> None:
        self._spawn_tool = spawn_tool
        self._workspace_root = workspace_root
        self._workflow_id = workflow_id

    # 执行 Coder、Tester 或 Reviewer 并将真实运行元数据组装成交接产物
    async def __call__(
        self,
        task: WorkflowTask,
        dependency_artifacts: list[HandoffArtifact],
        attempt: int,
    ) -> HandoffArtifact:
        before = (
            _scope_snapshot(self._workspace_root, task.allowed_paths)
            if task.owner == "coder"
            else {}
        )
        scope_audit = ScopeAuditLog()
        prompt = self._role_prompt(task, dependency_artifacts, attempt)
        invoke_params: dict[str, object] = {
            "description": f"{task.owner}: {task.title}",
            "prompt": prompt,
            "subagent_type": task.owner,
            "run_in_background": False,
            "max_tokens": task.token_budget,
            "max_wall_clock_s": math.ceil(task.time_budget_s),
        }
        if task.owner == "coder":
            invoke_params["allowed_paths"] = task.allowed_paths
            invoke_params["allowed_tools"] = _CODER_TOOLS
            invoke_params["scope_audit"] = scope_audit
        result = await self._spawn_tool.invoke(invoke_params)
        after = (
            _scope_snapshot(self._workspace_root, task.allowed_paths)
            if task.owner == "coder"
            else {}
        )
        if result.is_error:
            raise WorkflowTaskError(
                result.content,
                tokens=int(str(result.metadata.get("tokens") or 0)),
            )
        try:
            payload = _extract_json_object(result.content)
        except ValueError:
            if task.owner != "coder":
                raise
            payload = {"status": "succeeded", "summary": result.content}
        metadata = result.metadata
        artifact = self._artifact_from_payload(
            task,
            payload,
            metadata,
            attempt,
            sorted(set(_changed_paths(before, after)) | set(scope_audit.paths)),
            scope_audit.paths,
        )
        return artifact

    # 构造含依赖证据和角色专属 JSON schema 的冷启动提示
    def _role_prompt(
        self,
        task: WorkflowTask,
        dependency_artifacts: list[HandoffArtifact],
        attempt: int,
    ) -> str:
        evidence = [artifact.model_dump(mode="json") for artifact in dependency_artifacts]
        common: dict[str, Any] = {
            "workflow_id": self._workflow_id,
            "task": task.model_dump(mode="json"),
            "attempt": attempt,
            "dependency_evidence": evidence,
        }
        contract: dict[str, Any]
        if task.owner == "coder":
            contract = {
                "status": "succeeded|failed",
                "summary": "what was implemented",
                "conclusion": "why completion criteria are or are not met",
            }
            instruction = (
                "Only modify files under allowed_paths using write_file/edit_file. "
                "Do not run tests; the independent Tester owns verification."
            )
        elif task.owner == "tester":
            contract = {
                "status": "succeeded|failed",
                "summary": "verification scope",
                "commands": ["exact command"],
                "output": "key raw output including failures",
                "conclusion": "pass/fail conclusion against completion criteria",
                "test_summary": "concise evidence summary",
            }
            instruction = "Run the checks yourself, do not modify files, and preserve real output."
        elif task.owner == "reviewer":
            contract = {
                "status": "succeeded|failed",
                "summary": "review scope",
                "diff_summary": "findings from the actual diff",
                "test_summary": "assessment of Tester evidence",
                "security_summary": "security evidence or explicit not-run limitation",
                "review_decision": "accept|return",
                "conclusion": "evidence-based arbitration reason",
            }
            instruction = (
                "Inspect the actual diff and dependency evidence. Return the work if any "
                "completion, test, or security gate is not satisfied. Do not modify files."
            )
        else:
            contract = {"status": "succeeded|failed", "summary": "planning result"}
            instruction = "Analyze only and do not modify files."
        return (
            "Execute this delegated workflow task.\n"
            f"Context: {json.dumps(common, ensure_ascii=False)}\n"
            f"Role rule: {instruction}\n"
            "Finish with exactly one JSON object and no Markdown fence.\n"
            f"Required contract: {json.dumps(contract, ensure_ascii=False)}"
        )

    # 将角色 JSON、实际改动和子运行预算数据合并为统一交接模型
    def _artifact_from_payload(
        self,
        task: WorkflowTask,
        payload: dict[str, Any],
        metadata: dict[str, object],
        attempt: int,
        actual_changed_paths: list[str],
        scope_escalations: list[str],
    ) -> HandoffArtifact:
        raw_status = str(payload.get("status", "succeeded"))
        status: Literal["succeeded", "failed"] = (
            "failed" if raw_status == "failed" else "succeeded"
        )
        return HandoffArtifact(
            workflow_id=self._workflow_id,
            task_id=task.id,
            role=task.owner,
            status=status,
            summary=str(payload.get("summary") or "role completed without summary"),
            changed_paths=actual_changed_paths,
            scope_escalations=scope_escalations,
            commands=[str(item) for item in payload.get("commands") or []],
            output=str(payload.get("output") or ""),
            conclusion=str(payload.get("conclusion") or ""),
            diff_summary=str(payload.get("diff_summary") or ""),
            test_summary=str(payload.get("test_summary") or ""),
            security_summary=str(payload.get("security_summary") or ""),
            review_decision=payload.get("review_decision"),
            tokens=int(str(metadata.get("tokens") or 0)),
            elapsed_s=float(str(metadata.get("elapsed_s") or 0.0)),
            attempt=attempt,
            child_run_id=str(metadata.get("run_id") or ""),
        )


class WorkflowRunTool(BaseTool):
    name = "run_workflow"
    description = (
        "Run a bounded Planner → Coder → Tester → Reviewer workflow. The Planner returns a "
        "structured DAG, Coder writes are restricted to assigned paths, and every handoff is "
        "recorded as workflow events."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Complete engineering goal."},
            "allowed_paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Maximum workspace paths that Coder tasks may be assigned.",
            },
            "completion_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Observable conditions the Reviewer must arbitrate.",
            },
        },
        "required": ["goal", "allowed_paths", "completion_criteria"],
    }
    params_model = WorkflowRunParams

    # 绑定父运行、配置、工作区与 Subagent 工具，作为多角色工作流统一入口
    def __init__(
        self,
        spawn_tool: SpawnAgentTool,
        bus: EventBus,
        run_id: str,
        workspace_root: Path,
        config: SztuConfig,
    ) -> None:
        self._spawn_tool = spawn_tool
        self._bus = bus
        self._run_id = run_id
        self._workspace_root = workspace_root
        self._config = config

    # 先让 Planner 生成并校验 DAG，再调度角色任务并返回结构化结果
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        parsed = WorkflowRunParams.model_validate(params)
        if not parsed.allowed_paths or not parsed.completion_criteria:
            return ToolResult(
                content="allowed_paths and completion_criteria must not be empty",
                is_error=True,
                error_type="schema_error",
            )
        try:
            for path in parsed.allowed_paths:
                normalize_workspace_relative(path)
            limits = WorkflowLimits(
                max_concurrency=self._config.workflow.max_concurrency,
                max_depth=self._config.workflow.max_depth,
                max_tokens=0,
                max_wall_clock_s=self._config.budget.max_wall_clock_s,
                max_retries=self._config.workflow.max_retries,
            )
            orchestrator = WorkflowOrchestrator(self._bus, self._run_id, limits)
            graph, planner_tokens = await self._plan(parsed, orchestrator)
            executor = SpawnRoleExecutor(
                self._spawn_tool, self._workspace_root, graph.workflow_id
            )
            result = await orchestrator.run(
                graph, executor, initial_tokens=planner_tokens
            )
        except (PermissionError, ValueError, ValidationError, WorkflowTaskError) as exc:
            return ToolResult(
                content=f"workflow rejected: {exc}",
                is_error=True,
                error_type="runtime_error",
            )
        return ToolResult(
            content=result.model_dump_json(indent=2),
            is_error=result.status != "succeeded",
            error_type="runtime_error" if result.status != "succeeded" else None,
            metadata={
                "workflow_id": result.workflow_id,
                "status": result.status,
                "tokens": result.total_tokens,
                "elapsed_s": result.elapsed_s,
            },
        )

    # 调用只读 Planner 并在重试预算内解析结构化任务图
    async def _plan(
        self,
        params: WorkflowRunParams,
        orchestrator: WorkflowOrchestrator,
    ) -> tuple[WorkflowGraph, int]:
        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
        contract = {
            "planner_summary": "short planning rationale",
            "tasks": [
                {
                    "id": "unique-id",
                    "title": "short title",
                    "description": "self-contained delegated task",
                    "owner": "coder|tester|reviewer",
                    "dependencies": ["task-id"],
                    "completion_criteria": ["observable condition"],
                    "allowed_paths": ["required for coder, empty otherwise"],
                    "depth": 0,
                    "token_budget": 0,
                    "time_budget_s": 0,
                    "max_retries": None,
                }
            ],
        }
        prompt = (
            "Create a structured Planner handoff for this engineering goal. "
            "The graph must be acyclic, include at least one Coder, independent Tester, and "
            "Reviewer. Tester must depend on Coder; Reviewer must depend transitively on both. "
            "Every Coder needs the narrowest explicit allowed_paths inside the maximum scope.\n"
            "All role tasks are direct children, so set depth=0. Set token_budget=0 and "
            "time_budget_s=0 to inherit runtime budgets, and max_retries=null to inherit the "
            "workflow retry budget, unless the user explicitly requested a narrower numeric "
            "limit. Do not add planner-owned tasks; this Planner response is already the "
            "planning handoff.\n"
            f"Goal: {params.goal}\n"
            f"Maximum scope: {json.dumps(params.allowed_paths, ensure_ascii=False)}\n"
            f"Completion criteria: {json.dumps(params.completion_criteria, ensure_ascii=False)}\n"
            "Return exactly one JSON object without Markdown fences.\n"
            f"Contract: {json.dumps(contract, ensure_ascii=False)}"
        )
        last_error = "planner failed"
        total_tokens = 0
        for _attempt in range(self._config.workflow.max_retries + 1):
            result = await self._spawn_tool.invoke(
                {
                    "description": "plan workflow graph",
                    "prompt": prompt,
                    "subagent_type": "planner",
                    "run_in_background": False,
                }
            )
            total_tokens += int(str(result.metadata.get("tokens") or 0))
            if result.is_error:
                last_error = result.content
                continue
            try:
                payload = _extract_json_object(result.content)
                graph = WorkflowGraph.model_validate(
                    {
                        "workflow_id": workflow_id,
                        "goal": params.goal,
                        "planner_summary": payload.get("planner_summary"),
                        "tasks": payload.get("tasks"),
                    }
                )
                orchestrator.validate_graph(graph)
                self._validate_standard_workflow(graph, params.allowed_paths)
            except (PermissionError, ValueError, ValidationError) as exc:
                last_error = str(exc)
                continue
            return graph, total_tokens
        raise WorkflowTaskError(f"planner did not produce a valid task graph: {last_error}")

    # 强制基础角色链、依赖方向和父级写入范围，拒绝不安全 Planner 产物
    def _validate_standard_workflow(
        self, graph: WorkflowGraph, maximum_scope: list[str]
    ) -> None:
        by_id = {task.id: task for task in graph.tasks}
        roles = {task.owner for task in graph.tasks}
        required_roles = {"coder", "tester", "reviewer"}
        if not required_roles.issubset(roles):
            raise ValueError("workflow graph requires Coder, Tester, and Reviewer tasks")
        for task in graph.tasks:
            if task.owner != "coder":
                continue
            outside = [
                path for path in task.allowed_paths if not path_is_allowed(path, maximum_scope)
            ]
            if outside:
                raise PermissionError(
                    f"Planner assigned Coder paths outside maximum scope: {outside}"
                )

        cache: dict[str, set[str]] = {}

        # 递归计算任务全部祖先，验证 Tester 与 Reviewer 的证据依赖链
        def ancestors(task_id: str) -> set[str]:
            if task_id in cache:
                return cache[task_id]
            result: set[str] = set()
            for dependency in by_id[task_id].dependencies:
                result.add(dependency)
                result.update(ancestors(dependency))
            cache[task_id] = result
            return result

        coder_ids = {task.id for task in graph.tasks if task.owner == "coder"}
        tester_ids = {task.id for task in graph.tasks if task.owner == "tester"}
        if not any(ancestors(task_id) & coder_ids for task_id in tester_ids):
            raise ValueError("at least one Tester must depend on a Coder")
        reviewer_ids = {task.id for task in graph.tasks if task.owner == "reviewer"}
        if not any(
            ancestors(task_id) & coder_ids and ancestors(task_id) & tester_ids
            for task_id in reviewer_ids
        ):
            raise ValueError("at least one Reviewer must depend on Coder and Tester evidence")
