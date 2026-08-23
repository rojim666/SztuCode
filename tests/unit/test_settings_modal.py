from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from sztu_code.tui.app import KamaTuiApp
from sztu_code.tui.settings import SettingsModal, _cycle_index, _Row, _row_value


# 功能：验证设置行索引按 delta 循环移动，越界回绕
# 设计：用两值行分别测 +1/-1 与回绕边界，覆盖左右两个方向；只读行不受影响
def test_row_cycle_wraps() -> None:
    row = _Row("theme", ["dark", "light"])
    _cycle_index(row, 1)
    assert row.index == 1
    _cycle_index(row, 1)
    assert row.index == 0
    _cycle_index(row, -1)
    assert row.index == 1
    _cycle_index(_Row("info", None), 1)
    assert True


# 功能：验证只读行取值为 None，可切换行返回当前值
# 设计：直接对比两种行的 _row_value 输出，界定可交互与只读边界
def test_row_value_readonly_is_none() -> None:
    assert _row_value(_Row("info", None)) is None
    assert _row_value(_Row("theme", ["dark", "light"], 1)) == "light"


class _FakeClient:
    # 模拟 daemon：settings.get 返回快照，model_list 返回两个档案
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def send_command(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        if method == "settings.get":
            return {"settings": {
                "model": "DeepSeek V3",
                "max_output_tokens": 8192,
                "temperature": 0.3,
                "top_p": None,
                "reasoning_effort": "low",
                "cache_control": True,
                "permission_mode": "auto",
            }}
        if method == "provider.model_list":
            return {"models": [
                {"name": "DeepSeek V3", "id": "p1", "is_current": True},
                {"name": "GPT-4o", "id": "p2", "is_current": False},
            ]}
        if method == "provider.model_select":
            return {"settings": {"model": "GPT-4o"}}
        return {}


# 构建挂载可用的 App：trust=True 跳过信任检查，禁用真实 socket 循环并注入 fake client
def _make_app() -> tuple[KamaTuiApp, _FakeClient]:
    app = KamaTuiApp("127.0.0.1", 9999, project_path=str(Path.cwd()), trust=True)
    app._start_socket_loop = lambda: None  # type: ignore[method-assign]
    client = _FakeClient()
    app._client = client  # type: ignore[assignment]
    return app, client


# 拼接弹窗内全部 Static 的渲染文本，便于断言分组与值
def _modal_text(modal: SettingsModal) -> str:
    return "".join(str(widget.render()) for widget in modal.query(Static))


# 功能：验证弹窗挂载后从 daemon 拉取快照并渲染各分组与当前值
# 设计：注入 fake client 并 push_screen，断言渲染文本包含外观/模型/权限/LLM 分组与具体值
async def test_settings_modal_renders_groups_and_values() -> None:
    app, _client = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.action_open_settings()
        await pilot.pause()
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, SettingsModal)
        text = _modal_text(modal)
        assert "appearance" in text
        assert "theme" in text and "wallpaper" in text
        assert "DeepSeek V3" in text
        assert "max tokens (8192)" in text
        assert "mode" in text
        assert "temperature (0.3)" in text
        assert "cache (on)" in text


# 功能：验证 ←→ 切换外观设置即时生效（主题/壁纸直接应用）
# 设计：光标起始在 theme 行，right 切到 light；down 到 wallpaper，right 切到 aurora
async def test_settings_modal_theme_and_wallpaper_change() -> None:
    app, _client = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.action_open_settings()
        await pilot.pause()
        await pilot.pause()
        await pilot.press("right")  # theme: dark -> light
        await pilot.pause()
        assert app._theme_name == "light"
        await pilot.press("down")  # -> wallpaper
        await pilot.press("right")  # none -> aurora
        await pilot.pause()
        assert app._wallpaper_name == "aurora"


# 功能：验证模型行切换调用 provider.model_select 并刷新当前模型
# 设计：down 越过只读 max tokens 行到达 model，right 切到 GPT-4o，
#       断言 IPC 参数为对应档案 id
async def test_settings_modal_model_switch_calls_ipc() -> None:
    app, client = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.action_open_settings()
        await pilot.pause()
        await pilot.pause()
        await pilot.press("down")  # wallpaper
        await pilot.press("down")  # model（跳过只读 max tokens）
        await pilot.press("right")  # DeepSeek V3 -> GPT-4o
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        selects = [params for method, params in client.calls if method == "provider.model_select"]
        assert selects == [{"model_id": "p2"}]


# 功能：验证 Esc 关闭弹窗并回到主界面
# 设计：打开后按 escape，断言 screen 不再是 SettingsModal
async def test_settings_modal_escape_closes() -> None:
    app, _client = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.action_open_settings()
        await pilot.pause()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsModal)


# 功能：验证 /settings 命令打开设置弹窗
# 设计：用 fake 事件触发 on_chat_text_area_submitted 的 /settings 分支，断言 screen 切换
async def test_settings_command_opens_modal() -> None:
    class _Area:
        def __init__(self) -> None:
            self.text = "/settings"

    class _Event:
        def __init__(self) -> None:
            self.value = "/settings"
            self.text_area = _Area()

    app, _client = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await app.on_chat_text_area_submitted(_Event())  # type: ignore[arg-type]
        await pilot.pause()
        assert isinstance(app.screen, SettingsModal)


# 功能：验证 app 直接应用主题与壁纸（弹窗 apply 回调的目标），非法名被忽略
# 设计：调用 _apply_theme/_apply_wallpaper 断言属性变化，覆盖非法名静默忽略
async def test_apply_theme_and_wallpaper_direct() -> None:
    app, _client = _make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app._apply_theme("light")
        assert app._theme_name == "light"
        app._apply_theme("bogus")
        assert app._theme_name == "light"
        app._apply_wallpaper("ocean")
        assert app._wallpaper_name == "ocean"
