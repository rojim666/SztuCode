from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


# 清理文本使其可作为 Mermaid 节点标签：去除换行、转义特殊字符
def _sanitize_mermaid_label(text: str, max_len: int = 80) -> str:
    # 只取第一行，去除首尾空白
    cleaned = text.strip().split("\n")[0].strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    # 移除或替换会破坏 Mermaid 语法的字符
    cleaned = cleaned.replace('"', "'")     # 双引号 → 单引号
    cleaned = cleaned.replace("(", "（")    # 圆括号 → 全角
    cleaned = cleaned.replace(")", "）")
    cleaned = cleaned.replace("[", "【")    # 方括号 → 全角
    cleaned = cleaned.replace("]", "】")
    cleaned = cleaned.replace("{", "｛")    # 花括号 → 全角
    cleaned = cleaned.replace("}", "｝")
    cleaned = cleaned.replace("<", "＜")    # 尖括号 → 全角
    cleaned = cleaned.replace(">", "＞")
    cleaned = cleaned.replace("&", "＆")    # & → 全角
    cleaned = cleaned.replace("#", "＃")    # 仅替换行首 #（Mermaid 注释标记）
    if cleaned.startswith("＃"):
        cleaned = "_" + cleaned[1:]
    return cleaned


# 表示任务画布中的一个步骤节点
@dataclass
class CanvasNode:
    node_id: str  # "step_01"
    label: str  # 简短描述，如 "搜索认证相关代码"
    status: str  # "pending" | "running" | "done" | "failed"
    tool_names: list[str] = field(default_factory=list)
    summary: str = ""  # 该步骤完成了什么
    refs: list[str] = field(default_factory=list)  # 关联的卸载文件路径
    ts_start: str = ""
    ts_end: str = ""

    # 渲染为 Mermaid 节点行
    def to_mermaid_node(self) -> str:
        status_icons = {
            "pending": "⏳",
            "running": "🔵",
            "done": "✅",
            "failed": "❌",
        }
        icon = status_icons.get(self.status, "⏳")
        safe_label = _sanitize_mermaid_label(self.label)
        return f'    {self.node_id}["{icon} {safe_label}"]'

    # 渲染为文本摘要行
    def to_summary_line(self) -> str:
        icon = {"pending": "⏳", "running": "🔵", "done": "✅", "failed": "❌"}.get(
            self.status, "⏳"
        )
        tools = ", ".join(self.tool_names) if self.tool_names else "—"
        detail = self.summary[:120] if self.summary else "进行中..."
        return f"- {self.node_id}: {icon} {detail} (工具: {tools})"


# 维护 Mermaid 格式的任务执行画布
class TaskCanvas:
    """任务画布：将 Agent 执行过程组织为 Mermaid Flowchart。

    参考 TencentDB Agent Memory Level 2 — 用结构化有向图替代线性历史，
    让 Agent 在每一步清楚"走到了哪里、还剩什么、每个分支的依赖关系"。

    不额外调用 LLM — 由 AgentLoop 在每步结束时自动维护。
    """

    # 初始化空画布
    def __init__(self, max_visible_nodes: int = 20) -> None:
        self._nodes: list[CanvasNode] = []
        self._step_counter = 0
        self._max_visible = max_visible_nodes

    @property
    def nodes(self) -> list[CanvasNode]:
        return list(self._nodes)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # 注册一个新的步骤节点（AgentLoop 每步结束后调用）
    def record_step(
        self,
        *,
        label: str = "",
        tool_names: list[str] | None = None,
        summary: str = "",
        refs: list[str] | None = None,
        status: str = "done",
    ) -> CanvasNode:
        self._step_counter += 1
        node = CanvasNode(
            node_id=f"step_{self._step_counter:02d}",
            label=label or f"Step {self._step_counter}",
            status=status,
            tool_names=list(tool_names or []),
            summary=summary,
            refs=list(refs or []),
            ts_start=_now(),
            ts_end=_now() if status in ("done", "failed") else "",
        )
        self._nodes.append(node)
        return node

    # 将最近的 tool_use → tool_result 整理为一个画布节点
    def record_tool_calls(
        self,
        tool_names: list[str],
        summaries: list[str],
        ref_paths: list[str],
        *,
        status: str = "done",
    ) -> CanvasNode:
        label = "; ".join(tool_names[:3])
        if len(tool_names) > 3:
            label += f" +{len(tool_names) - 3} more"
        combined_summary = "; ".join(summaries[:3]) if summaries else ""
        return self.record_step(
            label=label,
            tool_names=list(tool_names),
            summary=combined_summary[:200],
            refs=list(ref_paths),
            status=status,
        )

    # 渲染为 Mermaid flowchart 文本
    def render_mermaid(self) -> str:
        if not self._nodes:
            return "(任务画布为空 — 尚无执行步骤)"

        visible = self._nodes[-self._max_visible :]
        lines = ["```mermaid", "graph TD"]

        # 绘制节点
        for node in visible:
            lines.append(node.to_mermaid_node())

        # 绘制边（顺序依赖）
        for i in range(len(visible) - 1):
            lines.append(f"    {visible[i].node_id} --> {visible[i+1].node_id}")

        # 折叠旧节点标记
        if len(self._nodes) > self._max_visible:
            hidden_count = len(self._nodes) - self._max_visible
            lines.append(f"    %% {hidden_count} 个更早的步骤已折叠")

        lines.append("```")
        return "\n".join(lines)

    # 渲染最近完成节点的文本摘要
    def recent_summary(self, n: int = 5) -> str:
        if not self._nodes:
            return ""
        recent = [node for node in self._nodes[-n:] if node.status == "done"]
        if not recent:
            return ""
        return "\n".join(node.to_summary_line() for node in recent)

    # 当前进行中的节点
    @property
    def active_nodes(self) -> list[CanvasNode]:
        return [n for n in self._nodes if n.status == "running"]

    # 按状态分组统计
    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self._nodes:
            counts[node.status] = counts.get(node.status, 0) + 1
        return counts

    # 更新最后一个节点的完成信息（工具执行完毕后调用）
    def finalize_last(
        self, *, label: str = "", status: str = "done",
        summary: str = "", refs: list[str] | None = None,
    ) -> None:
        if not self._nodes:
            return
        node = self._nodes[-1]
        if label.strip():
            node.label = _sanitize_mermaid_label(label)
        node.status = status
        if summary:
            node.summary = summary[:200]
        if refs:
            node.refs = list(refs)
        if status in ("done", "failed"):
            node.ts_end = _now()

    # 导出所有节点数据（用于事件流持久化）
    def export(self) -> list[dict[str, object]]:
        return [
            {
                "node_id": n.node_id,
                "label": n.label,
                "status": n.status,
                "tool_names": n.tool_names,
                "summary": n.summary,
                "refs": n.refs,
                "ts_start": n.ts_start,
                "ts_end": n.ts_end,
            }
            for n in self._nodes
        ]
