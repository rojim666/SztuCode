from __future__ import annotations

from functools import cache

from sztu_code.core.prompts.catalog import DEFAULT_PROMPT_CATALOG, PromptIndexError

MEMORY_EVOLUTION_PROMPT_IDS: tuple[str, ...] = ("meta-agent-analysis",)
ACTIVE_MEMORY_EVOLUTION_PROMPT_IDS: frozenset[str] = frozenset({"meta-agent-analysis"})
_GROUP = "memory-evolution-prompts"

# 单条轨迹节点字段渲染到 prompt 的截断长度
_NODE_FIELD_BUDGET = 120


# 第十三章提示词按 daemon 生命周期缓存；修改 Markdown 后重启即可生效
def load_memory_evolution_prompts() -> dict[str, str]:
    return DEFAULT_PROMPT_CATALOG.validate(
        _GROUP,
        expected_ids=MEMORY_EVOLUTION_PROMPT_IDS,
        active_ids=ACTIVE_MEMORY_EVOLUTION_PROMPT_IDS,
    )


# 按稳定 ID 返回单个第十三章原子提示词
def load_memory_evolution_prompt(prompt_id: str) -> str:
    try:
        return load_memory_evolution_prompts()[prompt_id]
    except KeyError as exc:
        raise PromptIndexError(
            f"unknown memory evolution prompt id: {prompt_id!r}"
        ) from exc


# Meta-Agent 专用 system prompt；[memory-evolution] 标记供测试与运行时区分调用方
@cache
def memory_evolution_system_prompt() -> str:
    return load_memory_evolution_prompt("meta-agent-analysis")


# 将单个轨迹节点渲染为紧凑行（五元组：state / skill / action / observation / verified）
def _render_node(node: dict[str, object]) -> str:
    parts = [
        f"- {node.get('node_id', '?')}"
        f" [status={node.get('status', '')}, verified={node.get('verified', 'unverified')}]"
    ]
    fields: tuple[tuple[str, str], ...] = (
        ("label", "动作"),
        ("skill", "技能"),
        ("state", "步前状态"),
        ("action", "意图"),
        ("observation", "观察"),
        ("summary", "摘要"),
    )
    for key, label in fields:
        value = str(node.get(key, "")).strip()
        if value:
            parts.append(f"{label}={value[:_NODE_FIELD_BUDGET]}")
    return " ".join(parts)


# 构建发送给 Meta-Agent 的用户消息：任务目标 + 完整结构化轨迹
def build_evolution_prompt(
    trajectory: list[dict[str, object]], *, goal: str = ""
) -> str:
    lines: list[str] = []
    if goal:
        lines.append("## 任务目标")
        lines.append(goal)
    lines.append("")
    lines.append("## 结构化轨迹（每步含 state / skill / action / observation / verified 五元组）")
    if trajectory:
        lines.extend(_render_node(node) for node in trajectory)
    else:
        lines.append("（轨迹为空——run 在第一步前失败）")
    lines.append("")
    lines.append("## 你的输出")
    lines.append("仅输出 JSON 数组。")
    return "\n".join(lines)
