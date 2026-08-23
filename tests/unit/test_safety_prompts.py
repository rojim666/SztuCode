from __future__ import annotations

import json
from pathlib import Path

import pytest

from sztu_code.core.prompts.safety_prompts import (
    ACTIVE_SAFETY_PROMPT_IDS,
    SAFETY_PROMPT_IDS,
    append_runtime_safety_prompt,
    load_safety_prompt,
    load_safety_prompts,
)
from sztu_code.core.prompts.system_prompt import PromptIndexError, build_static_base


# 功能：验证第十章索引完整声明五层安全与防护提示词且正文非空
# 设计：比较稳定 ID 顺序并遍历加载结果，覆盖缺项、重复项和空 Markdown
def test_chapter_ten_index_contains_all_prompts() -> None:
    prompts = load_safety_prompts()

    assert tuple(prompts) == SAFETY_PROMPT_IDS
    assert all(prompt.strip() for prompt in prompts.values())


# 功能：验证第十章只将恶意代码防护和 Auto Mode 标记为提示词消费者
# 设计：直接读取索引状态与代码常量比对，防止模型替代确定性权限或沙箱代码
def test_chapter_ten_active_status_matches_real_consumers() -> None:
    index_path = (
        Path(__file__).parents[2]
        / "src"
        / "sztu_code"
        / "core"
        / "prompts"
        / "content"
        / "safety-prompts"
        / "index.json"
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    active = {entry["id"] for entry in index["sections"] if entry["status"] == "active"}

    assert active == set(ACTIVE_SAFETY_PROMPT_IDS)


# 功能：验证恶意代码防护作为静态安全层注入主 Agent 和子 Agent 基础提示词
# 设计：完整比对原子正文是否存在于 build_static_base，确认所有运行路径共享该规则
def test_malicious_code_protection_is_in_static_base() -> None:
    assert load_safety_prompt("malicious-code-protection") in build_static_base()


# 功能：验证 Auto Mode 提示词仅在权限模式为 auto 时动态追加
# 设计：用相同基础提示分别渲染 auto、normal 和 plan，隔离验证条件注入边界
def test_auto_mode_prompt_is_conditionally_appended() -> None:
    auto = append_runtime_safety_prompt("BASE", "auto")

    assert load_safety_prompt("auto-mode") in auto
    assert append_runtime_safety_prompt("BASE", "normal") == "BASE"
    assert append_runtime_safety_prompt("BASE", "plan") == "BASE"


# 功能：验证确定性防护的参考提示词不会进入静态系统上下文
# 设计：使用命令注入检测的唯一标记，确认可按 ID 读取但不会污染普通模型提示词
def test_reference_only_safety_prompts_are_not_in_static_base() -> None:
    marker = "command_injection_detected"

    assert marker not in build_static_base()
    assert marker in load_safety_prompt("command-injection-detection")


# 功能：验证不存在的第十章提示词 ID 会返回明确索引错误
# 设计：传入未知 ID 并匹配错误类型与消息，避免调用方静默取得空提示词
def test_unknown_safety_prompt_id_is_rejected() -> None:
    with pytest.raises(PromptIndexError, match="unknown safety prompt id"):
        load_safety_prompt("missing")
