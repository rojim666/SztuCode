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

from sztu_code.core.config import SztuConfig, save_tui_settings
from sztu_code.core.skills.loader import SkillLoader
from sztu_code.core.transport.socket_client import IpcError, SocketClient
from sztu_code.core.trust import add_trusted, is_trusted
from sztu_code.tui.settings import SettingsModal
from sztu_code.tui.theme import (
    THEMES,
    WALLPAPER_ORDER,
    c,
    set_active,
    textual_theme,
    wallpaper_markup,
)

log = logging.getLogger(__name__)

# 日志视图保留的最大子 widget 数，超出后裁剪最旧行以控制长会话的渲染成本
_MAX_LOG_CHILDREN = 600


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

    # 流式刷新最小间隔：高频 token 按节流刷新，避免每个 token 都触发整块重渲染
    _MIN_FLUSH_INTERVAL = 0.03

    # 初始化为空文本块
    def __init__(self) -> None:
        super().__init__("")
        self._text = ""
        self._finalized = False
        self._last_flush = 0.0
        self._flush_pending = False

    # 追加一个 token；达到节流间隔才刷新，未刷新的文本由定时器兜底
    def append_token(self, token: str) -> None:
        if self._finalized:
            return
        self._text += token
        now = time.monotonic()
        if now - self._last_flush >= self._MIN_FLUSH_INTERVAL:
            self._last_flush = now
            self._flush_pending = False
            self.update(self._text)
        elif not self._flush_pending:
            self._flush_pending = True
            if self.is_attached:
                self.set_timer(self._MIN_FLUSH_INTERVAL, self._flush)
            else:
                # 未挂载（如测试直调）时直接刷新，避免文本滞留
                self._flush_pending = False
                self.update(self._text)

    # 定时器兜底：补刷节流窗口内滞留的文本
    def _flush(self) -> None:
        self._flush_pending = False
        if self._finalized:
            return
        self._last_flush = time.monotonic()
        self.update(self._text)

    # 将累积文本渲染为 Markdown，供流式块结束后显示
    def finalize_markdown(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._flush_pending = False
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
        color: $text;
        background: $surface;
        border: tall $accent;
    }
    PermissionSelect:focus {
        border: tall $accent;
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
        log.debug(
            "PermissionSelect.on_focus  has_focus=%s  app.focused=%r",
            self.has_focus,
            self.app.focused,
        )

    # 焦点离开时记录，用于追踪是否被其他控件抢走焦点
    def on_blur(self, event: events.Blur) -> None:
        log.debug("PermissionSelect.on_blur  app.focused=%r", self.app.focused)

    # 生成 Claude Code 风格的键盘优先授权单：上下文在上，决定项在下
    def _render_ui(self) -> str:
        preview = (
            _preview(self._param_preview.strip(), 116)
            if self._param_preview.strip()
            else "no parameters"
        )
        lines = [
            f"[bold {c('accent')}]Permission required[/bold {c('accent')}]  "
            f"[bold]{self._tool_name}[/bold]",
            f"[dim]└─ {preview}[/dim]",
            "",
        ]
        selected_styles = {
            "allow_once": f"bold #111315 on {c('ok')}",
            "always_allow": f"bold #111315 on {c('info')}",
            "deny_once": f"bold #FFFFFF on {c('danger')}",
            "always_deny": f"bold #FFFFFF on {c('danger2')}",
        }
        for i, (decision, label, key_hint) in enumerate(self._CHOICES):
            if i == self._cursor:
                style = selected_styles[decision]
                lines.append(
                    f"[dim]❯[/dim] [{style}] {i + 1}. {label} "
                    f"[/{style}]  [dim]{key_hint}[/dim]"
                )
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
        background: $surface2;
        border-left: solid $accent;
        color: $text;
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
            self._tool_name,
            (
                self._tool_name.replace("_", " ").title(),
                "This action needs your approval.",
            ),
        )
        preview = (
            _preview(self._param_preview.strip(), 140)
            if self._param_preview.strip()
            else "no parameters"
        )
        return (
            f"[bold {c('accent')}]● Approval required[/bold {c('accent')}]  "
            f"[bold]{action}[/bold]\n"
            f"[dim]  {self._tool_name}  └─ {preview}[/dim]\n"
            f"[dim]  {impact}[/dim]"
        )

    # 将块收缩为单行摘要并发布 Resolved 消息
    def _resolve(self, decision: str) -> None:
        if self._resolved:
            return
        self._resolved = True
        allowed = decision in ("allow_once", "always_allow")
        ok_color, danger_color = c("ok"), c("danger")
        icon = f"[bold {ok_color}]✓[/bold {ok_color}]" if allowed else (
            f"[bold {danger_color}]✗[/bold {danger_color}]"
        )
        label = self._LABEL_MAP.get(decision, decision)
        preview = (
            f"  [dim]{_preview(self._param_preview.strip(), 96)}[/dim]"
            if self._param_preview.strip()
            else ""
        )
        self.update(
            f"{icon} approval  [bold]{self._tool_name}[/bold]{preview}  [dim]{label}[/dim]"
        )
        self.post_message(self.Resolved(self, decision))


