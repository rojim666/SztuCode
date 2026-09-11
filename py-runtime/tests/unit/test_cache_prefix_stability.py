from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

from sztu_code.core.context import ExecutionContext
from sztu_code.core.llm.provider import _annotate_cache_control
from sztu_code.core.prompts import build_system_prompt
from sztu_code.core.prompts.system_prompt import render_git_snapshot


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)


def _make_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-m", "init")


def _blocks(message: dict[str, object]) -> list[dict[str, object]]:
    content = message["content"]
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


# 功能：git 快照不再写入 system prompt（否则每轮变化会击穿前缀缓存）
# 设计：造出未提交改动后构建 system prompt，断言不含 git 快照标记，且快照函数仍可取到内容
def test_system_prompt_excludes_git_snapshot(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "a.txt").write_text("hello\nworld\n", encoding="utf-8")

    prompt = build_system_prompt(workspace_root=tmp_path)

    assert "Git diff snapshot" not in prompt
    assert "Git branch:" not in prompt
    snapshot = render_git_snapshot(tmp_path)
    assert snapshot is not None
    assert "Git branch:" in snapshot


# 功能：同一输入下 system prompt 字节稳定，工作区改动不影响它
# 设计：连续构建两次并对比，再修改工作区后第三次构建，断言三者完全一致
def test_system_prompt_is_byte_stable_across_workspace_changes(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    first = build_system_prompt(workspace_root=tmp_path)
    second = build_system_prompt(workspace_root=tmp_path)
    assert first == second

    (tmp_path / "a.txt").write_text("changed\n", encoding="utf-8")
    third = build_system_prompt(workspace_root=tmp_path)
    assert third == first


# 功能：cache_control 断点打在最后一条消息上，且重复注解不累积
# 设计：构造含摘要 ack 的三条消息，连续注解两次，断言断点恒为 ack + 尾部两处
def test_annotate_cache_control_marks_trailing_and_is_idempotent() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "goal"},
        {"role": "assistant", "content": [{"type": "text", "text": "Understood."}]},
        {"role": "user", "content": [{"type": "text", "text": "next"}]},
    ]

    _annotate_cache_control(messages)
    assert _blocks(messages[1])[0]["cache_control"] == {"type": "ephemeral"}
    assert _blocks(messages[2])[-1]["cache_control"] == {"type": "ephemeral"}

    _annotate_cache_control(messages)
    breaks = sum("cache_control" in block for msg in messages for block in _blocks(msg))
    assert breaks == 2


# 功能：工作区快照注入到 goal 消息开头，system prompt 不受影响
# 设计：构造 ExecutionContext 后注入快照，断言 goal 以 system-reminder 开头并保留原文
def test_prepend_goal_reminder_keeps_goal_and_prepends_snapshot() -> None:
    context = ExecutionContext(run_id="run-1", goal="do the thing", max_steps=10)

    context.prepend_goal_reminder("Git branch: main")

    content = cast(str, context.messages[-1]["content"])
    assert content.startswith("<system-reminder>")
    assert "Git branch: main" in content
    assert content.endswith("do the thing")


# 功能：日期与记忆层不再写入 system prompt
# 设计：断言 system_prompt 只返回 base，动态内容改走 dynamic_context_reminder
def test_system_prompt_excludes_date_and_memory_layers(tmp_path: Path) -> None:
    prompt = build_system_prompt(workspace_root=tmp_path)
    assert "Today's date is" not in prompt
    assert " - Date: " not in prompt

    context = ExecutionContext(
        run_id="run-1",
        goal="g",
        max_steps=5,
        global_context="GLOBAL-MEMO",
        project_context="PROJECT-MEMO",
        project_profile_context="PROFILE-MEMO",
        session_notes="NOTE-MEMO",
    )
    system = context.system_prompt("BASE-PROMPT")
    assert system == "BASE-PROMPT"
    reminder = context.dynamic_context_reminder()
    for marker in ("GLOBAL-MEMO", "PROJECT-MEMO", "PROFILE-MEMO", "NOTE-MEMO"):
        assert marker in reminder
        assert marker not in system
