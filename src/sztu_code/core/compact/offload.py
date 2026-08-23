from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 总是触发卸载的工具（高输出量，结果冗长）
_DEFAULT_FORCE_TOOLS: frozenset[str] = frozenset({"bash", "grep", "glob"})

# 卸载阈值
_DEFAULT_MIN_CHARS = 2_000
_DEFAULT_MIN_LINES = 50
_DEFAULT_SUMMARY_MAX_CHARS = 300


# 返回当前 UTC 时间的简短时间戳字符串（用于文件名）
def _ts_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 根据工具类型和输出内容生成一行摘要（规则驱动，不调 LLM）
def _make_summary(tool_name: str, content: str, max_chars: int = _DEFAULT_SUMMARY_MAX_CHARS) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    line_count = len(lines)
    char_count = len(content)

    if not content.strip():
        return "(empty output)"

    if tool_name == "bash":
        # 提取末尾关键行：测试结果、错误、总结行
        markers = [
            "passed", "failed", "error", "PASSED", "FAILED", "ERROR",
            "===", "test", "ok", "FAIL", "success", "done",
        ]
        tail = lines[-15:] if len(lines) >= 15 else lines
        summary_lines = []
        for line in tail:
            line_lower = line.lower()
            if any(m in line_lower for m in markers) and len(line) > 5:
                summary_lines.append(line)
        if summary_lines:
            candidate = summary_lines[-1]
            if len(candidate) <= max_chars:
                return candidate
            return candidate[: max_chars - 3] + "..."
        # 回退：取最后一行有意义的内容
        for line in reversed(lines):
            if len(line) > 10:
                if len(line) <= max_chars:
                    return line
                return line[: max_chars - 3] + "..."
        return f"bash output: {line_count} lines"

    elif tool_name in ("read_file", "list_dir"):
        # 文件内容/目录列表，展示统计信息
        return (
            f"{tool_name} 输出: {line_count} 行, {char_count} 字符"
            f"{' (被截断)' if content.endswith('[truncated]') else ''}"
        )

    elif tool_name in ("grep", "glob"):
        # 搜索结果，展示匹配数量
        match_count = sum(
            1 for line in lines
            if line and not line.startswith("#") and not line.startswith("//")
        )
        first_few = [line[:120] for line in lines[:3] if line]
        preview = "; ".join(first_few)
        if len(preview) > max_chars:
            preview = preview[: max_chars - 3] + "..."
        if preview:
            return f"{tool_name}: {match_count} 条结果. 预览: {preview}"
        return f"{tool_name}: {match_count} 条结果"

    else:
        # 通用摘要：首行
        first = lines[0] if lines else content[:max_chars]
        if len(first) <= max_chars:
            suffix = f" (共 {line_count} 行)" if line_count > 1 else ""
            return first + suffix
        return first[: max_chars - 3] + "..."


@dataclass
class OffloadRecord:
    """单条工具结果卸载记录，对应 TencentDB Level 1 (offload.jsonl)"""

    id: str
    run_id: str
    tool_name: str
    tool_use_id: str
    ref_path: str  # 相对路径，如 "refs/bash_20260805_001.md"
    summary: str
    char_count: int
    line_count: int
    is_error: bool
    ts: str

    # 序列化为字典（写入 offload.jsonl）
    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "tool_use_id": self.tool_use_id,
            "ref_path": self.ref_path,
            "summary": self.summary,
            "char_count": self.char_count,
            "line_count": self.line_count,
            "is_error": self.is_error,
            "ts": self.ts,
        }

    # 从字典反序列化
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OffloadRecord:
        return cls(
            id=str(data["id"]),
            run_id=str(data.get("run_id", "")),
            tool_name=str(data["tool_name"]),
            tool_use_id=str(data.get("tool_use_id", "")),
            ref_path=str(data["ref_path"]),
            summary=str(data.get("summary", "")),
            char_count=int(data.get("char_count", 0)),
            line_count=int(data.get("line_count", 0)),
            is_error=bool(data.get("is_error", False)),
            ts=str(data.get("ts", "")),
        )


