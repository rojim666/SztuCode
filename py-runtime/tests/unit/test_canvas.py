from __future__ import annotations

from sztu_code.core.compact.canvas import CanvasNode, TaskCanvas

# ============================================================
# CanvasNode
# ============================================================


# 功能：验证 CanvasNode 正确渲染 Mermaid 节点行
# 设计：构造一个 done 状态节点，检查输出含 node_id、emoji、label
def test_canvas_node_to_mermaid() -> None:
    node = CanvasNode(
        node_id="step_01",
        label="搜索认证代码",
        status="done",
        tool_names=["grep", "read_file"],
        summary="找到 12 个相关文件",
    )
    mermaid = node.to_mermaid_node()
    assert 'step_01["✅ 搜索认证代码"]' in mermaid
    assert mermaid.startswith("    ")


# 功能：验证 failed 状态节点渲染 ❌ emoji
def test_canvas_node_failed_status() -> None:
    node = CanvasNode(node_id="step_03", label="运行测试", status="failed")
    assert "❌" in node.to_mermaid_node()


# 功能：验证 running 状态节点渲染 🔵 emoji
def test_canvas_node_running_status() -> None:
    node = CanvasNode(node_id="step_02", label="读取源码", status="running")
    assert "🔵" in node.to_mermaid_node()


# 功能：验证 pending 状态节点渲染 ⏳ emoji
def test_canvas_node_pending_status() -> None:
    node = CanvasNode(node_id="step_04", label="修复 bug", status="pending")
    assert "⏳" in node.to_mermaid_node()


# 功能：验证 to_summary_line 包含 emoji、摘要和工具名
def test_canvas_node_to_summary_line() -> None:
    node = CanvasNode(
        node_id="step_05",
        label="修复 auth.py",
        status="done",
        tool_names=["edit_file", "bash"],
        summary="修复了 token 刷新逻辑",
    )
    line = node.to_summary_line()
    assert "✅" in line
    assert "step_05" in line
    assert "token 刷新逻辑" in line
    assert "edit_file" in line


# ============================================================
# TaskCanvas
# ============================================================


# 功能：验证空画布渲染提示信息
def test_empty_canvas_renders_placeholder() -> None:
    canvas = TaskCanvas()
    result = canvas.render_mermaid()
    assert "为空" in result or "empty" in result.lower()


# 功能：验证 record_step 创建节点并递增计数
def test_record_step_creates_node() -> None:
    canvas = TaskCanvas()
    node = canvas.record_step(label="分析项目", tool_names=["list_dir"])
    assert node.node_id == "step_01"
    assert canvas.node_count == 1


# 功能：验证多次 record_step 产生的节点 ID 递增
def test_multiple_steps_increment_ids() -> None:
    canvas = TaskCanvas()
    n1 = canvas.record_step(label="第一步")
    n2 = canvas.record_step(label="第二步")
    n3 = canvas.record_step(label="第三步")
    assert n1.node_id == "step_01"
    assert n2.node_id == "step_02"
    assert n3.node_id == "step_03"
    assert canvas.node_count == 3


# 功能：验证 record_tool_calls 自动生成标签和组合摘要
def test_record_tool_calls_generates_label() -> None:
    canvas = TaskCanvas()
    node = canvas.record_tool_calls(
        tool_names=["grep", "read_file", "bash"],
        summaries=["找到 5 个匹配", "读取了 app.py", "pytest 通过"],
        ref_paths=["refs/grep_001.md", "refs/read_001.md", "refs/bash_001.md"],
    )
    assert node.node_id == "step_01"
    assert node.status == "done"
    assert "grep" in node.label
    assert "read_file" in node.label
    assert len(node.tool_names) == 3
    assert len(node.refs) == 3


# 功能：验证超过 3 个工具时标签添加 "+N more" 后缀
def test_record_tool_calls_truncates_label() -> None:
    canvas = TaskCanvas()
    node = canvas.record_tool_calls(
        tool_names=["grep", "read_file", "list_dir", "bash", "glob"],
        summaries=[""] * 5,
        ref_paths=[],
    )
    assert "+2 more" in node.label
    assert len(node.tool_names) == 5


