from __future__ import annotations

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG
from sztu_code.core.prompts.harness import PromptHarness, PromptRuntimeContext
from sztu_code.core.prompts.memory_system_prompts import load_memory_system_prompt
from sztu_code.core.prompts.safety_prompts import load_safety_prompt
from sztu_code.core.prompts.system_prompt import build_static_base

_ALL_GROUPS = (
    "main",
    "doing-tasks",
    "executing-actions-with-care",
    "output-efficiency",
    "tone-and-style",
    "tool-usage-policy",
    "tool-descriptions",
    "subagent-prompts",
    "slash-command-prompts",
    "safety-prompts",
    "context-management-prompts",
    "memory-system-prompts",
    "system-reminders",
)


# 功能：验证十三章提示词目录均能通过统一 Catalog 加载为完整元数据
# 设计：遍历全部分组检查稳定 ID、正文和来源，覆盖所有索引的共享解析路径
def test_catalog_loads_all_prompt_groups() -> None:
    for group in _ALL_GROUPS:
        entries = DEFAULT_PROMPT_CATALOG.entries(group)

        assert entries
        assert len({entry.prompt_id for entry in entries}) == len(entries)
        assert all(entry.group == group for entry in entries)
        assert all(entry.content and entry.source for entry in entries)


# 功能：验证运行时 Harness 只按实际权限和记忆能力注入对应提示词
# 设计：覆盖四种状态组合并比对完整原子正文，防止无消费者提示词进入上下文
def test_harness_injects_only_prompts_required_by_runtime_context() -> None:
    harness = PromptHarness()
    auto_mode = load_safety_prompt("auto-mode")
    auto_memory = load_memory_system_prompt("auto-memory")

    assert harness.runtime_entries(PromptRuntimeContext()) == ()
    assert harness.runtime_entries(PromptRuntimeContext(permission_mode="auto")) == (auto_mode,)
    assert harness.runtime_entries(PromptRuntimeContext(memory_enabled=True)) == (auto_memory,)
    assert harness.runtime_entries(
        PromptRuntimeContext(permission_mode="auto", memory_enabled=True)
    ) == (auto_mode, auto_memory)


# 功能：验证工具规则只按实际注册工具和危险任务意图注入
# 设计：普通读文件任务只拿读取规则，删除任务额外拿谨慎执行规则，避免全量常驻
def test_harness_injects_tool_and_care_rules_on_demand() -> None:
    harness = PromptHarness()
    read_rule = DEFAULT_PROMPT_CATALOG.get("tool-usage-policy", "read-files").content
    care_rule = DEFAULT_PROMPT_CATALOG.get(
        "executing-actions-with-care", "executing-actions-with-care"
    ).content
    entries = harness.runtime_entries(
        PromptRuntimeContext(tool_names=frozenset({"read_file"}), task_text="读取配置")
    )
    assert read_rule in entries
    assert care_rule not in entries
    dangerous = harness.runtime_entries(
        PromptRuntimeContext(tool_names=frozenset({"bash"}), task_text="删除旧分支并推送")
    )
    assert care_rule in dangerous


# 功能：验证参考提示词永远不会被 Harness 自动注入
# 设计：枚举全部 reference-only 元数据，并与所有运行状态的组合结果取交集
def test_harness_never_injects_reference_only_prompts() -> None:
    reference_contents = {
        entry.content
        for group in _ALL_GROUPS
        for entry in DEFAULT_PROMPT_CATALOG.entries(group)
        if entry.status == "reference-only"
    }
    harness = PromptHarness()
    injected = set(
        harness.runtime_entries(PromptRuntimeContext(permission_mode="auto", memory_enabled=True))
    )

    assert reference_contents
    assert reference_contents.isdisjoint(injected)


# 功能：验证运行时组合不会修改或复制静态提示词基座
# 设计：先保存静态基座，再组合全部动态能力并比较前缀与重复次数
def test_harness_preserves_static_prompt_stability() -> None:
    base = build_static_base()
    composed = PromptHarness().compose(
        base,
        PromptRuntimeContext(permission_mode="auto", memory_enabled=True),
    )

    assert composed.startswith(base + "\n\n")
    assert composed.count(base) == 1
    assert build_static_base() == base
