from __future__ import annotations

import json
from pathlib import Path

import pytest

from sztu_code.core.compact.compactor import _compact_prompt
from sztu_code.core.prompts.context_management_prompts import (
    ACTIVE_CONTEXT_MANAGEMENT_PROMPT_IDS,
    CONTEXT_MANAGEMENT_PROMPT_IDS,
    load_context_management_prompt,
    load_context_management_prompts,
)
from sztu_code.core.prompts.system_prompt import PromptIndexError


# 功能：验证第十一章索引完整声明四类上下文管理提示词且正文非空
# 设计：比较稳定 ID 顺序并遍历加载结果，覆盖缺项、重复项和空 Markdown
def test_chapter_eleven_index_contains_all_prompts() -> None:
    prompts = load_context_management_prompts()

    assert tuple(prompts) == CONTEXT_MANAGEMENT_PROMPT_IDS
    assert all(prompt.strip() for prompt in prompts.values())


# 功能：验证只有上下文压缩摘要连接到当前运行时压缩器
# 设计：直接检查索引状态，防止分析指令和示例被误注入普通 Agent
def test_chapter_eleven_active_status_matches_real_consumer() -> None:
    index_path = (
        Path(__file__).parents[2]
        / "src"
        / "sztu_code"
        / "core"
        / "prompts"
        / "content"
        / "context-management-prompts"
        / "index.json"
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    active = {entry["id"] for entry in index["sections"] if entry["status"] == "active"}

    assert active == set(ACTIVE_CONTEXT_MANAGEMENT_PROMPT_IDS) == {"context-compaction-summary"}


# 功能：验证 Compactor 按需使用第十一章上下文续接摘要而不是第八章通用摘要
# 设计：调用惰性访问函数并比对章节独有标签，覆盖实际模型调用入口且避免导入期加载
def test_compactor_uses_context_compaction_prompt() -> None:
    prompt = load_context_management_prompt("context-compaction-summary")
    compact_prompt = _compact_prompt()

    assert compact_prompt == prompt
    assert "Task Overview" in compact_prompt
    assert "<summary></summary>" in compact_prompt


# 功能：验证 reference-only 上下文提示词仍可按 ID 读取但不改变压缩器提示词
# 设计：抽查完整对话分析和子代理示例，确认它们被索引管理而非拼接进当前压缩请求
def test_reference_context_prompts_are_not_in_compactor_prompt() -> None:
    compact_prompt = _compact_prompt()

    assert "<analysis>" in load_context_management_prompt("full-compaction-analysis")
    assert "Delegation flow" in load_context_management_prompt("subagent-delegation-examples")
    assert "<analysis>" not in compact_prompt
    assert "Delegation flow" not in compact_prompt


# 功能：验证不存在的第十一章提示词 ID 会返回明确索引错误
# 设计：传入未知 ID 并匹配错误类型与消息，避免调用方静默取得空提示词
def test_unknown_context_management_prompt_id_is_rejected() -> None:
    with pytest.raises(PromptIndexError, match="unknown context management prompt id"):
        load_context_management_prompt("missing")
