from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

PROMPT_CONTENT_ROOT = Path(__file__).with_name("content")
_VALID_STATUSES = frozenset({"active", "reference-only"})


class PromptIndexError(RuntimeError):
    """提示词索引或原子文件无效。"""


@dataclass(frozen=True)
class PromptEntry:
    group: str
    prompt_id: str
    file: str
    content: str
    status: str
    source: str | None
    consumer: str | None
    command: str | None
    reason: str | None


# 校验提示词分组名，避免索引读取越过内容根目录
def _validate_group(group: str) -> None:
    if not group or group in {".", ".."} or Path(group).name != group:
        raise PromptIndexError(f"invalid prompt group: {group!r}")


# 读取可选字符串元数据并拒绝类型错误
def _optional_string(entry: Mapping[str, Any], key: str, index_path: Path) -> str | None:
    value = entry.get(key)
    if value is not None and not isinstance(value, str):
        raise PromptIndexError(f"invalid {key} metadata in prompt index: {index_path}")
    return value


# 从磁盘加载并完整校验一个提示词分组
def _load_group(group: str, prompt_root: Path) -> tuple[PromptEntry, ...]:
    _validate_group(group)
    group_root = prompt_root / group
    index_path = group_root / "index.json"
    try:
        raw_index: Any = json.loads(index_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PromptIndexError(f"cannot read prompt index: {index_path}") from exc
    except json.JSONDecodeError as exc:
        raise PromptIndexError(f"invalid prompt index JSON: {index_path}") from exc

    if not isinstance(raw_index, dict) or raw_index.get("version") != 1:
        raise PromptIndexError(f"unsupported prompt index version: {index_path}")
    sections = raw_index.get("sections")
    if not isinstance(sections, list) or not sections:
        raise PromptIndexError(f"prompt index has no sections: {index_path}")

    loaded: list[PromptEntry] = []
    seen_ids: set[str] = set()
    seen_commands: set[str] = set()
    for position, raw_entry in enumerate(sections):
        if not isinstance(raw_entry, dict):
            raise PromptIndexError(
                f"prompt index section {position} must be an object: {index_path}"
            )
        prompt_id = raw_entry.get("id")
        file_name = raw_entry.get("file")
        if not isinstance(prompt_id, str) or not prompt_id or prompt_id in seen_ids:
            raise PromptIndexError(
                f"prompt index section {position} has an invalid or duplicate id: {index_path}"
            )
        if (
            not isinstance(file_name, str)
            or Path(file_name).name != file_name
            or Path(file_name).suffix.lower() != ".md"
        ):
            raise PromptIndexError(
                f"prompt index section {prompt_id!r} has an invalid file: {index_path}"
            )

        status = raw_entry.get("status", "active")
        if status not in _VALID_STATUSES:
            raise PromptIndexError(f"invalid status for prompt {group}/{prompt_id}: {status!r}")
        command = _optional_string(raw_entry, "command", index_path)
        if command is not None:
            if not command.startswith("/") or command in seen_commands:
                raise PromptIndexError(
                    f"invalid or duplicate command for prompt {group}/{prompt_id}: {command!r}"
                )
            seen_commands.add(command)

        prompt_path = group_root / file_name
        try:
            content = prompt_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise PromptIndexError(f"cannot read prompt section: {prompt_path}") from exc
        if not content:
            raise PromptIndexError(f"prompt section is empty: {prompt_path}")

        seen_ids.add(prompt_id)
        loaded.append(
            PromptEntry(
                group=group,
                prompt_id=prompt_id,
                file=file_name,
                content=content,
                status=status,
                source=_optional_string(raw_entry, "source", index_path),
                consumer=_optional_string(raw_entry, "consumer", index_path),
                command=command,
                reason=_optional_string(raw_entry, "reason", index_path),
            )
        )
    return tuple(loaded)


# 按 daemon 生命周期缓存内置提示词分组
@cache
def _load_builtin_group(group: str) -> tuple[PromptEntry, ...]:
    return _load_group(group, PROMPT_CONTENT_ROOT)


class PromptCatalog:
    # 初始化提示词目录；内置目录启用 daemon 生命周期缓存
    def __init__(self, prompt_root: Path | None = None) -> None:
        self._root = prompt_root

    # 按索引顺序返回分组内全部提示词及元数据
    def entries(self, group: str) -> tuple[PromptEntry, ...]:
        if self._root is None:
            return _load_builtin_group(group)
        return _load_group(group, self._root)

    # 按稳定 ID 返回单个提示词，未知 ID 返回明确错误
    def get(self, group: str, prompt_id: str) -> PromptEntry:
        for entry in self.entries(group):
            if entry.prompt_id == prompt_id:
                return entry
        raise PromptIndexError(f"unknown prompt id: {group}/{prompt_id}")

    # 返回适合旧调用方使用的有序 ID 到正文映射
    def contents(self, group: str) -> dict[str, str]:
        return {entry.prompt_id: entry.content for entry in self.entries(group)}

    # 校验章节声明的稳定 ID、启用状态和命令映射
    def validate(
        self,
        group: str,
        *,
        expected_ids: tuple[str, ...],
        active_ids: frozenset[str] | None = None,
        commands: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        entries = self.entries(group)
        actual_ids = tuple(entry.prompt_id for entry in entries)
        if actual_ids != expected_ids:
            raise PromptIndexError(
                f"prompt group {group!r} index mismatch: "
                f"expected={list(expected_ids)}, actual={list(actual_ids)}"
            )
        if active_ids is not None:
            actual_active = frozenset(
                entry.prompt_id for entry in entries if entry.status == "active"
            )
            if actual_active != active_ids:
                raise PromptIndexError(
                    f"prompt group {group!r} active set mismatch: "
                    f"expected={sorted(active_ids)}, actual={sorted(actual_active)}"
                )
        if commands is not None:
            actual_commands = {
                entry.command: entry.prompt_id for entry in entries if entry.command is not None
            }
            if actual_commands != dict(commands):
                raise PromptIndexError(f"prompt group {group!r} command mapping mismatch")
        return {entry.prompt_id: entry.content for entry in entries}


DEFAULT_PROMPT_CATALOG = PromptCatalog()
