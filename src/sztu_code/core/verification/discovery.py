from __future__ import annotations

import logging
import re
import shlex
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sztu_code.core.verification.models import (
    CompletionCondition,
    CompletionContract,
    ContractSource,
)
from sztu_code.core.workspace.project_profile import ProjectProfile, ValidationCategory

logger = logging.getLogger(__name__)

# 用户声明的检查清单文件（相对工作区根）。格式：
# [[check]]
# id = "unit-tests"                                      # 可选，缺省生成 user-<n>
# description = "运行单元测试"                             # 可选，缺省用命令拼接
# command = ["uv", "run", "pytest", "tests/unit", "-q"]  # argv 数组，必填
# required = true                                        # 可选，默认 true
# priority = 0                                           # 可选，默认 0
CHECKS_FILE = Path(".sztu") / "checks.toml"

# 含 shell 语法的命令无法安全转为 argv（执行器以 create_subprocess_exec 直接执行，无 shell）
_SHELL_SYNTAX_RE = re.compile(r"[&|;<>`$\n]")

# 门禁类别策略：类别 → (required, priority)。未列出的类别不纳入契约。
# 规则详见 select_relevant_checks docstring。
_CATEGORY_POLICY: dict[ValidationCategory, tuple[bool, int]] = {
    ValidationCategory.STATIC_CHECK: (True, 20),
    ValidationCategory.UNIT_TEST: (True, 10),
    ValidationCategory.FORMAT: (False, 0),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


# 构建一次 run 的完成契约（issue #94 分支 3：检查发现与契约构建）
def build_completion_contract(
    run_id: str,
    profile: ProjectProfile | None,
    workspace_root: Path,
) -> CompletionContract | None:
    """按来源优先级构建完成契约；两个来源都为空时返回 None（门禁自然不触发）。

    来源优先级：
    1. 用户声明（source=USER）：workspace_root/.sztu/checks.toml 存在且解析出
       至少一条合法条件时独占生效，不再混入项目画像来源；
    2. 项目画像（source=PROJECT_CONFIG）：profile 的 validation_plan 经
       select_relevant_checks 过滤转换。profile 为 None（探测失败）时跳过。
    checks.toml 解析失败（TOML 语法错误或任一条目字段非法）记 warning 并整体
    忽略该文件、回落项目画像——坏配置不炸掉 run。最终条件按 argv 去重
    （相同命令只保留首条）并按 priority 降序稳定排序。
    """
    conditions = _load_user_checks(workspace_root)
    if not conditions and profile is not None:
        conditions = select_relevant_checks(profile)
    conditions = _dedup_and_sort(conditions)
    if not conditions:
        return None
    return CompletionContract(run_id=run_id, conditions=conditions, created_at=_now())


# 从项目画像的验证建议中筛选适合门禁的检查并转为完成条件
def select_relevant_checks(profile: ProjectProfile) -> list[CompletionCondition]:
    """类别过滤规则（保守、快速优先）：

    - STATIC_CHECK：required=True，priority=20（静态检查快，先跑先失败）；
    - UNIT_TEST：required=True，priority=10；
    - FORMAT：required=False，priority=0（格式偏差不应阻塞完成判定）；
    - INTEGRATION_TEST / BUILD：整体跳过——耗时长、常依赖外部环境或凭据，
      作为默认门禁过于激进；需要时用户可在 checks.toml 中显式声明。
    额外跳过（记 debug 日志）：
    - working_directory 不是工作区根（"." 以外）：执行器固定在根目录执行，
      无法安全表达子目录 cwd；
    - 命令含 shell 语法（& | ; < > ` $）或无法 shlex 拆分：无法安全转 argv。
    id 生成规则稳定：profile-<category>-<n>，n 为该类别内的出现序号。
    """
    conditions: list[CompletionCondition] = []
    counters: dict[ValidationCategory, int] = {}
    for component in profile.projects:
        for item in component.validation_plan:
            policy = _CATEGORY_POLICY.get(item.category)
            if policy is None:
                logger.debug(
                    "skipping non-gating category %s: %s", item.category.value, item.command
                )
                continue
            if item.working_directory not in ("", "."):
                logger.debug(
                    "skipping command outside workspace root (%s): %s",
                    item.working_directory,
                    item.command,
                )
                continue
            argv = _to_argv(item.command)
            if argv is None:
                logger.debug("skipping command not convertible to argv: %s", item.command)
                continue
            required, priority = policy
            counters[item.category] = counters.get(item.category, 0) + 1
            conditions.append(
                CompletionCondition(
                    id=(
                        f"profile-{item.category.value.replace('_', '-')}"
                        f"-{counters[item.category]}"
                    ),
                    description=item.reason or item.command,
                    source=ContractSource.PROJECT_CONFIG,
                    check_command=argv,
                    required=required,
                    priority=priority,
                )
            )
    return conditions


# 读取并解析用户声明的 checks.toml；文件缺失返回空列表，解析失败记 warning 并整体忽略
def _load_user_checks(workspace_root: Path) -> list[CompletionCondition]:
    path = workspace_root / CHECKS_FILE
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return _parse_user_checks(data)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as error:
        logger.warning("ignoring invalid checks file %s: %s", path, error)
        return []


# 将 checks.toml 数据转为条件列表；任一条目字段非法抛 ValueError（由调用方整体忽略）
def _parse_user_checks(data: dict[str, Any]) -> list[CompletionCondition]:
    entries = data.get("check", [])
    if not isinstance(entries, list):
        raise ValueError("[[check]] must be an array of tables")
    conditions: list[CompletionCondition] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"check #{index} must be a table")
        command = entry.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part for part in command)
        ):
            raise ValueError(f"check #{index}: command must be a non-empty array of strings")
        condition_id = entry.get("id", f"user-{index}")
        if not isinstance(condition_id, str) or not condition_id:
            raise ValueError(f"check #{index}: id must be a non-empty string")
        description = entry.get("description", " ".join(command))
        if not isinstance(description, str):
            raise ValueError(f"check #{index}: description must be a string")
        required = entry.get("required", True)
        if not isinstance(required, bool):
            raise ValueError(f"check #{index}: required must be a boolean")
        priority = entry.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError(f"check #{index}: priority must be an integer")
        conditions.append(
            CompletionCondition(
                id=condition_id,
                description=description,
                source=ContractSource.USER,
                check_command=list(command),
                required=required,
                priority=priority,
            )
        )
    return conditions


# 将命令字符串安全转为 argv；含 shell 语法或拆分失败返回 None
def _to_argv(command: str) -> list[str] | None:
    if _SHELL_SYNTAX_RE.search(command):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    return argv or None


# 按 argv 去重（保留首条）并按 priority 降序稳定排序
def _dedup_and_sort(conditions: list[CompletionCondition]) -> list[CompletionCondition]:
    unique: list[CompletionCondition] = []
    seen: set[tuple[str, ...]] = set()
    for cond in conditions:
        key = tuple(cond.check_command or ())
        if key in seen:
            continue
        seen.add(key)
        unique.append(cond)
    return sorted(unique, key=lambda cond: -cond.priority)
