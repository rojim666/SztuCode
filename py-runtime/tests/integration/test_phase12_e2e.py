"""
Phase 1+2 端到端集成测试

模拟一个真实的 coding agent 场景：
  搜索 → 阅读 → 修改 → 测试 → 完成

验证点:
  Phase 1: 卸载写入 refs/*.md + offload.jsonl + 占位符 + read_ref 回读
  Phase 2: 任务画布 Mermaid 节点 + system prompt 注入 + running→done 过渡
"""
from __future__ import annotations

import json
from pathlib import Path

from sztu_code.core.compact.canvas import TaskCanvas
from sztu_code.core.compact.offload import OffloadManager
from sztu_code.core.config import SztuConfig
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.runner import AgentRunner
from sztu_code.core.session.model import Session
from sztu_code.core.session.store import SessionStore

# ============================================================
# 场景模拟：Mock LLM 驱动一个 4 步 coding 任务
# ============================================================


class _CodingScenarioProvider:
    """模拟一个 4 步 coding agent 的 LLM 响应序列：
    Step 1: grep 搜索认证代码 → tool_use
    Step 2: read_file 读取源码 → tool_use
    Step 3: edit_file 修复 bug → tool_use
    Step 4: bash 运行测试 → tool_use
    Step 5: end_turn 报告完成
    """

    def __init__(self) -> None:
        self._step = 0

    # 模拟 LLM chat 调用，按步骤返回预设响应
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        self._step += 1

        if self._step == 1:
            # Step 1: 搜索认证相关代码
            return LlmResponse(
                stop_reason="tool_use",
                text="我来搜索认证相关的代码。",
                tool_calls=[
                    ToolCallBlock(
                        id="grep-1",
                        name="grep",
                        input={"pattern": "login|auth|token", "path": "."},
                    )
                ],
                usage=UsageStats(input_tokens=500, output_tokens=30),
            )

        elif self._step == 2:
            # Step 2: 读取找到的文件
            return LlmResponse(
                stop_reason="tool_use",
                text="找到了 auth.py，我来读取它的源码。",
                tool_calls=[
                    ToolCallBlock(
                        id="read-1",
                        name="read_file",
                        input={"path": "src/auth.py"},
                    )
                ],
                usage=UsageStats(input_tokens=800, output_tokens=30),
            )

        elif self._step == 3:
            # Step 3: 修复 bug
            return LlmResponse(
                stop_reason="tool_use",
                text="发现 token 刷新的问题，我来修复。",
                tool_calls=[
                    ToolCallBlock(
                        id="edit-1",
                        name="edit_file",
                        input={
                            "path": "src/auth.py",
                            "old_string": "token = old_token",
                            "new_string": "token = refresh_token()",
                        },
                    )
                ],
                usage=UsageStats(input_tokens=1200, output_tokens=30),
            )

        elif self._step == 4:
            # Step 4: 运行测试
            return LlmResponse(
                stop_reason="tool_use",
                text="修复完成，运行测试验证。",
                tool_calls=[
                    ToolCallBlock(
                        id="bash-1",
                        name="bash",
                        input={"command": "pytest tests/test_auth.py -v"},
                    )
                ],
                usage=UsageStats(input_tokens=1500, output_tokens=30),
            )

        else:
            # Step 5: 完成
            return LlmResponse(
                stop_reason="end_turn",
                text="Bug 修复完成！token 刷新逻辑已修正，所有测试通过。",
                usage=UsageStats(input_tokens=1800, output_tokens=50),
            )


def _make_config() -> SztuConfig:
    cfg = SztuConfig()
    cfg.agent.max_steps = 10
    cfg.compaction.auto_threshold = 0.0  # 不触发语义压缩，只测试卸载+画布
    cfg.offload.enabled = True
    cfg.offload.min_chars = 500  # 降低阈值以便触发卸载
    cfg.offload.force_tools = ["bash", "grep", "glob"]
    return cfg


# ============================================================
# 测试 1：完整场景端到端验证
# ============================================================