class SlashCompleteWidget(Static):
    """斜杠命令自动补全弹出框：输入 / 时显示可用 skill 列表并支持键盘筛选与选择。"""

    can_focus = False

    # 每页最多展示的命令条数，超出后通过 PgUp/PgDn 翻页
    _PAGE_SIZE = 10

    DEFAULT_CSS = """
    SlashCompleteWidget {
        height: auto;
        max-height: 14;
        overflow-y: auto;
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
        self._page = 0

    # 根据查询字符串筛选列表，重置光标并重新渲染
    def set_query(self, query: str) -> None:
        q = query.lower()
        self._filtered = [(n, d) for n, d in self._all_items if not q or q in n.lower()]
        self._page = 0
        self._cursor = min(self._cursor, max(0, len(self._filtered) - 1))
        if self.is_attached:
            self._redraw()

    # 当前总页数（至少 1 页）
    def _page_count(self) -> int:
        return max(1, (len(self._filtered) + self._PAGE_SIZE - 1) // self._PAGE_SIZE)

    # 当前页首条在完整列表中的下标
    def _page_start(self) -> int:
        return self._page * self._PAGE_SIZE

    # 当前页实际条数（最后一页可能不满一页）
    def _page_items(self) -> int:
        return min(self._PAGE_SIZE, len(self._filtered) - self._page_start())

    # 向上移动光标并重新渲染；页首再上翻则回到上一页
    def move_up(self) -> None:
        if not self._filtered:
            return
        if self._cursor > 0:
            self._cursor -= 1
        else:
            self._page = (self._page - 1) % self._page_count()
            self._cursor = self._page_items() - 1
        self._redraw()

    # 向下移动光标并重新渲染；页尾再下翻则进入下一页
    def move_down(self) -> None:
        if not self._filtered:
            return
        if self._cursor < self._page_items() - 1:
            self._cursor += 1
        else:
            self._page = (self._page + 1) % self._page_count()
            self._cursor = 0
        self._redraw()

    # 向上翻一页，光标保持在页内对应位置
    def page_up(self) -> None:
        if not self._filtered:
            return
        self._page = (self._page - 1) % self._page_count()
        self._cursor = min(self._cursor, self._page_items() - 1)
        self._redraw()

    # 向下翻一页，光标保持在页内对应位置
    def page_down(self) -> None:
        if not self._filtered:
            return
        self._page = (self._page + 1) % self._page_count()
        self._cursor = min(self._cursor, self._page_items() - 1)
        self._redraw()

    # 选中当前光标项并发布 Selected 消息
    def select_current(self) -> None:
        if not self._filtered:
            return
        index = self._page_start() + self._cursor
        if index < len(self._filtered):
            self.post_message(self.Selected(self._filtered[index][0]))

    # 返回当前是否有可选项
    def has_selection(self) -> bool:
        return len(self._filtered) > 0

    # 鼠标点击补全项时选中该条目（Static 默认不响应点击，按内容行号换算并叠加页偏移）
    def on_click(self, event: events.Click) -> None:
        row = event.y + self.scroll_offset.y
        index = self._page_start() + row
        if 0 <= index < len(self._filtered):
            event.stop()
            self._cursor = row
            self._redraw()
            self.post_message(self.Selected(self._filtered[index][0]))

    def on_mount(self) -> None:
        self._redraw()

    # 渲染当前页的命令列表，高亮光标项，底部显示翻页提示与页码
    def _redraw(self) -> None:
        if not self._filtered:
            self.update("[dim]  no matching commands[/dim]")
            return
        start = self._page_start()
        end = min(start + self._PAGE_SIZE, len(self._filtered))
        lines: list[str] = []
        for i in range(start, end):
            name, desc = self._filtered[i]
            desc_part = f"  [dim]{desc}[/dim]" if desc else ""
            if i - start == self._cursor:
                lines.append(f"  [bold cyan]❯ /{name}[/bold cyan]{desc_part}")
            else:
                lines.append(f"    [cyan]/{name}[/cyan]{desc_part}")
        page_info = f"  [dim]{self._page + 1}/{self._page_count()}[/dim]"
        lines.append(
            "[dim]  ↑↓ navigate   PgUp/PgDn page   tab/enter select   esc dismiss[/dim]"
            f"{page_info}"
        )
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
            elif key == "pageup":
                event.stop()
                event.prevent_default()
                popup.page_up()
                return
            elif key == "pagedown":
                event.stop()
                event.prevent_default()
                popup.page_down()
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
        border: round $border;
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


class _BgRun:
    """一次后台任务运行的状态记录（/bg 启动，随 run 事件更新）。"""

    # 初始化后台任务记录：run_id、目标、启动时间与运行状态
    def __init__(self, run_id: str, goal: str) -> None:
        self.run_id = run_id
        self.goal = goal
        self.started = time.monotonic()
        self.status = "running"  # running | success | failed | interrupted
        self.steps = 0
        self.reason = ""
        self.finished_at: float | None = None

    # 返回任务已持续的秒数（结束后固定为总时长）
    def elapsed(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - self.started


class TrustScreen(Screen[str]):
    """Claude Code 风格的文件夹信任确认屏，Enter 确认 / Esc 取消。"""

    DEFAULT_CSS = """
    TrustScreen { align: center middle; }
    .trust-panel { width: 74; padding: 1 2; background: $surface; border: round $border; }
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
        text_color, info_color = c("text"), c("info")
        lines = [
            f"[bold {text_color}]Accessing workspace:[/bold {text_color}]",
            f"[dim]  {self._path}[/dim]",
            "",
            f"[bold {text_color}]Quick safety check:[/bold {text_color}] "
            "Is this a project you created or one you trust?",
            "[dim](Like your own code, a well-known open source project, "
            "or work from your team).[/dim]",
            "[dim]If not, take a moment to review what's in this folder first.[/dim]",
            "",
            f"[{text_color}]SztuCode will be able to [bold]read, edit, and execute[/bold] ",
            "",
            "[dim]Security guide — review the folder contents before trusting[/dim]",
            "",
        ]
        for i, (label, _decision) in enumerate(self._OPTIONS):
            if i == self._cursor:
                lines.append(
                    f"[bold #111315 on {info_color}]  {label}  [/bold #111315 on {info_color}]"
                )
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
    """Codex-style workspace TUI backed by the existing agent event stream."""

    TITLE = "SztuCode"
    BINDINGS = [
        Binding("ctrl+q", "quit", "quit"),
        Binding("ctrl+s", "open_settings", "settings"),
        Binding("ctrl+shift+a", "mode_auto", "auto mode"),
        Binding("ctrl+shift+e", "mode_accept_edits", "accept edits"),
        Binding("ctrl+shift+p", "mode_plan", "plan mode"),
        Binding("tab", "cycle_mode", "switch mode", priority=True),
    ]
    _MODE_CYCLE = ("auto", "accept_edits", "plan")
    CSS = """
    Screen { layers: wallpaper base; background: $background; overflow: hidden; }
    #wallpaper { layer: wallpaper; width: 1fr; height: 1fr; }

    /* The top rail identifies the workspace without taking over the screen. */
    #header {
        height: 2;
        width: 1fr;
        background: $surface;
        color: $text;
        padding: 0 2;
        content-align: left middle;
        border-bottom: solid $border;
        text-overflow: ellipsis;
        overflow: hidden;
    }
    #transcript-label {
        height: 1;
        width: 1fr;
        background: $surface2;
        color: $text-muted;
        padding: 0 2;
        content-align: left middle;
        text-style: bold;
    }
    #welcome-card {
        height: auto;
        width: 1fr;
        margin: 1 2 0 2;
        padding: 1 2;
        background: $surface;
        border: round $border2;
        color: $text;
    }
    #log-view {
        height: 1fr;
        min-height: 4;
        max-height: 8;
        width: 1fr;
        background: transparent;
        padding: 0 1;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
    }
    #bg-panel {
        display: none;
        height: auto;
        max-height: 8;
        background: $surface;
        border: round $border;
        margin: 0 2 1 2;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }
    #bg-panel.visible { display: block; }
    #composer-label {
        height: 1;
        width: 1fr;
        background: $surface2;
        color: $accent;
        padding: 0 2;
        content-align: left middle;
        text-style: bold;
        border-top: solid $border;
    }
    #prompt {
        width: 1fr;
        height: 5;
        min-height: 4;
        max-height: 8;
        background: $surface;
        color: $text;
        border: round $border2;
        margin: 0 2 1 2;
        padding: 1 1;
    }
    #prompt:focus {
        border: round $accent;
    }
    #status {
        height: 1;
        width: 1fr;
        background: $surface;
        color: $text-muted;
        padding: 0 2;
        content-align: left middle;
        border-top: solid $border;
        text-overflow: ellipsis;
        overflow: hidden;
    }
    #footer {
        height: 1;
        width: 1fr;
        background: $surface;
        color: $text-muted;
        padding: 0 2;
        content-align: left middle;
        text-overflow: ellipsis;
        overflow: hidden;
    }
    #composer-spacer {
        height: 4;
        width: 1fr;
        background: transparent;
    }
    #banner { display: none; }
    Static.user-turn { color: $text; padding: 1 2 0 2; }
    Static.run-header { color: $text-muted; padding: 1 2 0 2; }
    Static.step-divider { color: $text-muted; padding: 0 2; }
    Static.run-ok { color: $ok; padding: 0 2 1 2; }
    Static.run-err { color: $danger; padding: 0 2 1 2; }
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
        session_id: str | None = None,
        initial_prompt: str | None = None,
        output_last_message: str | None = None,
        theme: str | None = None,
        wallpaper: str | None = None,
    ) -> None:
        super().__init__()
        for name in THEMES:
            self.register_theme(textual_theme(name))
        self._theme_name = theme if theme in THEMES else "dark"
        self._wallpaper_name = wallpaper if wallpaper in WALLPAPER_ORDER else "none"
        self.theme = textual_theme(self._theme_name).name
        set_active(self._theme_name)
        self._host = host
        self._port = port
        self._replay_run_id = replay_run_id
        self._client: SocketClient | None = None
        self._current_llm: LLMStreamBlock | None = None
        self._pending_tool_blocks: dict[str, ToolCallBlock] = {}
        self._pending_permission_blocks: dict[str, PermissionBlock] = {}
        self._session_id: str | None = session_id
        self._initial_prompt = initial_prompt
        self._output_last_message = output_last_message
        self._last_message_parts: list[str] = []
        self._output_last_message_error: OSError | None = None
        self._workspace: dict[str, Any] | None = None
        self._project_path = str(Path(project_path or Path.cwd()).resolve())
        self._read_only = read_only
        self._force_trust = trust
        self._model = "loading…"
        self._busy = False
        self._state = "connecting"
        self._last_context_pct: float = 0.0
        self._session_tokens: dict[str, int] = {
            "in": 0,
            "out": 0,
            "cache_read": 0,
            "cache_write": 0,
        }
        self._slash_items: list[tuple[str, str]] = []
        self._subagent_run_ids: dict[str, str] = {}  # child run_id -> description
        self._subagent_start_times: dict[str, float] = {}  # child run_id -> start time
        self._run_block: RunBlock | None = None  # 当前活动 run 的输出块
        self._mode: str = "plan" if read_only else "auto"  # 只读模式锁定 plan
        self._bg_run_ids: set[str] = set()  # 后台任务 run_id 集合（事件按此路由）
        self._bg_runs: dict[str, _BgRun] = {}  # run_id -> 后台任务状态

    def compose(self) -> ComposeResult:
        yield Static("", id="wallpaper")
        yield Label(
            f"[bold {c('ok')}]SztuCode[/bold {c('ok')}]  [dim]connecting...[/dim]",
            id="header",
        )
        yield Static(
            f"[bold {c('text')}]AGENT TRANSCRIPT[/bold {c('text')}]  "
            f"[dim]live session events[/dim]",
            id="transcript-label",
        )
        yield Static(self._welcome_text(), id="welcome-card")
        yield VerticalScroll(id="log-view")
        yield VerticalScroll(id="bg-panel")
        yield Static(
            f"[bold {c('accent')}]PROMPT[/bold {c('accent')}]  "
            f"[dim]send a message to continue the session[/dim]",
            id="composer-label",
        )
        yield ChatTextArea(id="prompt", show_line_numbers=False)
        yield Static("", id="composer-spacer")
        yield Static("", id="status")
        yield Static(
            "[dim]Ctrl+C[/dim] interrupt   [dim]Tab[/dim] mode   "
            "[dim]Ctrl+S[/dim] settings   [dim]Ctrl+Q[/dim] quit",
            id="footer",
        )

    def on_mount(self) -> None:
        self._slash_items = self._builtin_slash_items()
        # 独立 group：避免被 socket 循环的 exclusive worker 取消
        self.run_worker(
            self._load_slash_items(), name="slash_items", group="slash", exclusive=False
        )
        self._render_wallpaper()
        prompt = self.query_one("#prompt", ChatTextArea)
        prompt.disabled = True
        prompt.border_title = "connecting..."
        if self._needs_trust_check():
            self.push_screen(TrustScreen(self._project_path), self._on_trust_result)
        else:
            self._start_socket_loop()

    # 终端尺寸变化时按新尺寸重新生成背景壁纸
    def on_resize(self, event: events.Resize) -> None:
        if self._wallpaper_name != "none":
            self._render_wallpaper(event.size.width, event.size.height)

    # 生成并刷新背景壁纸层；样式为 none 时清空背景
    def _render_wallpaper(self, width: int | None = None, height: int | None = None) -> None:
        try:
            layer = self.query_one("#wallpaper", Static)
        except Exception:
            return
        if self._wallpaper_name == "none":
            layer.update("")
            return
        w = width if width is not None else self.size.width
        h = height if height is not None else self.size.height
        markup = wallpaper_markup(self._wallpaper_name, w, h)
        layer.update(markup)

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
    def _welcome_text(self) -> str:
        project_path = self._project_path
        if self._workspace is not None:
            project_path = str(self._workspace.get("path") or project_path)
        return (
            f"[bold {c('ok')}]›  SztuCode[/bold {c('ok')}]  "
            f"[dim]workspace[/dim]\n"
            f"[dim]model:[/dim]  [bold]{self._model}[/bold]  "
            f"[{c('info')}]/model[/{c('info')}] [dim]to change[/dim]\n"
            f"[dim]directory:[/dim] {_preview(project_path, 96)}"
        )

    # 刷新顶部启动卡片中的模型和目录信息
    def _update_welcome_card(self) -> None:
        try:
            self.query_one("#welcome-card", Static).update(self._welcome_text())
        except Exception:
            return

    # 返回当前模式的富文本标签，用于 header 栏显示
    def _mode_label(self) -> str:
        if self._read_only:
            return f"[bold #111315 on {c('accent')}] READONLY [/bold #111315 on {c('accent')}]"
        colors = {"auto": c("ok"), "accept_edits": c("info"), "plan": c("accent")}
        labels = {"auto": "AUTO", "accept_edits": "EDITS", "plan": "PLAN"}
        color = colors.get(self._mode, c("ok"))
        label = labels.get(self._mode, self._mode.upper())
        return f"[bold #111315 on {color}] {label} [/bold #111315 on {color}]"

    # 返回内建斜杠命令（不依赖技能扫描，首帧立即可用）
    def _builtin_slash_items(self) -> list[tuple[str, str]]:
        return [
            ("compact", "compress context window"),
            ("security-review", "review branch changes for security issues"),
            ("batch", "orchestrate independent work in parallel"),
            ("review-pr", "review a GitHub pull request"),
            ("pr-comments", "fetch GitHub pull request comments"),
            ("commit", "commit the intended git changes"),
            ("create-pr", "create a GitHub pull request"),
            ("new", "start a fresh task"),
            ("workspace", "open a local repository"),
            ("files", "show workspace file tree"),
            ("search", "search files in the workspace"),
            ("changes", "show uncommitted changes"),
            ("diff", "inspect a file diff"),
            ("bg", "run a task in the background"),
            ("bgs", "toggle background task list"),
            ("theme", "switch light/dark theme"),
            ("wallpaper", "cycle background style"),
            ("model", "change the active model"),
            ("settings", "open settings dialog"),
        ]

    # 构建斜杠命令候选列表：内建命令 + 所有已注册 skill
    def _build_slash_items(self) -> list[tuple[str, str]]:
        items = self._builtin_slash_items()
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

    # 后台加载技能斜杠命令：技能扫描是同步 CPU 工作，用线程执行避免阻塞首帧
    async def _load_slash_items(self) -> None:
        try:
            self._slash_items = await asyncio.to_thread(self._build_slash_items)
        except Exception:
            log.exception("failed to load slash items")

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
        if self._settings_modal_open():
            return  # 设置弹窗打开时权限快捷键由弹窗自行处理
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
        if self._output_last_message:
            try:
                Path(self._output_last_message).expanduser().write_text(
                    "".join(self._last_message_parts), encoding="utf-8"
                )
            except OSError as error:
                self._output_last_message_error = error
        self.exit()

    @property
    def output_last_message_error(self) -> OSError | None:
        return self._output_last_message_error

    # 打开弹窗式设置界面；已打开时不重复入栈，关闭后焦点还给输入框
    def action_open_settings(self) -> None:
        if isinstance(self.screen, SettingsModal):
            return
        self.push_screen(SettingsModal(), callback=lambda _result: self._refocus_prompt())

    # 打开模型选择设置，并把焦点直接放到 model 行
    def action_open_model(self) -> None:
        if isinstance(self.screen, SettingsModal):
            return
        self.push_screen(
            SettingsModal(focus_row="model"),
            callback=lambda _result: self._refocus_prompt(),
        )

    # 设置弹窗关闭后把键盘焦点还给输入框（若其可输入）
    def _refocus_prompt(self) -> None:
        prompt = self._prompt()
        if prompt is not None and not prompt.disabled:
            prompt.focus()

    # 切换到 Auto 模式：自动批准所有工具调用
    async def action_mode_auto(self) -> None:
        await self._set_mode("auto")

    # 切换到 Accept Edits 模式：自动批准编辑类工具（write_file, note_save）
    async def action_mode_accept_edits(self) -> None:
        await self._set_mode("accept_edits")

    # 切换到 Plan 模式：只允许只读工具，拒绝所有写入和执行
    async def action_mode_plan(self) -> None:
        await self._set_mode("plan")

    # 设置弹窗是否处于打开状态（未运行的 App 上按未打开处理）
    def _settings_modal_open(self) -> bool:
        try:
            return isinstance(self.screen, SettingsModal)
        except Exception:
            return False

    # Tab 循环 Auto、Accept Edits、Plan；设置弹窗打开时不响应
    async def action_cycle_mode(self) -> None:
        if self._settings_modal_open():
            return
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
            else:
                log.warning(
                    "mode switch rejected target=%s error=%s",
                    mode,
                    result.get("error", "unknown"),
                )
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
                self._update_welcome_card()
            else:
                self._model = "not configured"
                self._update_welcome_card()
            self._update_header("ready")
        except (IpcError, RuntimeError, OSError):
            self._model = "unavailable"
            self._update_welcome_card()
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
        # 后台任务：/bg <goal> 在独立会话启动，/bgs 切换任务列表面板
        if content == "/bg":
            event.text_area.text = ""
            self._append(Static("[yellow]usage: /bg <goal>[/yellow]", classes="log-line"))
            return
        if content.startswith("/bg "):
            event.text_area.text = ""
            self.run_worker(
                self._start_background_run(content.removeprefix("/bg ").strip()),
                name="bg_run",
                exclusive=False,
            )
            return
        if content == "/bgs":
            event.text_area.text = ""
            self._toggle_bg_panel()
            return
        # 明暗主题与背景壁纸切换
        if content == "/theme":
            event.text_area.text = ""
            self._cycle_theme()
            return
        if content == "/wallpaper":
            event.text_area.text = ""
            self._cycle_wallpaper()
            return
        # 打开弹窗式设置界面
        if content == "/settings":
            event.text_area.text = ""
            self.action_open_settings()
            return
        if content == "/model":
            event.text_area.text = ""
            self.action_open_model()
            return
        # 检测 /system-prompt 指令
        if content == "/system-prompt":
            event.text_area.text = ""
            self.run_worker(self._show_system_prompt(), name="system_prompt", exclusive=False)
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
        prompt.border_title = "agent is working  ·  Ctrl+C to interrupt"
        self._append(Static(f"[bold]>[/bold] {content}", classes="user-turn"))
        self._update_header("running")
        self.run_worker(self._do_send_message(content), name="send_message", exclusive=False)

    # 在 worker 中执行手动压缩命令，完成后显示结果横幅
    # 打印当前分层系统提示词（静态段 + 边界 + 发现的指令文件预览）
    async def _show_system_prompt(self) -> None:
        from sztu_code.core.prompts.system_prompt import (
            DYNAMIC_BOUNDARY,
            build_static_base,
            discover_instruction_files,
        )

        body = build_static_base() + f"\n\n{DYNAMIC_BOUNDARY}"
        if self._workspace is not None:
            entries = discover_instruction_files(Path(self._workspace["path"]))
            body += f"\n\n# Project instructions ({len(entries)} files)"
            for label, content in entries:
                body += f"\n## {label}\n{content[:800]}"
        self._append(Static(f"[bold cyan]/system-prompt[/bold cyan]\n{body}", classes="log-line"))

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
            self._append(Static(
                "[yellow]open a workspace first: /workspace <folder>[/yellow]",
                classes="log-line",
            ))
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
            self._append(Static(
                "[yellow]open a workspace first: /workspace <folder>[/yellow]",
                classes="log-line",
            ))
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
            self._append(Static(
                "[yellow]open a workspace first: /workspace <folder>[/yellow]",
                classes="log-line",
            ))
            return
        try:
            result = await self._client.send_command("change.list", {
                "workspace_id": self._workspace["workspace_id"],
            })
            changes = result.get("changes", [])
            body = "\n".join(
                f"  {change.get('index_status')}{change.get('worktree_status')}  "
                f"{change.get('path')}"
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
            self._append(Static(
                "[yellow]open a workspace first: /workspace <folder>[/yellow]",
                classes="log-line",
            ))
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
                prompt.border_title = "message  ·  Enter send  ·  Shift+Enter newline"
            self._update_header("ready")
            self._append(Static(f"[red]send error: {e}[/red]", classes="log-line"))

    # 通过 agent.run 在独立会话中启动一次后台任务，立即返回 run_id 并登记状态
    async def _start_background_run(self, goal: str) -> None:
        if self._client is None:
            self._append(Static("[yellow]not connected[/yellow]", classes="log-line"))
            return
        if not goal:
            self._append(Static("[yellow]usage: /bg <goal>[/yellow]", classes="log-line"))
            return
        try:
            result = await self._client.send_command("agent.run", {"goal": goal})
            run_id = str(result.get("run_id") or "")
            if not run_id:
                raise RuntimeError("daemon returned no run_id")
            self._bg_run_ids.add(run_id)
            self._bg_runs[run_id] = _BgRun(run_id, goal)
            self._append(Static(
                f"[bold cyan]⏳ background[/bold cyan]  {_preview(goal, 72)}  "
                f"[dim]{run_id[:8]}[/dim]",
                classes="log-line",
            ))
            self._update_status()
            self._render_bg_panel()
        except (IpcError, RuntimeError, OSError) as e:
            self._append(Static(f"[red]background error: {e}[/red]", classes="log-line"))

    # 处理后台任务的 run 事件：只更新状态面板，不混入主日志流
    def _handle_bg_event(self, event: dict[str, Any]) -> None:
        t = event.get("type", "")
        run = self._bg_runs.get(str(event.get("run_id") or ""))
        if run is None:
            return
        if t == "run.started":
            run.status = "running"
        elif t == "step.started":
            run.steps = int(event.get("step") or 0)
        elif t == "run.finished":
            run.status = str(event.get("status") or "failed")
            run.reason = str(event.get("reason") or "")
            run.steps = int(event.get("steps") or run.steps)
            run.finished_at = time.monotonic()
        else:
            return
        if t == "run.finished":
            # 在主时间线收尾：绿/黄/红区分成功、中断与失败
            color = "green" if run.status == "success" else (
                "yellow" if run.status == "interrupted" else "red"
            )
            icon = "✓" if run.status == "success" else (
                "⏸" if run.status == "interrupted" else "✗"
            )
            self._append(Static(
                f"[dim]└─[/dim] [bold {color}]{icon}[/bold {color}] "
                f"[cyan]bg:[/cyan] {_preview(run.goal, 72)}  "
                f"[dim]{run.run_id[:8]} · {run.steps} steps · {run.elapsed():.0f}s[/dim]",
                classes="log-line",
            ))
        self._update_status()
        self._render_bg_panel()

    # 切换后台任务面板的显示/隐藏
    def _toggle_bg_panel(self) -> None:
        try:
            panel = self.query_one("#bg-panel", VerticalScroll)
        except Exception:
            return
        if "visible" in panel.classes:
            panel.remove_class("visible")
        else:
            panel.add_class("visible")
            self._render_bg_panel()

    # 重绘后台任务面板：每个后台 run 一行状态摘要，无任务时自动收起
    def _render_bg_panel(self) -> None:
        try:
            panel = self.query_one("#bg-panel", VerticalScroll)
        except Exception:
            return
        panel.remove_children()
        if not self._bg_runs:
            panel.remove_class("visible")
            return
        if any(run.status == "running" for run in self._bg_runs.values()):
            panel.add_class("visible")
        for run in list(self._bg_runs.values())[-8:]:
            icon = {
                "running": f"[{c('info')}]●[/{c('info')}]",
                "success": f"[{c('ok')}]✓[/{c('ok')}]",
                "failed": f"[{c('danger')}]✗[/{c('danger')}]",
                "interrupted": f"[{c('warn')}]⏸[/{c('warn')}]",
            }.get(run.status, "○")
            detail = f"  [dim]{run.reason}[/dim]" if run.reason and run.status != "running" else ""
            panel.mount(Static(
                f"{icon} {_preview(run.goal, 56)}  "
                f"[dim]{run.run_id[:8]} · {run.steps} steps · {run.elapsed():.0f}s[/dim]{detail}",
                classes="log-line",
            ))
        panel.scroll_end(animate=False)

    # 直接应用指定主题并持久化到客户端设置
    def _apply_theme(self, name: str) -> None:
        if name not in THEMES:
            return
        self._theme_name = name
        self.theme = textual_theme(name).name
        set_active(name)
        self._update_status()
        self.run_worker(self._persist_tui_settings(), name="persist_tui", exclusive=False)

    # 循环切换明暗主题并追加日志
    def _cycle_theme(self) -> None:
        order = tuple(THEMES.keys())
        self._apply_theme(order[(order.index(self._theme_name) + 1) % len(order)])
        self._append(Static(
            f"[bold cyan]theme[/bold cyan]  [bold]{self._theme_name}[/bold]",
            classes="log-line",
        ))

    # 直接应用指定壁纸样式并持久化到客户端设置
    def _apply_wallpaper(self, name: str) -> None:
        if name not in WALLPAPER_ORDER:
            return
        self._wallpaper_name = name
        self._render_wallpaper()
        self._update_status()
        self.run_worker(self._persist_tui_settings(), name="persist_tui", exclusive=False)

    # 循环切换壁纸样式并追加日志
    def _cycle_wallpaper(self) -> None:
        self._apply_wallpaper(WALLPAPER_ORDER[
            (WALLPAPER_ORDER.index(self._wallpaper_name) + 1) % len(WALLPAPER_ORDER)
        ])
        self._append(Static(
            f"[bold cyan]wallpaper[/bold cyan]  [bold]{self._wallpaper_name}[/bold]",
            classes="log-line",
        ))

    # 将主题与壁纸选择写入客户端设置（尽力而为，失败仅记日志）
    async def _persist_tui_settings(self) -> None:
        try:
            await asyncio.to_thread(
                save_tui_settings, theme=self._theme_name, wallpaper=self._wallpaper_name
            )
        except Exception:
            log.exception("failed to persist tui settings")

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
                    p.border_title = "message  ·  Enter send  ·  Shift+Enter newline"
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
        self._trim_log(log_view)
        log_view.scroll_end(animate=False)

    # 裁剪最旧的历史行，防止 widget 无限增长拖慢渲染；活动 run 块、流式块与未决工具/权限块受保护
    def _trim_log(self, log_view: VerticalScroll) -> None:
        overflow = len(log_view.children) - _MAX_LOG_CHILDREN
        if overflow <= 0:
            return
        protected: set[Widget] = set()
        if self._run_block is not None:
            protected.add(self._run_block)
        if self._current_llm is not None:
            protected.add(self._current_llm)
        protected.update(self._pending_tool_blocks.values())
        protected.update(self._pending_permission_blocks.values())
        removed = 0
        for child in list(log_view.children):
            if removed >= overflow:
                break
            if child in protected:
                continue
            try:
                child.remove()
            except Exception:
                continue
            removed += 1

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
            color = c("danger")
        elif pct >= 0.75:
            color = c("warn")
        elif pct >= 0.50:
            color = c("ok")
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

    # 根据连接和运行状态刷新顶部标题，并联动底部状态栏
    def _update_header(self, state: str) -> None:
        self._state = state
        try:
            header = self.query_one("#header", Label)
        except NoMatches:
            return
        project_path = self._project_path
        if self._workspace is not None:
            project_path = str(self._workspace.get("path") or project_path)
        project_name = Path(project_path).name or project_path
        project_name = _preview(project_name, 28)
        location = _preview(project_path, 48)
        workspace = (
            f"[bold {c('info')}]{project_name}[/bold {c('info')}]  "
            f"[dim]{location}[/dim]"
        )
        model = f"[dim]model[/dim] [{c('text-muted')}]{self._model}[/{c('text-muted')}]"
        color = {
            "ready": "green",
            "running": "yellow",
            "disconnected": "red",
            "connecting": "dim",
        }.get(state, "dim")
        header.update(
            f"[bold {c('ok')}]SztuCode[/bold {c('ok')}]  {workspace}  "
            f"{model}  {self._mode_label()}  [{color}]● {state}[/{color}]"
        )
        self._update_status()

    # 刷新底部状态栏：会话用量、上下文占用、后台任务数与当前主题
    def _update_status(self) -> None:
        try:
            status = self.query_one("#status", Static)
        except Exception:
            return
        ses = self._session_tokens
        parts = [f"in={self._fmt_tokens(ses['in'])}", f"out={self._fmt_tokens(ses['out'])}"]
        if ses["cache_read"]:
            parts.append(f"cache↗{self._fmt_tokens(ses['cache_read'])}")
        if ses["cache_write"]:
            parts.append(f"cache↖{self._fmt_tokens(ses['cache_write'])}")
        bg_running = sum(1 for run in self._bg_runs.values() if run.status == "running")
        bg_part = f"bg {bg_running}/{len(self._bg_runs)}" if self._bg_runs else "bg 0"
        state_color = {
            "ready": "green",
            "running": "yellow",
            "disconnected": "red",
            "connecting": "dim",
        }.get(self._state, "dim")
        status.update(
            f"[dim]session[/dim] {' '.join(parts)}  "
            f"{self._render_ctx_bar(self._last_context_pct)}  "
            f"[{c('info')}]{bg_part}[/{c('info')}]  "
            f"[dim]theme[/dim] {self._theme_name}  [{state_color}]{self._state}[/{state_color}]"
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
                        "workflow.*",
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
                    prompt.border_title = "message  ·  Enter send  ·  Shift+Enter newline"
                    prompt.focus()
                self._update_header("ready")
                if self._initial_prompt:
                    initial_prompt = self._initial_prompt
                    self._initial_prompt = None
                    self.run_worker(
                        self._do_send_message(initial_prompt),
                        name="initial_prompt",
                        group="session",
                        exclusive=False,
                    )
                await loop_task
            except IpcError as e:
                header.update(
                    f"[bold {c('ok')}]SztuCode[/bold {c('ok')}]  "
                    f"[red]subscribe error: {e}[/red]"
                )
            finally:
                if not loop_task.done():
                    loop_task.cancel()
                self._client = None
                prompt = self._prompt()
                if prompt is not None:
                    prompt.disabled = True
                    prompt.read_only = False
                    prompt.border_title = "connection lost  ·  retrying"
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

        # 后台任务的 run 事件按 run_id 归属路由到任务面板，不进入主日志流
        run_id = event.get("run_id")
        if run_id is not None and run_id in self._bg_run_ids:
            self._handle_bg_event(event)
            return

        session_id = event.get("session_id")
        if session_id is not None and session_id != self._session_id:
            return

        if t == "llm.token":
            token = event.get("token", "")
            self._last_message_parts.append(str(token))
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
                self._update_welcome_card()
                self._update_header("running")
            return

        if t == "session.waiting_for_input":
            self._busy = False
            prompt = self._prompt()
            if prompt is not None:
                prompt.disabled = False
                prompt.read_only = False
                prompt.border_title = "message  ·  Enter send  ·  Shift+Enter newline"
                prompt.focus()
            self._update_header("ready")

        elif t == "session.closed":
            self._busy = False
            prompt = self._prompt()
            if prompt is not None:
                prompt.disabled = True
                prompt.read_only = False
                prompt.border_title = "session closed  ·  start a new session to continue"
            self._update_header("disconnected")

        elif t == "run.started":
            self._last_message_parts.clear()
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
            elif status == "interrupted":
                self._append(Static(
                    f"[dim]└─[/dim] [bold yellow]⏸[/bold yellow] {desc_part}",
                    classes="log-line",
                ))
            else:
                self._append(Static(
                    f"[dim]└─[/dim] [bold red]✗[/bold red] {desc_part}",
                    classes="log-line",
                ))

        elif t == "workflow.started":
            tasks = event.get("tasks") or []
            lines = [
                f"[bold cyan]多智能体工作流[/bold cyan]  [dim]{len(tasks)} 个任务[/dim]"
            ]
            for task in tasks:
                dependencies = ", ".join(task.get("dependencies") or []) or "无"
                lines.append(
                    f"  [dim]○[/dim] ({task.get('owner', 'agent')}) "
                    f"{_preview(str(task.get('title', '')), 64)}  "
                    f"[dim]依赖: {dependencies}[/dim]"
                )
            self._append(Static("\n".join(lines), classes="log-line"))

        elif t == "workflow.task_updated":
            task = event.get("task") or {}
            status = str(task.get("status") or "pending")
            icons = {
                "running": "[bold cyan]●[/bold cyan]",
                "succeeded": "[bold green]✓[/bold green]",
                "failed": "[bold red]✗[/bold red]",
                "blocked": "[bold yellow]⊘[/bold yellow]",
                "cancelled": "[bold yellow]■[/bold yellow]",
                "timed_out": "[bold yellow]⌛[/bold yellow]",
                "rejected": "[bold red]↩[/bold red]",
            }
            if status != "pending":
                error = str(task.get("error") or "")
                detail = f"  [dim]{_preview(error, 80)}[/dim]" if error else ""
                self._append(Static(
                    f"{icons.get(status, '○')} ({task.get('owner', 'agent')}) "
                    f"{_preview(str(task.get('title', '')), 64)}{detail}",
                    classes="log-line",
                ))

        elif t == "workflow.handoff":
            artifact = event.get("artifact") or {}
            escalations = artifact.get("scope_escalations") or []
            escalation = (
                f"  [yellow]范围审批: {', '.join(escalations)}[/yellow]"
                if escalations
                else ""
            )
            self._append(Static(
                f"[dim]交接[/dim] ({artifact.get('role', 'agent')}) "
                f"{_preview(str(artifact.get('summary', '')), 88)}{escalation}",
                classes="log-line",
            ))

        elif t == "workflow.reviewed":
            decision = str(event.get("decision") or "return")
            label = "接受" if decision == "accept" else "退回"
            color = "green" if decision == "accept" else "red"
            self._append(Static(
                f"[bold {color}]Reviewer {label}[/bold {color}]  "
                f"{_preview(str(event.get('conclusion') or ''), 100)}",
                classes="log-line",
            ))

        elif t == "workflow.finished":
            status = str(event.get("status") or "failed")
            color = "green" if status == "succeeded" else "red"
            self._append(Static(
                f"[bold {color}]工作流 {status}[/bold {color}]  "
                f"[dim]tokens={event.get('total_tokens', 0)} "
                f"elapsed={float(event.get('elapsed_s') or 0.0):.1f}s[/dim]",
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
                elif status == "interrupted":
                    # 预算/上限耗尽：区别于失败，提示用户可发送消息续跑
                    detail = f"  [dim]{reason}[/dim]" if reason else ""
                    self._run_block.mount(Static(
                        f"[bold yellow]⏸ 预算用尽，可继续[/bold yellow]{detail}"
                        f"  [dim]{steps} steps[/dim]  （发送『继续』可续跑）",
                        classes="run-interrupted",
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
            self._update_status()

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
            log.debug(
                "PermissionSelect mounted before #prompt  pending=%d",
                len(self._pending_permission_blocks),
            )

        elif t == "permission.denied":
            # 处理超时或断连等非用户交互 deny（主动 deny 已由 select 回调处理）
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
                        p.border_title = "message  ·  Enter send  ·  Shift+Enter newline"
                        p.focus()

        elif t == "permission.mode_changed":
            new_mode = str(event.get("new_mode", "normal"))
            self._mode = new_mode
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
    app.run(inline=True, inline_no_clear=True)
