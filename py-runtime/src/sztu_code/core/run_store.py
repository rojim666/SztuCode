from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

# run 生命周期状态：running 表示执行中，completed/cancelled 为终态
RunStatus = Literal["running", "completed", "cancelled"]

# 默认运行记录根目录；测试可通过 SZTU_RUNS_DIR 覆盖
_DEFAULT_RUNS_DIR = "~/.sztu/runs"
# 终态集合：进入终态后不允许再被覆盖，保证一个 run 只有一个最终结果
_TERMINAL: frozenset[str] = frozenset({"completed", "cancelled"})


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunRecord:
    run_id: str
    session_id: str = ""
    status: RunStatus = "running"
    goal: str = ""
    started_at: str = ""
    ended_at: str | None = None
    result: str = ""
    reason: str | None = None
    steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # 从磁盘 dict 还原 RunRecord，容忍缺失或类型异常字段
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        status = data.get("status", "running")
        if status not in _TERMINAL and status != "running":
            status = "running"
        return cls(
            run_id=str(data.get("run_id", "")),
            session_id=str(data.get("session_id", "")),
            status=status,
            goal=str(data.get("goal", "")),
            started_at=str(data.get("started_at", "")),
            ended_at=str(data["ended_at"]) if data.get("ended_at") else None,
            result=str(data.get("result", "")),
            reason=str(data["reason"]) if data.get("reason") is not None else None,
            steps=max(0, int(data.get("steps", 0) or 0)),
        )


class RunStore:
    # 初始化运行记录根目录，按需创建
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(os.environ.get("SZTU_RUNS_DIR", _DEFAULT_RUNS_DIR)).expanduser()
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    # 返回指定 run_id 的目录路径
    def run_dir(self, run_id: str) -> Path:
        return self._root / run_id

    # 返回指定 run_id 的运行记录文件路径
    def record_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    # 写入一条 running 记录，表示任务已被接收
    def start(self, run_id: str, *, goal: str = "", session_id: str = "") -> RunRecord:
        record = RunRecord(
            run_id=run_id,
            session_id=session_id,
            status="running",
            goal=goal,
            started_at=_now(),
        )
        self._write(record)
        return record

    # 将 running 记录推进到终态；已终态或不存在时返回原记录/None，保证单一最终结果
    def finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        reason: str | None = None,
        steps: int = 0,
        result: str = "",
    ) -> RunRecord | None:
        if status not in _TERMINAL:
            raise ValueError(f"finish requires a terminal status, got {status!r}")
        record = self.get(run_id)
        if record is None or record.status in _TERMINAL:
            return record
        record.status = status
        record.reason = reason
        record.steps = steps
        record.result = result
        record.ended_at = _now()
        self._write(record)
        return record

    # 读取指定 run_id 的记录，不存在或损坏时返回 None
    def get(self, run_id: str) -> RunRecord | None:
        path = self.record_path(run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("skip invalid run record path=%s", path)
            return None
        if not isinstance(data, dict):
            return None
        try:
            return RunRecord.from_dict(data)
        except (TypeError, ValueError, KeyError):
            logger.warning("skip malformed run record path=%s", path)
            return None

    # 返回所有仍处于 running 状态的记录，供启动对账使用
    def list_running(self) -> list[RunRecord]:
        records: list[RunRecord] = []
        for path in self._root.glob("*/run.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("status") != "running":
                continue
            try:
                records.append(RunRecord.from_dict(data))
            except (TypeError, ValueError, KeyError):
                continue
        return records

    # 把崩溃遗留的 running 记录标记为 cancelled（daemon 启动时调用）
    def reconcile(self) -> list[RunRecord]:
        changed: list[RunRecord] = []
        for record in self.list_running():
            record.status = "cancelled"
            record.reason = "daemon_restarted"
            record.ended_at = _now()
            self._write(record)
            changed.append(record)
        return changed

    # 原子写入运行记录，避免半写文件被误读为合法状态
    def _write(self, record: RunRecord) -> None:
        path = self.record_path(record.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
