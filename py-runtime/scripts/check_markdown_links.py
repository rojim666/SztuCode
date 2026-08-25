#!/usr/bin/env python3
"""Check that local relative links in the repository Markdown files resolve to existing paths."""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 引用式链接定义，例如 `[index]: docs/README.md`
_REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(\S+)")

# URI scheme 前缀，例如 `http:` / `https:` / `mailto:`
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

# 围栏代码块的起止行，捕获围栏字符及长度
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


class BrokenLink(NamedTuple):
    doc: Path
    line: int
    target: str


# 收集待检查的 Markdown：根目录文档与 docs/ 下的全部文档
def iter_markdown_files(root: Path) -> list[Path]:
    return sorted(root.glob("*.md")) + sorted(root.glob("docs/**/*.md"))


# 逐行产出围栏代码块之外的内容，避免把代码示例中的链接当成文档链接
def iter_content_lines(lines: Iterable[str]) -> Iterator[tuple[int, str]]:
    fence: str | None = None
    for lineno, line in enumerate(lines, 1):
        match = _FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
            else:
                yield lineno, line
            continue
        # 闭合围栏必须同字符且不短于开栏，避免 ```` 内嵌的 ``` 提前结束代码块
        if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
            fence = None


# 从 `](` 的 `]` 处向左回溯配对的 `[`，返回其下标，找不到时返回 -1
def _find_label_start(line: str, close_bracket: int) -> int:
    depth = 0
    for index in range(close_bracket, -1, -1):
        char = line[index]
        if char == "]":
            depth += 1
        elif char == "[":
            depth -= 1
            if depth == 0:
                return index
    return -1


# 解析 `](` 之后的链接目标，支持 <...> 包裹、可选标题和目标中的嵌套括号
def _parse_destination(line: str, open_paren: int) -> str:
    index = open_paren + 1
    length = len(line)
    while index < length and line[index] in " \t":
        index += 1
    if index >= length:
        return ""
    if line[index] == "<":
        end = line.find(">", index + 1)
        return "" if end == -1 else line[index + 1 : end].strip()

    start = index
    depth = 1
    while index < length:
        char = line[index]
        if char in " \t":
            break
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    return line[start:index]


# 提取一行中的链接目标，跳过图片语法并兼容引用式定义
def extract_link_targets(line: str) -> list[str]:
    targets: list[str] = []

    reference = _REFERENCE_DEFINITION.match(line)
    if reference:
        definition = reference.group(1)
        if definition.startswith("<") and definition.endswith(">"):
            definition = definition[1:-1]
        targets.append(definition)

    search_from = 0
    while True:
        close_bracket = line.find("](", search_from)
        if close_bracket == -1:
            break
        search_from = close_bracket + 1

        label_start = _find_label_start(line, close_bracket)
        if label_start == -1:
            continue
        # `![alt](src)` 是图片，按 issue 要求不校验；外层 `[![alt](src)](target)` 仍会命中 target
        if label_start > 0 and line[label_start - 1] == "!":
            continue

        destination = _parse_destination(line, close_bracket + 1)
        if destination:
            targets.append(destination)
    return targets


# 判断链接目标是否是需要校验的仓库内路径，排除外链、邮箱和纯锚点
def is_local_target(target: str) -> bool:
    if not target or target.startswith(("#", "//", "?")):
        return False
    return not _URI_SCHEME.match(target)


# 把链接目标解析为文件系统路径：截断 fragment 与 query，并解码 %20 等转义
def resolve_target(doc: Path, target: str, root: Path) -> Path | None:
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    if not path_part:
        return None
    decoded = unquote(path_part)
    # 以 `/` 开头的目标按仓库根解析，与常见 Markdown 渲染器行为一致
    if decoded.startswith("/"):
        return root / decoded.lstrip("/")
    return doc.parent / decoded


# 检查单个文档，返回其中所有指向不存在路径的本地链接
def check_file(doc: Path, root: Path) -> list[BrokenLink]:
    broken: list[BrokenLink] = []
    lines = doc.read_text(encoding="utf-8").splitlines()
    for lineno, line in iter_content_lines(lines):
        for target in extract_link_targets(line):
            if not is_local_target(target):
                continue
            resolved = resolve_target(doc, target, root)
            if resolved is None or resolved.exists():
                continue
            broken.append(BrokenLink(doc, lineno, target))
    return broken


# 检查仓库范围内的全部 Markdown，按文件和行号顺序一次性返回所有坏链
def check_repository(root: Path) -> list[BrokenLink]:
    broken: list[BrokenLink] = []
    for doc in iter_markdown_files(root):
        broken.extend(check_file(doc, root))
    return broken


# 解析命令行参数，报告全部坏链并返回进程退出码
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local Markdown links")
    parser.add_argument("--root", default=str(_REPO_ROOT), help="Repository root to scan")
    args = parser.parse_args(argv)

    root = Path(args.root)
    documents = iter_markdown_files(root)
    broken = check_repository(root)

    if broken:
        for link in broken:
            try:
                location: Path = link.doc.relative_to(root)
            except ValueError:
                location = link.doc
            print(f"{location.as_posix()}:{link.line} -> {link.target}", file=sys.stderr)
        print(
            f"ERROR: 共检查 {len(documents)} 个文件，发现 {len(broken)} 条坏链。",
            file=sys.stderr,
        )
        return 1

    print(f"OK: 共检查 {len(documents)} 个文件，未发现坏链。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
