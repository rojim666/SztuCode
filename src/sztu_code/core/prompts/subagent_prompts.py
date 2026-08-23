from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError

SUBAGENT_PROMPT_IDS: tuple[str, ...] = (
    "explore",
    "plan",
    "general",
    "agent-creation-architect",
    "conversation-summarization",
    "webfetch-summarizer",
    "bash-command-prefix-detection",
    "security-monitor",
    "session-memory-update",
    "prompt-suggestion-generator",
)
ACTIVE_SUBAGENT_PROMPT_IDS: frozenset[str] = frozenset(
    {"explore", "plan", "general", "conversation-summarization"}
)
_GROUP = "subagent-prompts"


# 第八章提示词按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_subagent_prompts() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP, expected_ids=SUBAGENT_PROMPT_IDS, active_ids=ACTIVE_SUBAGENT_PROMPT_IDS
    )


# 按稳定 ID 返回单个第八章原子提示词
def load_subagent_prompt(prompt_id: str) -> str:
    try:
        return load_subagent_prompts()[prompt_id]
    except KeyError as exc:
        raise PromptIndexError(f"unknown subagent prompt id: {prompt_id!r}") from exc
