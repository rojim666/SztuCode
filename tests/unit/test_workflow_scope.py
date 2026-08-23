from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionMode
from sztu_code.core.tools.base import ToolPermission, ToolResult
from sztu_code.core.tools.builtin.write_file import WriteFileTool
from sztu_code.core.tools.invocation import invoke_tool
from sztu_code.core.tools.registry import ToolRegistry
from sztu_code.core.workflow.scope import ScopeAuditLog, normalize_workspace_relative


# 执行一次带权限系统的范围写入，并可在审批事件到达时自动响应
async def _invoke_write(
    tmp_path: Path,
    manager: PermissionManager,
    decision: str | None,
    path: str = "docs/result.txt",
) -> tuple[ToolResult, list[BaseModel], ScopeAuditLog]:
    audit = ScopeAuditLog()
    registry = ToolRegistry()
    registry.register(WriteFileTool(tmp_path, ["src"], audit))
    bus = EventBus()
    events: list[BaseModel] = []

    # 收集权限与工具事件，并模拟桌面端返回用户决策
    async def collect(event: BaseModel) -> None:
        events.append(event)
        if event.type == "permission.requested" and decision is not None:  # type: ignore[attr-defined]
            manager.respond(event.tool_use_id, decision)  # type: ignore[attr-defined]

    bus.subscribe(collect)
    result = await invoke_tool(
        registry,
        ToolCallBlock(
            id="write-1",
            name="write_file",
            input={"path": path, "content": "approved"},
        ),
        bus,
        run_id="run-scope",
        permission_manager=manager,
        session_id="session-scope",
    )
    return result, events, audit


# 功能：验证分配范围内外的写入会被动态分为普通写权限与 full-access 权限
# 设计：直接调用 classify_permission，隔离文件系统与审批流程，只检查权限升级决策本身
def test_scope_changes_dynamic_permission_level(tmp_path: Path) -> None:
    tool = WriteFileTool(tmp_path, ["src"])
    assert tool.classify_permission({"path": "src/main.py"}) == ToolPermission.WORKSPACE_WRITE
    assert (
        tool.classify_permission({"path": "docs/result.txt"})
        == ToolPermission.DANGER_FULL_ACCESS
    )


# 功能：验证普通模式下越界写入会发起审批，用户允许后才真正落盘
# 设计：在 permission.requested 回调中 allow_once，断言事件、文件与审计证据三者同时存在
async def test_out_of_scope_write_runs_after_user_approval(tmp_path: Path) -> None:
    result, events, audit = await _invoke_write(
        tmp_path, PermissionManager(), "allow_once"
    )
    assert not result.is_error
    assert (tmp_path / "docs/result.txt").read_text(encoding="utf-8") == "approved"
    assert "permission.requested" in [event.type for event in events]  # type: ignore[attr-defined]
    assert audit.paths == ["docs/result.txt"]


# 功能：验证普通模式下用户拒绝越界写入时文件不会被创建
# 设计：对同一越界调用返回 deny_once，确认权限失败事件出现且审计日志保持为空
async def test_out_of_scope_write_stops_after_user_denial(tmp_path: Path) -> None:
    result, events, audit = await _invoke_write(
        tmp_path, PermissionManager(), "deny_once"
    )
    assert result.is_error
    assert result.error_type == "permission_denied"
    assert not (tmp_path / "docs/result.txt").exists()
    assert "permission.denied" in [event.type for event in events]  # type: ignore[attr-defined]
    assert audit.paths == []


# 功能：验证 full-access（auto）模式会直接放行越界写入而不挂起审批
# 设计：不给事件回调任何响应，若实现仍等待审批测试会超时；同时断言文件与审计记录已生成
async def test_auto_mode_allows_scope_escalation_without_prompt(tmp_path: Path) -> None:
    manager = PermissionManager(mode=PermissionMode.AUTO)
    result, events, audit = await _invoke_write(tmp_path, manager, None)
    assert not result.is_error
    assert (tmp_path / "docs/result.txt").exists()
    assert "permission.requested" not in [event.type for event in events]  # type: ignore[attr-defined]
    assert audit.paths == ["docs/result.txt"]


# 功能：验证 accept_edits 只自动放行分配范围内编辑，越界仍需显式审批
# 设计：在 accept_edits 模式对越界调用响应 allow_once，断言确实出现 requested 而非静默放行
async def test_accept_edits_still_prompts_for_scope_escalation(tmp_path: Path) -> None:
    manager = PermissionManager(mode=PermissionMode.ACCEPT_EDITS)
    result, events, _ = await _invoke_write(tmp_path, manager, "allow_once")
    assert not result.is_error
    assert "permission.requested" in [event.type for event in events]  # type: ignore[attr-defined]


# 功能：验证范围内写入的 always_allow 缓存不能静默放行后续 full-access 越界写入
# 设计：先缓存同工具的普通写权限，再执行越界写并断言仍出现独立审批事件
async def test_scope_escalation_ignores_workspace_write_cache(tmp_path: Path) -> None:
    manager = PermissionManager()
    in_scope, _, _ = await _invoke_write(
        tmp_path,
        manager,
        "always_allow",
        path="src/approved.txt",
    )
    escalated, events, audit = await _invoke_write(
        tmp_path,
        manager,
        "allow_once",
    )
    assert not in_scope.is_error
    assert not escalated.is_error
    assert "permission.requested" in [event.type for event in events]  # type: ignore[attr-defined]
    assert audit.paths == ["docs/result.txt"]


# 功能：验证模型伪造内部权限字段时仍不能绕过越界写审批
# 设计：直接调用工具并注入同名布尔值，断言身份令牌校验拒绝可序列化伪造值
async def test_serialized_permission_marker_cannot_bypass_scope(tmp_path: Path) -> None:
    tool = WriteFileTool(tmp_path, ["src"])
    with pytest.raises(PermissionError, match="requires approval"):
        await tool.invoke(
            {
                "path": "docs/result.txt",
                "content": "forged",
                "__sztu_permission_grant__": True,
            }
        )
    assert not (tmp_path / "docs/result.txt").exists()


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "C:/outside.txt", "C:\\outside.txt", "C:outside.txt", "../outside"],
)
# 功能：验证工作流分配范围在 POSIX 与 Windows 语义下都必须是安全相对路径
# 设计：覆盖根路径、盘符绝对路径、盘符相对路径和父目录穿越，避免跨平台解析差异
def test_workflow_scope_rejects_cross_platform_absolute_paths(path: str) -> None:
    with pytest.raises(PermissionError, match="inside the assigned workspace scope"):
        normalize_workspace_relative(path)
