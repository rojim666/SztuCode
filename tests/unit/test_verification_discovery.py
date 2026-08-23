from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.verification import (
    ContractSource,
    build_completion_contract,
    select_relevant_checks,
)
from sztu_code.core.workspace.project_profile import (
    ProjectComponent,
    ProjectProfile,
    ValidationCategory,
    ValidationCommand,
)


def _write_checks(workspace: Path, content: str) -> None:
    checks_dir = workspace / ".sztu"
    checks_dir.mkdir(parents=True, exist_ok=True)
    (checks_dir / "checks.toml").write_text(content, encoding="utf-8")


def _vc(
    category: ValidationCategory,
    command: str,
    *,
    working_directory: str = ".",
    reason: str = "",
) -> ValidationCommand:
    return ValidationCommand(
        category=category,
        command=command,
        working_directory=working_directory,
        reason=reason or f"reason for {command}",
    )


def _profile(*commands: ValidationCommand) -> ProjectProfile:
    return ProjectProfile(
        projects=[ProjectComponent(path=".", validation_plan=list(commands))]
    )


# 功能：合法 checks.toml 独占生效，字段解析正确且 user 条件优先于 profile 来源
# 设计：文件与 profile 同时存在，断言只产出 USER 条件；覆盖显式/缺省 id、
# description、required、priority 各字段的解析与默认值
def test_user_checks_take_precedence_and_parse_fields(tmp_path: Path) -> None:
    _write_checks(
        tmp_path,
        """
[[check]]
id = "unit-tests"
description = "运行单元测试"
command = ["uv", "run", "pytest", "tests/unit", "-q"]
required = true
priority = 5

[[check]]
command = ["ruff", "check", "."]
required = false
""",
    )
    profile = _profile(_vc(ValidationCategory.UNIT_TEST, "uv run pytest"))
    contract = build_completion_contract("run-1", profile, tmp_path)
    assert contract is not None
    assert contract.run_id == "run-1"
    assert all(cond.source is ContractSource.USER for cond in contract.conditions)
    first, second = contract.conditions
    # priority 降序：显式 priority=5 的排前
    assert first.id == "unit-tests"
    assert first.description == "运行单元测试"
    assert first.check_command == ["uv", "run", "pytest", "tests/unit", "-q"]
    assert first.required is True
    assert first.priority == 5
    # 缺省字段：id 自动生成、description 回落命令拼接、priority=0
    assert second.id == "user-2"
    assert second.description == "ruff check ."
    assert second.required is False
    assert second.priority == 0


