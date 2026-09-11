from __future__ import annotations

from sztu_code.core.context import ExecutionContext


def _make_ctx(**kwargs) -> ExecutionContext:
    defaults = dict(run_id="r1", goal="test goal", max_steps=5)
    defaults.update(kwargs)
    return ExecutionContext(**defaults)


# 功能：验证三层记忆全部存在时都出现在 dynamic_context_reminder 中且顺序正确
# 设计：记忆层已移出 system prompt（保持前缀缓存稳定），断言各 section 依次出现在动态提醒里
def test_all_layers_present() -> None:
    ctx = _make_ctx(
        global_context="global line",
        project_context="project line",
        session_notes="session note",
    )
    # system prompt 只含稳定 base，记忆层走消息尾部的动态提醒
    assert ctx.system_prompt("BASE") == "BASE"
    reminder = ctx.dynamic_context_reminder()
    assert "## Global Context\nglobal line" in reminder
    assert "## Project Context\nproject line" in reminder
    assert "## Session Notes\nsession note" in reminder
    # 顺序：global 在 project 之前，project 在 session 之前
    assert reminder.index("Global") < reminder.index("Project") < reminder.index("Session")


# 功能：验证三层均为空时 system prompt 只含 base、动态提醒为空
# 设计：不设置任何记忆字段，断言输出等于 base 且提醒为空串
def test_no_layers() -> None:
    ctx = _make_ctx()
    prompt = ctx.system_prompt("BASE_ONLY")
    assert prompt == "BASE_ONLY"
    assert ctx.dynamic_context_reminder() == ""


# 功能：验证只有 global_context 时只出现 Global section，其他 section 不出现
# 设计：只设置 global_context，断言 Project 和 Session 标题不在动态提醒中
def test_only_global() -> None:
    ctx = _make_ctx(global_context="global content")
    reminder = ctx.dynamic_context_reminder()
    assert "## Global Context" in reminder
    assert "## Project Context" not in reminder
    assert "## Session Notes" not in reminder


# 功能：验证项目画像作为独立段落注入动态提醒，且位于项目上下文之后
# 设计：同时设置人工项目上下文、生成画像与会话笔记，断言安全说明不覆盖用户内容且三个段落顺序稳定
def test_project_profile_follows_project_context() -> None:
    ctx = _make_ctx(
        project_context="user project context",
        project_profile_context="Detected Project Profile\nadvisory only",
        session_notes="remember this",
    )

    reminder = ctx.dynamic_context_reminder()

    assert "## Project Context\nuser project context" in reminder
    assert "## Project Profile\nDetected Project Profile\nadvisory only" in reminder
    assert (
        reminder.index("## Project Context")
        < reminder.index("## Project Profile")
        < reminder.index("## Session Notes")
    )


# 功能：验证 session_notes 非空时包含 note_save 提示语
# 设计：只设置 session_notes，断言动态提醒含 note_save 相关提示
def test_session_notes_hint() -> None:
    ctx = _make_ctx(session_notes="some note")
    reminder = ctx.dynamic_context_reminder()
    assert "note_save" in reminder
