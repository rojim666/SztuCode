from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError
from sztu_code.core.prompts.harness import DEFAULT_PROMPT_HARNESS, PromptRuntimeContext

MEMORY_SYSTEM_PROMPT_IDS: tuple[str, ...] = (
    "auto-memory",
    "memory-update",
    "private-feedback",
    "claude-md-creation",
)
ACTIVE_MEMORY_SYSTEM_PROMPT_IDS: frozenset[str] = frozenset({"auto-memory"})
_GROUP = "memory-system-prompts"


# 第十二章提示词按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_memory_system_prompts() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP, expected_ids=MEMORY_SYSTEM_PROMPT_IDS, active_ids=ACTIVE_MEMORY_SYSTEM_PROMPT_IDS
    )


# 按稳定 ID 返回单个第十二章原子提示词
def load_memory_system_prompt(prompt_id: str) -> str:
    try:
        return load_memory_system_prompts()[prompt_id]
    except KeyError as exc:
        raise PromptIndexError(f"unknown memory system prompt id: {prompt_id!r}") from exc


# 仅为具备会话记忆工具的运行追加 Auto Memory 指令
def append_runtime_memory_prompt(prompt: str, *, enabled: bool) -> str:
    return DEFAULT_PROMPT_HARNESS.compose(prompt, PromptRuntimeContext(memory_enabled=enabled))
