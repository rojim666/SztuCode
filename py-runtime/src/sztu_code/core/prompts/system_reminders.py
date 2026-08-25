from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError

SYSTEM_REMINDER_IDS: tuple[str, ...] = (
    "plan-mode",
    "task-management",
    "file-related",
    "ide-integration",
    "hooks",
    "session-and-budget",
)
ACTIVE_SYSTEM_REMINDER_IDS: frozenset[str] = frozenset()
_GROUP = "system-reminders"


# 第十三章提醒按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_system_reminders() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP,
        expected_ids=SYSTEM_REMINDER_IDS,
        active_ids=ACTIVE_SYSTEM_REMINDER_IDS,
    )


# 按稳定 ID 返回单个第十三章系统提醒原子正文
def load_system_reminder(reminder_id: str) -> str:
    try:
        return load_system_reminders()[reminder_id]
    except KeyError as exc:
        raise PromptIndexError(f"unknown system reminder id: {reminder_id!r}") from exc
