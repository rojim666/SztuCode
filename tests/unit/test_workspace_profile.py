from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from sztu_code.core.bus.commands import Command, WorkspaceProfileCommand, WorkspaceProfileResult
from sztu_code.core.workspace import WorkspaceManager


# 从画像中的技术结论取名称，保持刷新断言紧凑可读。
def _language_names(profile: object) -> set[str]:
    return {
        finding.name
        for project in profile.projects
        for finding in project.languages
    }


# 功能：验证工作区画像默认复用缓存，而显式刷新会重新读取当前项目结构。
# 设计：先创建 Node 项目，再新增 Python 清单，分别断言缓存稳定性和 refresh=True 的磁盘状态反映。
def test_workspace_profile_refreshes_detected_workspace_state(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"name": "web"}), encoding="utf-8")
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    first = manager.profile(workspace.id)
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'api'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    cached = manager.profile(workspace.id)
    refreshed = manager.profile(workspace.id, refresh=True)

    assert _language_names(first) == {"Node.js"}
    assert _language_names(cached) == {"Node.js"}
    assert _language_names(refreshed) == {"Node.js", "Python"}


# 功能：验证 workspace.profile 命令模型可被判别联合解析并序列化结构化画像结果。
# 设计：用 TypeAdapter 走真实 Command union，再以最小项目画像构造 Result，覆盖协议字段而不依赖 daemon。
def test_workspace_profile_command_roundtrip_uses_structured_result(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"name": "web"}), encoding="utf-8")
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    command = TypeAdapter(Command).validate_python(
        {"type": "workspace.profile", "workspace_id": workspace.id, "refresh": True}
    )
    result = WorkspaceProfileResult(profile=manager.profile(workspace.id, refresh=True))

    assert isinstance(command, WorkspaceProfileCommand)
    assert command.refresh is True
    assert result.model_dump(mode="json")["profile"]["projects"][0]["path"] == "."
