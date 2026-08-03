from __future__ import annotations

import subprocess
from pathlib import Path

from sztu_code.core.prompts import build_system_prompt
from sztu_code.core.prompts.system_prompt import (
    DYNAMIC_BOUNDARY,
    MAX_INSTRUCTION_FILE_CHARS,
    build_static_base,
    discover_instruction_files,
    render_git_snapshot,
)


# 在临时目录执行 git 命令
def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# 功能：验证静态基础段包含 Intro/System/Doing tasks/Actions 四层
# 设计：直接拼 build_static_base，断言四个锚点标题都存在
def test_static_base_contains_all_four_sections() -> None:
    base = build_static_base()
    assert "interactive agent" in base
    assert "# System" in base
    assert "# Doing tasks" in base
    assert "# Executing actions with care" in base
    assert "NEVER generate or guess URLs" in base


# 功能：验证完整提示词含动态边界、环境与项目段
# 设计：无 workspace 时断言 boundary 与 Environment 段存在，且不含指令段
def test_build_system_prompt_has_boundary_and_environment() -> None:
    prompt = build_system_prompt(workspace_root=None)
    assert DYNAMIC_BOUNDARY in prompt
    assert "# Environment context" in prompt
    assert "# Project context" in prompt
    assert "# Project instructions" not in prompt


# 功能：验证从工作区发现 CLAUDE.md 并注入指令段
# 设计：临时目录放一份 CLAUDE.md，build 后断言其内容与文件名出现
def test_discover_and_inject_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("项目规则：先写测试再实现\n", encoding="utf-8")

    entries = discover_instruction_files(tmp_path)
    assert len(entries) == 1
    assert entries[0][0] == "CLAUDE.md"
    assert "先写测试再实现" in entries[0][1]

    prompt = build_system_prompt(workspace_root=tmp_path)
    assert "## CLAUDE.md" in prompt
    assert "先写测试再实现" in prompt


# 功能：验证超大指令文件被按预算截断
# 设计：写入远超单文件上限的 CLAUDE.md，断言内容被截断且含 [truncated]
def test_instruction_file_budget_truncation(tmp_path: Path) -> None:
    big = "x" * (MAX_INSTRUCTION_FILE_CHARS + 200)
    (tmp_path / "CLAUDE.md").write_text(big, encoding="utf-8")

    entries = discover_instruction_files(tmp_path)

    assert len(entries) == 1
    assert len(entries[0][1]) <= MAX_INSTRUCTION_FILE_CHARS + len("\n[truncated]")
    assert entries[0][1].endswith("[truncated]")


# 功能：验证 git 快照渲染分支、提交与 diff
# 设计：临时 git 仓库提交后修改文件，断言 branch/commit/diff 出现在快照里
def test_git_snapshot_renders(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "a.txt").write_text("one\nTWO\n", encoding="utf-8")

    snapshot = render_git_snapshot(tmp_path)

    assert snapshot is not None
    assert "Git branch: main" in snapshot
    assert "Recent commits" in snapshot
    assert "Git diff snapshot" in snapshot
