from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult
from sztu_code.core.tools.workspace import resolve_workspace_path

# 遍历时剪枝忽略的目录，避免列出一堆依赖与构建产物
_IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".codegraph", "dist", "build"}
# 单次列出的最大文件数，超出即截断
_MAX_MATCHES = 200


# 匹配相对路径，并允许每个 **/ 模式片段表示零级目录
def _matches_glob(path: str, pattern: str) -> bool:
    pending = [pattern]
    seen: set[str] = set()
    while pending:
        candidate = pending.pop()
        if candidate in seen:
            continue
        seen.add(candidate)
        if fnmatch.fnmatch(path, candidate):
            return True

        start = 0
        while (index := candidate.find("**/", start)) != -1:
            pending.append(candidate[:index] + candidate[index + 3 :])
            start = index + 1
    return False


class GlobSearchParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str
    path: str = ""


class GlobSearchTool(BaseTool):
    params_model = GlobSearchParams
    name = "glob_search"
    required_permission = ToolPermission.READ_ONLY
    aliases: ClassVar[list[str]] = ["glob", "Glob"]
    description = (
        "List files matching a glob pattern (e.g. '**/*.py'). "
        "Returns paths relative to the workspace root."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match file paths, e.g. '**/*.py'.",
            },
            "path": {
                "type": "string",
                "description": "Dir to search within. Empty = whole workspace.",
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

    # 遍历目录（单文件时直接判断），收集匹配 pattern 的相对路径
    def _collect(self, target: Path, pattern: str) -> list[str]:
        root = (self._workspace_root or Path.cwd()).resolve()
        results: list[str] = []
        if target.is_file():
            rel = target.relative_to(root).as_posix()
            if _matches_glob(rel, pattern):
                results.append(rel)
            return results
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
            for filename in filenames:
                rel = (Path(dirpath) / filename).relative_to(root).as_posix()
                if _matches_glob(rel, pattern):
                    results.append(rel)
        return results

    # 列出匹配 glob pattern 的文件相对路径，去重排序并截断
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = GlobSearchParams.model_validate(params)
        if not p.pattern.strip():
            return ToolResult(
                content="pattern must not be empty", is_error=True, error_type="schema_error"
            )
        # 路径越界/不存在时向上抛异常，与 read_file 一致，由 invoke_tool 统一分类
        target = self._resolve_target(p.path)

        results = sorted(set(self._collect(target, p.pattern)))
        if not results:
            return ToolResult(content="No files found.")
        body = "\n".join(results[:_MAX_MATCHES])
        if len(results) > _MAX_MATCHES:
            body += f"\n[truncated: {len(results) - _MAX_MATCHES} more]"
        return ToolResult(content=body)
