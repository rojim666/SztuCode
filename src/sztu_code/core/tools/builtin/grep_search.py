from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult
from sztu_code.core.tools.workspace import resolve_workspace_path

# 搜索时剪枝忽略的目录，避免扫入依赖与构建产物
_IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".codegraph", "dist", "build"}
# 单次搜索最大命中行数，超出即截断
_MAX_MATCHES = 200
# 单文件最多读取的字节数，防止读入超大的压缩/打包文件
_MAX_BYTES = 512 * 1024


class GrepSearchParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str
    path: str = ""
    glob: str = ""
    case_sensitive: bool = False


class GrepSearchTool(BaseTool):
    params_model = GrepSearchParams
    name = "grep_search"
    required_permission = ToolPermission.READ_ONLY
    aliases: ClassVar[list[str]] = ["grep", "Grep"]
    description = (
        "Search file contents with a regular expression. Returns matching lines "
        "as 'path:line: text', with paths relative to the workspace root."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression to search for.",
            },
            "path": {
                "type": "string",
                "description": "Dir or file to search within. Empty = whole workspace.",
            },
            "glob": {
                "type": "string",
                "description": "Optional file name glob filter, e.g. '*.py'.",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether matching is case-sensitive. Default false.",
            },
        },
        "required": ["pattern"],
    }

    # 绑定可选工作区根目录，使搜索不依赖 daemon 的进程目录
    def __init__(self, workspace_root: Path | None = None) -> None:
        self._workspace_root = workspace_root

    # 解析搜索目标：空路径落到工作区根，越界或不存在时报错
    def _resolve_target(self, path_str: str) -> Path:
        target = resolve_workspace_path(self._workspace_root, path_str or ".")
        if not target.exists():
            raise FileNotFoundError(f"path not found: {path_str}")
        return target

    # 遍历目标目录（单文件时直接返回），剪枝忽略目录并按 glob 过滤
    def _iter_files(self, target: Path, glob_filter: str) -> Iterator[Path]:
        root = (self._workspace_root or Path.cwd()).resolve()
        files: list[Path] = [target] if target.is_file() else []
        if not target.is_file():
            for dirpath, dirnames, filenames in os.walk(target):
                dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
                files.extend(Path(dirpath) / f for f in filenames)
        for file in files:
            rel = file.relative_to(root)
            if glob_filter and not fnmatch.fnmatch(rel.as_posix(), glob_filter):
                continue
            yield file

    # 执行正则搜索，产出 file:line: text 结果，达到上限即截断
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = GrepSearchParams.model_validate(params)
        if not p.pattern.strip():
            return ToolResult(
                content="pattern must not be empty", is_error=True, error_type="schema_error"
            )
        try:
            matcher = re.compile(p.pattern, 0 if p.case_sensitive else re.IGNORECASE)
        except re.error as exc:
            return ToolResult(
                content=f"invalid regex: {exc}", is_error=True, error_type="schema_error"
            )
        # 路径越界/不存在时向上抛异常，与 read_file 一致，由 invoke_tool 统一分类
        target = self._resolve_target(p.path)

        root = (self._workspace_root or Path.cwd()).resolve()
        matches: list[str] = []
        for file in self._iter_files(target, p.glob):
            # 流式读取最多 _MAX_BYTES 字节，避免 read_bytes 先加载完整文件
            with file.open("rb") as fh:
                raw = fh.read(_MAX_BYTES)
            if b"\x00" in raw[:8192]:
                continue  # 跳过二进制文件
            text = raw.decode("utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if matcher.search(line):
                    rel = file.relative_to(root)
                    matches.append(f"{rel.as_posix()}:{lineno}: {line}")
                    if len(matches) >= _MAX_MATCHES:
                        matches.append("[truncated]")
                        return ToolResult(content="\n".join(matches))
        if not matches:
            return ToolResult(content="No matches found.")
        return ToolResult(content="\n".join(matches))
