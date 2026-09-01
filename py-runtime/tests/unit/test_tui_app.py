from __future__ import annotations

import asyncio
from pathlib import Path

from rich.markdown import Markdown
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from sztu_code.tui.app import (
    _MAX_LOG_CHILDREN,
    SztuTuiApp,
    LLMStreamBlock,
    PermissionBlock,
    PermissionSelect,
    RunBlock,
    ToolCallBlock,
    _BgRun,
    _param_summary,
    _preview,
)


# 功能：验证 _preview 超出长度时截断并追加省略号
# 设计：不依赖任何 TUI 组件，纯函数测试
def test_preview_truncates() -> None:
    assert _preview("abcde", 3) == "abc…"
    assert _preview("ab", 5) == "ab"


# 功能：验证工具参数摘要优先展示工具最关键字段
# 设计：覆盖 read_file/bash/note_save 三类常见工具，避免工具块摘要退化成整段 JSON
def test_param_summary_prefers_key_fields() -> None:
    assert _param_summary("read_file", {"path": "README.md"}) == "path='README.md'"
    assert _param_summary("bash", {"command": "echo hi", "timeout": 1}) == "command='echo hi'"
    assert _param_summary("note_save", {"content": "Python 3.12"}) == "content='Python 3.12'"


def test_tui_banner_keeps_the_large_sztucode_wordmark() -> None:
    assert "███████╗" in SztuTuiApp._BANNER
    assert "输入消息开始对话" in SztuTuiApp._BANNER


async def test_tui_mounts_workbench_layout_without_banner(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp(
        "127.0.0.1", 9999, project_path=str(tmp_path / "proj"), trust=True,
    )
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.query_one("#header")
        assert app.query_one("#transcript-label")
        assert app.query_one("#composer-label")
        assert app.query_one("#prompt")
        assert app.query_one("#composer-spacer")
        assert app.query_one("#status")
        assert app.query_one("#footer")
        assert not app.query("#banner")
        assert "SztuCode" in str(app.query_one("#header").render())
        assert app.query_one("#prompt").region.y < app.query_one("#status").region.y


def test_tui_uses_the_launch_directory_as_the_initial_project_path() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    assert app._project_path


def test_welcome_card_matches_sztucode_model_switcher_style() -> None:
    app = SztuTuiApp("127.0.0.1", 9999, project_path="/tmp/example")
    rendered = app._welcome_text()

    assert "SztuCode" in rendered
    assert "model:" in rendered
    assert "/model" in rendered
    assert "to change" in rendered
    assert "directory:" in rendered


def test_model_command_is_available_in_slash_completion() -> None:
    names = {name for name, _description in SztuTuiApp("127.0.0.1", 9999)._builtin_slash_items()}
    assert "model" in names


def test_header_does_not_show_the_internal_conversation_id() -> None:
    class _Header:
        value = ""

        def update(self, value: str) -> None:
            self.value = value

    app = SztuTuiApp("127.0.0.1", 9999)
    app._session_id = "internal-session-id"
    header = _Header()
    app.query_one = lambda *_args, **_kwargs: header  # type: ignore[method-assign]

    app._update_header("ready")

    assert "internal-session-id" not in header.value


async def test_tab_cycles_only_the_three_visible_permission_modes() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    selected: list[str] = []

    async def record(mode: str) -> None:
        selected.append(mode)

    app._set_mode = record  # type: ignore[method-assign]
    await app.action_cycle_mode()

    assert app._mode == "auto"
    assert selected == ["accept_edits"]


# 功能：验证模式标签仅显示当前模式，三合一紧凑设计
# 设计：默认 auto 模式只显示 AUTO 富文本，不泄露其他两档；标签嵌入 header 栏不再单独占位
def test_mode_switcher_keeps_controls_near_the_composer() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)

    rendered = app._mode_label()

    # 单档：只显示当前模式
    assert "AUTO" in rendered
    assert "EDITS" not in rendered
    assert "PLAN" not in rendered
    # 富文本格式：有一段着色标签
    assert "on #" in rendered


async def test_mode_changes_do_not_append_timeline_status() -> None:
    class _Client:
        async def send_command(self, method: str, params: dict) -> dict:
            assert (method, params) == ("permission.set_mode", {"mode": "plan"})
            return {"ok": True}

    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._client = _Client()  # type: ignore[assignment]
    app._append = lambda widget: appended.append(widget)  # type: ignore[method-assign]
    app._update_header = lambda state: None  # type: ignore[method-assign]

    await app._set_mode("plan")

    assert app._mode == "plan"
    assert appended == []


