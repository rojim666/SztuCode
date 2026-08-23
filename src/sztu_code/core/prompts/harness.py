from __future__ import annotations

import re
from dataclasses import dataclass

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptCatalog


@dataclass(frozen=True)
class PromptRuntimeContext:
    permission_mode: str = "normal"
    memory_enabled: bool = False
    tool_names: frozenset[str] = frozenset()
    task_text: str = ""


_TOOL_PROMPT_RULES: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (frozenset({"read_file"}), ("read-files",)),
    (frozenset({"edit_file"}), ("edit-files",)),
    (frozenset({"write_file"}), ("create-files",)),
    (frozenset({"glob_search", "list_dir"}), ("search-files",)),
    (frozenset({"grep_search"}), ("search-content",)),
    (frozenset({"bash"}), ("reserve-bash", "sztucode-tool-environment")),
    (frozenset({"spawn_agent"}), ("delegate-exploration",)),
    (
        frozenset({"task_create", "task_update", "task_list", "task_get"}),
        ("task-management",),
    ),
)

_CAUTIOUS_ACTION_RE = re.compile(
    r"(?:\b(?:delete|remove|drop|reset|rebase|push|publish|deploy|release|overwrite|"
    r"credential|secret|production)\b|删除|清空|重置|变基|推送|发布|部署|覆盖|密钥|生产环境)",
    re.IGNORECASE,
)


class PromptHarness:
    # 初始化运行时提示词组合器并允许测试注入独立目录
    def __init__(self, catalog: PromptCatalog | None = None) -> None:
        self._catalog = catalog or DEFAULT_PROMPT_CATALOG

    # 根据当前运行能力选择真正需要注入的动态原子提示词
    def runtime_entries(self, context: PromptRuntimeContext) -> tuple[str, ...]:
        entries: list[str] = []
        selected_tool_prompts: list[str] = []
        for tool_names, prompt_ids in _TOOL_PROMPT_RULES:
            if context.tool_names & tool_names:
                selected_tool_prompts.extend(prompt_ids)
        if len(context.tool_names) > 1:
            selected_tool_prompts.append("parallel-tool-calls")
        entries.extend(
            self._catalog.get("tool-usage-policy", prompt_id).content
            for prompt_id in dict.fromkeys(selected_tool_prompts)
        )
        if _CAUTIOUS_ACTION_RE.search(context.task_text):
            entries.extend(
                entry.content for entry in self._catalog.entries("executing-actions-with-care")
            )
        if context.permission_mode == "auto":
            entries.append(self._catalog.get("safety-prompts", "auto-mode").content)
        if context.memory_enabled:
            entries.append(self._catalog.get("memory-system-prompts", "auto-memory").content)
        return tuple(entries)

    # 将运行时原子提示词追加到既有基座且保持基座字节稳定
    def compose(self, base_prompt: str, context: PromptRuntimeContext) -> str:
        return "\n\n".join((base_prompt, *self.runtime_entries(context)))


DEFAULT_PROMPT_HARNESS = PromptHarness()