# 功能：验证 render_mermaid 生成合法的 Mermaid flowchart
def test_render_mermaid_produces_valid_flowchart() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="第一步", tool_names=["grep"], status="done")
    canvas.record_step(label="第二步", tool_names=["read_file"], status="done")
    canvas.record_step(label="第三步", tool_names=["edit_file"], status="running")

    output = canvas.render_mermaid()
    assert "```mermaid" in output
    assert "graph TD" in output
    assert '["✅ 第一步"]' in output
    assert '["✅ 第二步"]' in output
    assert '["🔵 第三步"]' in output
    assert "step_01 --> step_02" in output
    assert "step_02 --> step_03" in output
    assert output.endswith("```")


# 功能：验证超过 max_visible 节点时折叠旧节点并显示计数
def test_render_mermaid_folds_old_nodes() -> None:
    canvas = TaskCanvas(max_visible_nodes=3)
    for i in range(5):
        canvas.record_step(label=f"Step {i}", status="done")

    output = canvas.render_mermaid()
    # 应只显示最后 3 个节点
    assert "step_03" in output
    assert "step_04" in output
    assert "step_05" in output
    assert "step_01" not in output
    assert "step_02" not in output
    # 应有折叠提示
    assert "2" in output  # "2 个更早的步骤"


# 功能：验证 recent_summary 只返回最近 N 个 done 状态的节点
def test_recent_summary_only_done_nodes() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="A", status="done", summary="完成了 A")
    canvas.record_step(label="B", status="running", summary="正在做 B")
    canvas.record_step(label="C", status="done", summary="完成了 C")

    summary = canvas.recent_summary(n=3)
    assert "完成了 A" in summary
    assert "完成了 C" in summary
    assert "正在做 B" not in summary  # running 节点不在摘要中


# 功能：验证 stats 正确统计各状态节点数量
def test_stats_counts_statuses() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="A", status="done")
    canvas.record_step(label="B", status="done")
    canvas.record_step(label="C", status="running")
    canvas.record_step(label="D", status="failed")

    s = canvas.stats()
    assert s.get("done") == 2
    assert s.get("running") == 1
    assert s.get("failed") == 1


# 功能：验证 active_nodes 只返回 running 状态的节点
def test_active_nodes_returns_running() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="A", status="done")
    canvas.record_step(label="B", status="running")
    canvas.record_step(label="C", status="running")

    active = canvas.active_nodes
    assert len(active) == 2
    assert all(n.status == "running" for n in active)


# 功能：验证 export 导出的数据可序列化
def test_export_returns_serializable_data() -> None:
    canvas = TaskCanvas()
    canvas.record_step(
        label="导出测试",
        tool_names=["bash"],
        summary="完成",
        refs=["refs/test.md"],
    )
    data = canvas.export()
    assert len(data) == 1
    assert data[0]["node_id"] == "step_01"
    assert data[0]["tool_names"] == ["bash"]
    assert data[0]["refs"] == ["refs/test.md"]


# 功能：验证 nodes 属性返回副本，修改对外部无影响
def test_nodes_returns_copy() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="A")
    nodes = canvas.nodes
    nodes.append(CanvasNode(node_id="x", label="y", status="done"))
    assert canvas.node_count == 1  # 外部修改不影响内部


# ============================================================
# 与 context 集成
# ============================================================


# 功能：验证动态画布不再改变 system prompt，而是作为消息尾部的紧凑增量
# 设计：先记录画布节点，再比较注入前后 system prompt 并检查末尾状态消息
def test_canvas_update_keeps_system_prompt_stable() -> None:
    from sztu_code.core.context import ExecutionContext

    canvas = TaskCanvas()
    canvas.record_step(label="测试步骤", tool_names=["bash"], status="done")

    ctx = ExecutionContext(
        run_id="r1",
        goal="test canvas injection",
        max_steps=5,
        canvas=canvas,
    )
    before = ctx.system_prompt("You are a helpful assistant.")
    ctx.add_canvas_update()
    after = ctx.system_prompt("You are a helpful assistant.")
    assert before == after
    assert "## Task Canvas" not in after
    assert "测试步骤" in ctx.messages[-1]["content"][0]["text"]


# 功能：验证 system_prompt 在无 canvas 时不包含画布段
def test_system_prompt_without_canvas() -> None:
    from sztu_code.core.context import ExecutionContext

    ctx = ExecutionContext(
        run_id="r1",
        goal="test without canvas",
        max_steps=5,
    )
    prompt = ctx.system_prompt("You are a helpful assistant.")
    assert "## Task Canvas" not in prompt


