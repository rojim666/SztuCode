"""
Phase 3 单元测试：异步压缩 + 记忆版本化 + 精确 Token 计数
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from sztu_code.core.compact.compactor import Compactor
from sztu_code.core.compact.token_counter import TokenCounter
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, UsageStats
from sztu_code.core.session.store import SessionStore, _filter_active_notes
from sztu_code.core.tools.builtin.note_update import NoteUpdateTool

# ============================================================
# 3a: 异步压缩
# ============================================================


def _stub_provider(summary: str = "## 1. Original Goal\nTest\n## 2. Completed\n- done") -> Any:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="end_turn",
        text=summary,
        usage=UsageStats(input_tokens=100, output_tokens=30),
    ))
    return provider


# 功能：验证 compact_async 不阻塞调用者（立即返回 Task）
# 设计：在 async 上下文中调用 compact_async 后检查返回值类型
async def test_compact_async_returns_immediately(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-async")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = [
        {"role": "user", "content": "x" * 500},
        {"role": "assistant", "content": "y" * 500},
    ]

    task = compactor.compact_async(ctx, provider)
    assert task is not None
    assert isinstance(task, asyncio.Task)
    await task  # 等待完成避免 RuntimeWarning


# 功能：验证异步压缩完成后 context.compacted 为 True
# 设计：调用 compact_async 并等待 Task 完成
async def test_compact_async_completes_successfully(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-async2")
    ctx = ExecutionContext(run_id="r2", goal="test", max_steps=5)
    ctx.messages = [
        {"role": "user", "content": "x" * 500},
        {"role": "assistant", "content": "y" * 500},
    ]

    task = compactor.compact_async(ctx, provider)
    assert task is not None
    await task

    assert ctx.compacted is True
    assert len(ctx.messages) == 2


# 功能：验证异步压缩期间有新消息追加时，新消息被保留
# 设计：在 compact_async 执行期间向 context 追加新消息，验证最终保留
async def test_compact_async_preserves_new_messages(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-async3")
    ctx = ExecutionContext(run_id="r3", goal="test", max_steps=5)
    ctx.messages = [
        {"role": "user", "content": "x" * 500},
        {"role": "assistant", "content": "y" * 500},
    ]

    task = compactor.compact_async(ctx, provider)
    assert task is not None
    # 在压缩完成前追加新消息
    ctx.messages.append({"role": "user", "content": "new message after snapshot"})
    await task

    assert ctx.compacted is True
    # 应该有压缩对 + 新消息 = 3 条
    assert len(ctx.messages) == 3
    assert ctx.messages[-1]["content"] == "new message after snapshot"


# ============================================================
# 3b: 记忆版本化
# ============================================================


# 功能：验证 append_note 返回有效的 note_id
def test_append_note_returns_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-notes-1"
    note_id = store.append_note(sid, "使用 Python 3.12", "run-1")
    assert note_id.startswith("note-")
    assert len(note_id) > 0


# 功能：验证 read_notes 读取刚保存的活跃笔记
def test_read_notes_returns_active_notes(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-notes-2"
    store.append_note(sid, "数据库决定用 SQLite", "run-1")
    notes = store.read_notes(sid)
    assert "SQLite" in notes


# 功能：验证 update_note 成功后旧笔记被隐藏，新笔记显示
def test_update_note_hides_old_shows_new(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-notes-3"
    old_id = store.append_note(sid, "使用 SQLite", "run-1")
    store.update_note(sid, old_id, "改用 PostgreSQL", "run-2")
    notes = store.read_notes(sid)
    # 新笔记应可见
    assert "PostgreSQL" in notes
    # 旧笔记应隐藏
    assert "SQLite" not in notes


# 功能：验证 update_note 返回新的 note_id
def test_update_note_returns_new_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-notes-4"
    old_id = store.append_note(sid, "旧内容", "run-1")
    new_id = store.update_note(sid, old_id, "新内容", "run-2")
    assert new_id is not None
    assert new_id != old_id
    assert new_id.startswith("note-")


# 功能：验证 update_note 对不存在的 note_id 返回 None
def test_update_note_missing_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-notes-5"
    result = store.update_note(sid, "note-nonexistent", "内容", "run-1")
    assert result is None


# 功能：验证多次更新形成完整的 supersedes 链
def test_update_note_supersedes_chain(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-notes-6"
    # V1
    v1 = store.append_note(sid, "使用 React", "run-1")
    # V2 替代 V1
    v2 = store.update_note(sid, v1, "使用 Vue 3", "run-2")
    assert v2 is not None
    # V3 替代 V2
    v3 = store.update_note(sid, v2, "使用 Svelte", "run-3")
    assert v3 is not None
    # 只有最新版本可见
    notes = store.read_notes(sid)
    assert "Svelte" in notes
    assert "Vue 3" not in notes
    assert "React" not in notes


# 功能：验证 _filter_active_notes 正确过滤混合状态
def test_filter_active_notes_mixed() -> None:
    raw = """---
