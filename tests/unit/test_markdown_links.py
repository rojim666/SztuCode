from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_markdown_links.py"


# 用文件路径加载脚本模块：scripts/ 不是包，无法按模块名导入
def _load_checker() -> object:
    spec = importlib.util.spec_from_file_location("check_markdown_links", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# 在临时目录写入一个 Markdown 文件，自动创建父目录
def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# 功能：验证指向存在文件的相对链接不报错，指向缺失文件的相对链接被报出
# 设计：同一文档内并列一条好链和一条坏链，确认检查器逐链判断而非按文件粗粒度放过或全否
def test_existing_and_missing_relative_links(tmp_path: Path) -> None:
    _write(tmp_path, "docs/target.md", "# 目标\n")
    doc = _write(tmp_path, "README.md", "[好](docs/target.md)\n[坏](docs/missing.md)\n")

    broken = checker.check_file(doc, tmp_path)  # type: ignore[attr-defined]

    assert [(link.line, link.target) for link in broken] == [(2, "docs/missing.md")]


# 功能：验证 `../` 上跨目录链接与目录链接都按当前文档所在目录正确解析
# 设计：让深层文档回指根目录文件和一个目录，覆盖"目标不是普通文件"的分支，防止实现只用 is_file() 判断
def test_parent_directory_and_directory_links(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# 根\n")
    (tmp_path / "docs" / "getting-started").mkdir(parents=True)
    doc = _write(
        tmp_path,
        "docs/development/development.md",
        "[根](../../README.md)\n[目录](../getting-started/)\n[越界](../../nope.md)\n",
    )

    broken = checker.check_file(doc, tmp_path)  # type: ignore[attr-defined]

    assert [(link.line, link.target) for link in broken] == [(3, "../../nope.md")]


# 功能：验证 URL 编码的空格能解码后命中真实文件，未解码时的字面路径不会被误判为存在
# 设计：文件名真实含空格，链接写 %20，若实现漏掉 unquote 就会报坏链，这是最小可暴露该缺陷的用例
def test_url_encoded_space_is_decoded(tmp_path: Path) -> None:
    _write(tmp_path, "docs/my note.md", "# note\n")
    doc = _write(tmp_path, "README.md", "[编码](docs/my%20note.md)\n[未存在](docs/other%20note.md)\n")

    broken = checker.check_file(doc, tmp_path)  # type: ignore[attr-defined]

    assert [(link.line, link.target) for link in broken] == [(2, "docs/other%20note.md")]


# 功能：验证带 #fragment 的本地路径只校验 fragment 前的文件路径，纯锚点链接完全跳过
# 设计：好链带 fragment、坏链也带 fragment，确认报错时输出保留原始目标（含 fragment）而不是截断后的路径
def test_fragment_handling(tmp_path: Path) -> None:
    _write(tmp_path, "docs/guide.md", "# 指南\n")
    doc = _write(
        tmp_path,
        "README.md",
        "[章节](docs/guide.md#安装)\n[本页](#顶部)\n[缺失](docs/gone.md#节)\n",
    )

    broken = checker.check_file(doc, tmp_path)  # type: ignore[attr-defined]

    assert [(link.line, link.target) for link in broken] == [(3, "docs/gone.md#节")]


# 功能：验证外部 URL、邮箱和协议相对链接不参与文件存在性校验
# 设计：这些目标在本地文件系统必然不存在，若实现漏过滤就会全部报错，因此一次断言 broken 为空即可覆盖
def test_external_targets_are_skipped(tmp_path: Path) -> None:
    doc = _write(
        tmp_path,
        "README.md",
        "[站点](https://example.com/a.md)\n"
        "[明文](http://example.com/b.md)\n"
        "[邮箱](mailto:dev@example.com)\n"
        "[CDN](//cdn.example.com/c.md)\n",
    )

    assert checker.check_file(doc, tmp_path) == []  # type: ignore[attr-defined]


# 功能：验证围栏代码块中的示例链接不报错，且围栏结束后恢复检查
# 设计：用 ``` 与 ~~~ 两种围栏，并在 ```` 内嵌 ``` 验证闭合需同字符且不短于开栏；末尾放真坏链确认状态机正确退出而非吞掉后续内容
def test_fenced_code_blocks_are_skipped(tmp_path: Path) -> None:
    doc = _write(
        tmp_path,
        "README.md",
        "```\n[示例](nope.md)\n```\n"
        "~~~markdown\n- [title](url)\n~~~\n"
        "````\n```\n[内嵌](also-nope.md)\n```\n````\n"
        "[真坏链](really-missing.md)\n",
    )

    broken = checker.check_file(doc, tmp_path)  # type: ignore[attr-defined]

    assert [(link.line, link.target) for link in broken] == [(12, "really-missing.md")]


# 功能：验证图片链接被跳过，但包裹图片的外层链接目标仍会校验
# 设计：直接复刻 README 的 badge 语法 `[![alt](url)](target)`，锁住嵌套方括号的解析，朴素正则实现会在此失败
def test_image_links_skipped_but_wrapping_link_checked(tmp_path: Path) -> None:
    doc = _write(
        tmp_path,
        "README.md",
        "![缺图](docs/images/missing.png)\n"
        "[![License](https://img.shields.io/badge/x)](LICENSE)\n",
    )

    broken = checker.check_file(doc, tmp_path)  # type: ignore[attr-defined]

    assert [(link.line, link.target) for link in broken] == [(2, "LICENSE")]


# 功能：验证跨多个文件的多条坏链会一次性全部报告
# 设计：两个文件各含两条坏链，断言四条齐全且按文件与行号有序，排除"发现首条即短路返回"的实现
def test_all_broken_links_reported_together(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "[a](a.md)\n[b](b.md)\n")
    _write(tmp_path, "docs/index.md", "[c](c.md)\n[d](d.md)\n")

    broken = checker.check_repository(tmp_path)  # type: ignore[attr-defined]

    assert [(link.doc.name, link.line, link.target) for link in broken] == [
        ("README.md", 1, "a.md"),
        ("README.md", 2, "b.md"),
        ("index.md", 1, "c.md"),
        ("index.md", 2, "d.md"),
    ]


# 功能：验证无坏链时 main 返回 0
# 设计：走完整 CLI 入口而非直接调 check_repository，覆盖参数解析与返回码约定；main 返回 int 而非 sys.exit，便于直接断言
def test_main_returns_zero_when_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "docs/target.md", "# 目标\n")
    _write(tmp_path, "README.md", "[好](docs/target.md)\n")

    code = checker.main(["--root", str(tmp_path)])  # type: ignore[attr-defined]

    assert code == 0
    assert "未发现坏链" in capsys.readouterr().out


# 功能：验证发现坏链时 main 返回 1，且输出包含源文件、行号和原始目标三要素
# 设计：断言 stderr 中的 `路径:行号 -> 目标` 格式而非仅断言返回码，坏链定位信息是该脚本的核心产出
def test_main_reports_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "docs/guide.md", "占位\n[缺失](../missing.md)\n")

    code = checker.main(["--root", str(tmp_path)])  # type: ignore[attr-defined]

    assert code == 1
    err = capsys.readouterr().err
    assert "docs/guide.md:2 -> ../missing.md" in err


# 功能：验证本仓库当前的 Markdown 文档全部通过检查
# 设计：作为回归防线，让后续文档移动引入的坏链直接在单元测试阶段暴露，而不必等到有人手工点击链接
def test_repository_documents_have_no_broken_links() -> None:
    documents = checker.iter_markdown_files(_REPO_ROOT)  # type: ignore[attr-defined]
    broken = checker.check_repository(_REPO_ROOT)  # type: ignore[attr-defined]

    assert documents, "未扫描到任何 Markdown 文件，扫描范围可能失效"
    assert broken == [], "\n".join(f"{link.doc}:{link.line} -> {link.target}" for link in broken)
