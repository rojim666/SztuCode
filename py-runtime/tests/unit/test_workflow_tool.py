from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from sztu_code.core.config import SztuConfig
from sztu_code.core.events.bus import EventBus
from sztu_code.core.tools.base import ToolResult
from sztu_code.core.workflow.tool import WorkflowRunTool


class _ScriptedSpawn:
    # 保存工作区与 Planner 范围模式，并记录每次角色调用参数
    def __init__(
        self,
        workspace: Path,
        *,
        unsafe_plan: bool = False,
        invalid_depth_once: bool = False,
    ) -> None:
        self._workspace = workspace
        self._unsafe_plan = unsafe_plan
        self._invalid_depth_once = invalid_depth_once
        self.calls: list[dict[str, object]] = []

    # 按 subagent_type 返回 Planner、Coder、Tester 和 Reviewer 的确定性结果
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.calls.append(params)
        role = str(params.get("subagent_type") or "coder")
        if role == "planner":
            planner_attempt = sum(
                call.get("subagent_type") == "planner" for call in self.calls
            )
            coder_path = "docs/out.txt" if self._unsafe_plan else "src/out.txt"
            payload = {
                "planner_summary": "先实现，再独立测试与审查",
                "tasks": [
                    {
                        "id": "code",
                        "title": "实现",
                        "description": "写入目标文件",
                        "owner": "coder",
                        "dependencies": [],
                        "completion_criteria": ["文件已写入"],
                        "allowed_paths": [coder_path],
                        "depth": (
                            3
                            if self._invalid_depth_once and planner_attempt == 1
                            else 0
                        ),
                    },
                    {
                        "id": "test",
                        "title": "测试",
                        "description": "独立验证",
                        "owner": "tester",
                        "dependencies": ["code"],
                        "completion_criteria": ["检查通过"],
                    },
                    {
                        "id": "review",
                        "title": "审查",
                        "description": "质量仲裁",
                        "owner": "reviewer",
                        "dependencies": ["code", "test"],
                        "completion_criteria": ["Reviewer 接受"],
                    },
                ],
            }
            return ToolResult(
                content=json.dumps(payload, ensure_ascii=False),
                metadata={"run_id": "planner-run", "tokens": 5, "elapsed_s": 0.01},
            )
        if role == "coder":
            target = self._workspace / "src/out.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("implemented", encoding="utf-8")
            payload = {
                "status": "succeeded",
                "summary": "实现完成",
                "conclusion": "文件已写入",
            }
        elif role == "tester":
            payload = {
                "status": "succeeded",
                "summary": "独立验证",
                "commands": ["pytest -q"],
                "output": "1 passed",
                "conclusion": "验证通过",
                "test_summary": "1 passed",
            }
        else:
            payload = {
                "status": "succeeded",
                "summary": "质量审查",
                "diff_summary": "Diff 范围正确",
                "test_summary": "Tester 通过",
                "security_summary": "无高危问题",
                "review_decision": "accept",
                "conclusion": "接受",
            }
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            metadata={"run_id": f"{role}-run", "tokens": 10, "elapsed_s": 0.01},
        )


# 构造工作流工具、事件收集器和脚本化 Spawn 替身
def _tool(
    tmp_path: Path,
    *,
    unsafe_plan: bool = False,
    invalid_depth_once: bool = False,
    max_retries: int = 0,
) -> tuple[WorkflowRunTool, _ScriptedSpawn, list[BaseModel]]:
    bus = EventBus()
    events: list[BaseModel] = []

    # 收集所有工作流事件，模拟 daemon Trace 订阅链
    async def collect(event: BaseModel) -> None:
        events.append(event)

    bus.subscribe(collect)
    spawn = _ScriptedSpawn(
        tmp_path,
        unsafe_plan=unsafe_plan,
        invalid_depth_once=invalid_depth_once,
    )
    config = SztuConfig()
    config.workflow.max_retries = max_retries
    tool = WorkflowRunTool(
        spawn,  # type: ignore[arg-type]
        bus,
        "parent-run",
        tmp_path,
        config,
    )
    return tool, spawn, events


# 功能：验证 run_workflow 从 Planner 产图到 Reviewer 接受的完整入口
# 设计：脚本化四角色但保留真实解析、范围快照、DAG 调度和事件发布，覆盖模块间接线
async def test_workflow_tool_runs_full_role_chain(tmp_path: Path) -> None:
    tool, spawn, events = _tool(tmp_path)
    result = await tool.invoke(
        {
            "goal": "实现一个文件并验证",
            "allowed_paths": ["src"],
            "completion_criteria": ["文件存在", "测试通过"],
        }
    )
    assert not result.is_error
    assert result.metadata["status"] == "succeeded"
    assert result.metadata["tokens"] == 35
    assert (tmp_path / "src/out.txt").read_text(encoding="utf-8") == "implemented"
    assert [str(call.get("subagent_type")) for call in spawn.calls] == [
        "planner",
        "coder",
        "tester",
        "reviewer",
    ]
    coder_call = spawn.calls[1]
    assert coder_call["allowed_paths"] == ["src/out.txt"]
    assert "bash" not in coder_call["allowed_tools"]  # type: ignore[operator]
    assert events[0].type == "workflow.started"  # type: ignore[attr-defined]
    assert events[-1].type == "workflow.finished"  # type: ignore[attr-defined]


# 功能：验证 Planner 不能把 Coder 分配到调用方声明的最大范围之外
# 设计：让 Planner 返回 docs 路径而父范围只有 src，断言在任何 Coder 调用前拒绝整张图
async def test_workflow_tool_rejects_planner_scope_expansion(tmp_path: Path) -> None:
    tool, spawn, events = _tool(tmp_path, unsafe_plan=True)
    result = await tool.invoke(
        {
            "goal": "越界计划",
            "allowed_paths": ["src"],
            "completion_criteria": ["安全完成"],
        }
    )
    assert result.is_error
    assert "outside maximum scope" in result.content
    assert len(spawn.calls) == 1
    assert events == []


# 功能：验证 Planner 首次返回超深任务图时会在预算内重试并累计两次规划 token
# 设计：首份图 depth=3、第二份图合法，断言角色链完成且总 token 包含失败规划尝试
async def test_workflow_tool_retries_invalid_planner_graph(tmp_path: Path) -> None:
    tool, spawn, _ = _tool(
        tmp_path,
        invalid_depth_once=True,
        max_retries=1,
    )
    result = await tool.invoke(
        {
            "goal": "重试无效计划",
            "allowed_paths": ["src"],
            "completion_criteria": ["文件存在", "测试通过"],
        }
    )
    assert not result.is_error
    assert result.metadata["tokens"] == 40
    assert [call.get("subagent_type") for call in spawn.calls].count("planner") == 2
