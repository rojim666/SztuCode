from __future__ import annotations

import json
from pathlib import Path

import pytest

from sztu_code.core.agents.loader import AgentProfileLoader
from sztu_code.core.compact.compactor import _compact_prompt
from sztu_code.core.prompts.subagent_prompts import (
    ACTIVE_SUBAGENT_PROMPT_IDS,
    SUBAGENT_PROMPT_IDS,
    load_subagent_prompt,
    load_subagent_prompts,
)
from sztu_code.core.prompts.system_prompt import PromptIndexError, build_static_base


# 功能：验证第八章索引完整声明全部十类子代理提示词且正文非空
# 设计：比较稳定 ID 顺序并遍历加载结果，覆盖缺项、重复项和空 Markdown
def test_chapter_eight_index_contains_all_prompts() -> None:
    prompts = load_subagent_prompts()

    assert tuple(prompts) == SUBAGENT_PROMPT_IDS
    assert all(prompt.strip() for prompt in prompts.values())


# 功能：验证只有当前存在真实运行消费者的四类提示词被标记为 active
# 设计：直接读取索引状态与代码常量比对，防止参考提示词被误接入运行链路
def test_chapter_eight_index_marks_only_real_consumers_active() -> None:
    index_path = (
        Path(__file__).parents[2]
        / "src"
        / "sztu_code"
        / "core"
        / "prompts"
        / "content"
        / "subagent-prompts"
        / "index.json"
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    active = {entry["id"] for entry in index["sections"] if entry["status"] == "active"}

    assert active == set(ACTIVE_SUBAGENT_PROMPT_IDS)


@pytest.mark.parametrize(
    ("role", "prompt_id"),
    (("explore", "explore"), ("plan", "plan"), ("coder", "general")),
)
# 功能：验证三个内建角色按 prompt_id 加载第八章 Markdown
# 设计：参数化比对角色提示词与索引加载结果，避免依赖易变的局部文案
def test_builtin_roles_load_indexed_markdown(role: str, prompt_id: str) -> None:
    profile = AgentProfileLoader().load(role)

    assert profile is not None
    assert profile.prompt_id == prompt_id
    assert profile.system_prompt == load_subagent_prompt(prompt_id)


# 功能：验证压缩器不使用第八章通用对话摘要原子提示词
# 设计：调用压缩器惰性访问函数并与参考正文比对，确认真实消费者选择稳定
def test_compactor_loads_conversation_summarization_prompt() -> None:
    # 第八章提示词仍保留为可复用的通用摘要参考，不再是当前压缩器消费者
    assert _compact_prompt() != load_subagent_prompt("conversation-summarization")
    assert "All user messages" in load_subagent_prompt("conversation-summarization")


# 功能：验证 reference-only 提示词不会注入主提示词或活跃消费者
# 设计：用命令检测提示词的唯一标记扫描所有活跃文本，并反向确认参考正文存在标记
def test_reference_only_prompts_are_not_injected_into_active_agents() -> None:
    reference_marker = "command_injection_detected"
    active_text = "\n".join(
        [
            build_static_base(),
            *(load_subagent_prompt(prompt_id) for prompt_id in ACTIVE_SUBAGENT_PROMPT_IDS),
        ]
    )

    assert reference_marker not in active_text
    assert reference_marker in load_subagent_prompt("bash-command-prefix-detection")


# 功能：验证请求不存在的第八章提示词 ID 时返回明确索引错误
# 设计：使用未知稳定 ID 并匹配错误类型和消息，防止静默返回空提示词
def test_unknown_subagent_prompt_id_is_rejected() -> None:
    with pytest.raises(PromptIndexError, match="unknown subagent prompt id"):
        load_subagent_prompt("missing")