# 功能：验证 4 步 coding 场景中 Phase 1+2 全部机制正常工作
# 设计：用 mock provider 模拟搜索→阅读→修改→测试→完成，
#       检查卸载文件、占位符、画布节点、system prompt 注入
async def test_coding_scenario_phase1_offloading(tmp_path: Path) -> None:
    """Phase 1 验证：卸载文件 + 占位符 + read_ref 回读"""
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-e2e-1",
        mode="chat",
        status="active",
        title="E2E Test",
        created_at="2026-08-05T00:00:00Z",
        updated_at="2026-08-05T00:00:00Z",
    )
    store.write_meta(session)
    store.append_message("sess-e2e-1", "user", "修复 auth.py 的 token 刷新 bug")

    runner = AgentRunner(
        _make_config(),
        provider=_CodingScenarioProvider(),  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )
    outcome = await runner.run_and_capture(
        "修复 auth.py 的 token 刷新 bug",
        run_id="run-e2e-1",
        session=session,
        store=store,
    )

    # 验证任务完成
    assert outcome.status == "success"
    assert "Bug 修复完成" in outcome.result

    # --- Phase 1 验证：卸载 ---
    session_dir = store.session_dir("sess-e2e-1")
    refs_dir = session_dir / "refs"
    offload_index = session_dir / "offload" / "offload.jsonl"

    # grep 和 bash 是强制卸载工具，read_file 输出大也会触发卸载
    assert refs_dir.exists(), "refs/ 目录应存在"
    ref_files = list(refs_dir.glob("*.md"))
    assert len(ref_files) >= 2, f"至少 grep 和 bash 应触发卸载，实际: {len(ref_files)}"

    # offload.jsonl 应有索引记录
    assert offload_index.exists(), "offload.jsonl 应存在"
    index_lines = offload_index.read_text(encoding="utf-8").strip().splitlines()
    assert len(index_lines) >= 2, f"索引记录应 ≥ 2 条，实际: {len(index_lines)}"

    # 每条索引记录应有合法结构
    for line in index_lines:
        record = json.loads(line)
        assert "id" in record
        assert "ref_path" in record
        assert "tool_name" in record
        assert "summary" in record

    # --- 验证消息中包含占位符 ---
    messages = store.read_messages("sess-e2e-1")
    tool_result_messages = [
        msg for msg in messages
        if msg["role"] == "user" and isinstance(msg["content"], list)
    ]
    placeholder_count = 0
    for msg in tool_result_messages:
        for block in msg["content"]:
            if isinstance(block.get("content"), str) and "[上下文卸载:" in block["content"]:
                placeholder_count += 1
    assert placeholder_count >= 2, f"至少 2 个占位符，实际: {placeholder_count}"


# 功能：验证 Phase 2 任务画布在 system prompt 中正确注入
# 设计：检查 context.canvas 存在、画布有 4 个节点、system prompt 含 Mermaid
async def test_coding_scenario_phase2_canvas(tmp_path: Path) -> None:
    """Phase 2 验证：画布节点作为稳定 system 后的增量消息"""
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-e2e-2",
        mode="chat",
        status="active",
        title="Canvas Test",
        created_at="2026-08-05T00:00:00Z",
        updated_at="2026-08-05T00:00:00Z",
    )
    store.write_meta(session)
    store.append_message("sess-e2e-2", "user", "test canvas")

    # 注入一个自带 canvas 的 ExecutionContext 来验证
    canvas = TaskCanvas()
    canvas.record_step(
        label="搜索认证代码",
        tool_names=["grep"],
        summary="找到 12 个文件",
        refs=["refs/grep_001.md"],
    )
    canvas.record_step(
        label="读取 auth.py",
        tool_names=["read_file"],
        summary="312 行",
        refs=["refs/read_file_001.md"],
    )
    canvas.record_step(
        label="修复 token 刷新",
        tool_names=["edit_file"],
        summary="修改了 refresh_token 函数",
    )
    canvas.record_step(
        label="运行测试",
        tool_names=["bash"],
        status="done",
        summary="45 passed",
        refs=["refs/bash_001.md"],
    )

    ctx = ExecutionContext(
        run_id="run-canvas",
        goal="test canvas",
        max_steps=5,
        canvas=canvas,
    )
    before = ctx.system_prompt("You are a helpful assistant.")
    ctx.add_canvas_update()
    after = ctx.system_prompt("You are a helpful assistant.")

    # 动态画布不污染 system 前缀缓存，仅追加当前步骤的紧凑状态
    assert before == after
    assert "## Task Canvas" not in after
    update = ctx.messages[-1]["content"][0]["text"]
    assert "step_04" in update
    assert "运行测试" in update
    assert "45 passed" in update
    assert "done:4" in update


# 功能：验证画布 running→done 状态转换
# 设计：模拟标准 AgentLoop 流程——先 record_step(running) → 工具执行 → finalize_last(done)
def test_canvas_running_to_done_transition() -> None:
    """画布状态转换：running → done"""
    canvas = TaskCanvas()

    # 步骤开始：标记 running
    canvas.record_step(label="执行搜索", tool_names=["grep"], status="running")
    assert canvas.active_nodes[0].status == "running"

    # 工具执行完毕：finalize
    canvas.finalize_last(
        label="搜索完成",
        status="done",
        summary="找到 5 个文件",
        refs=["refs/grep_001.md"],
    )

    node = canvas.nodes[0]
    assert node.status == "done"
    assert node.ts_end != ""
    assert "5 个文件" in node.summary
    assert node.refs == ["refs/grep_001.md"]


