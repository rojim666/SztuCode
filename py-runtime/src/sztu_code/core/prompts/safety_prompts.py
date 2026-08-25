from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError
from sztu_code.core.prompts.harness import DEFAULT_PROMPT_HARNESS, PromptRuntimeContext

SAFETY_PROMPT_IDS: tuple[str, ...] = (
    "malicious-code-protection",
    "command-injection-detection",
    "sandbox",
    "permission-modes",
    "auto-mode",
)
ACTIVE_SAFETY_PROMPT_IDS: frozenset[str] = frozenset({"malicious-code-protection", "auto-mode"})
_GROUP = "safety-prompts"


# 第十章提示词按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_safety_prompts() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP, expected_ids=SAFETY_PROMPT_IDS, active_ids=ACTIVE_SAFETY_PROMPT_IDS
    )


# 按稳定 ID 返回单个第十章原子提示词
def load_safety_prompt(prompt_id: str) -> str:
    try:
        return load_safety_prompts()[prompt_id]
    except KeyError as exc:
        raise PromptIndexError(f"unknown safety prompt id: {prompt_id!r}") from exc


# 根据当前权限模式追加运行时安全提示词；目前仅 Auto Mode 需要动态注入
def append_runtime_safety_prompt(prompt: str, permission_mode: str) -> str:
    return DEFAULT_PROMPT_HARNESS.compose(
        prompt, PromptRuntimeContext(permission_mode=permission_mode)
    )
