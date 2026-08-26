from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError

SLASH_COMMAND_PROMPT_IDS: tuple[str, ...] = (
    "security-review",
    "batch",
    "review-pr",
    "pr-comments",
    "git-commit",
    "create-pr",
)
ACTIVE_SLASH_COMMAND_PROMPT_IDS: frozenset[str] = frozenset(SLASH_COMMAND_PROMPT_IDS)
SLASH_COMMAND_PROMPT_COMMANDS: dict[str, str] = {
    "/security-review": "security-review",
    "/batch": "batch",
    "/review-pr": "review-pr",
    "/pr-comments": "pr-comments",
    "/commit": "git-commit",
    "/create-pr": "create-pr",
}
_GROUP = "slash-command-prompts"


# 第九章提示词按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_slash_command_prompts() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP,
        expected_ids=SLASH_COMMAND_PROMPT_IDS,
        active_ids=ACTIVE_SLASH_COMMAND_PROMPT_IDS,
        commands=SLASH_COMMAND_PROMPT_COMMANDS,
    )


# 按稳定 ID 返回单个第九章原子提示词
def load_slash_command_prompt(prompt_id: str) -> str:
    try:
        return load_slash_command_prompts()[prompt_id]
    except KeyError as exc:
        raise PromptIndexError(f"unknown slash command prompt id: {prompt_id!r}") from exc


# 按斜杠命令名解析第九章提示词；非内建命令返回 None 供 Skill 继续处理
def resolve_slash_command_prompt(command: str) -> tuple[str, str] | None:
    prompt_id = SLASH_COMMAND_PROMPT_COMMANDS.get(command)
    if prompt_id is None:
        return None
    return prompt_id, load_slash_command_prompt(prompt_id)