# 功能：验证 error 工具结果将画布节点标记为 failed
def test_canvas_error_marks_failed() -> None:
    """画布状态转换：running → failed (error)"""
    canvas = TaskCanvas()
    canvas.record_step(label="运行测试", tool_names=["bash"], status="running")
    canvas.finalize_last(label="测试失败", status="failed", summary="3 tests failed")

    node = canvas.nodes[0]
    assert node.status == "failed"
    assert "3 tests failed" in node.summary


# ============================================================
# Phase 1+2 协同验证
# ============================================================


# 功能：验证卸载 ref_path 正确关联到画布节点
# 设计：创建 OffloadManager 和 TaskCanvas，卸载一条记录后检查画布节点引用
def test_offload_ref_linked_to_canvas_node(tmp_path: Path) -> None:
    """画布节点 refs 字段关联卸载文件"""
    mgr = OffloadManager(tmp_path)
    canvas = TaskCanvas()

    # 卸载一个 bash 结果
    record = mgr.offload("bash", "toolu_test", "test output\n" * 100, "run-test")

    # 画布节点引用该卸载文件
    canvas.record_step(
        label="运行测试",
        tool_names=["bash"],
        summary=record.summary,
        refs=[record.ref_path],
        status="done",
    )

    node = canvas.nodes[0]
    assert record.ref_path in node.refs

    # Agent 可以通过 read_ref 回读该文件
    restored = mgr.read_ref(record.ref_path)
    assert "test output" in restored


# ============================================================
# 大规模场景压力测试
# ============================================================


# 功能：验证 50 步 coding 任务中卸载+画布不崩溃且保持正确性
# 设计：循环创建 50 个卸载记录和画布节点，验证计数和渲染
def test_stress_50_steps(tmp_path: Path) -> None:
    """50 步大规模场景：卸载 + 画布"""
    mgr = OffloadManager(tmp_path)
    canvas = TaskCanvas(max_visible_nodes=20)

    for i in range(50):
        # 每步：卸载一个工具结果 + 画布记录
        tool_name = "bash" if i % 2 == 0 else "grep"
        record = mgr.offload(
            tool_name, f"tool_{i}", f"step {i} output\n" * 100, "run-stress",
        )
        canvas.record_step(
            label=f"Step {i}: {tool_name}",
            tool_names=[tool_name],
            summary=record.summary,
            refs=[record.ref_path],
            status="done",
        )

    # 验证
    assert canvas.node_count == 50
    assert len(mgr.list_by_run("run-stress")) == 50

    # 渲染不应崩溃
    mermaid = canvas.render_mermaid()
    assert "30 个更早的步骤已折叠" in mermaid

    # 统计正确
    s = canvas.stats()
    assert s["done"] == 50


# 功能：验证 read_ref 从画布节点 linkage 回读卸载内容
# 设计：走完整的 Phase 1→2 链路——offload → canvas refs → read_ref
def test_full_phase12_linkage(tmp_path: Path) -> None:
    """完整链路：卸载 → 画布引用 → 回读"""
    mgr = OffloadManager(tmp_path)
    canvas = TaskCanvas()

    # 模拟 3 步任务
    original_outputs = []
    for i, (tool, label) in enumerate([
        ("grep", "搜索认证代码"),
        ("read_file", "读取源码"),
        ("bash", "运行测试"),
    ]):
        original = f"{label} 的完整输出\n" * 200
        original_outputs.append(original)
        record = mgr.offload(tool, f"tool_{i}", original, "run-link")
        canvas.record_step(
            label=label,
            tool_names=[tool],
            summary=record.summary,
            refs=[record.ref_path],
            status="done",
        )

    # 验证链路：画布节点 → ref_path → read_ref → 完整原文
    for i, node in enumerate(canvas.nodes):
        ref_path = node.refs[0]
        restored = mgr.read_ref(ref_path)
        assert restored.rstrip() == original_outputs[i].rstrip(), (
            f"节点 {node.node_id} 的卸载内容不匹配"
        )

    # 验证 Mermaid 包含全部 3 个节点
    mermaid = canvas.render_mermaid()
    assert "搜索认证代码" in mermaid
    assert "读取源码" in mermaid
    assert "运行测试" in mermaid
