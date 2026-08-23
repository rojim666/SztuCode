from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError

CONTEXT_MANAGEMENT_PROMPT_IDS: tuple[str, ...] = (
    "context-compaction-summary",
    "full-compaction-analysis",
    "recent-messages-analysis",
    "subagent-delegation-examples",
)
ACTIVE_CONTEXT_MANAGEMENT_PROMPT_IDS: frozenset[str] = frozenset({"context-compaction-summary"})
_GROUP = "context-management-prompts"


# 第十一章提示词按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_context_management_prompts() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP,
        expected_ids=CONTEXT_MANAGEMENT_PROMPT_IDS,
        active_ids=ACTIVE_CONTEXT_MANAGEMENT_PROMPT_IDS,
    )


# 按稳定 ID 返回单个第十一章原子提示词
def load_context_management_prompt(prompt_id: str) -> str:
    try:
        return load_context_management_prompts()[prompt_id]
    except KeyError as exc:
        raise PromptIndexError(f"unknown context management prompt id: {prompt_id!r}") from exc
