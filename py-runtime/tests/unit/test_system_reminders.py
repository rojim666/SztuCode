from __future__ import annotations

import json
from pathlib import Path

import pytest

from sztu_code.core.prompts.system_prompt import PromptIndexError
from sztu_code.core.prompts.system_reminders import (
    ACTIVE_SYSTEM_REMINDER_IDS,
    SYSTEM_REMINDER_IDS,
    load_system_reminder,
    load_system_reminders,
)


# 功能：验证第十三章索引完整声明六类系统提醒且正文非空
# 设计：比较稳定 ID 顺序并遍历加载结果，覆盖缺项、重复项和空 Markdown
def test_chapter_thirteen_index_contains_all_reminders() -> None:
    reminders = load_system_reminders()

    assert tuple(reminders) == SYSTEM_REMINDER_IDS
    assert all(reminder.strip() for reminder in reminders.values())


# 功能：验证当前没有统一系统提醒注入器时六类提醒均为 reference-only
# 设计：直接检查索引状态与代码常量，防止模型看到虚构的 IDE、Hook 或预算状态
def test_chapter_thirteen_active_status_matches_runtime() -> None:
    index_path = (
        Path(__file__).parents[2]
        / "src"
        / "sztu_code"
        / "core"
        / "prompts"
        / "content"
        / "system-reminders"
        / "index.json"
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    active = {entry["id"] for entry in index["sections"] if entry["status"] == "active"}

    assert active == set(ACTIVE_SYSTEM_REMINDER_IDS) == set()


# 功能：验证六类系统提醒均可按稳定 ID 独立读取
# 设计：抽查计划、文件、Hook 和预算唯一标记，确认索引映射到对应原子文件
def test_system_reminders_are_loadable_by_id() -> None:
    assert "Plan Mode" in load_system_reminder("plan-mode")
    assert "file exists but is empty" in load_system_reminder("file-related")
    assert "Hook executed successfully" in load_system_reminder("hooks")
    assert "Current token usage" in load_system_reminder("session-and-budget")


# 功能：验证不存在的第十三章提醒 ID 会返回明确索引错误
# 设计：传入未知 ID 并匹配错误类型与消息，避免调用方静默取得空提醒
def test_unknown_system_reminder_id_is_rejected() -> None:
    with pytest.raises(PromptIndexError, match="unknown system reminder id"):
        load_system_reminder("missing")
