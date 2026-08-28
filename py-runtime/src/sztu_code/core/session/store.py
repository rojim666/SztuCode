from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sztu_code.core.session.model import RunStats, Session

logger = logging.getLogger(__name__)

MessageContent = str | list[dict[str, Any]]

_CONTINUATION_PREFIX = (
    "This session is being continued from a previous conversation that ran out of "
    "context. The summary below covers the earlier portion of the conversation."
)
_CONTINUATION_ACK = "Understood, I'll continue from this summary."


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def _is_internal_compaction_message(message: dict[str, Any]) -> bool:
    text = _message_text(message.get("content"))
    if message.get("role") == "user":
        return text.startswith(_CONTINUATION_PREFIX) and "\n\nSummary:\n" in text
    if message.get("role") == "assistant":
        return text == _CONTINUATION_ACK
    return False


def _history_signature(message: dict[str, Any]) -> str:
    return json.dumps(
        {"role": message.get("role"), "content": message.get("content")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _merge_history(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not existing:
        return list(incoming)
    if not incoming:
        return existing
    existing_signatures = [_history_signature(message) for message in existing]
    incoming_signatures = [_history_signature(message) for message in incoming]
    for size in range(min(len(existing), len(incoming)), 0, -1):
        if existing_signatures[-size:] == incoming_signatures[:size]:
            return [*existing, *incoming[size:]]
    return [*existing, *incoming]


class SessionStore:
    # 初始化 session 文件存储根目录
    def __init__(
        self,
        root: Path,
        *,
        tool_result_limit: int = 8_000,
        tool_result_keep: int = 4_000,
    ) -> None:
        self._root = root.expanduser()
        self._tool_result_limit = tool_result_limit
        self._tool_result_keep = tool_result_keep
        self._root.mkdir(parents=True, exist_ok=True)

    # 返回指定 session 的目录路径
    def session_dir(self, sid: str) -> Path:
        return self._root / sid

    # 返回指定 session 下的 runs 目录路径
    def runs_dir(self, sid: str) -> Path:
        return self.session_dir(sid) / "runs"

    # 将 session meta 写入 meta.json
    def write_meta(self, session: Session) -> None:
        path = self.session_dir(session.id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "meta.json").write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # 从 meta.json 读取 session meta
    def read_meta(self, sid: str) -> Session:
        data = json.loads((self.session_dir(sid) / "meta.json").read_text(encoding="utf-8"))
        return Session.from_dict(data)

    def backfill_run_stats(self, session: Session) -> bool:
        changed = False
        for run_id in session.run_ids:
            existing = session.run_stats.get(run_id)
            # 已有非零 context_pct 的统计视为完整，跳过；否则尝试从事件补全
            if existing is not None and existing.context_pct > 0:
                continue
            events_path = self.runs_dir(session.id) / run_id / "events.jsonl"
            if not events_path.exists():
                continue
            try:
                lines = events_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            context_pct = 0.0
            for line in reversed(lines):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type")
                if etype == "run.finished":
                    if existing is None:
                        session.run_stats[run_id] = RunStats(
                            input_tokens=max(0, int(event.get("total_input_tokens", 0))),
                            output_tokens=max(0, int(event.get("total_output_tokens", 0))),
                            cache_read_input_tokens=max(
                                0, int(event.get("cache_read_input_tokens", 0))
                            ),
                            elapsed_s=max(0.0, float(event.get("elapsed_s", 0.0))),
                            context_pct=max(0.0, float(event.get("context_pct", 0.0))),
                        )
                        changed = True
                    # 事件缺 context_pct（旧版本）时继续向前找 llm.usage 兜底
                    context_pct = max(0.0, float(event.get("context_pct", 0.0)))
                    if context_pct > 0:
                        break
                elif etype == "llm.usage" and context_pct == 0:
                    context_pct = max(0.0, float(event.get("context_pct", 0.0)))
                    if context_pct > 0:
                        break
            if existing is not None and existing.context_pct == 0 and context_pct > 0:
                existing.context_pct = context_pct
                changed = True
        if changed:
            self.write_meta(session)
        return changed

    def delete(self, sid: str) -> None:
        path = self.session_dir(sid).resolve()
        root = self._root.resolve()
        if path == root:
            raise ValueError("invalid session id")
        try:
            path.relative_to(root)
        except ValueError:
            raise ValueError("invalid session id") from None
        if path.exists():
            shutil.rmtree(path)

    # 读取磁盘中全部有效 session 元数据，并按最近更新时间稳定排序
    def list_sessions(self, *, include_archived: bool = False) -> list[Session]:
        sessions: list[Session] = []
        for meta_path in self._root.glob("*/meta.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                session = Session.from_dict(data)
            except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
                logger.warning("skip invalid session metadata path=%s", meta_path)
                continue
            if include_archived or not session.archived:
                sessions.append(session)
        return sorted(sessions, key=lambda session: (session.updated_at, session.id), reverse=True)

    # 追加一条 Anthropic API 消息到 thread.jsonl
    def append_message(
        self,
        sid: str,
        role: str,
        content: MessageContent,
        run_id: str | None = None,
    ) -> None:
        row: dict[str, Any] = {"ts": _now(), "role": role, "content": content}
        if run_id is not None:
            row["run_id"] = run_id
        path = self.session_dir(sid)
        path.mkdir(parents=True, exist_ok=True)
        with (path / "thread.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 批量追加一次 run 新产生的消息到 thread.jsonl
    def append_messages(
        self,
        sid: str,
        messages: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        for msg in messages:
            self.append_message(
                sid,
                role=str(msg["role"]),
                content=msg["content"],
                run_id=run_id,
            )

    def _read_thread_file(
        self, sid: str, path: Path, *, include_run_id: bool
    ) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        messages: list[dict[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("skip broken thread row sid=%s line=%s", sid, line_no)
                continue
            role = row.get("role")
            if role not in ("user", "assistant"):
                logger.warning(
                    "skip unknown thread role sid=%s line=%s role=%s",
                    sid,
                    line_no,
                    role,
                )
                continue
            message = {
                "role": role,
                "content": row.get("content", ""),
                "ts": row.get("ts", ""),
            }
            if include_run_id and row.get("run_id") is not None:
                message["run_id"] = str(row["run_id"])
            messages.append(message)
        return messages

    # 读取当前模型上下文，并返回可直接传给 Anthropic 的 messages。
    def read_messages(self, sid: str, *, include_run_id: bool = False) -> list[dict[str, Any]]:
        path = self.session_dir(sid) / "thread.jsonl"
        messages = self._read_thread_file(sid, path, include_run_id=include_run_id)

        messages = self._trim_orphan_tool_use(messages)
        from sztu_code.core.compact.budget import truncate_tool_results
        return truncate_tool_results(
            messages,
            limit=self._tool_result_limit,
            keep=self._tool_result_keep,
        )

    def read_history(self, sid: str) -> list[dict[str, Any]]:
        session_dir = self.session_dir(sid)
        current = session_dir / "thread.jsonl"
        archives = sorted(
            session_dir.glob("thread_*.jsonl.bak"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        sources = [*archives, *([current] if current.exists() else [])]
        history: list[dict[str, Any]] = []
        for source in sources:
            chunk = self._read_thread_file(sid, source, include_run_id=True)
            visible = [
                message for message in chunk
                if not _is_internal_compaction_message(message)
            ]
            history = _merge_history(history, visible)

        history = self._trim_orphan_tool_use(history)
        from sztu_code.core.compact.budget import truncate_tool_results
        return truncate_tool_results(
            history,
            limit=self._tool_result_limit,
            keep=self._tool_result_keep,
        )

    def read_context_injections(self, sid: str) -> list[dict[str, Any]]:
        try:
            session = self.read_meta(sid)
        except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
            return []

        injections: list[dict[str, Any]] = []
        for run_id in session.run_ids:
            events_path = self.runs_dir(sid) / run_id / "events.jsonl"
            if not events_path.exists():
                continue
            try:
                lines = events_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "skip broken run event sid=%s run_id=%s line=%s",
                        sid,
                        run_id,
                        line_no,
                    )
                    continue
                if event.get("type") != "context.injected":
                    continue
                try:
                    chars = max(0, int(event.get("chars") or 0))
                except (TypeError, ValueError):
                    chars = 0
                label = str(event.get("label") or "上下文注入")
                if label == "系统提示词":
                    label = "上下文注入"
                injections.append(
                    {
                        "run_id": str(event.get("run_id") or run_id),
                        "source": str(event.get("source") or "system"),
                        "label": label,
                        "chars": chars,
                        "preview": str(event.get("preview") or ""),
                        "text": str(event.get("text") or event.get("preview") or ""),
                        "ts": str(event.get("ts") or ""),
                    }
                )
        return injections

    # 裁掉尾部未配对 tool_use 以及其后的消息，避免 Anthropic messages.invalid
    def _trim_orphan_tool_use(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pending: set[str] = set()
        last_balanced = 0
        for idx, msg in enumerate(messages, start=1):
            content = msg.get("content")
            if isinstance(content, list):
                if msg.get("role") == "assistant":
                    for block in content:
                        if block.get("type") == "tool_use":
                            pending.add(str(block.get("id", "")))
                elif msg.get("role") == "user":
                    for block in content:
                        if block.get("type") == "tool_result":
                            pending.discard(str(block.get("tool_use_id", "")))
            if not pending:
                last_balanced = idx
        if pending:
            logger.warning("trim orphan tool_use blocks from thread")
            return messages[:last_balanced]
        return messages

    # 将压缩后的消息对覆盖写入 thread.jsonl，原文件备份为 thread_<ts>.jsonl.bak
    def write_compacted(self, sid: str, messages: list[dict[str, Any]]) -> None:
        path = self.session_dir(sid) / "thread.jsonl"
        ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        bak = self.session_dir(sid) / f"thread_{ts_str}_{uuid.uuid4().hex[:8]}.jsonl.bak"
        if path.exists():
            path.rename(bak)
        try:
            with path.open("w", encoding="utf-8") as f:
                for msg in messages:
                    row: dict[str, Any] = {
                        "ts": _now(),
                        "role": msg["role"],
                        "content": msg["content"],
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            if not path.exists() and bak.exists():
                bak.rename(path)
            raise

    # 读取 notes.md 全文（仅活跃笔记），文件不存在时返回空字符串
    # Phase 3b: 支持 supersedes 版本化 — 被替代的旧笔记自动隐藏
    def read_notes(self, sid: str) -> str:
        path = self.session_dir(sid) / "notes.md"
        if not path.exists():
            return ""
        raw = path.read_text(encoding="utf-8")
        return _filter_active_notes(raw)

    # 将一条主动笔记追加到 notes.md（带结构化元数据）
    def append_note(self, sid: str, content: str, run_id: str) -> str:
        note_id = f"note-{uuid.uuid4().hex[:12]}"
        path = self.session_dir(sid)
        path.mkdir(parents=True, exist_ok=True)
        header = (
            f"---\n"
            f"id: {note_id}\n"
            f"status: active\n"
            f"supersedes: \n"
            f"superseded_by: \n"
            f"ts: {_now()}\n"
            f"run_id: {run_id}\n"
            f"---\n"
        )
        with (path / "notes.md").open("a", encoding="utf-8") as f:
            f.write(header + content.strip() + "\n\n")
        return note_id

    # 更新一条已有笔记：旧笔记标记 archived，新笔记记录 supersedes 链
    def update_note(self, sid: str, note_id: str, new_content: str, run_id: str) -> str | None:
        path = self.session_dir(sid) / "notes.md"
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        if f"id: {note_id}" not in raw:
            return None

        # 将旧笔记标记为 archived + superseded_by
        updated_raw = raw.replace(
            f"id: {note_id}\nstatus: active",
            f"id: {note_id}\nstatus: archived",
        )
        # 追加新笔记
        new_id = f"note-{uuid.uuid4().hex[:12]}"
        header = (
            f"---\n"
            f"id: {new_id}\n"
            f"status: active\n"
            f"supersedes: {note_id}\n"
            f"superseded_by: \n"
            f"ts: {_now()}\n"
            f"run_id: {run_id}\n"
            f"---\n"
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(updated_raw + header + new_content.strip() + "\n\n", encoding="utf-8")
        tmp.replace(path)
        return new_id


# 从 notes.md 原文中提取仅 status=active 的笔记内容
def _filter_active_notes(raw: str) -> str:
    import re
    raw = raw.strip()
    # 不含 --- 标记的旧格式文件，原样返回（向后兼容）
    if "---" not in raw:
        return raw
    # 匹配每个笔记块：---\n 元数据 \n---\n 内容
    # 块之间由 \n\n---\n 分隔
    pattern = re.compile(
        r'^---\n(.*?)\n---\n(.*?)(?=\n\n---\n|\n*$)', re.DOTALL | re.MULTILINE
    )
    parts: list[str] = []
    for match in pattern.finditer(raw):
        header = match.group(1)
        body = match.group(2).strip()
        if 'status: active' in header:
            # 提取 run_id 用于显示
            run_match = re.search(r'run_id:\s*(\S+)', header)
            run_info = f" ({run_match.group(1)})" if run_match else ""
            parts.append(f"## Note{run_info}\n{body}")
    return "\n\n".join(parts)
