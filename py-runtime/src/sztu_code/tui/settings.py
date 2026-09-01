from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from sztu_code.tui.theme import THEMES, WALLPAPER_ORDER, c

if TYPE_CHECKING:
    from sztu_code.tui.app import SztuTuiApp

# 权限模式的可选值（与 permission.set_mode 契约一致）
_MODE_NAMES = ("auto", "accept_edits", "plan")


# 设置弹窗中的一行：名称、可选值、当前索引与切换回调（values=None 表示只读信息行）
@dataclass
class _Row:
    name: str
    values: list[str] | None
    index: int = 0
    apply: Callable[[str], Any] | None = None
    enabled: bool = True


# 将行的当前索引按 delta 循环移动（左移/右移，越界回绕）
def _cycle_index(row: _Row, delta: int) -> None:
    if not row.values:
        return
    size = len(row.values)
    row.index = (row.index + delta) % size


# 取当前行的可切换值（只读行返回 None）
def _row_value(row: _Row) -> str | None:
    if not row.values:
        return None
    return row.values[row.index]


class SettingsModal(ModalScreen[None]):
    """弹窗式设置界面：外观/模型/权限/LLM 参数分组，↑↓ 移动、←→ 切换、Esc 关闭。"""

    DEFAULT_CSS = """
    SettingsModal { align: center middle; }
    #settings-panel {
        width: 64;
        max-height: 24;
        background: $surface;
        border: round $border2;
        padding: 1 2;
        scrollbar-size-vertical: 1;
    }
    #settings-panel:focus {
        border: round $accent;
    }
    #settings-panel > Static.group-title {
        color: $accent;
        margin-top: 1;
    }
    #settings-panel > Static.row-line {
        color: $text;
    }
    #settings-panel > Static.row-line.cursor {
        background: $surface2;
    }
    #settings-panel > Static.hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    # 初始化弹窗：行与分组数据为空，挂载后从 daemon 拉取
    def __init__(self, *, focus_row: str | None = None) -> None:
        super().__init__()
        self._focus_row = focus_row
        self._rows: list[_Row] = []
        self._groups: list[tuple[str, int]] = []  # (组标题, 起始行索引)
        self._cursor = 0
        self._connected: bool | None = None
        self._load_error = ""
        self._snapshot: dict[str, Any] = {}
        self._model_profiles: list[tuple[str, str]] = []  # (名称, profile id)
        self._model_name = ""

    # 供类型检查使用的宿主 App 引用（运行时即 self.app）
    @property
    def _host_app(self) -> SztuTuiApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="settings-panel")

    # 挂载后抢占焦点并异步加载 daemon 设置
    def on_mount(self) -> None:
        panel = self.query_one("#settings-panel", VerticalScroll)
        panel.focus()
        self._connected = self._host_app._client is not None
        if self._connected:
            self.app.run_worker(self._load(), name="settings_load", exclusive=False)
        else:
            self._build_rows()
            self._redraw()

    # 从 daemon 拉取设置快照与模型档案，随后重建可交互行
    async def _load(self) -> None:
        client = self._host_app._client
        if client is None:
            self._connected = False
            self._build_rows()
            self._redraw()
            return
        try:
            result = await client.send_command("settings.get", {})
            self._snapshot = dict(result.get("settings") or {})
        except Exception:
            self._load_error = "failed to load settings"
        try:
            result = await client.send_command("provider.model_list", {})
            self._model_profiles = [
                (str(m.get("name") or ""), str(m.get("id") or ""))
                for m in (result.get("models") or [])
            ]
        except Exception:
            self._load_error = "failed to load models"
        self._model_name = str(
            self._snapshot.get("model") or self._host_app._model or ""
        )
        self._build_rows()
        self._redraw()

    # 根据主题/壁纸/权限模式与 daemon 快照重建设置行
    def _build_rows(self) -> None:
        app = self._host_app
        rows: list[_Row] = []
        groups: list[tuple[str, int]] = []

        groups.append(("appearance", len(rows)))
        rows.append(_Row(
            "theme",
            list(THEMES.keys()),
            tuple(THEMES.keys()).index(app._theme_name),
            lambda value: app._apply_theme(value),
        ))
        rows.append(_Row(
            "wallpaper",
            list(WALLPAPER_ORDER),
            WALLPAPER_ORDER.index(app._wallpaper_name),
            lambda value: app._apply_wallpaper(value),
        ))

        groups.append(("model", len(rows)))
        names = [name for name, _profile_id in self._model_profiles]
        current = names.index(self._model_name) if self._model_name in names else 0
        if names:
            rows.append(_Row("model", names, current, self._select_model))
        else:
            rows.append(_Row("model", None))
        max_tokens = self._snapshot.get("max_output_tokens")
        rows.append(_Row(
            f"max tokens ({max_tokens if isinstance(max_tokens, int) else '—'})", None
        ))

        groups.append(("permissions", len(rows)))
        mode_index = _MODE_NAMES.index(app._mode) if app._mode in _MODE_NAMES else 0
        rows.append(_Row(
            "mode",
            list(_MODE_NAMES),
            mode_index,
            lambda value: app.run_worker(app._set_mode(value), name="settings_mode"),
            enabled=not app._read_only,
        ))

        groups.append(("llm", len(rows)))
        temperature = self._snapshot.get("temperature")
        top_p = self._snapshot.get("top_p")
        reasoning = str(self._snapshot.get("reasoning_effort") or "")
        cache = bool(self._snapshot.get("cache_control", True))
        rows.append(_Row(f"temperature ({_fmt_float(temperature)})", None))
        rows.append(_Row(f"top_p ({_fmt_float(top_p)})", None))
        rows.append(_Row(f"reasoning ({reasoning or '—'})", None))
        rows.append(_Row(f"cache ({'on' if cache else 'off'})", None))

        self._rows = rows
        self._groups = groups
        self._cursor = 0
        if self._focus_row:
            for index, row in enumerate(rows):
                if row.name == self._focus_row and row.values is not None and row.enabled:
                    self._cursor = index
                    break

    # 重绘弹窗全部内容：分组标题、设置行与操作提示
    def _redraw(self) -> None:
        panel = self.query_one("#settings-panel", VerticalScroll)
        panel.remove_children()
        panel.mount(Static(
            f"[bold {c('accent')}]⚙ SztuCode Settings[/bold {c('accent')}]",
            classes="group-title",
        ))
        if self._connected is False:
            panel.mount(Static(
                "[dim]daemon 未连接，仅本地外观设置可用[/dim]", classes="row-line"
            ))
        elif self._load_error:
            panel.mount(Static(f"[dim]{self._load_error}[/dim]", classes="row-line"))
        for index, (title, start) in enumerate(self._groups):
            end = self._groups[index + 1][1] if index + 1 < len(self._groups) else len(self._rows)
            panel.mount(Static(title, classes="group-title"))
            for row_index in range(start, end):
                row = self._rows[row_index]
                panel.mount(Static(
                    self._row_text(row),
                    classes="row-line cursor" if row_index == self._cursor else "row-line",
                ))
        panel.mount(Static(
            "[dim]↑↓ select · ←→ change · esc close[/dim]", classes="hint"
        ))

    # 生成单行设置文本：▸ 可切换值 / · 只读信息
    def _row_text(self, row: _Row) -> str:
        value = _row_value(row)
        if value is not None:
            arrow = f"[{c('info')}]▸[/{c('info')}]"
            value_part = f"[{c('info')}]{value}[/{c('info')}]"
        else:
            arrow = "[dim]·[/dim]"
            value_part = "[dim]—[/dim]"
        suffix = "" if row.enabled else "  [dim](readonly)[/dim]"
        return f"  {arrow} [bold]{row.name:<16}[/bold] {value_part}{suffix}"

    # 键盘导航：↑↓ 移动、←→ 切换并应用、Esc 关闭
    def on_key(self, event: events.Key) -> None:
        key = event.key
        if key in ("escape", "q"):
            event.stop()
            self.dismiss(None)
        elif key in ("up", "k"):
            event.stop()
            self._move_cursor(-1)
        elif key in ("down", "j"):
            event.stop()
            self._move_cursor(1)
        elif key in ("left", "h"):
            event.stop()
            self._change(-1)
        elif key in ("right", "l"):
            event.stop()
            self._change(1)

    # 在可交互行之间移动光标（跳过只读与禁用行）
    def _move_cursor(self, delta: int) -> None:
        if not self._rows:
            return
        size = len(self._rows)
        for _ in range(size):
            self._cursor = (self._cursor + delta) % size
            row = self._rows[self._cursor]
            if row.values is not None and row.enabled:
                break
        self._redraw()

    # 循环切换当前行的值并调用其应用回调
    def _change(self, delta: int) -> None:
        if not self._rows:
            return
        row = self._rows[self._cursor]
        if row.values is None or not row.enabled:
            return
        _cycle_index(row, delta)
        value = row.values[row.index]
        if row.apply is not None:
            row.apply(value)
        self._redraw()

    # 按名称选择模型档案（经 worker 调度异步 IPC）
    def _select_model(self, name: str) -> None:
        profile_id = next((profile_id for n, profile_id in self._model_profiles if n == name), "")
        if not profile_id:
            return
        self.app.run_worker(
            self._ipc_select_model(profile_id), name="settings_model_select"
        )

    # 调用 daemon 切换模型档案并重新加载弹窗数据
    async def _ipc_select_model(self, profile_id: str) -> None:
        client = self._host_app._client
        if client is None:
            return
        try:
            result = await client.send_command("provider.model_select", {"model_id": profile_id})
            settings = result.get("settings") or {}
            self._model_name = str(settings.get("model") or self._model_name)
        except Exception:
            self._load_error = "model switch failed"
        await self._load()


# 将可选浮点参数格式化为展示文本
def _fmt_float(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):g}"
