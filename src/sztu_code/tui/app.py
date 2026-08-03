from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from rich.markdown import Markdown
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Label, Static, TextArea

from sztu_code.core.config import SztuConfig
from sztu_code.core.skills.loader import SkillLoader
from sztu_code.core.transport.socket_client import IpcError, SocketClient
from sztu_code.core.trust import add_trusted, is_trusted

log = logging.getLogger(__name__)


def _preview(s: str, n: int) -> str:
    return s[:n] + "…" if len(s) > n else s




def _params_str(params: dict[str, Any]) -> str:
    return json.dumps(params, ensure_ascii=False, indent=2)


# 从工具参数中提取最适合摘要展示的关键字段
def _param_summary(tool_name: str, params: dict[str, Any], max_len: int = 72) -> str:
    keys_by_tool = {
        "read_file": ("path",),
        "write_file": ("path",),
        "list_dir": ("path", "max_depth"),
        "bash": ("command",),
        "note_save": ("content",),
    }
    keys = keys_by_tool.get(tool_name, ())
    parts = [f"{key}={params[key]!r}" for key in keys if key in params]
    if not parts:
        parts = [f"{key}={value!r}" for key, value in list(params.items())[:2]]
    return _preview(", ".join(parts), max_len)


class LLMStreamBlock(Static):
    """在同一个 Static widget 中累积 LLM 流式 token。"""

    DEFAULT_CSS = "LLMStreamBlock { padding: 0 2; color: $text; }"

    # 初始化为空文本块
    def __init__(self) -> None:
        super().__init__("")
        self._text = ""
        self._finalized = False

    # 追加一个 token 并刷新显示
    def append_token(self, token: str) -> None:
        if self._finalized:
            return
        self._text += token
        self.update(self._text)

    # 将累积文本渲染为 Markdown，供流式块结束后显示
    def finalize_markdown(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        if self._text.strip():
            self.update(Markdown(self._text, code_theme="monokai"))


class ToolCallBlock(Widget):
    """可折叠的工具调用块：折叠时显示摘要，点击后展开完整 params 和 output。"""

    DEFAULT_CSS = """
    ToolCallBlock { height: auto; padding: 0 2; color: $text-muted; }
    ToolCallBlock > .summary { color: $text-muted; }
    ToolCallBlock > .detail { display: none; padding: 0 2 0 4; color: $text-muted; }
    ToolCallBlock.expanded > .detail { display: block; }
    """

    # 初始化工具调用信息
    def __init__(self, tool_name: str, params: dict[str, Any]) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._params = params
        self._params_full = _params_str(params)
        self._output = ""
        self._elapsed_ms = 0
        self._is_error = False
        self._finished = False

    def compose(self) -> ComposeResult:
        yield Static(self._summary(), classes="summary")
        yield Static("", classes="detail")

    # 生成摘要行文本
    def _summary(self) -> str:
        if self._tool_name == "note_save" and self._finished and not self._is_error:
            return f"  [green]remembered[/green]  [dim]{self._elapsed_ms}ms[/dim]"

        params_pre = _param_summary(self._tool_name, self._params)
        line = f"  [dim]tool[/dim] [bold]{self._tool_name}[/bold]"
        if params_pre:
            line += f"  [dim]{params_pre}[/dim]"
        if self._finished:
            color = "red" if self._is_error else "green"
            status = "failed" if self._is_error else "done"
            hint = "  [dim](click to expand)[/dim]" if self._output else ""
            line += f"  [{color}]{status}[/{color}]  [dim]{self._elapsed_ms}ms[/dim]{hint}"
        return line

    # 工具调用完成时更新结果并刷新摘要（widget 未挂载时跳过 DOM 更新）
    def set_result(self, output: str, elapsed_ms: int, *, is_error: bool = False) -> None:
        self._output = output
        self._elapsed_ms = elapsed_ms
        self._is_error = is_error
        self._finished = True
        if self.children:
            self.query_one(".summary", Static).update(self._summary())

    # 点击时切换展开/折叠状态
    def on_click(self) -> None:
        if not self._finished:
            return
        if "expanded" in self.classes:
            self.remove_class("expanded")
        else:
            detail = self.query_one(".detail", Static)
            detail.update(
                f"[dim]params[/dim]\n{self._params_full}\n\n"
                f"[dim]output[/dim]\n{self._output}\n\n"
                f"[dim]elapsed:[/dim] {self._elapsed_ms}ms"
            )
            self.add_class("expanded")


class PermissionSelect(Static):
    """内联权限选择控件：挂载在日志流中，键盘焦点无需 ModalScreen。"""

    can_focus = True

    DEFAULT_CSS = """
    PermissionSelect {
        height: auto;
        margin: 0 3 1 3;
        padding: 1 2;
        color: #D7DCE1;
        background: #181B1F;
        border: tall #F2BB6C;
    }
    PermissionSelect:focus {
        border: tall #F2BB6C;
    }
    """

    _CHOICES: tuple[tuple[str, str, str], ...] = (
        ("allow_once",   "Allow once",             "Y / 1"),
        ("always_allow", "Always allow this tool", "A / 2"),
        ("deny_once",    "Deny this time",         "N / 3"),
        ("always_deny",  "Always deny this tool",  "D / 4"),
    )
    _KEY_MAP: dict[str, str] = {
        "y": "allow_once",  "1": "allow_once",
        "a": "always_allow","2": "always_allow",
        "n": "deny_once",   "3": "deny_once",
        "d": "always_deny", "4": "always_deny",
    }

    # 用户作出权限决策时发布，携带工具 ID 和决策字符串
    class Decided(Message):
        # 初始化决策消息，存储控件引用、工具 ID 和决策
        def __init__(self, widget: PermissionSelect, tool_use_id: str, decision: str) -> None:
            self.widget = widget
            self.tool_use_id = tool_use_id
            self.decision = decision
            super().__init__()

    # 初始化控件，携带动作摘要，让底部授权单在不回看日志时也完整可读
    def __init__(self, tool_use_id: str, tool_name: str, param_preview: str) -> None:
        super().__init__("")
        self._tool_use_id = tool_use_id
        self._tool_name = tool_name
        self._param_preview = param_preview
        self._cursor = 0

    def on_mount(self) -> None:
        self.update(self._render_ui())
        self.focus()
        log.debug(
            "PermissionSelect.on_mount  can_focus=%s  focused_after=%r",
            self.can_focus,
            self.app.focused,
        )
        self.app.call_after_refresh(self._log_deferred_focus)

    # 在下一帧记录焦点是否真正转移到本控件
    def _log_deferred_focus(self) -> None:
        log.debug(
            "PermissionSelect.deferred_focus  app.focused=%r  has_focus=%s  focusable=%s",
            self.app.focused,
            self.has_focus,
            self.focusable,
        )

    # 焦点到达时记录，用于确认 focus() 是否真正生效
    def on_focus(self, event: events.Focus) -> None:
        log.debug("PermissionSelect.on_focus  has_focus=%s  app.focused=%r", self.has_focus, self.app.focused)

    # 焦点离开时记录，用于追踪是否被其他控件抢走焦点
    def on_blur(self, event: events.Blur) -> None:
        log.debug("PermissionSelect.on_blur  app.focused=%r", self.app.focused)

    # 生成 Claude Code 风格的键盘优先授权单：上下文在上，决定项在下
    def _render_ui(self) -> str:
        preview = _preview(self._param_preview.strip(), 116) if self._param_preview.strip() else "no parameters"
        lines = [
            f"[bold #F2BB6C]Permission required[/bold #F2BB6C]  [bold]{self._tool_name}[/bold]",
            f"[dim]└─ {preview}[/dim]",
            "",
        ]
        selected_styles = {
            "allow_once": "bold #111315 on #76D6C1",
            "always_allow": "bold #111315 on #84B8FF",
            "deny_once": "bold #FFFFFF on #A84F55",
            "always_deny": "bold #FFFFFF on #7A353A",
        }
        for i, (decision, label, key_hint) in enumerate(self._CHOICES):
            if i == self._cursor:
                style = selected_styles[decision]
                lines.append(f"[dim]❯[/dim] [{style}] {i + 1}. {label} [/{style}]  [dim]{key_hint}[/dim]")
            else:
                lines.append(f"  {i + 1}. {label}  [dim]{key_hint}[/dim]")
        lines.append("\n[dim]↑↓ / j k select  ·  Enter confirm  ·  Y A N D direct[/dim]")
        return "\n".join(lines)

    # 方向键导航；快捷键直接选择；enter 确认光标位置
    def on_key(self, event: events.Key) -> None:
        log.debug("PermissionSelect.on_key  key=%r  char=%r", event.key, event.character)
        key = event.key
        if key in ("up", "k"):
            event.stop()
            self._cursor = (self._cursor - 1) % len(self._CHOICES)
            self.update(self._render_ui())
        elif key in ("down", "j"):
            event.stop()
            self._cursor = (self._cursor + 1) % len(self._CHOICES)
            self.update(self._render_ui())
        elif key == "enter":
            event.stop()
            self._pick(self._CHOICES[self._cursor][0])
        else:
            decision = self._KEY_MAP.get(key)
            if decision is not None:
                event.stop()
                self._pick(decision)

    # 发布决策消息，由宿主 App 负责 IPC 回复和控件清理
    def _pick(self, decision: str) -> None:
        log.debug("PermissionSelect._pick  decision=%s", decision)
        self.post_message(self.Decided(self, self._tool_use_id, decision))


class PermissionBlock(Static):
    """日志里的权限审批摘要：给出动作、目标与可恢复的最终决定。"""

    DEFAULT_CSS = """
    PermissionBlock {
        height: auto;
        margin: 1 2 0 2;
        padding: 0 1 0 2;
        background: #1C1A17;
        border-left: solid #F2BB6C;
        color: #D7DCE1;
    }
    """

    _LABEL_MAP: dict[str, str] = {
        "allow_once":   "allowed (once)",
        "always_allow": "always allowed",
        "deny_once":    "denied",
        "always_deny":  "always denied",
        "timeout":      "⏱ timed out",
    }
    LABEL_MAP = _LABEL_MAP
    _ACTION_MAP: dict[str, tuple[str, str]] = {
        "bash": ("Shell command", "Runs a command in the current project."),
        "write_file": ("Write file", "Changes a file in the current project."),
        "edit_file": ("Edit file", "Changes a file in the current project."),
        "read_file": ("Read file", "Reads a file from the current project."),
        "list_dir": ("List directory", "Reads the current project structure."),
    }

    # 子类提交消息：用户作出权限决策时发布
    class Resolved(Message):
        def __init__(self, block: PermissionBlock, decision: str) -> None:
            self.block = block
            self.decision = decision
            super().__init__()

    # 初始化审批块，记录工具 ID、名称和参数预览
    def __init__(self, tool_use_id: str, tool_name: str, param_preview: str) -> None:
        self._tool_use_id = tool_use_id
        self._tool_name = tool_name
        self._param_preview = param_preview
        self._resolved = False
        super().__init__(self._pending_text(), classes="permission-block")

    def _pending_text(self) -> str:
        action, impact = self._ACTION_MAP.get(
            self._tool_name, (self._tool_name.replace("_", " ").title(), "This action needs your approval.")
        )
        preview = _preview(self._param_preview.strip(), 140) if self._param_preview.strip() else "no parameters"
        return (
            f"[bold #F2BB6C]● Approval required[/bold #F2BB6C]  [bold]{action}[/bold]\n"
            f"[dim]  {self._tool_name}  └─ {preview}[/dim]\n"
            f"[dim]  {impact}[/dim]"
        )

    # 将块收缩为单行摘要并发布 Resolved 消息
    def _resolve(self, decision: str) -> None:
        if self._resolved:
            return
        self._resolved = True
        allowed = decision in ("allow_once", "always_allow")
        icon = "[bold green]✓[/bold green]" if allowed else "[bold red]✗[/bold red]"
        label = self._LABEL_MAP.get(decision, decision)
        preview = f"  [dim]{_preview(self._param_preview.strip(), 96)}[/dim]" if self._param_preview.strip() else ""
        self.update(
            f"{icon} approval  [bold]{self._tool_name}[/bold]{preview}  [dim]{label}[/dim]"
        )
        self.post_message(self.Resolved(self, decision))


class SlashCompleteWidget(Static):
    """斜杠命令自动补全弹出框：输入 / 时显示可用 skill 列表并支持键盘筛选与选择。"""

    can_focus = False

    DEFAULT_CSS = """
    SlashCompleteWidget {
        height: auto;
        padding: 0 1;
        margin: 0 2;
        background: $surface;
        border: round $surface-lighten-2;
    }
    """

    # 用户选中某条命令时发布
    class Selected(Message):
        # 初始化，携带被选中的 skill 名称
        def __init__(self, skill_name: str) -> None:
            self.skill_name = skill_name
            super().__init__()

    # 初始化，接收全量 (name, description) 列表
    def __init__(self, items: list[tuple[str, str]]) -> None:
        super().__init__("")
        self._all_items = items
        self._filtered: list[tuple[str, str]] = list(items)
        self._cursor = 0

    # 根据查询字符串筛选列表，重置光标并重新渲染
    def set_query(self, query: str) -> None:
        q = query.lower()
        self._filtered = [(n, d) for n, d in self._all_items if not q or q in n.lower()]
        self._cursor = min(self._cursor, max(0, len(self._filtered) - 1))
        if self.is_attached:
            self._redraw()

    # 向上移动光标并重新渲染
    def move_up(self) -> None:
        if self._filtered:
            self._cursor = (self._cursor - 1) % len(self._filtered)
            self._redraw()

    # 向下移动光标并重新渲染
    def move_down(self) -> None:
        if self._filtered:
            self._cursor = (self._cursor + 1) % len(self._filtered)
            self._redraw()

    # 选中当前光标项并发布 Selected 消息
    def select_current(self) -> None:
        if self._filtered:
            self.post_message(self.Selected(self._filtered[self._cursor][0]))

    # 返回当前是否有可选项
    def has_selection(self) -> bool:
        return len(self._filtered) > 0

    def on_mount(self) -> None:
        self._redraw()

    # 渲染筛选后的命令列表，高亮当前光标项
    def _redraw(self) -> None:
        if not self._filtered:
            self.update("[dim]  no matching commands[/dim]")
            return
        lines: list[str] = []
        for i, (name, desc) in enumerate(self._filtered):
            desc_part = f"  [dim]{desc}[/dim]" if desc else ""
            if i == self._cursor:
                lines.append(f"  [bold cyan]❯ /{name}[/bold cyan]{desc_part}")
            else:
                lines.append(f"    [cyan]/{name}[/cyan]{desc_part}")
        lines.append("[dim]  ↑↓ navigate   tab/enter select   esc dismiss[/dim]")
        self.update("\n".join(lines))


class ChatTextArea(TextArea):
    """支持 Enter 提交、Cmd/Shift/Alt+Enter 换行的多行聊天输入框。"""

    DEFAULT_CSS = """
    ChatTextArea {
        height: auto;
        min-height: 3;
        max-height: 12;
        border: round $surface-lighten-2;
        background: $background;
        padding: 0 1;
        margin: 1 2;
        scrollbar-size-vertical: 1;
    }
    ChatTextArea:focus {
        border: round $accent;
        background: $background;
    }
    """

    # 子类自定义的提交消息，供宿主 App 监听
    class Submitted(Message):
        def __init__(self, area: ChatTextArea) -> None:
            self.text_area = area
            self.value = area.text
            super().__init__()

    # 输入内容以 / 开头且无空格时发布，query 为 / 之后的字符串（可为空串）；None 表示收起弹窗
    class SlashChanged(Message):
        def __init__(self, query: str | None) -> None:
            self.query = query
            super().__init__()

    # 文本变化时检测 / 前缀，通知宿主 App 更新自动补全弹窗
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = self.text
        if text.startswith("/") and " " not in text:
            self.post_message(ChatTextArea.SlashChanged(query=text[1:]))
        else:
            self.post_message(ChatTextArea.SlashChanged(query=None))

    # Enter 提交；↑↓/Tab/Esc 路由到自动补全弹窗；Cmd/Shift/Alt+Enter 插入换行；其余键交回 TextArea
    async def _on_key(self, event: events.Key) -> None:
        key = event.key

        popup: SlashCompleteWidget | None = None
        try:
            popup = self.app.query_one(SlashCompleteWidget)
        except NoMatches:
            popup = None

        if key == "enter":
            event.stop()
            event.prevent_default()
            if popup is not None and popup.has_selection():
                popup.select_current()
                return
            if self.text.strip():
                self.post_message(self.Submitted(self))
            return
        if key in ("alt+enter", "shift+enter", "ctrl+j", "super+enter"):
            event.stop()
            event.prevent_default()
            if not self.read_only:
                self.insert("\n")
            return
        # Tab：有弹窗时选中候选项；无弹窗时不交给 TextArea（避免插入 \t），让 App 层 Tab 绑定生效
        if key == "tab":
            event.stop()
            event.prevent_default()
            if popup is not None and popup.has_selection():
                popup.select_current()
            return
        if popup is not None:
            if key == "up":
                event.stop()
                event.prevent_default()
                popup.move_up()
                return
            elif key == "down":
                event.stop()
                event.prevent_default()
                popup.move_down()
                return
            elif key == "escape":
                event.stop()
                event.prevent_default()
                self.post_message(ChatTextArea.SlashChanged(query=None))
                return
        await super()._on_key(event)


class RunBlock(Widget):
    """一次 run 的输出容器：标题、步骤、回复、用量与完成状态装进一个带边框的块里。"""

    DEFAULT_CSS = """
    RunBlock {
        height: auto;
        margin: 1 2 1 2;
        padding: 0 0 1 0;
        border: round #30353D;
    }
    """

    # 初始化一次 run 的输出块
    def __init__(self, run_id: str, goal: str) -> None:
        super().__init__()
        self._run_id = run_id
        self._goal = goal

    # 生成 run 块标题行
    def compose(self) -> ComposeResult:
        yield Static(
            f"[dim]run[/dim]  [cyan]{self._run_id[:8]}[/cyan]  "
            f"[dim]{_preview(self._goal, 96)}[/dim]",
            classes="run-header",
        )


class TrustScreen(Screen[str]):
    """Claude Code 风格的文件夹信任确认屏，Enter 确认 / Esc 取消。"""

    DEFAULT_CSS = """
    TrustScreen { align: center middle; }
    .trust-panel { width: 74; padding: 1 2; background: #181B1F; border: round #30353D; }
    """

    _OPTIONS: tuple[tuple[str, str], ...] = (
        ("1. Yes, I trust this folder", "trust"),
        ("2. Open read-only", "read_only"),
        ("3. No, exit", "abort"),
    )

    # 初始化信任屏，记录待确认的项目路径
    def __init__(self, project_path: str) -> None:
        super().__init__()
        self._path = project_path
        self._cursor = 0

    def compose(self) -> ComposeResult:
        yield Static(self._build_text(), classes="trust-panel")

    # 挂载后重绘当前选中项
    def on_mount(self) -> None:
        self._redraw()

    # 更新面板中的文本以反映光标位置
    def _redraw(self) -> None:
        self.query_one(Static).update(self._build_text())

    # 生成安全提示文本与选项列表（当前项高亮）
    def _build_text(self) -> str:
        lines = [
            "[bold #E8EAED]Accessing workspace:[/bold #E8EAED]",
            f"[dim]  {self._path}[/dim]",
            "",
            "[bold #F1F3F5]Quick safety check:[/bold #F1F3F5] "
            "Is this a project you created or one you trust?",
            "[dim](Like your own code, a well-known open source project, or work from your team).[/dim]",
            "[dim]If not, take a moment to review what's in this folder first.[/dim]",
            "",
            "[#F1F3F5]SztuCode will be able to [bold]read, edit, and execute[/bold] "
            "",
            "[dim]Security guide — review the folder contents before trusting[/dim]",
            "",
        ]
        for i, (label, _decision) in enumerate(self._OPTIONS):
            if i == self._cursor:
                lines.append(f"[bold #111315 on #84B8FF]  {label}  [/bold #111315 on #84B8FF]")
            else:
                lines.append(f"  {label}")
        lines.append("")
        lines.append("[dim]Enter to confirm · Esc to cancel · ↑/↓ to select[/dim]")
        return "\n".join(lines)

    # 键盘导航：↑↓ 选择、Enter 确认、Esc 取消、数字键直达
    def on_key(self, event: events.Key) -> None:
        key = event.key
        if key in ("up", "k"):
            event.stop()
            self._cursor = (self._cursor - 1) % len(self._OPTIONS)
            self._redraw()
        elif key in ("down", "j"):
            event.stop()
            self._cursor = (self._cursor + 1) % len(self._OPTIONS)
            self._redraw()
        elif key == "enter":
            event.stop()
            self.dismiss(self._OPTIONS[self._cursor][1])
        elif key in ("1", "2", "3"):
            event.stop()
            self.dismiss(self._OPTIONS[int(key) - 1][1])
        elif key == "escape":
            event.stop()
            self.dismiss("abort")


class KamaTuiApp(App[None]):
    """SztuCode TUI：终端滚屏风格，实时展示 agent 执行过程。"""

    TITLE = "SZTUCODE"
    BINDINGS = [
        Binding("ctrl+q", "quit", "quit"),
        Binding("ctrl+shift+a", "mode_auto", "auto mode"),
        Binding("ctrl+shift+e", "mode_accept_edits", "accept edits"),
        Binding("ctrl+shift+p", "mode_plan", "plan mode"),
        Binding("tab", "cycle_mode", "switch mode", priority=True),
    ]
    _MODE_CYCLE = ("auto", "accept_edits", "plan")
    CSS = """
    Screen { background: #111315; }
    #header {
        height: 1;
        background: #181B1F;
        color: #F1F3F5;
        padding: 0 1;
    }
    #log-view {
        height: 1fr;
        width: 1fr;
        background: #111315;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
    }
    #prompt {
        width: 1fr;
        background: #181B1F;
        color: #F1F3F5;
        border: tall #30353D;
        margin: 0 1 1 1;
    }
    #prompt:focus {
        border: tall #F2BB6C;
    }
    #banner { padding: 2 3 1 3; color: #F1F3F5; }
    Static.user-turn { color: $text; padding: 1 2 0 2; }
    Static.run-header { color: $text-muted; padding: 1 2 0 2; }
    Static.step-divider { color: $text-muted; padding: 0 2; }
    Static.run-ok { color: green; padding: 0 2 1 2; }
    Static.run-err { color: red; padding: 0 2 1 2; }
    Static.usage { padding: 0 2; }
    Static.log-line { padding: 0 2; }
    """

    _BANNER = r"""
[bold #00E5E5] ███████╗███████╗████████╗██╗   ██╗ ██████╗ ██████╗ ██████╗ ███████╗
 ██╔════╝╚══███╔╝╚══██╔══╝██║   ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝
 ███████╗  ███╔╝    ██║   ██║   ██║██║     ██║   ██║██║  ██║█████╗
 ╚════██║ ███╔╝     ██║   ██║   ██║██║     ██║   ██║██║  ██║██╔══╝
 ███████║███████╗   ██║   ╚██████╔╝╚██████╗╚██████╔╝██████╔╝███████╗
 ╚══════╝╚══════╝   ╚═╝    ╚═════╝  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝[/bold #00E5E5]
[dim]  输入消息开始对话  ·  键入 / 触发 skill  ·  Ctrl+C 退出[/dim]
""".strip()

    # 初始化连接参数、项目目录与只读状态
    def __init__(
        self,
        host: str,
        port: int,
        *,
        project_path: str | None = None,
        read_only: bool = False,
        trust: bool = False,
        replay_run_id: str | None = None,
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._replay_run_id = replay_run_id
        self._client: SocketClient | None = None
        self._current_llm: LLMStreamBlock | None = None
        self._pending_tool_blocks: dict[str, ToolCallBlock] = {}
        self._pending_permission_blocks: dict[str, PermissionBlock] = {}
        self._session_id: str | None = None
        self._workspace: dict[str, Any] | None = None
        self._project_path = str(Path(project_path or Path.cwd()).resolve())
        self._read_only = read_only
        self._force_trust = trust
        self._model = "loading…"
        self._busy = False
        self._last_context_pct: float = 0.0
        self._session_tokens: dict[str, int] = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
        self._slash_items: list[tuple[str, str]] = []
        self._subagent_run_ids: dict[str, str] = {}  # child run_id -> description
        self._subagent_start_times: dict[str, float] = {}  # child run_id -> start time
        self._run_block: RunBlock | None = None  # 当前活动 run 的输出块
        self._mode: str = "plan" if read_only else "auto"  # 只读模式锁定 plan

    def compose(self) -> ComposeResult:
        yield Label("[bold #76D6C1]SZTUCODE[/bold #76D6C1]  [dim]connecting...[/dim]", id="header")
        yield VerticalScroll(id="log-view")
        yield ChatTextArea(id="prompt", show_line_numbers=False)

    def on_mount(self) -> None:
        self._slash_items = self._build_slash_items()
        self._append(Static(self._BANNER, id="banner"))
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.disabled = True
        prompt.border_title = "connecting..."
        if self._needs_trust_check():
            self.push_screen(TrustScreen(self._project_path), self._on_trust_result)
        else:
            self._start_socket_loop()

    # 是否需要在启动前做文件夹信任确认
    def _needs_trust_check(self) -> bool:
        return not self._read_only and not self._force_trust and not is_trusted(self._project_path)

    # 启动 socket 连接循环（信任确认后或无需确认时调用）
    def _start_socket_loop(self) -> None:
        self.run_worker(self._socket_loop(), exclusive=True, name="socket")

    # 信任确认结果回调：信任则记录，只读则切换模式，拒绝则退出
    def _on_trust_result(self, decision: str | None) -> None:
        if decision == "abort" or decision is None:
            self.exit()
            return
        if decision == "trust":
            add_trusted(self._project_path)
        elif decision == "read_only":
            self._read_only = True
        self._start_socket_loop()

    # 返回当前模式的富文本标签，用于 header 栏显示
    def _mode_label(self) -> str:
        if self._read_only:
            return "[bold #111315 on #F2BB6C] READONLY [/bold #111315 on #F2BB6C]"
        colors = {"auto": "#76D6C1", "accept_edits": "#84B8FF", "plan": "#F2BB6C"}
        labels = {"auto": "AUTO", "accept_edits": "EDITS", "plan": "PLAN"}
        color = colors.get(self._mode, "#76D6C1")
        label = labels.get(self._mode, self._mode.upper())
        return f"[bold #111315 on {color}] {label} [/bold #111315 on {color}]"

    # 构建斜杠命令候选列表：内建命令 + 所有已注册 skill
    def _build_slash_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = [
            ("compact", "compress context window"),
            ("new", "start a fresh task"),
            ("workspace", "open a local repository"),
            ("files", "show workspace file tree"),
            ("search", "search files in the workspace"),
            ("changes", "show uncommitted changes"),
            ("diff", "inspect a file diff"),
        ]
        try:
            loader = SkillLoader()
            for skill in loader.list_all_skills():
                desc = skill.description.splitlines()[0] if skill.description else ""
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                items.append((skill.name, desc))
        except Exception:
            pass
        return items

    # 根据 / 前缀查询字符串挂载、更新或移除自动补全弹窗
    def on_chat_text_area_slash_changed(self, event: ChatTextArea.SlashChanged) -> None:
        query = event.query
        if query is None:
            try:
                self.query_one(SlashCompleteWidget).remove()
            except NoMatches:
                pass
            return
        try:
            popup = self.query_one(SlashCompleteWidget)
            popup.set_query(query)
        except NoMatches:
            popup = SlashCompleteWidget(self._slash_items)
            self.mount(popup, before="#prompt")
            popup.set_query(query)

    # 用户选中自动补全项后将 /{name} 填入输入框并移除弹窗
    def on_slash_complete_widget_selected(self, event: SlashCompleteWidget.Selected) -> None:
        prompt = self._prompt()
        if prompt is not None:
            prompt.text = f"/{event.skill_name} "
            prompt.move_cursor(prompt.document.end)
        try:
            self.query_one(SlashCompleteWidget).remove()
        except NoMatches:
            pass

    # 记录按键焦点；当 PermissionSelect 失去焦点后作为兜底处理权限快捷键
    def on_key(self, event: events.Key) -> None:
        log.debug("App.on_key  key=%r  focused=%r", event.key, self.focused)
        if not self._pending_permission_blocks:
            return
        try:
            select = self.query_one(PermissionSelect)
            if select.has_focus:
                return  # PermissionSelect 有焦点时自行处理，事件不会冒泡到这里
            key = event.key
            decision = PermissionSelect._KEY_MAP.get(key)
            if decision:
                event.stop()
                select._pick(decision)
            elif key in ("up", "k"):
                event.stop()
                select._cursor = (select._cursor - 1) % len(PermissionSelect._CHOICES)
                select.update(select._render_ui())
            elif key in ("down", "j"):
                event.stop()
                select._cursor = (select._cursor + 1) % len(PermissionSelect._CHOICES)
                select.update(select._render_ui())
            elif key == "enter":
                event.stop()
                select._pick(PermissionSelect._CHOICES[select._cursor][0])
        except Exception:
            pass

    # 退出前尽力关闭当前 session，失败也不阻塞 TUI 退出
    async def action_quit(self) -> None:
        if self._client is not None and self._session_id is not None:
            try:
                await self._client.send_command("session.close", {"session_id": self._session_id})
            except (IpcError, RuntimeError, OSError):
                self._append(Static("[yellow]warning: failed to close session[/yellow]"))
        self.exit()

    # 切换到 Auto 模式：自动批准所有工具调用
    async def action_mode_auto(self) -> None:
        await self._set_mode("auto")

    # 切换到 Accept Edits 模式：自动批准编辑类工具（write_file, note_save）
    async def action_mode_accept_edits(self) -> None:
        await self._set_mode("accept_edits")

    # 切换到 Plan 模式：只允许只读工具，拒绝所有写入和执行
    async def action_mode_plan(self) -> None:
        await self._set_mode("plan")

    # Tab 循环 Auto、Accept Edits、Plan；让模式选择不必离开输入框
    async def action_cycle_mode(self) -> None:
        try:
            index = self._MODE_CYCLE.index(self._mode)
        except ValueError:
            index = -1
        await self._set_mode(self._MODE_CYCLE[(index + 1) % len(self._MODE_CYCLE)])

    # 向 daemon 发送模式切换命令并更新本地状态
    async def _set_mode(self, mode: str) -> None:
        if self._read_only and mode != "plan":
            log.debug("mode switch blocked in read-only target=%s", mode)
            return
        if self._client is None:
            log.debug("mode switch ignored while disconnected target=%s", mode)
            return
        try:
            result = await self._client.send_command("permission.set_mode", {"mode": mode})
            if result.get("ok"):
                self._mode = mode
                self._update_header("ready")
                self._update_header("ready")
            else:
                log.warning("mode switch rejected target=%s error=%s", mode, result.get("error", "unknown"))
        except (IpcError, RuntimeError, OSError) as e:
            log.warning("mode switch failed target=%s error=%s", mode, e)

    # 从 daemon 读取保存的 Provider 配置；无论任务是否已运行，都能显示当前模型
    async def _refresh_model_status(self) -> None:
        if self._client is None:
            return
        try:
            result = await self._client.send_command("provider.status", {})
            model = str(result.get("model") or "")
            if model:
                self._model = model
            else:
                self._model = "not configured"
            self._update_header("ready")
        except (IpcError, RuntimeError, OSError):
            self._model = "unavailable"
            self._update_header("ready")

    # 将输入框提交内容发送给当前 chat session；用 worker 发送，避免 await 阻塞 App 消息泵
    async def on_chat_text_area_submitted(self, event: ChatTextArea.Submitted) -> None:
        content = event.value.strip()
        if not content:
            return
        if content == "/new":
            event.text_area.text = ""
            self.run_worker(self._create_new_session(), name="new_session", exclusive=False)
            return
        if content.startswith("/workspace "):
            event.text_area.text = ""
            self.run_worker(
                self._open_workspace(content.removeprefix("/workspace ").strip()),
                name="open_workspace",
                exclusive=False,
            )
            return
        if content == "/files":
            event.text_area.text = ""
            self.run_worker(self._show_workspace_tree(), name="workspace_tree", exclusive=False)
            return
        if content.startswith("/search "):
            event.text_area.text = ""
            self.run_worker(
                self._search_workspace(content.removeprefix("/search ").strip()),
                name="workspace_search",
                exclusive=False,
            )
            return
        if content == "/changes":
            event.text_area.text = ""
            self.run_worker(self._show_changes(), name="change_list", exclusive=False)
            return
        if content.startswith("/diff "):
            event.text_area.text = ""
            self.run_worker(
                self._show_diff(content.removeprefix("/diff ").strip()),
                name="change_diff",
                exclusive=False,
            )
            return
        # 检测 /compact 指令
        if content == "/compact":
            event.text_area.text = ""
            if self._client is not None and self._session_id is not None and not self._busy:
                self.run_worker(self._do_compact(), name="compact", exclusive=False)
            return
        # 检测三种模式切换指令：/auto /edits /plan
        mode_map = {"/auto": "auto", "/edits": "accept_edits", "/plan": "plan"}
        if content in mode_map:
            event.text_area.text = ""
            self.run_worker(self._set_mode(mode_map[content]), name="set_mode", exclusive=False)
            return
        if self._client is None or self._session_id is None or self._busy:
            self._append(Static("[yellow]agent busy or disconnected[/yellow]", classes="log-line"))
            return
        self._busy = True
        prompt = event.text_area
        prompt.text = ""
        prompt.disabled = True
        prompt.read_only = False
        prompt.border_title = "agent is working..."
        self._append(Static(f"[bold]>[/bold] {content}", classes="user-turn"))
        self._update_header("running")
        self.run_worker(self._do_send_message(content), name="send_message", exclusive=False)

    # 在 worker 中执行手动压缩命令，完成后显示结果横幅
    async def _do_compact(self) -> None:
        if self._client is None or self._session_id is None:
            return
        self._append(Static("[dim]⚡ compacting context...[/dim]", classes="log-line"))
        try:
            result = await self._client.send_command(
                "session.compact",
                {"session_id": self._session_id, "focus": ""},
            )
            summary_tokens = result.get("summary_tokens", 0)
            saved_tokens = result.get("saved_tokens", 0)
            self._last_context_pct = 0.0
            self._append(Static(
                f"[bold cyan]⚡ Context compacted[/bold cyan]"
                f"  [dim]summary={summary_tokens} tokens  saved≈{saved_tokens} tokens[/dim]",
                classes="log-line",
            ))
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]compact error: {e}[/red]", classes="log-line"))

    # 创建新的 chat session 并保留当前的单栏日志视图
    async def _create_new_session(self) -> None:
        if self._client is None:
            return
        try:
            create_params: dict[str, Any] = {"mode": "chat"}
            if self._workspace is not None:
                create_params["workspace_id"] = self._workspace["workspace_id"]
            created = await self._client.send_command("session.create", create_params)
            self._session_id = str(created["session_id"])
            self._session_tokens = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
            self._append(Static("[bold cyan]new task started[/bold cyan]", classes="log-line"))
            self._update_header("ready")
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]new task error: {e}[/red]", classes="log-line"))

    # 打开本地工作区并将其显示在状态栏，供后续文件浏览与搜索使用
    async def _open_workspace(self, path: str) -> None:
        if self._client is None:
            return
        if not path:
            self._append(Static("[yellow]usage: /workspace <folder>[/yellow]", classes="log-line"))
            return
        try:
            result = await self._client.send_command("workspace.open", {"path": path})
            self._workspace = dict(result["workspace"])
            self._append(Static(
                f"[bold cyan]workspace opened[/bold cyan]  "
                f"[dim]{self._workspace['path']}[/dim]",
                classes="log-line",
            ))
            self._update_header("ready")
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]workspace error: {e}[/red]", classes="log-line"))

    # 展示当前工作区的顶层文件树，保留主任务时间线的阅读密度
    async def _show_workspace_tree(self) -> None:
        if self._client is None or self._workspace is None:
            self._append(Static("[yellow]open a workspace first: /workspace <folder>[/yellow]", classes="log-line"))
            return
        try:
            result = await self._client.send_command("workspace.tree", {
                "workspace_id": self._workspace["workspace_id"],
                "max_depth": 2,
            })
            nodes = result.get("nodes", [])
            labels = [str(node.get("path", "")) for node in nodes[:30]]
            body = "\n".join(f"  {label}" for label in labels) or "  (empty)"
            self._append(Static(
                f"[bold cyan]files[/bold cyan]\n[dim]{body}[/dim]",
                classes="log-line",
            ))
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]file tree error: {e}[/red]", classes="log-line"))

    # 搜索当前工作区并将命中行以可读摘要加入任务时间线
    async def _search_workspace(self, query: str) -> None:
        if self._client is None or self._workspace is None:
            self._append(Static("[yellow]open a workspace first: /workspace <folder>[/yellow]", classes="log-line"))
            return
        if not query:
            self._append(Static("[yellow]usage: /search <text>[/yellow]", classes="log-line"))
            return
        try:
            result = await self._client.send_command("file.search", {
                "workspace_id": self._workspace["workspace_id"],
                "query": query,
            })
            matches = result.get("matches", [])
            body = "\n".join(
                f"  {match.get('path')}:{match.get('line')}  {match.get('preview')}"
                for match in matches[:20]
            ) or "  (no matches)"
            self._append(Static(
                f"[bold cyan]search[/bold cyan] [dim]{query!r}[/dim]\n[dim]{body}[/dim]",
                classes="log-line",
            ))
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]search error: {e}[/red]", classes="log-line"))

    # 展示当前工作区未提交变更的文件状态，便于在任务结束后快速审阅
    async def _show_changes(self) -> None:
        if self._client is None or self._workspace is None:
            self._append(Static("[yellow]open a workspace first: /workspace <folder>[/yellow]", classes="log-line"))
            return
        try:
            result = await self._client.send_command("change.list", {
                "workspace_id": self._workspace["workspace_id"],
            })
            changes = result.get("changes", [])
            body = "\n".join(
                f"  {change.get('index_status')}{change.get('worktree_status')}  {change.get('path')}"
                for change in changes[:50]
            ) or "  (clean working tree)"
            self._append(Static(
                f"[bold cyan]changes[/bold cyan]\n[dim]{body}[/dim]",
                classes="log-line",
            ))
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]changes error: {e}[/red]", classes="log-line"))

    # 展示指定文件的 Git diff，原始 patch 保持可复制且不修改工作区
    async def _show_diff(self, path: str) -> None:
        if self._client is None or self._workspace is None:
            self._append(Static("[yellow]open a workspace first: /workspace <folder>[/yellow]", classes="log-line"))
            return
        if not path:
            self._append(Static("[yellow]usage: /diff <path>[/yellow]", classes="log-line"))
            return
        try:
            result = await self._client.send_command("change.diff", {
                "workspace_id": self._workspace["workspace_id"],
                "path": path,
            })
            diff = str(result.get("diff") or "(no Git diff available)")
            self._append(Static(
                f"[bold cyan]diff[/bold cyan] [dim]{path}[/dim]\n{diff[:12_000]}",
                classes="log-line",
            ))
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]diff error: {e}[/red]", classes="log-line"))

    # 在 worker 中执行 IPC 发送，使 App 消息泵在 agent 运行期间仍能处理键盘/焦点等消息
    async def _do_send_message(self, content: str) -> None:
        if self._client is None:
            return
        try:
            await self._client.send_command(
                "session.send_message",
                {"session_id": self._session_id, "content": content},
            )
        except (IpcError, RuntimeError, OSError) as e:
            self._busy = False
            prompt = self._prompt()
            if prompt is not None:
                prompt.disabled = False
                prompt.read_only = False
                prompt.border_title = "type a message — enter to send, ⌘/⇧/⌥+enter for newline"
            self._update_header("ready")
            self._append(Static(f"[red]send error: {e}[/red]", classes="log-line"))

    # 处理内联审批控件的用户决策：发送 IPC 响应并恢复输入框
    async def on_permission_select_decided(self, msg: PermissionSelect.Decided) -> None:
        tool_use_id = msg.tool_use_id
        decision = msg.decision
        log.info("permission decided tool_use_id=%s decision=%s", tool_use_id, decision)
        try:
            msg.widget.remove()
            perm_block = self._pending_permission_blocks.pop(tool_use_id, None)
            if perm_block is not None:
                perm_block._resolve(decision)
            if self._client is not None:
                try:
                    await self._client.send_command(
                        "permission.respond",
                        {"tool_use_id": tool_use_id, "decision": decision},
                    )
                except (IpcError, RuntimeError, OSError):
                    pass
            if not self._pending_permission_blocks:
                p = self._prompt()
                if p is not None:
                    p.disabled = False
                    p.read_only = False
                    p.border_title = "type a message — enter to send, ⌘/⇧/⌥+enter for newline"
                    p.focus()
        except Exception:
            log.exception("on_permission_select_decided failed tool_use_id=%s", tool_use_id)

    # 向日志视图追加 widget：有活动 run 块时装入块内，否则直接追加到日志流
    def _append(self, widget: Widget) -> None:
        log_view = self.query_one("#log-view", VerticalScroll)
        if self._run_block is not None:
            self._run_block.mount(widget)
        else:
            log_view.mount(widget)
        log_view.scroll_end(animate=False)

    # 结束当前 LLM 流式块（下一个 token 将开启新块）
    def _break_llm(self) -> None:
        if self._current_llm is not None:
            self._current_llm.finalize_markdown()
        self._current_llm = None

    # 将选择控件挂载到 Screen 顶层（#prompt 之前），避免 VerticalScroll 争抢焦点
    def _mount_permission_select(self, select: PermissionSelect) -> None:
        self.mount(select, before="#prompt")

    # 安全获取输入框，便于组件测试中未挂载时跳过 UI 操作
    def _prompt(self) -> ChatTextArea | None:
        try:
            return self.query_one("#prompt", ChatTextArea)
        except Exception:
            return None

    # 生成 context 占用率的彩色进度条字符串
    def _render_ctx_bar(self, pct: float) -> str:
        width = 20
        filled = int(pct * width)
        bar = "█" * filled + "░" * (width - filled)
        label = f"ctx {pct * 100:.0f}%"
        if pct >= 0.90:
            color = "bold red"
        elif pct >= 0.75:
            color = "yellow"
        elif pct >= 0.50:
            color = "green"
        else:
            color = "dim"
        return f"[{color}]{label} {bar}[/{color}]"

    # 将大数字格式化为人类可读形式（如 1.2K、3.4M）
    @staticmethod
    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    # 根据连接和运行状态刷新顶部标题
    def _update_header(self, state: str) -> None:
        try:
            header = self.query_one("#header", Label)
        except NoMatches:
            return
        project_path = self._project_path
        if self._workspace is not None:
            project_path = str(self._workspace.get("path") or project_path)
        workspace = f"  [dim]·[/dim] [#84B8FF]{project_path}[/#84B8FF]"
        model = f"  [dim]model[/dim] [#D7DCE1]{self._model}[/#D7DCE1]"
        color = {
            "ready": "green",
            "running": "yellow",
            "disconnected": "red",
            "connecting": "dim",
        }.get(state, "dim")
        header.update(
            f"[bold #76D6C1]SZTUCODE[/bold #76D6C1]  [dim]{self._host}:{self._port}[/dim]"
            f"{model}{workspace}  {self._mode_label()}  [{color}]{state}[/{color}]"
        )

    # 管理 SocketClient 生命周期：连接、订阅事件、断线重连
    async def _socket_loop(self) -> None:
        header = self.query_one("#header", Label)

        while True:
            client = SocketClient(self._host, self._port)
            self._client = None
            try:
                await client.connect()
            except (ConnectionRefusedError, OSError):
                log.warning("connection refused %s:%s, retrying", self._host, self._port)
                self._update_header("disconnected")
                await asyncio.sleep(2)
                continue

            log.info("connected to %s:%s", self._host, self._port)
            self._client = client
            self._update_header("connecting")
            loop_task = asyncio.create_task(client.run_event_loop())

            async def on_event(event: dict[str, Any]) -> None:
                self._handle_event(event)

            client.on_event(on_event)

            try:
                loop_task.add_done_callback(
                    lambda t: log.error("loop_task failed: %s", t.exception())
                    if not t.cancelled() and t.exception() is not None
                    else None
                )
                params: dict[str, Any] = {
                    "topics": [
                        "session.*",
                        "run.*",
                        "step.*",
                        "tool.*",
                        "llm.model_selected",
                        "llm.token",
                        "llm.usage",
                        "log.*",
                        "permission.*",
                        "context.*",
                        "subagent.*",
                        "skill.*",
                    ],
                    "scope": "global",
                }
                if self._replay_run_id is not None:
                    params["replay_from_run"] = self._replay_run_id
                await client.send_command("event.subscribe", params)
                # 先打开工作区，再用其 workspace_id 创建 session，使 agent 的读写绑定到当前项目
                if self._workspace is None:
                    await self._open_workspace(self._project_path)
                if self._session_id is not None:
                    await client.send_command("session.resume", {"session_id": self._session_id})
                else:
                    create_params: dict[str, Any] = {"mode": "chat"}
                    if self._workspace is not None:
                        create_params["workspace_id"] = self._workspace["workspace_id"]
                    created = await client.send_command("session.create", create_params)
                    self._session_id = str(created["session_id"])
                self._session_tokens = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
                log.info("session created session_id=%s", self._session_id)
                await self._set_mode("plan" if self._read_only else "auto")
                await self._refresh_model_status()
                prompt = self._prompt()
                if prompt is not None:
                    prompt.disabled = False
                    prompt.read_only = False
                    prompt.border_title = "type a message — enter to send, ⌘/⇧/⌥+enter for newline"
                    prompt.focus()
                self._update_header("ready")
                await loop_task
            except IpcError as e:
                header.update(f"[bold #76D6C1]SZTUCODE[/bold #76D6C1]  [red]subscribe error: {e}[/red]")
            finally:
                if not loop_task.done():
                    loop_task.cancel()
                self._client = None
                prompt = self._prompt()
                if prompt is not None:
                    prompt.disabled = True
                    prompt.read_only = False
                    prompt.border_title = "disconnected, retrying..."
                self._break_llm()
                await client.close()

            self._update_header("disconnected")
            await asyncio.sleep(2)

    # 根据事件 type 路由到对应渲染逻辑；捕获异常防止 socket loop 因单个事件崩溃
    def _handle_event(self, event: dict[str, Any]) -> None:
        try:
            self._handle_event_inner(event)
        except Exception:
            log.exception("_handle_event crashed  event_type=%s", event.get("type", "?"))

    # 实际的事件路由逻辑
    def _handle_event_inner(self, event: dict[str, Any]) -> None:
        t = event.get("type", "")

        session_id = event.get("session_id")
        if session_id is not None and session_id != self._session_id:
            return

        if t == "llm.token":
            token = event.get("token", "")
            if self._current_llm is None:
                llm_block = LLMStreamBlock()
                self._append(llm_block)
                self._current_llm = llm_block
            self._current_llm.append_token(token)
            return

        self._break_llm()

        if t == "llm.model_selected":
            model = str(event.get("model") or "")
            if model:
                self._model = model
                self._update_header("running")
            return

        if t == "session.waiting_for_input":
            self._busy = False
            prompt = self._prompt()
            if prompt is not None:
                prompt.disabled = False
                prompt.read_only = False
                prompt.border_title = "type a message — enter to send, ⌘/⇧/⌥+enter for newline"
                prompt.focus()
            self._update_header("ready")

        elif t == "session.closed":
            self._busy = False
            prompt = self._prompt()
            if prompt is not None:
                prompt.disabled = True
                prompt.read_only = False
                prompt.border_title = "session closed"
            self._update_header("disconnected")

        elif t == "run.started":
            run_id = event.get("run_id", "")
            goal = event.get("goal", "")
            block = RunBlock(run_id, goal)
            self._append(block)
            self._run_block = block

        elif t == "skill.invoked":
            skill_name = event.get("skill_name", "")
            arguments = event.get("arguments", "")
            args_preview = _preview(arguments, 80) if arguments else ""
            args_part = f"  [dim]{args_preview}[/dim]" if args_preview else ""
            self._append(Static(
                f"[bold cyan]/{skill_name}[/bold cyan]{args_part}",
                classes="log-line",
            ))

        elif t == "subagent.started":
            run_id = event.get("run_id", "")
            description = event.get("description", "")
            self._subagent_run_ids[run_id] = description
            self._subagent_start_times[run_id] = time.monotonic()
            short_id = run_id[:8] if len(run_id) >= 8 else run_id
            self._append(Static(
                f"[dim]┌─[/dim] [cyan]{_preview(description, 72)}[/cyan]  [dim]{short_id}[/dim]",
                classes="log-line",
            ))

        elif t == "subagent.finished":
            run_id = event.get("run_id", "")
            status = event.get("status", "")
            description = self._subagent_run_ids.pop(run_id, event.get("description", ""))
            start = self._subagent_start_times.pop(run_id, None)
            elapsed = f"  [dim]{time.monotonic() - start:.1f}s[/dim]" if start is not None else ""
            desc_part = f"[cyan]{_preview(description, 72)}[/cyan]{elapsed}"
            if status == "success":
                self._append(Static(
                    f"[dim]└─[/dim] [bold green]✓[/bold green] {desc_part}",
                    classes="log-line",
                ))
            else:
                self._append(Static(
                    f"[dim]└─[/dim] [bold red]✗[/bold red] {desc_part}",
                    classes="log-line",
                ))

        elif t == "step.started":
            run_id = event.get("run_id", "")
            if run_id in self._subagent_run_ids:
                return
            step = event.get("step", "")
            self._append(Static(
                f"[dim]step {step}[/dim]",
                classes="step-divider",
            ))

        elif t == "tool.call_started":
            tool_use_id = str(event.get("tool_use_id", ""))
            tool_name = str(event.get("tool_name", ""))
            params = event.get("params") or {}
            run_id = event.get("run_id", "")
            tc_block = ToolCallBlock(tool_name, params)
            if run_id in self._subagent_run_ids:
                tc_block.styles.padding = (0, 2, 0, 6)
            self._pending_tool_blocks[tool_use_id] = tc_block
            self._append(tc_block)

        elif t == "tool.call_finished":
            tool_use_id = str(event.get("tool_use_id", ""))
            elapsed_ms = int(event.get("elapsed_ms") or 0)
            output = str(event.get("output") or "")
            if tool_use_id in self._pending_tool_blocks:
                tc_done = self._pending_tool_blocks.pop(tool_use_id)
                tc_done.set_result(output, elapsed_ms)

        elif t == "tool.call_failed":
            tool_use_id = str(event.get("tool_use_id", ""))
            elapsed_ms = int(event.get("elapsed_ms") or 0)
            error_msg = str(event.get("error_message") or "")
            if tool_use_id in self._pending_tool_blocks:
                tc_done = self._pending_tool_blocks.pop(tool_use_id)
                tc_done.set_result(error_msg, elapsed_ms, is_error=True)

        elif t == "run.finished":
            status = event.get("status", "")
            steps = event.get("steps", 0)
            reason = event.get("reason") or ""
            if self._run_block is not None:
                if status == "success":
                    self._run_block.mount(Static(
                        f"[bold green]✓ completed[/bold green]  [dim]{steps} steps[/dim]",
                        classes="run-ok",
                    ))
                else:
                    detail = f"  [dim]{reason}[/dim]" if reason else ""
                    self._run_block.mount(Static(
                        f"[bold red]✗ failed[/bold red]{detail}  [dim]{steps} steps[/dim]",
                        classes="run-err",
                    ))
            self._run_block = None

        elif t == "llm.usage":
            run_id = event.get("run_id", "")
            if run_id in self._subagent_run_ids:
                return
            inp = int(event.get("input_tokens") or 0)
            out = int(event.get("output_tokens") or 0)
            cache_read = int(event.get("cache_read_input_tokens") or 0)
            cache_write = int(event.get("cache_creation_input_tokens") or 0)
            model = str(event.get("model") or "")
            # 累加到 session 总计
            self._session_tokens["in"] += inp
            self._session_tokens["out"] += out
            self._session_tokens["cache_read"] += cache_read
            self._session_tokens["cache_write"] += cache_write
            ses = self._session_tokens
            pct = float(event.get("context_pct") or 0.0)
            self._last_context_pct = pct
            ctx_bar = self._render_ctx_bar(pct)
            # 本轮用量
            parts = [f"in={self._fmt_tokens(inp)}", f"out={self._fmt_tokens(out)}"]
            if cache_read:
                parts.append(f"cache↗{self._fmt_tokens(cache_read)}")
            if cache_write:
                parts.append(f"cache↖{self._fmt_tokens(cache_write)}")
            step_line = f"[dim]  turn: {'  '.join(parts)}  {ctx_bar}[/dim]"
            # 会话累计
            ses_parts = [
                f"in={self._fmt_tokens(ses['in'])}",
                f"out={self._fmt_tokens(ses['out'])}",
            ]
            if ses["cache_read"]:
                ses_parts.append(f"cache↗{self._fmt_tokens(ses['cache_read'])}")
            ses_line = f"[dim]  session: {'  '.join(ses_parts)}  [bold]{model}[/bold][/dim]"
            self._append(Static(f"{step_line}\n{ses_line}", classes="usage"))

        elif t == "context.compacting":
            self._append(Static("[dim]compacting context...[/dim]", classes="log-line"))

        elif t == "context.compacted":
            orig = event.get("original_tokens", 0)
            summary = event.get("summary_tokens", 0)
            self._last_context_pct = 0.0
            self._append(Static(
                f"[bold cyan]⚡ Context compacted[/bold cyan]"
                f"  [dim]original≈{orig} tokens → summary={summary} tokens[/dim]",
                classes="log-line",
            ))

        elif t == "permission.requested":
            tool_use_id = str(event.get("tool_use_id", ""))
            tool_name = str(event.get("tool_name", ""))
            param_preview = str(event.get("param_preview", ""))
            try:
                _focused_repr = repr(self.focused)
            except Exception:
                _focused_repr = "?"
            log.info(
                "permission.requested tool=%s id=%s  app.focused=%s",
                tool_name, tool_use_id, _focused_repr,
            )
            perm_block = PermissionBlock(tool_use_id, tool_name, param_preview)
            self._pending_permission_blocks[tool_use_id] = perm_block
            prompt = self._prompt()
            if prompt is not None:
                prompt.disabled = True
                prompt.border_title = "permission required"
            self._append(perm_block)
            select = PermissionSelect(tool_use_id, tool_name, param_preview)
            self._mount_permission_select(select)
            log.debug("PermissionSelect mounted before #prompt  pending=%d", len(self._pending_permission_blocks))

        elif t == "permission.denied":
            # 处理超时或断连等非用户交互触发的 deny（用户主动 deny 已由 on_permission_select_decided 处理）
            tool_use_id = str(event.get("tool_use_id", ""))
            decision = str(event.get("decision", "denied"))
            if tool_use_id in self._pending_permission_blocks:
                perm_block = self._pending_permission_blocks.pop(tool_use_id)
                perm_block._resolve(decision)
                try:
                    select = self.query_one(PermissionSelect)
                    select.remove()
                except Exception:
                    pass
                if not self._pending_permission_blocks:
                    p = self._prompt()
                    if p is not None:
                        p.disabled = False
                        p.read_only = False
                        p.border_title = "type a message — enter to send, ⌘/⇧/⌥+enter for newline"
                        p.focus()

        elif t == "permission.mode_changed":
            new_mode = str(event.get("new_mode", "normal"))
            self._mode = new_mode
            self._update_header("ready")
            self._update_header("ready")

        elif t == "log.line":
            level = event.get("level", "INFO")
            color = "bold red" if level == "ERROR" else ("yellow" if level == "WARNING" else "dim")
            self._append(Static(
                f"[{color}]{level}[/{color}]  "
                f"[dim]{event.get('source', '')}[/dim]  {event.get('message', '')}",
                classes="log-line",
            ))


# TUI 入口：读取配置并启动 KamaTuiApp
def run(config: SztuConfig, replay_run_id: str | None = None) -> None:
    app = KamaTuiApp(config.host, config.port, replay_run_id=replay_run_id)
    app.run()
