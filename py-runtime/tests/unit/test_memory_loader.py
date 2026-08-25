from __future__ import annotations

from pathlib import Path

from sztu_code.core.memory.loader import MemoryCatalog, MemoryDocument, load_context_file
from sztu_code.core.tools.builtin.memory_read import MemoryReadTool


# 功能：验证文件存在时返回去除首尾空格的完整内容
# 设计：用 tmp_path 写入带前后空白行的文件，断言 strip 后内容一致
def test_load_existing_file(tmp_path: Path) -> None:
    ctx = tmp_path / "context.md"
    ctx.write_text("  # My Context\n- item one\n", encoding="utf-8")
    result = load_context_file(ctx)
    assert result == "# My Context\n- item one"


# 功能：验证文件不存在时返回空字符串
# 设计：传入不存在的路径，无需创建文件，断言返回值为空字符串
def test_load_missing_file(tmp_path: Path) -> None:
    result = load_context_file(tmp_path / "nonexistent.md")
    assert result == ""


# 功能：验证文件存在但内容为空（或仅空白）时返回空字符串
# 设计：写入纯空白内容，strip 后为空，断言返回空字符串
def test_load_empty_file(tmp_path: Path) -> None:
    ctx = tmp_path / "context.md"
    ctx.write_text("   \n\n  ", encoding="utf-8")
    result = load_context_file(ctx)
    assert result == ""


# 功能：验证短记忆保持全文内联，避免小文件按需读取带来的额外模型回合
# 设计：设置高于内容长度的阈值，断言目录输出与原文完全相同
def test_short_memory_remains_inline() -> None:
    catalog = MemoryCatalog([MemoryDocument("project", "# Rules\nUse pytest", "context.md")])
    assert catalog.prompt_content("project") == "# Rules\nUse pytest"
    assert catalog.requires_reader() is False


# 功能：验证长记忆仅披露标题目录，不把正文写入 system prompt
# 设计：使用极低阈值强制渐进式模式，断言标题和读取提示存在而敏感正文不存在
def test_long_memory_uses_progressive_index() -> None:
    content = "# Build\nsecret build details\n## Tests\npytest rules"
    catalog = MemoryCatalog(
        [MemoryDocument("project", content, ".sztu/context.md")],
        inline_chars=10,
    )
    prompt = catalog.prompt_content("project")
    assert "Build" in prompt
    assert "Tests" in prompt
    assert "memory_read" in prompt
    assert "secret build details" not in prompt
    assert catalog.requires_reader() is True


# 功能：验证记忆搜索只返回命中附近片段并提供继续检索游标
# 设计：构造两个分离命中，限制返回长度后检查相关内容和分页元数据
def test_memory_search_returns_bounded_excerpt() -> None:
    content = "# A\nalpha\nnear cache rule\ncontext\n" + ("padding\n" * 20) + "cache second"
    catalog = MemoryCatalog([MemoryDocument("project", content, "context.md")])
    result = catalog.read("project", query="cache", limit=80)
    assert "cache rule" in result
    assert "memory search" in result
    assert len(result) < len(content)


# 功能：验证 memory_read 工具支持分页且单次返回量受限制
# 设计：读取长记忆的中间页，断言内容位置、next_offset 与返回大小均正确
async def test_memory_read_tool_pages_content() -> None:
    catalog = MemoryCatalog([MemoryDocument("session", "0123456789" * 500, "notes.md")])
    result = await MemoryReadTool(catalog).invoke(
        {"layer": "session", "offset": 100, "limit": 120}
    )
    assert result.is_error is False
    assert "next_offset=220" in result.content
    assert len(result.content) < 220