class OffloadManager:
    """管理工具结果的上下文卸载：写入 refs/*.md + 索引 → offload.jsonl

    参考 TencentDB Agent Memory 的四层递进架构：
      Level 0: refs/*.md       — 完整工具输出原文
      Level 1: offload.jsonl   — 调用级摘要索引
      Level 2: *.mmd           — Mermaid 任务画布（Phase 2）
      Level 3: 上下文占位符     — 注入 context.messages
    """

    # 初始化卸载管理器，绑定 session 目录
    def __init__(
        self,
        session_dir: Path,
        *,
        enabled: bool = True,
        min_chars: int = _DEFAULT_MIN_CHARS,
        min_lines: int = _DEFAULT_MIN_LINES,
        force_tools: frozenset[str] | None = None,
        summary_max_chars: int = _DEFAULT_SUMMARY_MAX_CHARS,
    ) -> None:
        self._session_dir = session_dir
        self._enabled = enabled
        self._min_chars = min_chars
        self._min_lines = min_lines
        self._force_tools = force_tools if force_tools is not None else _DEFAULT_FORCE_TOOLS
        self._summary_max_chars = summary_max_chars
        self._refs_dir = session_dir / "refs"
        self._offload_dir = session_dir / "offload"
        self._index_path = self._offload_dir / "offload.jsonl"
        # Bug5 fix: 仅在启用时才创建目录
        if self._enabled:
            self._refs_dir.mkdir(parents=True, exist_ok=True)
            self._offload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    # 判断工具结果是否需要触发卸载
    def should_offload(self, tool_name: str, content: str) -> bool:
        if not self._enabled:
            return False
        # 回读工具已经自行分页，禁止再次卸载形成 read → offload → read 循环
        if tool_name in {"memory_read", "read_ref"}:
            return False
        if tool_name in self._force_tools:
            return True
        if len(content) > self._min_chars:
            return True
        if content.count("\n") >= self._min_lines:
            return True
        return False

    # 将工具结果写入 refs/*.md 并追加 offload.jsonl 索引记录
    def offload(
        self,
        tool_name: str,
        tool_use_id: str,
        content: str,
        run_id: str,
        is_error: bool = False,
    ) -> OffloadRecord:
        # 确保目录存在（首次 offload 调用时可能还未创建）
        self._refs_dir.mkdir(parents=True, exist_ok=True)
        self._offload_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一 ID 和文件名
        record_id = f"off_{_ts_compact()}_{uuid.uuid4().hex[:8]}"
        ref_filename = f"{tool_name}_{_ts_compact()}_{uuid.uuid4().hex[:8]}.md"
        ref_path = f"refs/{ref_filename}"
        line_count = content.count("\n") + 1

        # Level 0: 写入完整工具输出到 refs/*.md
        full_path = self._session_dir / ref_path
        header = (
            f"# {tool_name} @ {_now()}\n"
            f"# run_id: {run_id}\n"
            f"# tool_use_id: {tool_use_id}\n"
            f"# 字符数: {len(content)} | 行数: {line_count}\n\n"
        )
        try:
            full_path.write_text(header + content, encoding="utf-8")
        except OSError:
            logger.exception("offload: 写入 refs 文件失败 path=%s", full_path)
            raise

        # Level 1: 生成摘要并写索引记录
        summary = _make_summary(tool_name, content, self._summary_max_chars)

        record = OffloadRecord(
            id=record_id,
            run_id=run_id,
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            ref_path=ref_path,
            summary=summary,
            char_count=len(content),
            line_count=line_count,
            is_error=is_error,
            ts=_now(),
        )

        # 索引写入失败不阻塞：ref 文件是 Level 0 真源，索引仅用于 list_by_run
        try:
            with self._index_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("offload: 写入 offload.jsonl 失败，ref 文件仍可用 path=%s", full_path)

        logger.debug(
            "offload: tool=%s chars=%d lines=%d ref=%s",
            tool_name, record.char_count, record.line_count, ref_path,
        )
        return record

    # 按 ref_path 读取卸载文件的完整内容（Level 0 回读）
    def read_ref(self, ref_path: str) -> str:
        # 安全检查：防止路径遍历
        unsafe = Path(ref_path)
        if ".." in unsafe.parts:
            raise ValueError(f"ref_path 包含非法路径遍历: {ref_path}")
        full_path = self._session_dir / ref_path
        if not full_path.is_file():
            raise FileNotFoundError(f"卸载文件不存在: {ref_path}")
        text = full_path.read_text(encoding="utf-8")
        # 剥离文件头：# 开头的注释行（元数据）+ 其后一个空行分隔符
        if text.startswith("# "):
            lines = text.splitlines(keepends=True)
            # 跳过所有 # 开头注释行
            idx = 0
            while idx < len(lines) and lines[idx].startswith("# "):
                idx += 1
            # 跳过恰好一个分隔空行（注释块与内容之间的空白行）
            if idx < len(lines) and lines[idx].strip() == "":
                idx += 1
            if idx > 0 and idx < len(lines):
                return "".join(lines[idx:])
        return text

    # 生成注入上下文的占位符文本（Level 3）
    def placeholder(self, record: OffloadRecord, *, compact: bool = True) -> str:
        if compact:
            return (
                f"[上下文卸载: {record.ref_path}]\n"
                f"摘要: {record.summary}\n"
                f"统计: {record.char_count} 字符, {record.line_count} 行\n"
                f"使用 read_ref(\"{record.ref_path}\") 读取完整输出"
            )
        return (
            f"[上下文卸载: {record.ref_path}]\n"
            f"id: {record.id}\n"
            f"tool: {record.tool_name}\n"
            f"摘要: {record.summary}\n"
            f"统计: {record.char_count} 字符, {record.line_count} 行"
            f"{' (错误)' if record.is_error else ''}\n"
            f"使用 read_ref(\"{record.ref_path}\") 读取完整输出"
        )

    # 按 run_id 查询该次 run 的所有卸载记录
    def list_by_run(self, run_id: str) -> list[OffloadRecord]:
        records: list[OffloadRecord] = []
        if not self._index_path.exists():
            return records
        for line in self._index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("run_id") == run_id:
                records.append(OffloadRecord.from_dict(data))
        return records