id: note-001
status: active
supersedes:
superseded_by:
ts: 2026-08-05T12:00:00Z
run_id: run-1
---
使用 SQLite

---
id: note-002
status: archived
supersedes:
superseded_by: note-003
ts: 2026-08-05T12:01:00Z
run_id: run-2
---
使用 PostgreSQL

---
id: note-003
status: active
supersedes: note-002
superseded_by:
ts: 2026-08-05T12:01:00Z
run_id: run-2
---
改用 PostgreSQL
"""
    active = _filter_active_notes(raw)
    assert "SQLite" in active
    assert "改用 PostgreSQL" in active


# 功能：验证 NoteUpdateTool 成功更新笔记
async def test_note_update_tool_invoke(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-tool-1"
    old_id = store.append_note(sid, "使用 pip", "run-1")
    tool = NoteUpdateTool(store, sid, "run-2")
    result = await tool.invoke({"note_id": old_id, "content": "改用 uv"})
    assert result.is_error is False
    assert old_id in result.content
    # 新版本可见
    notes = store.read_notes(sid)
    assert "改用 uv" in notes


# 功能：验证 NoteUpdateTool 对不存在的 note_id 返回错误
async def test_note_update_tool_missing_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    tool = NoteUpdateTool(store, "sess-tool-2", "run-1")
    result = await tool.invoke({"note_id": "note-fake", "content": "内容"})
    assert result.is_error is True


# ============================================================
# 3c: 精确 Token 计数
# ============================================================


# 功能：验证 TokenCounter 对文本返回正数
def test_token_counter_positive() -> None:
    counter = TokenCounter()
    result = counter.count("hello world")
    assert result > 0


# 功能：验证 TokenCounter 对空字符串返回至少 1
def test_token_counter_empty() -> None:
    counter = TokenCounter()
    result = counter.count("")
    assert result >= 1


# 功能：验证 count_messages 计算多条消息的 token 总数
def test_token_counter_count_messages() -> None:
    counter = TokenCounter()
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    total = counter.count_messages(messages)
    assert total > 0


# 功能：验证 count_messages 处理混合 content 格式（字符串 + 列表）
def test_token_counter_mixed_content() -> None:
    counter = TokenCounter()
    messages = [
        {"role": "user", "content": "text message"},
        {"role": "user", "content": [{"type": "text", "text": "block message"}]},
    ]
    total = counter.count_messages(messages)
    assert total > 0


# 功能：验证 precise_available 反映 tiktoken 是否可用
def test_token_counter_precise_available() -> None:
    counter = TokenCounter()
    # 不强制断言 True/False — tiktoken 可能安装也可能未安装
    assert isinstance(counter.precise_available, bool)


# ============================================================
# 向后兼容：旧格式 notes.md 兼容
# ============================================================


# 功能：验证 read_notes 对旧格式笔记仍正确读取（向后兼容）
def test_read_notes_legacy_format(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions" / "sess-legacy"
    session_dir.mkdir(parents=True)
    (session_dir / "notes.md").write_text(
        "## Note (2026-08-04, run-old)\n旧格式笔记内容\n\n",
        encoding="utf-8",
    )
    store = SessionStore(tmp_path / "sessions")
    notes = store.read_notes("sess-legacy")
    # 旧格式不含 --- 标记，不过滤，原样返回
    assert "旧格式笔记内容" in notes


# ============================================================
# 空 notes 文件
# ============================================================


# 功能：验证不存在 notes.md 时 read_notes 返回空字符串
def test_read_notes_missing_file(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    notes = store.read_notes("sess-empty")
    assert notes == ""
