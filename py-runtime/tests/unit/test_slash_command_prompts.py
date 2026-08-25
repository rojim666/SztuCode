from __future__ import annotations

import json
from pathlib import Path

import pytest

from sztu_code.core.prompts.slash_command_prompts import (
    ACTIVE_SLASH_COMMAND_PROMPT_IDS,
    SLASH_COMMAND_PROMPT_COMMANDS,
    SLASH_COMMAND_PROMPT_IDS,
    load_slash_command_prompt,
    load_slash_command_prompts,
    resolve_slash_command_prompt,
)
from sztu_code.core.prompts.system_prompt import PromptIndexError, build_static_base


# 功能：验证第九章索引完整声明六类斜杠命令提示词且正文非空
# 设计：比较稳定 ID 顺序并遍历加载结果，覆盖缺项、重复项和空 Markdown
def test_chapter_nine_index_contains_all_prompts() -> None:
    prompts = load_slash_command_prompts()

    assert tuple(prompts) == SLASH_COMMAND_PROMPT_IDS
    assert all(prompt.strip() for prompt in prompts.values())


# 功能：验证第九章索引中的命令名唯一且全部接入现有会话命令入口
# 设计：直接检查索引元数据与命令映射，防止文档状态和运行时消费者不一致
def test_chapter_nine_prompts_are_active_slash_commands() -> None:
    index_path = (
        Path(__file__).parents[2]
        / "src"
        / "sztu_code"
        / "core"
        / "prompts"
        / "content"
        / "slash-command-prompts"
        / "index.json"
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    commands = [entry["command"] for entry in index["sections"]]
    active = {entry["id"] for entry in index["sections"] if entry["status"] == "active"}

    assert len(commands) == len(set(commands)) == len(SLASH_COMMAND_PROMPT_IDS)
    assert all(command.startswith("/") for command in commands)
    assert active == set(ACTIVE_SLASH_COMMAND_PROMPT_IDS) == set(SLASH_COMMAND_PROMPT_IDS)
    assert set(commands) == set(SLASH_COMMAND_PROMPT_COMMANDS)


# 功能：验证第九章工作流提示词可通过稳定 ID 独立读取
# 设计：抽查安全审查和提交工作流的唯一标记，确认索引映射到正确原子文件
def test_load_slash_command_prompt_by_id() -> None:
    assert "HIGH-CONFIDENCE security" in load_slash_command_prompt("security-review")
    assert "Committing changes with git" in load_slash_command_prompt("git-commit")


# 功能：验证命令解析器返回稳定 ID 和对应原子提示词，未知命令交还 Skill 处理
# 设计：分别覆盖一个内建命令和未知命令，确认解析边界不会吞掉用户 Skill
def test_resolve_slash_command_prompt() -> None:
    resolved = resolve_slash_command_prompt("/review-pr")

    assert resolved == ("review-pr", load_slash_command_prompt("review-pr"))
    assert resolve_slash_command_prompt("/custom-skill") is None


# 功能：验证第九章 reference-only 提示词不会自动注入主系统提示词
# 设计：使用安全审查提示词的唯一标记对比静态主提示词和单项加载结果
def test_slash_command_prompts_are_not_injected_into_main_prompt() -> None:
    marker = "FALSE POSITIVE FILTERING"

    assert marker not in build_static_base()
    assert marker in load_slash_command_prompt("security-review")


# 功能：验证不存在的第九章提示词 ID 会返回明确索引错误
# 设计：传入未知 ID 并匹配错误类型与消息，避免调用方静默取得空提示词
def test_unknown_slash_command_prompt_id_is_rejected() -> None:
    with pytest.raises(PromptIndexError, match="unknown slash command prompt id"):
        load_slash_command_prompt("missing")