# ============================================================
# 标签中双引号转义
# ============================================================


# 功能：验证节点标签中的双引号被转义，避免破坏 Mermaid 语法
def test_node_label_escapes_quotes() -> None:
    node = CanvasNode(
        node_id="step_01",
        label='修复 "login" 函数',
        status="done",
    )
    mermaid = node.to_mermaid_node()
    assert "'" in mermaid  # 双引号被替换为单引号
    assert '"' not in mermaid.split('["', 1)[1].split('"]')[0]


# ============================================================
# Mermaid 特殊字符转义（Bug 修复回归测试）
# ============================================================


# 功能：验证圆括号被转为全角，避免破坏 Mermaid 节点语法
def test_sanitize_parentheses_in_label() -> None:
    node = CanvasNode(node_id="step_01", label="修复 bug (auth.py)", status="done")
    mermaid = node.to_mermaid_node()
    assert "（" in mermaid
    assert "(" not in mermaid.split('["', 1)[1]


# 功能：验证方括号被转为全角
def test_sanitize_square_brackets_in_label() -> None:
    node = CanvasNode(node_id="step_01", label="读取 config[key]", status="done")
    mermaid = node.to_mermaid_node()
    assert "【" in mermaid


# 功能：验证花括号被转为全角
def test_sanitize_curly_braces_in_label() -> None:
    node = CanvasNode(node_id="step_01", label="format {name}", status="done")
    mermaid = node.to_mermaid_node()
    assert "｛" in mermaid


# 功能：验证尖括号被转为全角
def test_sanitize_angle_brackets_in_label() -> None:
    node = CanvasNode(node_id="step_01", label="import <module>", status="done")
    mermaid = node.to_mermaid_node()
    assert "＜" in mermaid


# 功能：验证 & 被转为全角
def test_sanitize_ampersand_in_label() -> None:
    node = CanvasNode(node_id="step_01", label="build & deploy", status="done")
    mermaid = node.to_mermaid_node()
    assert "＆" in mermaid


# 功能：验证标签中的换行符被剥离
def test_label_with_newlines_stripped() -> None:
    node = CanvasNode(node_id="step_01", label="第一行\n第二行\n第三行", status="done")
    mermaid = node.to_mermaid_node()
    assert "\n" not in mermaid.split('["', 1)[1].split('"]')[0]


# 功能：验证超长标签被截断
def test_label_truncated_to_max_len() -> None:
    long_label = "A" * 100
    node = CanvasNode(node_id="step_01", label=long_label, status="done")
    mermaid = node.to_mermaid_node()
    # 标签应被截断到 ≤ 80 字符（+ ...）
    label_part = mermaid.split('["', 1)[1].split('"]')[0]
    assert len(label_part) <= 85  # emoji + space + truncated label


# 功能：验证画布在仅有 running 节点时 recent_summary 不返回 running 节点
def test_recent_summary_excludes_running() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="A", status="running")
    canvas.record_step(label="B", status="running")
    assert canvas.recent_summary() == ""


# 功能：验证 finalize_last 方法正确更新标签、状态、摘要和 refs
def test_finalize_last_updates_all_fields() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="初始标签", tool_names=["bash"], status="running")
    canvas.finalize_last(
        label="执行测试",
        status="done",
        summary="42 passed, 3 failed",
        refs=["refs/bash_001.md", "refs/grep_001.md"],
    )
    node = canvas.nodes[0]
    assert node.label == "执行测试"
    assert node.status == "done"
    assert "42 passed" in node.summary
    assert len(node.refs) == 2
    assert node.ts_end != ""


# 功能：验证 finalize_last 在空画布时不抛异常
def test_finalize_last_on_empty_canvas() -> None:
    canvas = TaskCanvas()
    canvas.finalize_last(label="不会崩溃", status="done")
    assert canvas.node_count == 0


# 功能：验证 finalize_last 传入空标签时不覆盖现有标签
def test_finalize_last_empty_label_preserves_existing() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="保留此标签", status="running")
    canvas.finalize_last(label="", status="done")
    assert "保留此标签" in canvas.nodes[0].label


# ============================================================
# 大规模画布测试
# ============================================================