# 功能：checks.toml TOML 语法错误时整体忽略并回落 profile 来源
# 设计：写入非法 TOML，断言产出 PROJECT_CONFIG 条件且记 warning 日志
def test_invalid_toml_falls_back_to_profile(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_checks(tmp_path, "[[check]\ncommand = broken")
    profile = _profile(_vc(ValidationCategory.UNIT_TEST, "uv run pytest"))
    with caplog.at_level("WARNING"):
        contract = build_completion_contract("run-1", profile, tmp_path)
    assert contract is not None
    [cond] = contract.conditions
    assert cond.source is ContractSource.PROJECT_CONFIG
    assert any("ignoring invalid checks file" in rec.message for rec in caplog.records)


# 功能：checks.toml 条目字段非法（command 非数组）时整体忽略并回落 profile
# 设计：TOML 语法合法但 schema 非法——部分合法条目也不生效，避免静默丢弃用户检查
def test_invalid_schema_falls_back_to_profile(tmp_path: Path) -> None:
    _write_checks(
        tmp_path,
        """
[[check]]
command = ["ok", "entry"]

[[check]]
command = "not an array"
""",
    )
    profile = _profile(_vc(ValidationCategory.STATIC_CHECK, "uv run ruff check ."))
    contract = build_completion_contract("run-1", profile, tmp_path)
    assert contract is not None
    [cond] = contract.conditions
    assert cond.source is ContractSource.PROJECT_CONFIG


# 功能：无 checks.toml 时 profile 转换的类别过滤规则与 argv 转换
# 设计：构造覆盖全部 5 个类别的最小 profile（不依赖真实文件探测，跨平台稳定）；
# 断言 STATIC_CHECK/UNIT_TEST required、FORMAT 可选、INTEGRATION_TEST/BUILD 跳过
def test_profile_category_filtering_and_conversion(tmp_path: Path) -> None:
    profile = _profile(
        _vc(ValidationCategory.FORMAT, "uv run ruff format --check ."),
        _vc(ValidationCategory.STATIC_CHECK, "uv run ruff check ."),
        _vc(ValidationCategory.UNIT_TEST, "uv run pytest"),
        _vc(ValidationCategory.INTEGRATION_TEST, "uv run pytest tests/integration"),
        _vc(ValidationCategory.BUILD, "uv build"),
    )
    contract = build_completion_contract("run-1", profile, tmp_path)
    assert contract is not None
    by_id = {cond.id: cond for cond in contract.conditions}
    assert set(by_id) == {"profile-static-check-1", "profile-unit-test-1", "profile-format-1"}
    static = by_id["profile-static-check-1"]
    assert static.source is ContractSource.PROJECT_CONFIG
    assert static.check_command == ["uv", "run", "ruff", "check", "."]
    assert static.required is True
    unit = by_id["profile-unit-test-1"]
    assert unit.check_command == ["uv", "run", "pytest"]
    assert unit.required is True
    fmt = by_id["profile-format-1"]
    assert fmt.required is False
    # priority 降序：static_check > unit_test > format
    assert [c.id for c in contract.conditions] == [
        "profile-static-check-1",
        "profile-unit-test-1",
        "profile-format-1",
    ]


# 功能：含 shell 语法的命令与子目录 working_directory 的命令被跳过
# 设计：&& 串联命令无法安全转 argv；执行器固定在工作区根执行，子目录命令不可表达
def test_profile_skips_shell_syntax_and_subdirectory_commands(tmp_path: Path) -> None:
    profile = _profile(
        _vc(ValidationCategory.UNIT_TEST, "cmake -S . -B build && cmake --build build"),
        _vc(ValidationCategory.UNIT_TEST, "uv run pytest", working_directory="packages/api"),
        _vc(ValidationCategory.UNIT_TEST, "uv run pytest"),
    )
    conditions = select_relevant_checks(profile)
    assert len(conditions) == 1
    # id 序号按类别内出现顺序计数，前两条被跳过不占号后仍保持稳定
    assert conditions[0].id == "profile-unit-test-1"
    assert conditions[0].check_command == ["uv", "run", "pytest"]


# 功能：相同 argv 去重（只保留首条）与 priority 降序稳定排序
# 设计：user 来源写两条相同命令 + 不同 priority 的第三条，断言去重与排序结果
def test_dedup_and_priority_sort(tmp_path: Path) -> None:
    _write_checks(
        tmp_path,
        """
[[check]]
id = "a"
command = ["uv", "run", "pytest"]

[[check]]
id = "duplicate"
command = ["uv", "run", "pytest"]

[[check]]
id = "b"
command = ["ruff", "check", "."]
priority = 10
""",
    )
    contract = build_completion_contract("run-1", None, tmp_path)
    assert contract is not None
    assert [cond.id for cond in contract.conditions] == ["b", "a"]


# 功能：两来源皆空时返回 None（门禁自然不触发）
# 设计：覆盖三种空场景——无文件且 profile=None、profile 仅含跳过类别、
# checks.toml 合法但条目为空（回落 profile 后仍为空）
def test_empty_sources_return_none(tmp_path: Path) -> None:
    assert build_completion_contract("run-1", None, tmp_path) is None

    skipped_only = _profile(
        _vc(ValidationCategory.BUILD, "uv build"),
        _vc(ValidationCategory.INTEGRATION_TEST, "uv run pytest tests/integration"),
    )
    assert build_completion_contract("run-1", skipped_only, tmp_path) is None

    _write_checks(tmp_path, "# 没有任何 [[check]] 条目\n")
    assert build_completion_contract("run-1", None, tmp_path) is None


# 功能：checks.toml 合法但条目为空时回落 profile 来源
# 设计：空文件不视为"用户显式声明无检查"，保守回落项目画像
def test_empty_checks_file_falls_back_to_profile(tmp_path: Path) -> None:
    _write_checks(tmp_path, "")
    profile = _profile(_vc(ValidationCategory.UNIT_TEST, "uv run pytest"))
    contract = build_completion_contract("run-1", profile, tmp_path)
    assert contract is not None
    [cond] = contract.conditions
    assert cond.source is ContractSource.PROJECT_CONFIG


# 功能：多组件 monorepo 画像中各组件的根目录命令均被收集且 id 序号跨组件连续
# 设计：两个组件各带一条根目录 UNIT_TEST 命令，断言 id 稳定递增、无冲突
def test_profile_multiple_components_stable_ids(tmp_path: Path) -> None:
    profile = ProjectProfile(
        monorepo=True,
        projects=[
            ProjectComponent(
                path=".",
                validation_plan=[_vc(ValidationCategory.UNIT_TEST, "uv run pytest")],
            ),
            ProjectComponent(
                path="tools",
                validation_plan=[_vc(ValidationCategory.UNIT_TEST, "npm test")],
            ),
        ],
    )
    conditions = select_relevant_checks(profile)
    assert [cond.id for cond in conditions] == ["profile-unit-test-1", "profile-unit-test-2"]
    assert conditions[1].check_command == ["npm", "test"]
