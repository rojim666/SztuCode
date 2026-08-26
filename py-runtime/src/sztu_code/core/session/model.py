from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SessionStatus = Literal["active", "waiting_for_input", "closed"]
SessionMode = Literal["one_shot", "chat"]


@dataclass
class RunStats:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    elapsed_s: float = 0.0
    context_pct: float = 0.0  # 最近一次 LLM 调用的上下文占用百分比

    def to_dict(self) -> dict[str, int | float]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "elapsed_s": self.elapsed_s,
            "context_pct": self.context_pct,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunStats:
        return cls(
            input_tokens=max(0, int(data.get("input_tokens", 0))),
            output_tokens=max(0, int(data.get("output_tokens", 0))),
            cache_read_input_tokens=max(0, int(data.get("cache_read_input_tokens", 0))),
            elapsed_s=max(0.0, float(data.get("elapsed_s", 0.0))),
            context_pct=max(0.0, float(data.get("context_pct", 0.0))),
        )


@dataclass
class Session:
    id: str
    mode: SessionMode
    status: SessionStatus
    title: str
    created_at: str
    updated_at: str
    run_ids: list[str] = field(default_factory=list)
    run_stats: dict[str, RunStats] = field(default_factory=dict)
    archived: bool = False
    pinned: bool = False
    workspace_id: str | None = None

    # 将 Session 转为可写入 meta.json 的普通 dict
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "status": self.status,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "run_ids": list(self.run_ids),
            "run_stats": {run_id: stats.to_dict() for run_id, stats in self.run_stats.items()},
            "archived": self.archived,
            "pinned": self.pinned,
            "workspace_id": self.workspace_id,
        }

    # 从 meta.json 的 dict 还原 Session 对象
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        return cls(
            id=str(data["id"]),
            mode=data["mode"],
            status=data["status"],
            title=str(data.get("title", "")),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            run_ids=[str(x) for x in data.get("run_ids", [])],
            run_stats={
                str(run_id): RunStats.from_dict(stats)
                for run_id, stats in data.get("run_stats", {}).items()
                if isinstance(stats, dict)
            },
            archived=bool(data.get("archived", False)),
            pinned=bool(data.get("pinned", False)),
            workspace_id=str(data["workspace_id"]) if data.get("workspace_id") else None,
        )