# 功能：验证大量节点不会导致渲染崩溃
# 设计：创建 200 个节点，只渲染最后 20 个
def test_large_canvas_does_not_crash() -> None:
    canvas = TaskCanvas(max_visible_nodes=20)
    for i in range(200):
        canvas.record_step(label=f"Step {i}", status="done")
    output = canvas.render_mermaid()
    assert "```mermaid" in output
    assert "180 个更早的步骤已折叠" in output
    # 只有最后 20 个节点可见
    assert "step_181" in output
    assert "step_001" not in output


# 功能：验证画布统计在大规模场景下仍正确
def test_large_canvas_stats() -> None:
    canvas = TaskCanvas()
    for i in range(50):
        status = "done" if i % 2 == 0 else "failed"
        canvas.record_step(label=f"Step {i}", status=status)
    s = canvas.stats()
    assert s["done"] == 25
    assert s["failed"] == 25


# 功能：验证节点计数准确性
def test_node_count_accuracy() -> None:
    canvas = TaskCanvas()
    assert canvas.node_count == 0
    canvas.record_step(label="A")
    canvas.record_step(label="B")
    assert canvas.node_count == 2
    canvas.record_step(label="C")
    assert canvas.node_count == 3


# ============================================================
# 端到端场景模拟
# ============================================================


# 功能：模拟完整 coding agent 场景 — 搜索→阅读→修改→测试
# 设计：按典型顺序创建节点，验证 Mermaid 输出包含完整执行图
def test_end_to_end_coding_scenario() -> None:
    canvas = TaskCanvas()
    # Step 1: 搜索
    canvas.record_step(
        label="搜索认证相关代码",
        tool_names=["grep"],
        summary="找到 12 个匹配文件",
        refs=["refs/grep_001.md"],
    )
    # Step 2: 阅读
    canvas.finalize_last(label="", status="done")
    canvas.record_step(
        label="读取 auth.py 源码",
        tool_names=["read_file"],
        summary="312 行，包含 login/logout/refresh 函数",
        refs=["refs/read_file_001.md"],
    )
    # Step 3: 修改
    canvas.finalize_last(label="", status="done")
    canvas.record_step(
        label="修复 token 刷新逻辑",
        tool_names=["edit_file"],
        summary="修改了 refresh_token 函数",
        refs=[],
    )
    # Step 4: 测试
    canvas.finalize_last(label="", status="done")
    canvas.record_step(
        label="运行测试验证",
        tool_names=["bash"],
        summary="45 passed, 0 failed",
        status="done",
        refs=["refs/bash_001.md"],
    )

    output = canvas.render_mermaid()
    assert "搜索认证" in output
    assert "读取 auth" in output
    assert "修复 token" in output
    assert "运行测试" in output
    assert "step_01 --> step_02" in output
    assert "step_02 --> step_03" in output
    assert "step_03 --> step_04" in output


# ============================================================
# 空标签边缘情况
# ============================================================


# 功能：验证空标签节点渲染不崩溃
def test_empty_label_node_renders() -> None:
    canvas = TaskCanvas()
    canvas.record_step(label="", tool_names=["bash"])
    output = canvas.render_mermaid()
    assert "```mermaid" in output


# 功能：验证 record_tool_calls 仍正确工作（保留兼容性）
def test_record_tool_calls_still_works() -> None:
    canvas = TaskCanvas()
    node = canvas.record_tool_calls(
        tool_names=["grep", "read_file"],
        summaries=["找到结果", "读取完成"],
        ref_paths=["refs/grep_001.md"],
    )
    assert node.status == "done"
    assert node.node_id == "step_01"
    assert len(node.tool_names) == 2


# ============================================================
# Recuris 五元组结构化轨迹（AC-1）
# ============================================================


# 功能：验证 record_step 记录五元组字段（state/skill/action/observation/verified）
# 设计：五元组是失败定位的证据基础，每个画布节点都应携带
def test_record_step_with_five_element_fields() -> None:
    canvas = TaskCanvas()
    node = canvas.record_step(
        label="运行认证测试",
        tool_names=["bash"],
        state="已修复 refresh_token，待验证",
        action="pytest tests/unit/test_auth.py -q",
        observation="42 passed, 1 failed",
        verified="failed",
    )
    assert node.state == "已修复 refresh_token，待验证"
    assert node.skill == "bash"
    assert node.action == "pytest tests/unit/test_auth.py -q"
    assert node.observation == "42 passed, 1 failed"
    assert node.verified == "failed"