async def test_provider_status_updates_the_current_model() -> None:
    class _Client:
        async def send_command(self, method: str, params: dict) -> dict:
            assert method == "provider.status"
            assert params == {}
            return {"model": "configured-model"}

    app = SztuTuiApp("127.0.0.1", 9999)
    app._client = _Client()  # type: ignore[assignment]
    app._update_header = lambda state: None  # type: ignore[method-assign]

    await app._refresh_model_status()

    assert app._model == "configured-model"


def test_permission_prompt_explains_the_action_and_keyboard_choices() -> None:
    block = PermissionBlock("tool-1", "bash", "command='git status'")
    selector = PermissionSelect("tool-1", "bash", "command='git status'")

    assert "Approval required" in block._pending_text()
    assert "Shell command" in block._pending_text()
    rendered = selector._render_ui()
    assert "Permission required" in rendered
    assert "Allow once" in rendered
    assert "Always allow this tool" in rendered
    assert "Y A N D direct" in rendered


# 功能：验证 llm.token 事件累积到 LLMStreamBlock，不连续 token 各自新开一块
# 设计：monkey-patch _append 收集追加的 widgets，断言 token 追加到同一块；
#       发送非 token 事件后新 block 被重置，下一个 token 开启新块
def test_llm_tokens_accumulate_in_block() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({"type": "llm.token", "token": "Hello", "run_id": "r", "ts": "t"})
    app._handle_event({"type": "llm.token", "token": " world", "run_id": "r", "ts": "t"})

    assert len(appended) == 1  # same block reused
    assert isinstance(appended[0], LLMStreamBlock)
    assert appended[0]._text == "Hello world"  # type: ignore[attr-defined]


# 功能：验证 LLMStreamBlock 结束时会把累积文本渲染为 Rich Markdown
# 设计：直接调用 finalize_markdown，断言 renderable 类型，覆盖 Markdown polish 的核心行为
def test_llm_block_finalize_renders_markdown() -> None:
    block = LLMStreamBlock()
    block.append_token("## Title\n\n- one\n\n```python\nprint('hi')\n```")
    block.finalize_markdown()
    assert isinstance(block.content, Markdown)


# 功能：验证非 token 事件后 _current_llm 被重置，下一个 token 开启新块
# 设计：插入 step.started 中断流，验证之前的 block 被 finalize，之后的 llm.token 创建新 LLMStreamBlock
def test_llm_block_resets_after_non_token_event() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({"type": "llm.token", "token": "A", "run_id": "r", "ts": "t"})
    app._handle_event({"type": "step.started", "run_id": "r", "step": 2, "ts": "t"})
    app._handle_event({"type": "llm.token", "token": "B", "run_id": "r", "ts": "t"})

    llm_blocks = [w for w in appended if isinstance(w, LLMStreamBlock)]
    assert len(llm_blocks) == 2
    assert llm_blocks[0]._finalized  # type: ignore[attr-defined]


