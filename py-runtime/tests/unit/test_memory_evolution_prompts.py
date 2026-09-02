from __future__ import annotations

from sztu_code.core.prompts.memory_evolution_prompts import (
    build_evolution_prompt,
    memory_evolution_system_prompt,
)


def _trajectory() -> list[dict[str, object]]:
    return [
        {
            "node_id": "step_01",
            "label": "搜索认证代码",
            "status": "done",
            "skill": "grep",
            "verified": "verified",
        },
        {
            "node_id": "step_03",
            "label": "运行测试",
            "status": "failed",
            "observation": "1 failed: test_refresh_token",
            "verified": "failed",
        },
    ]


# 功能：验证 Meta-Agent system prompt 含稳定标记
# 设计：[memory-evolution] 标记供运行时区分 Meta-Agent 调用与主循环调用
def test_system_prompt_has_stable_marker() -> None:
    assert "[memory-evolution]" in memory_evolution_system_prompt()


# 功能：验证 system prompt 声明三个归因组件方向
# 设计：note_content / state_representation / invocation_timing 是失败归因的
#       枚举空间，Meta-Agent 需要在提示词中被告知
def test_system_prompt_lists_attribution_components() -> None:
    prompt = memory_evolution_system_prompt()
    for component in ("note_content", "state_representation", "invocation_timing"):
        assert component in prompt


# 功能：验证 system prompt 声明输出 JSON 契约字段
# 设计：extract_patches 按这些字段解析，提示词与解析器必须一致
def test_system_prompt_specifies_patch_schema() -> None:
    prompt = memory_evolution_system_prompt()
    for field in ("target_note", "proposed_content", "attribution", "evidence_refs"):
        assert field in prompt


# 功能：验证进化 prompt 嵌入轨迹节点证据
# 设计：Meta-Agent 的归因必须基于轨迹——node_id、观察、验证结论都要出现
def test_prompt_embeds_trajectory_nodes() -> None:
    prompt = build_evolution_prompt(_trajectory())
    assert "step_01" in prompt
    assert "step_03" in prompt
    assert "test_refresh_token" in prompt
    assert "failed" in prompt


# 功能：验证进化 prompt 嵌入任务目标
# 设计：归因需要知道 run 想完成什么——goal 是轨迹解释的锚点
def test_prompt_includes_goal_when_given() -> None:
    prompt = build_evolution_prompt(_trajectory(), goal="修复认证问题")
    assert "修复认证问题" in prompt


# 功能：验证空轨迹时 prompt 仍可构建
# 设计：轨迹为空是边界情况（run 在第一步前失败），构建不应抛异常
def test_prompt_with_empty_trajectory() -> None:
    prompt = build_evolution_prompt([], goal="anything")
    assert isinstance(prompt, str)
    assert len(prompt) > 0
