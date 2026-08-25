from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pytest

from sztu_code.core.tools.builtin.grep_search import _MAX_BYTES, GrepSearchTool


def _make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text(
        "import os\n\nclass Greeter:\n    def hello(self):\n        return \"hi\"\n",
        encoding="utf-8",
    )
    (root / "src" / "util.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    (root / "README.md").write_text("# Project\ngreeter is a demo\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.py").write_text("GREETER_SENTINEL = 1\n", encoding="utf-8")


# 功能：正则命中时返回 file:line: text 格式且路径相对工作区根
# 设计：在 tmp 树中搜 "class Greeter"，断言命中行含相对路径 src/main.py 与行号
async def test_match_returns_file_line_text(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "class Greeter"})
    assert not result.is_error
    assert "src/main.py:3: class Greeter:" in result.content


# 功能：命中结果保留行首空格和行尾空白
# 设计：精确比较包含四格缩进与两个尾随空格的整行，防止 strip 再次破坏源文本
async def test_match_preserves_space_indentation_and_trailing_whitespace(
    tmp_path: Path,
) -> None:
    source = tmp_path / "example.py"
    source.write_text('def greet():\n    return "hello"  \n', encoding="utf-8")
    tool = GrepSearchTool(tmp_path)

    result = await tool.invoke({"pattern": "return"})

    assert not result.is_error
    assert result.content == 'example.py:2:     return "hello"  '


# 功能：命中结果保留 Tab 缩进且不携带 CRLF 换行符
# 设计：用字节写入固定 CRLF 与 Tab，精确断言单行输出以覆盖跨平台换行处理
async def test_match_preserves_tab_indentation_without_source_newline(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_bytes(b'def greet():\r\n\treturn "hello"\r\n')
    tool = GrepSearchTool(tmp_path)

    result = await tool.invoke({"pattern": "return"})

    assert not result.is_error
    assert result.content == 'example.py:2: \treturn "hello"'


# 功能：默认忽略大小写，case_sensitive=True 时区分大小写
# 设计：同一 pattern 分别搜大小写两种写法，验证开关行为
async def test_case_sensitivity_flag(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    insensitive = await tool.invoke({"pattern": "GREETER"})
    assert not insensitive.is_error
    assert "src/main.py" in insensitive.content
    sensitive = await tool.invoke({"pattern": "GREETER", "case_sensitive": True})
    assert not sensitive.is_error
    assert sensitive.content == "No matches found."


# 功能：忽略 node_modules/.git 等目录，不扫入依赖产物
# 设计：node_modules 下放置含目标词的哨兵文件，确认搜索结果不包含它
async def test_ignores_ignored_dirs(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "GREETER_SENTINEL"})
    assert not result.is_error
    assert "No matches found." == result.content


# 功能：glob 过滤只搜索匹配的文件名
# 设计：同 pattern 带 glob="*.py"，断言 README.md（含目标词）不被搜到
async def test_glob_filter(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "greeter", "glob": "*.py"})
    assert not result.is_error
    assert "README.md" not in result.content
    assert "src/main.py" in result.content


# 功能：path 参数指定搜索范围，越界路径抛出 PermissionError
# 设计：path="../secret" 触发 resolve_workspace_path 的越界保护
async def test_path_traversal_raises(tmp_path: Path) -> None:
    tool = GrepSearchTool(tmp_path)
    with pytest.raises(PermissionError):
        await tool.invoke({"pattern": "x", "path": "../secret"})


# 功能：非法正则返回 is_error 且 error_type 为 schema_error
# 设计：pattern="[" 无法编译，断言错误分类而不是抛异常
async def test_invalid_regex_returns_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "["})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：命中数超过上限时截断并追加 [truncated] 标记
# 设计：生成 250 行匹配文件，断言结果以 [truncated] 结尾且行数受限
async def test_truncated_at_match_limit(tmp_path: Path) -> None:
    f = tmp_path / "bulk.txt"
    f.write_text("\n".join(f"line {i} TARGET" for i in range(250)), encoding="utf-8")
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "TARGET"})
    assert not result.is_error
    assert result.content.endswith("[truncated]")
    # 200 条命中 + 1 条截断标记
    assert result.content.count("\n") == 200


# 功能：无命中返回 No matches found
# 设计：搜索不存在的词，断言返回提示文案
async def test_no_matches(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "nonexistent_symbol_xyz"})
    assert not result.is_error
    assert result.content == "No matches found."


# 功能：超过 _MAX_BYTES 的文件只搜索前 _MAX_BYTES 字节，限制前文本可命中、限制后不返回
# 设计：构造限制前后各一个目标词的大文件，分别搜索验证截断边界，不依赖进程内存统计
async def test_only_bytes_within_limit_are_searched(tmp_path: Path) -> None:
    big = tmp_path / "big.txt"
    big.write_bytes(b"TARGET_BEFORE\n" + b"a" * _MAX_BYTES + b"\nTARGET_AFTER\n")
    tool = GrepSearchTool(tmp_path)

    before = await tool.invoke({"pattern": "TARGET_BEFORE"})
    assert not before.is_error
    assert "big.txt:1: TARGET_BEFORE" in before.content

    after = await tool.invoke({"pattern": "TARGET_AFTER"})
    assert not after.is_error
    assert after.content == "No matches found."


# 功能：流式读取以 _MAX_BYTES 为上限调用 read，避免先整读文件再切片
# 设计：monkeypatch Path.open 返回记录 read(n) 的替身文件对象，断言读取参数含上限值且总读取字节不超限
async def test_read_call_carries_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (_MAX_BYTES + 4096))

    class _SpyFile:
        # 替身文件对象：透传真实句柄，同时记录每次 read(n) 的调用参数
        def __init__(self, fh: BinaryIO) -> None:
            self._fh = fh
            self.read_args: list[int] = []
            self.total_bytes = 0

        # 记录读取请求大小与返回字节数，供断言证明读取上限生效
        def read(self, n: int = -1) -> bytes:
            self.read_args.append(n)
            data = self._fh.read(n)
            self.total_bytes += len(data)
            return data

        def __enter__(self) -> _SpyFile:
            return self

        def __exit__(self, *_exc: object) -> None:
            self._fh.close()

    opened_spies: list[_SpyFile] = []
    real_open = Path.open

    # 替换 Path.open 使其返回替身，从而捕获真实读取行为
    def spy_open(self: Path, *args: object, **kwargs: object) -> _SpyFile:
        spy = _SpyFile(real_open(self, *args, **kwargs))
        opened_spies.append(spy)
        return spy

    monkeypatch.setattr(Path, "open", spy_open)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "zzz_missing"})

    assert not result.is_error
    assert opened_spies
    spy = opened_spies[0]
    assert _MAX_BYTES in spy.read_args
    assert spy.total_bytes <= _MAX_BYTES