# 功能：验证 skill 未显式传入时从 tool_names 派生
# 设计：多工具步骤的 skill 为分号连接的工具名，保证五元组始终完整
def test_skill_derived_from_tool_names() -> None:
    canvas = TaskCanvas()
    node = canvas.record_step(label="搜索并阅读", tool_names=["grep", "read_file"])
    assert node.skill == "grep; read_file"


# 功能：验证 verified 字段默认值为 unverified
# 设计：无验证信号的步骤不能伪装成已验证，默认必须是 unverified
def test_verified_defaults_to_unverified() -> None:
    node = CanvasNode(node_id="step_01", label="普通步骤", status="done")
    assert node.verified == "unverified"


# 功能：验证 export 输出包含五元组全部字段（AC-1 字段存在性断言）
# 设计：结构化轨迹的持久化载体是 export，五元组字段必须全部出现
def test_export_contains_five_element_fields() -> None:
    canvas = TaskCanvas()
    canvas.record_step(
        label="运行测试",
        tool_names=["bash"],
        state="待验证",
        action="pytest",
        observation="3 passed",
        verified="verified",
    )
    data = canvas.export()
    for key in ("state", "skill", "action", "observation", "verified"):
        assert key in data[0]
    assert data[0]["state"] == "待验证"
    assert data[0]["skill"] == "bash"
    assert data[0]["observation"] == "3 passed"
    assert data[0]["verified"] == "verified"


# 功能：验证 finalize_last 可补齐步后才可知的 observation/verified
# 设计：state 在步前已知，observation/verified 在工具执行后才能确定
def test_finalize_last_completes_five_elements() -> None:
    canvas = TaskCanvas()
    canvas.record_step(
        label="运行测试",
        tool_names=["bash"],
        state="待验证",
        status="running",
    )
    canvas.finalize_last(
        status="failed",
        observation="1 failed: test_refresh_token",
        verified="failed",
    )
    node = canvas.nodes[0]
    assert node.observation == "1 failed: test_refresh_token"
    assert node.verified == "failed"
    assert node.state == "待验证"  # 步前状态不被事后信息覆盖


# 功能：验证 finalize_last 不传五元组参数时保留原值
# 设计：与 label 的语义一致，空值不覆盖已有内容
def test_finalize_last_preserves_five_elements_when_omitted() -> None:
    canvas = TaskCanvas()
    canvas.record_step(
        label="运行测试",
        tool_names=["bash"],
        state="待验证",
        action="pytest",
        observation="首次观察",
        verified="verified",
    )
    canvas.finalize_last(status="done", summary="完成了")
    node = canvas.nodes[0]
    assert node.state == "待验证"
    assert node.observation == "首次观察"
    assert node.verified == "verified"


# 功能：验证 record_tool_calls 将组合摘要同步为 observation
# 设计：便捷入口创建的节点也应携带完整五元组语义
def test_record_tool_calls_sets_observation() -> None:
    canvas = TaskCanvas()
    node = canvas.record_tool_calls(
        tool_names=["bash"],
        summaries=["42 passed"],
        ref_paths=["refs/bash_001.md"],
    )
    assert node.observation == "42 passed"
    assert node.verified == "unverified"


# 功能：验证五元组字段不影响既有 Mermaid 渲染
# 设计：新增字段是纯增量，渲染路径必须保持向后兼容
def test_five_elements_do_not_break_rendering() -> None:
    canvas = TaskCanvas()
    canvas.record_step(
        label="运行测试",
        tool_names=["bash"],
        state="待验证",
        action="pytest",
        observation="3 passed",
        verified="verified",
    )
    output = canvas.render_mermaid()
    assert '["✅ 运行测试"]' in output


# 功能：验证五元组 observation 缺省时可从 summary 推导展示
# 设计：to_summary_line 应展示验证状态，让失败定位时一眼可见 verified 结论
def test_summary_line_shows_verified_state() -> None:
    node = CanvasNode(
        node_id="step_02",
        label="运行测试",
        status="failed",
        tool_names=["bash"],
        verified="failed",
    )
    line = node.to_summary_line()
    assert "failed" in line