# 功能：验证 run.started 创建单个 RunBlock 输出块并记录为活动块
# 设计：run_test 挂载真实 DOM，断言只有一个块且标题包含 run_id 与 goal
async def test_run_started_creates_run_block_with_content(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp("127.0.0.1", 9999, project_path=str(tmp_path / "proj"), trust=True)
    async with app.run_test() as pilot:
        app._handle_event({
            "type": "run.started", "run_id": "run-abc", "goal": "do the thing", "ts": "t"
        })
        await pilot.pause()
        blocks = app.query(RunBlock)
        assert len(blocks) == 1
        title = blocks[0].children[0].content
        assert "run-abc" in title
        assert "do the thing" in title
        assert app._run_block is blocks[0]  # type: ignore[attr-defined]


# 功能：验证 run.finished success 在活动块内追加 completed 并关闭块
# 设计：先 feed run.started 建块，再 feed run.finished，断言块末子项是完成状态
async def test_run_finished_success_shows_completed(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp("127.0.0.1", 9999, project_path=str(tmp_path / "proj"), trust=True)
    async with app.run_test() as pilot:
        app._handle_event({"type": "run.started", "run_id": "r", "goal": "g", "ts": "t"})
        await pilot.pause()  # 等待 RunBlock compose（标题）先挂载
        app._handle_event({
            "type": "run.finished", "run_id": "r", "status": "success", "steps": 3, "ts": "t"
        })
        await pilot.pause()
        blocks = app.query(RunBlock)
        assert len(blocks) == 1
        footer = blocks[0].children[-1].content
        assert "completed" in footer
        assert "green" in footer
        assert app._run_block is None  # type: ignore[attr-defined]


# 功能：验证 run.finished failed 在活动块内追加 failed 并关闭块
# 设计：与 success 对称，检查红色标记差异
async def test_run_finished_failed_shows_red(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp("127.0.0.1", 9999, project_path=str(tmp_path / "proj"), trust=True)
    async with app.run_test() as pilot:
        app._handle_event({"type": "run.started", "run_id": "r", "goal": "g", "ts": "t"})
        await pilot.pause()  # 等待 RunBlock compose（标题）先挂载
        app._handle_event({
            "type": "run.finished", "run_id": "r", "status": "failed",
            "steps": 1, "reason": "llm_error", "ts": "t"
        })
        await pilot.pause()
        blocks = app.query(RunBlock)
        assert len(blocks) == 1
        footer = blocks[0].children[-1].content
        assert "failed" in footer
        assert "red" in footer
        assert app._run_block is None  # type: ignore[attr-defined]


# 功能：验证 tool.call_started 追加 ToolCallBlock，call_finished 更新其结果
# 设计：直接调用 _handle_event 两次，通过 _pending_tool_blocks 验证状态流转
def test_tool_call_started_and_finished() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({
        "type": "tool.call_started",
        "tool_use_id": "uid-1",
        "tool_name": "bash",
        "params": {"command": "echo hi"},
        "run_id": "r", "ts": "t",
    })
    assert "uid-1" in app._pending_tool_blocks  # type: ignore[attr-defined]

    app._handle_event({
        "type": "tool.call_finished",
        "tool_use_id": "uid-1",
        "tool_name": "bash",
        "elapsed_ms": 42,
        "output": "hi",
        "run_id": "r", "ts": "t",
    })
    assert "uid-1" not in app._pending_tool_blocks  # type: ignore[attr-defined]
    block = appended[0]
    assert isinstance(block, ToolCallBlock)
    assert block._finished  # type: ignore[attr-defined]
    assert block._output == "hi"  # type: ignore[attr-defined]


# 功能：验证 note_save 成功完成时工具块摘要显示 remembered
# 设计：直接操作 ToolCallBlock，覆盖 note_save 的特殊低噪声展示策略
def test_note_save_tool_block_shows_remembered() -> None:
    block = ToolCallBlock("note_save", {"content": "Python 3.12"})
    block.set_result("saved", 3)
    assert "remembered" in block._summary()  # type: ignore[attr-defined]


# 功能：验证提交用户输入时会追加 user turn，并进入 busy 状态
# 设计：用 fake client 替代 SocketClient，直接调用 on_chat_text_area_submitted，
#       覆盖 TextArea 清空内容 + 设置 busy 占位符的核心状态迁移
async def test_input_submit_appends_user_turn_and_disables_prompt() -> None:
    class _FakeArea:
        def __init__(self) -> None:
            self.disabled = False
            self.border_title = ""
            self.text = "hello"

    class _FakeEvent:
        def __init__(self, area: _FakeArea) -> None:
            self.value = area.text
            self.text_area = area

    class _FakeClient:
        async def send_command(self, method: str, params: dict) -> dict:
            return {"run_id": "run-1"}

    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]
    app._update_header = lambda state: None  # type: ignore[method-assign]
    app._client = _FakeClient()  # type: ignore[assignment]
    app._session_id = "sess-1"

    area = _FakeArea()
    event = _FakeEvent(area)
    await app.on_chat_text_area_submitted(event)  # type: ignore[arg-type]

    assert app._busy  # type: ignore[attr-defined]
    assert area.disabled
    assert area.text == ""
    assert "agent is working" in area.border_title.lower()
    assert appended[0].content == "[bold]>[/bold] hello"


async def test_model_command_opens_model_settings() -> None:
    class _FakeArea:
        text = "/model"

    class _FakeEvent:
        value = "/model"
        text_area = _FakeArea()

    app = SztuTuiApp("127.0.0.1", 9999)
    opened: list[bool] = []
    app.action_open_model = lambda: opened.append(True)  # type: ignore[method-assign]

    await app.on_chat_text_area_submitted(_FakeEvent())  # type: ignore[arg-type]

    assert opened == [True]
    assert _FakeEvent.text_area.text == ""


# 功能：验证未知事件类型不抛异常也不追加任何 widget
# 设计：发送 type 为 unknown 的事件，断言 appended 为空
def test_unknown_event_silently_ignored() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._handle_event({"type": "some.unknown.type", "run_id": "r", "ts": "t"})
    assert appended == []


# 功能：验证日志视图子 widget 数被上限裁剪，且活动 run 块不受裁剪影响
# 设计：run_test 挂载真实 DOM，先追加超过上限的行断言 children 封顶；再启动 run 块并继续追加，
#       确认 run 块仍挂载且数量不超上限，覆盖裁剪与保护两条路径
async def test_log_view_caps_children_and_keeps_run_block(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp("127.0.0.1", 9999, project_path=str(tmp_path / "proj"), trust=True)
    async with app.run_test() as pilot:
        for i in range(800):
            app._append(Static(f"line {i}"))
        await pilot.pause()
        log_view = app.query_one("#log-view", VerticalScroll)
        assert len(log_view.children) == _MAX_LOG_CHILDREN
        app._handle_event({"type": "run.started", "run_id": "r1", "goal": "g", "ts": "t"})
        await pilot.pause()
        for i in range(700):
            app._append(Static(f"x {i}"))
        await pilot.pause()
        run_block = app.query_one(RunBlock)
        assert run_block.is_attached
        assert len(log_view.children) == _MAX_LOG_CHILDREN


# 功能：验证高频 token 被节流刷新：文本完整累积，但 update 调用数远小于 token 数
# 设计：挂载 LLMStreamBlock 并计数 update 调用，连续追加 200 个 token 后断言刷新次数受节流限制、
#       _text 仍完整累积，覆盖节流路径与定时器兜底；finalize 后内容为 Markdown
async def test_llm_stream_throttles_high_frequency_tokens(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp("127.0.0.1", 9999, project_path=str(tmp_path / "proj"), trust=True)
    async with app.run_test() as pilot:
        block = LLMStreamBlock()
        app._append(block)
        await pilot.pause()
        updates = 0
        original_update = block.update

        def counting(value: object) -> None:
            nonlocal updates
            updates += 1
            original_update(value)

        block.update = counting  # type: ignore[method-assign]
        for _ in range(200):
            block.append_token("tok ")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()
        assert updates < 200
        assert block._text == "tok " * 200  # type: ignore[attr-defined]
        block.finalize_markdown()
        assert isinstance(block.content, Markdown)


# 功能：验证终端尺寸变化时背景壁纸按新尺寸重新生成
# 设计：挂载真实 DOM 并 resize_terminal，断言壁纸行数与新高度一致，
#       覆盖 on_resize → _render_wallpaper(event.size) 的联动路径
async def test_wallpaper_regenerates_on_resize(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(SztuTuiApp, "_start_socket_loop", lambda self: None)
    app = SztuTuiApp(
        "127.0.0.1", 9999,
        project_path=str(tmp_path / "proj"), trust=True, wallpaper="ocean",
    )
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        rows = str(app.query_one("#wallpaper").render()).splitlines()
        assert len(rows) == 40


# 功能：验证技能斜杠命令由后台加载填充候选列表
# 设计：monkeypatch _build_slash_items 返回带技能的列表并直接 await _load_slash_items，
#       断言 _slash_items 被替换，避免依赖真实技能扫描和定时等待的不确定性
async def test_slash_items_load_async(monkeypatch) -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    monkeypatch.setattr(
        app,
        "_build_slash_items",
        lambda: app._builtin_slash_items() + [("my-skill", "desc")],
    )

    await app._load_slash_items()

    assert ("my-skill", "desc") in app._slash_items
    assert app._builtin_slash_items()[0] in app._slash_items


# 功能：验证第九章六个斜杠命令全部出现在 TUI 首帧自动补全中
# 设计：直接读取不依赖异步 Skill 扫描的内建候选，确保每个运行时命令都可被发现
def test_chapter_nine_slash_items_are_builtin() -> None:
    names = {name for name, _description in SztuTuiApp("127.0.0.1", 9999)._builtin_slash_items()}

    assert {
        "security-review",
        "batch",
        "review-pr",
        "pr-comments",
        "commit",
        "create-pr",
    } <= names


# 功能：验证 /theme 按序切换明暗主题并更新 Textual 主题与全局取色
# 设计：直接调用 _cycle_theme 两次，断言主题名与 textual theme 依次切换，
#       覆盖循环首尾衔接（light 之后回到 dark）；async 提供事件循环供 run_worker 调度
async def test_theme_cycle_toggles_dark_and_light() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    app._cycle_theme()
    assert app._theme_name == "light"
    assert app.theme == "sztu-light"
    app._cycle_theme()
    assert app._theme_name == "dark"
    assert app.theme == "sztu-dark"
    assert len(appended) == 2  # 每次切换追加一条日志


# 功能：验证 /wallpaper 循环完整一圈后回到初始样式
# 设计：调用 _cycle_wallpaper 共 4 次（与 WALLPAPER_ORDER 等长），断言回到 none，
#       且未挂载壁纸层时 _render_wallpaper 静默跳过不抛异常
async def test_wallpaper_cycle_returns_to_none() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]

    start = app._wallpaper_name
    for _ in range(4):
        app._cycle_wallpaper()
    assert app._wallpaper_name == start


# 功能：验证 /bg 通过 agent.run 在独立会话启动后台任务并登记 run_id
# 设计：注入 fake client 返回 run_id，直接 await _start_background_run，
#       断言 run_id 登记与目标记录，不依赖真实 daemon
async def test_bg_command_starts_background_run() -> None:
    class _FakeClient:
        async def send_command(self, method: str, params: dict) -> dict:
            assert method == "agent.run"
            assert params == {"goal": "summarize repo"}
            return {"run_id": "bg-42"}

    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]
    app._client = _FakeClient()  # type: ignore[assignment]

    await app._start_background_run("summarize repo")

    assert app._bg_run_ids == {"bg-42"}
    assert app._bg_runs["bg-42"].goal == "summarize repo"


# 功能：验证后台 run 事件按 run_id 路由到任务面板而非主日志 RunBlock
# 设计：预置后台 run_id，feed run.finished，断言状态与步数更新、
#       主 _run_block 保持 None（未被 run 事件创建）
def test_bg_events_route_to_bg_panel_not_main_log() -> None:
    app = SztuTuiApp("127.0.0.1", 9999)
    appended: list[Widget] = []
    app._append = lambda w: appended.append(w)  # type: ignore[method-assign]
    app._bg_run_ids = {"bg-1"}
    app._bg_runs["bg-1"] = _BgRun("bg-1", "do it")

    app._handle_event({
        "type": "run.finished", "run_id": "bg-1", "status": "success",
        "steps": 3, "reason": "", "ts": "t",
    })

    assert app._bg_runs["bg-1"].status == "success"
    assert app._bg_runs["bg-1"].steps == 3
    assert app._bg_runs["bg-1"].finished_at is not None
    assert app._run_block is None  # 后台任务不创建主日志 RunBlock


# 功能：验证状态栏文本包含会话用量、后台任务数与主题名
# 设计：注入 fake #status widget 并设置 token 与后台任务状态，
#       断言关键片段存在，覆盖状态栏的信息聚合
def test_status_bar_renders_session_and_bg_info() -> None:
    class _Status:
        value = ""

        def update(self, value: str) -> None:
            self.value = value

    app = SztuTuiApp("127.0.0.1", 9999)
    status = _Status()
    app.query_one = lambda *_args, **_kwargs: status  # type: ignore[method-assign]
    app._session_tokens = {"in": 1200, "out": 340, "cache_read": 0, "cache_write": 0}
    app._state = "ready"
    app._bg_runs = {"bg-1": _BgRun("bg-1", "g")}

    app._update_status()

    assert "in=1.2K" in status.value
    assert "out=340" in status.value
    assert "bg 1/1" in status.value
    assert "theme" in status.value


# 功能：验证鼠标点击补全项选中对应条目并发布 Selected（Static 默认不响应点击）
# 设计：挂载 SlashCompleteWidget 后直接调用 on_click 模拟点击第二行，
#       断言宿主 App 收到对应 skill 名，覆盖行号换算与消息路由
async def test_slash_widget_click_selects_item() -> None:
    from textual.app import App as TextualApp
    from textual.app import ComposeResult

    from sztu_code.tui.app import SlashCompleteWidget

    class _Click:
        y = 1

        def stop(self) -> None:
            pass

    class _Host(TextualApp[None]):
        def __init__(self) -> None:
            super().__init__()
            self.selected: list[str] = []

        def compose(self) -> ComposeResult:
            yield SlashCompleteWidget([
                ("settings", "open settings dialog"),
                ("theme", "switch theme"),
            ])

        def on_slash_complete_widget_selected(self, event: SlashCompleteWidget.Selected) -> None:
            self.selected.append(event.skill_name)

    host = _Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        popup = host.query_one(SlashCompleteWidget)
        popup.on_click(_Click())  # type: ignore[arg-type]
        await pilot.pause()
        assert host.selected == ["theme"]



# 功能：验证斜杠补全弹窗按每页 10 条分页，页数按总数向上取整
# 设计：构造 25 个候选项，断言页数与各页条数，覆盖最后一页不满一页的情况
def test_slash_widget_paginates_into_fixed_pages() -> None:
    from sztu_code.tui.app import SlashCompleteWidget

    popup = SlashCompleteWidget([(f"cmd{i}", f"desc {i}") for i in range(25)])

    assert popup._page_count() == 3
    assert popup._page_items() == 10  # 第 1 页满页
    popup._page = 1
    assert popup._page_start() == 10
    popup._page = 2
    assert popup._page_items() == 5  # 最后一页不满一页


# 功能：验证光标跨页导航：页尾下翻进入下一页首项，页首上翻回到上一页末项
# 设计：move_down 10 次到达页尾再下翻，断言页码与页内光标；再 move_up 回到上一页末项
def test_slash_widget_navigation_crosses_pages() -> None:
    from sztu_code.tui.app import SlashCompleteWidget

    popup = SlashCompleteWidget([(f"cmd{i}", "") for i in range(25)])
    selected: list[str] = []
    popup.post_message = lambda m: selected.append(m.skill_name)  # type: ignore[method-assign]

    for _ in range(9):
        popup.move_down()
    assert (popup._page, popup._cursor) == (0, 9)

    popup.move_down()  # 第 1 页末尾 → 第 2 页首项
    assert (popup._page, popup._cursor) == (1, 0)
    popup.select_current()
    assert selected == ["cmd10"]

    popup.move_up()  # 第 2 页页首 → 第 1 页末项
    assert (popup._page, popup._cursor) == (0, 9)


# 功能：验证 PgUp/PgDn 直接翻页，光标保持在页内对应位置并在末页钳制
# 设计：page_down 进入第 2 页，再进入第 3 页（仅 5 项）验证光标钳制，page_up 回退
def test_slash_widget_pgup_pgdn_switch_pages() -> None:
    from sztu_code.tui.app import SlashCompleteWidget

    popup = SlashCompleteWidget([(f"cmd{i}", "") for i in range(25)])
    popup._cursor = 7

    popup.page_down()
    assert (popup._page, popup._cursor) == (1, 7)
    popup.page_down()
    assert (popup._page, popup._cursor) == (2, 4)  # 末页仅 5 项，光标钳制
    popup.page_up()
    assert (popup._page, popup._cursor) == (1, 4)


# 功能：验证筛选后回到第 1 页，避免旧页码越界
# 设计：先翻到第 2 页再 set_query 过滤，断言页码归零且筛选生效
def test_slash_widget_query_resets_page() -> None:
    from sztu_code.tui.app import SlashCompleteWidget

    popup = SlashCompleteWidget([(f"cmd{i}", "") for i in range(25)])
    popup._page = 1

    popup.set_query("cmd2")

    assert popup._page == 0
    assert all(name.startswith("cmd2") for name, _ in popup._filtered)


# 功能：验证非首页点击换算：页内行号叠加页偏移选中完整列表对应项
# 设计：翻到第 2 页后模拟点击第 3 行，断言选中全局第 13 项
async def test_slash_widget_click_maps_page_offset() -> None:
    from textual.app import App as TextualApp
    from textual.app import ComposeResult

    from sztu_code.tui.app import SlashCompleteWidget

    class _Click:
        y = 2

        def stop(self) -> None:
            pass

    class _Host(TextualApp[None]):
        def __init__(self) -> None:
            super().__init__()
            self.selected: list[str] = []

        def compose(self) -> ComposeResult:
            yield SlashCompleteWidget([(f"cmd{i}", f"desc {i}") for i in range(25)])

        def on_slash_complete_widget_selected(self, event: SlashCompleteWidget.Selected) -> None:
            self.selected.append(event.skill_name)

    host = _Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        popup = host.query_one(SlashCompleteWidget)
        popup._page = 1
        popup._redraw()
        popup.on_click(_Click())  # type: ignore[arg-type]
        await pilot.pause()
        assert host.selected == ["cmd12"]  # 10 + 2
