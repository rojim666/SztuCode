from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG

BUILTIN_TOOL_DESCRIPTION_NAMES: tuple[str, ...] = (
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "glob_search",
    "grep_search",
    "bash",
    "spawn_agent",
    "agent_result",
    "ask_user_question",
    "memory_read",
    "note_save",
    "note_update",
    "read_ref",
    "task_create",
    "task_update",
    "task_list",
    "task_get",
)


# 工具描述随 daemon 生命周期缓存；修改 Markdown 后重启即可加载新版本
def load_tool_descriptions() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        "tool-descriptions", expected_ids=BUILTIN_TOOL_DESCRIPTION_NAMES
    )
