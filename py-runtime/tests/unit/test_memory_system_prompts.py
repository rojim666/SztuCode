from __future__ import annotations

import json
from pathlib import Path

import pytest

from sztu_code.core.prompts.memory_system_prompts import (
    ACTIVE_MEMORY_SYSTEM_PROMPT_IDS,
    MEMORY_SYSTEM_PROMPT_IDS,
    append_runtime_memory_prompt,
    load_memory_system_prompt,
    load_memory_system_prompts,
)
from sztu_code.core.prompts.system_prompt import PromptIndexError, build_static_base


# 功能：验证第十二章索引完整声明四类记忆系统提示词且正文非空
# 设计：比较稳定 ID 顺序并遍历加载结果，覆盖缺项、重复项和空 Markdown
def test_chapter_twelve_index_contains_all_prompts() -> None:
    prompts = load_memory_system_prompts()

    assert tuple(prompts) == MEMORY_SYSTEM_PROMPT_IDS
    assert all(prompt.strip() for prompt in prompts.values())


# 功能：验证只有 Auto Memory 指令连接到当前会话运行时
# 设计：直接检查索引状态，防止未实现的自动更新和 CLAUDE.md 生成链路被误标为 active
def test_chapter_twelve_active_status_matches_real_consumer() -> None:
    index_path = (
        Path(__file__).parents[2]
        / "src"
        / "sztu_code"
        / "core"
        / "prompts"
        / "content"
        / "memory-system-prompts"
        / "index.json"
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    active = {entry["id"] for entry in index["sections"] if entry["status"] == "active"}

    assert active == set(ACTIVE_MEMORY_SYSTEM_PROMPT_IDS) == {"auto-memory"}


# 功能：验证 Auto Memory 指令只为具备会话记忆工具的运行追加
# 设计：用同一基础提示分别启用和禁用，确认一次性运行不会看到不存在的工具能力
def test_auto_memory_prompt_is_conditionally_appended() -> None:
    enabled = append_runtime_memory_prompt("BASE", enabled=True)

    assert load_memory_system_prompt("auto-memory") in enabled
    assert "note_save" in enabled
    assert append_runtime_memory_prompt("BASE", enabled=False) == "BASE"


# 功能：验证第十二章提示词不会无条件进入主 Agent 静态提示词
# 设计：检查 Auto Memory 唯一标题，确保是否注入由 Session Runner 的真实能力决定
def test_memory_prompt_is_not_in_static_base() -> None:
    assert "# Auto Memory" not in build_static_base()


# 功能：验证 reference-only 记忆提示词可按稳定 ID 独立读取
# 设计：抽查自动更新、私有反馈和 CLAUDE.md 创建的唯一标记，确认索引映射正确
def test_reference_memory_prompts_are_loadable() -> None:
    assert "Current State" in load_memory_system_prompt("memory-update")
    assert "<description>" in load_memory_system_prompt("private-feedback")
    assert "Analyze the codebase" in load_memory_system_prompt("claude-md-creation")


# 功能：验证不存在的第十二章提示词 ID 会返回明确索引错误
# 设计：传入未知 ID 并匹配错误类型与消息，避免调用方静默取得空提示词
def test_unknown_memory_system_prompt_id_is_rejected() -> None:
    with pytest.raises(PromptIndexError, match="unknown memory system prompt id"):
        load_memory_system_prompt("missing")
