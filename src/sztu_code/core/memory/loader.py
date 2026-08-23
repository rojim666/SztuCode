from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_INLINE_CHARS = 2_000
_DEFAULT_READ_CHARS = 1_600
_MAX_READ_CHARS = 4_000
_MAX_INDEX_HEADINGS = 16


# 读取指定路径的 context.md，路径不存在或内容为空时返回空字符串
def load_context_file(path: Path) -> str:
    p = path.expanduser()
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class MemoryDocument:
    name: str
    content: str
    source: str


class MemoryCatalog:
    """为稳定提示词提供记忆目录，并按需披露原文。"""

    # 构建本次 run 的不可变记忆快照，避免运行中磁盘变化破坏提示词缓存
    def __init__(
        self,
        documents: Iterable[MemoryDocument],
        *,
        inline_chars: int = _DEFAULT_INLINE_CHARS,
    ) -> None:
        self._documents = {doc.name: doc for doc in documents if doc.content.strip()}
        self._inline_chars = max(0, inline_chars)

    # 返回指定记忆层是否存在
    def has(self, name: str) -> bool:
        return name in self._documents

    # 仅当至少一层记忆被折叠时才需要注册读取工具，避免无意义的 schema token
    def requires_reader(self) -> bool:
        return any(
            len(document.content.strip()) > self._inline_chars
            for document in self._documents.values()
        )

    # 返回 system prompt 使用的渐进式披露文本：短文内联，长文仅展示目录
    def prompt_content(self, name: str) -> str:
        document = self._documents.get(name)
        if document is None:
            return ""
        content = document.content.strip()
        if len(content) <= self._inline_chars:
            return content

        headings = _extract_headings(content)
        index = "\n".join(f"- {heading}" for heading in headings)
        if not index:
            index = "- (no Markdown headings; use query search or paged reading)"
        return (
            f"[Progressive memory: {len(content)} characters, source: {document.source}]\n"
            f"Available topics:\n{index}\n"
            f"Use memory_read(layer=\"{name}\", query=\"...\") for relevant excerpts; "
            "omit query to read by offset."
        )

    # 分页读取或搜索一个记忆层，限制单次返回量以防全文重新灌入上下文
    def read(
        self,
        name: str,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = _DEFAULT_READ_CHARS,
    ) -> str:
        document = self._documents.get(name)
        if document is None:
            available = ", ".join(sorted(self._documents)) or "none"
            raise KeyError(f"memory layer not found: {name}; available: {available}")

        content = document.content
        safe_limit = min(max(1, limit), _MAX_READ_CHARS)
        safe_offset = max(0, offset)
        if query.strip():
            return _search_excerpt(content, query.strip(), safe_offset, safe_limit)

        excerpt = content[safe_offset : safe_offset + safe_limit]
        next_offset = safe_offset + len(excerpt)
        suffix = (
            f"\n\n[memory page: {name}, chars {safe_offset}:{next_offset}/{len(content)}"
            + (f", next_offset={next_offset}" if next_offset < len(content) else ", end")
            + "]"
        )
        return excerpt + suffix


# 从 Markdown 中提取有限数量的标题，作为低 token 的主题目录
def _extract_headings(content: str) -> list[str]:
    headings: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        title = stripped.lstrip("#").strip()
        if title and title not in headings:
            headings.append(title[:120])
        if len(headings) >= _MAX_INDEX_HEADINGS:
            break
    return headings


# 返回查询命中附近的紧凑片段；offset 表示跳过前 N 个命中
def _search_excerpt(content: str, query: str, offset: int, limit: int) -> str:
    lowered_query = query.casefold()
    matches = [
        index
        for index, line in enumerate(content.splitlines())
        if lowered_query in line.casefold()
    ]
    if offset >= len(matches):
        return f"No memory matches for {query!r} after match offset {offset}."

    lines = content.splitlines()
    chunks: list[str] = []
    used = 0
    consumed = 0
    for match_index in matches[offset:]:
        start = max(0, match_index - 2)
        end = min(len(lines), match_index + 3)
        chunk = "\n".join(lines[start:end]).strip()
        if not chunk:
            continue
        separator = "\n\n---\n\n" if chunks else ""
        if used + len(separator) + len(chunk) > limit:
            remaining = limit - used - len(separator)
            if remaining > 0:
                chunks.append(separator + chunk[:remaining])
            break
        chunks.append(separator + chunk)
        used += len(separator) + len(chunk)
        consumed += 1

    next_match = offset + max(1, consumed)
    suffix = (
        f"\n\n[memory search: {query!r}, matches {offset + 1}-"
        f"{min(next_match, len(matches))}/{len(matches)}"
        + (f", next_offset={next_match}" if next_match < len(matches) else ", end")
        + "]"
    )
    return "".join(chunks) + suffix
