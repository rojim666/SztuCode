# SztuCode 桌面 GUI 客户端 —— 类似 Codex Desktop 的本地 Agent 交互界面
from __future__ import annotations

import asyncio
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Any

from sztu_code.core.transport.socket_client import IpcError, SocketClient

# ── 颜色主题 ──────────────────────────────────────────────────────────────
BG = "#1e1e2e"
SIDEBAR_BG = "#181825"
CHAT_BG = "#1e1e2e"
USER_BUBBLE = "#3b82f6"
AGENT_BUBBLE = "#313244"
TOOL_CARD = "#45475a"
TEXT_PRIMARY = "#cdd6f4"
TEXT_SECONDARY = "#a6adc8"
TEXT_MUTED = "#6c7086"
ACCENT_GREEN = "#a6e3a1"
ACCENT_RED = "#f38ba8"
ACCENT_YELLOW = "#f9e2af"
INPUT_BG = "#313244"
BORDER = "#45475a"
FONT = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO = ("Cascadia Code", 10)
FONT_BOLD = ("Segoe UI", 11, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")


# ── 事件队列条目 ──────────────────────────────────────────────────────────
class _UIEvent:
    __slots__ = ("kind", "data")
    def __init__(self, kind: str, data: Any = None) -> None:
        self.kind = kind
        self.data = data


# ── 聊天消息模型 ──────────────────────────────────────────────────────────
class _Message:
    __slots__ = ("role", "content", "tool_calls")
    def __init__(self, role: str, content: str = "") -> None:
        self.role = role      # "user" | "agent" | "tool"
        self.content = content
        self.tool_calls: list[dict[str, Any]] = []


# ── 桌面应用主窗口 ────────────────────────────────────────────────────────
class SztuCodeDesktop(tk.Tk):
    """基于 tkinter 的桌面 GUI 客户端，通过 TCP 连接到 sztu-code daemon。"""

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._session_id: str | None = None
        self._messages: list[_Message] = []
        self._pending_tools: dict[str, _Message] = {}  # tool_use_id → tool msg
        self._ui_queue: queue.Queue[_UIEvent] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._mode: str = "normal"  # 当前权限模式
        self._session_tokens: dict[str, int] = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}

        self._setup_ui()
        self._start_connection()

        # 每 50ms 从队列取 UI 事件并处理
        self._poll_ui_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 搭建 ────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        self.title("SztuCode Desktop")
        self.geometry("900x700")
        self.minsize(600, 400)
        self.configure(bg=BG)

        # 顶部标题栏
        self._header = tk.Frame(self, bg=SIDEBAR_BG, height=44)
        self._header.pack(fill=tk.X, side=tk.TOP)
        self._header.pack_propagate(False)

        title = tk.Label(
            self._header, text="SztuCode Desktop",
            fg=TEXT_PRIMARY, bg=SIDEBAR_BG, font=FONT_TITLE,
        )
        title.pack(side=tk.LEFT, padx=16, pady=8)

        self._status_dot = tk.Canvas(
            self._header, width=12, height=12, bg=SIDEBAR_BG, highlightthickness=0,
        )
        self._status_dot.pack(side=tk.LEFT, padx=(0, 4))
        self._dot = self._status_dot.create_oval(2, 2, 10, 10, fill=ACCENT_RED, outline="")

        self._status_label = tk.Label(
            self._header, text="disconnected",
            fg=ACCENT_RED, bg=SIDEBAR_BG, font=FONT_SMALL,
        )
        self._status_label.pack(side=tk.LEFT)

        self._addr_label = tk.Label(
            self._header, text=f"  {self._host}:{self._port}",
            fg=TEXT_MUTED, bg=SIDEBAR_BG, font=FONT_SMALL,
        )
        self._addr_label.pack(side=tk.LEFT)

        # 模式切换按钮
        self._mode_buttons = tk.Frame(self._header, bg=SIDEBAR_BG)
        self._mode_buttons.pack(side=tk.RIGHT, padx=8)

        for label, mode, color in [
            ("N", "normal", "#6c7086"),
            ("P", "plan", "#f9e2af"),
            ("E", "accept_edits", "#a6e3a1"),
            ("A", "auto", "#89b4fa"),
        ]:
            btn = tk.Button(
                self._mode_buttons, text=label, font=("Segoe UI", 9, "bold"),
                bg=color if label in ("N",) else SIDEBAR_BG,
                fg=color, borderwidth=0, padx=8, pady=2,
                cursor="hand2", relief=tk.FLAT,
                activebackground=color, activeforeground=BG,
                command=lambda m=mode: self._set_mode(m),
            )
            btn.pack(side=tk.RIGHT, padx=2)
            self._mode_buttons._btns = getattr(self._mode_buttons, "_btns", {})  # type: ignore[attr-defined]
            self._mode_buttons._btns[mode] = btn  # type: ignore[attr-defined]

        # 主聊天区域
        chat_frame = tk.Frame(self, bg=CHAT_BG)
        chat_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self._chat_canvas = tk.Canvas(chat_frame, bg=CHAT_BG, highlightthickness=0)
        self._chat_scrollbar = ttk.Scrollbar(
            chat_frame, orient=tk.VERTICAL, command=self._chat_canvas.yview,
        )
        self._chat_inner = tk.Frame(self._chat_canvas, bg=CHAT_BG)

        self._chat_inner.bind("<Configure>", lambda e: self._chat_canvas.configure(
            scrollregion=self._chat_canvas.bbox("all"),
        ))
        self._chat_canvas_window = self._chat_canvas.create_window(
            (0, 0), window=self._chat_inner, anchor="nw", tags="inner",
        )

        self._chat_canvas.configure(yscrollcommand=self._chat_scrollbar.set)
        self._chat_canvas.bind_all("<MouseWheel>", lambda e: self._chat_canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units",
        ))

        self._chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 让内部 frame 宽度跟随 canvas
        self._chat_canvas.bind("<Configure>", self._on_canvas_resize)

        # 底部输入区
        input_frame = tk.Frame(self, bg=INPUT_BG, height=80)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM)
        input_frame.pack_propagate(False)

        self._input_text = tk.Text(
            input_frame, bg=INPUT_BG, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
            font=FONT, wrap=tk.WORD, height=3, borderwidth=0, padx=12, pady=10,
            relief=tk.FLAT,
        )
        self._input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 8), pady=10)
        self._input_text.bind("<Return>", self._on_enter)
        self._input_text.bind("<Shift-Return>", lambda e: None)  # Shift+Enter 换行

        send_btn = tk.Button(
            input_frame, text="Send", command=self._send_message,
            bg=USER_BUBBLE, fg=TEXT_PRIMARY, font=FONT_BOLD,
            borderwidth=0, padx=20, pady=8, cursor="hand2",
            activebackground="#2563eb", activeforeground=TEXT_PRIMARY,
        )
        send_btn.pack(side=tk.RIGHT, padx=(0, 12), pady=10)

        # 全局快捷键
        self.bind("<Control-a>", lambda e: self._set_mode("auto"))
        self.bind("<Control-e>", lambda e: self._set_mode("accept_edits"))
        self.bind("<Control-p>", lambda e: self._set_mode("plan"))
        self.bind("<Control-n>", lambda e: self._set_mode("normal"))

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self._chat_canvas.itemconfig(self._chat_canvas_window, width=event.width)

    # ── 消息渲染 ───────────────────────────────────────────────────────
    def _add_user_bubble(self, text: str) -> None:
        """渲染用户消息气泡（右对齐，蓝色）"""
        row = tk.Frame(self._chat_inner, bg=CHAT_BG)
        row.pack(fill=tk.X, padx=16, pady=(12, 2))

        bubble = tk.Frame(row, bg=USER_BUBBLE)
        bubble.pack(side=tk.RIGHT, anchor="e")

        lbl = tk.Label(
            bubble, text=self._wrap_text(text, 60), fg=TEXT_PRIMARY,
            bg=USER_BUBBLE, font=FONT, justify=tk.LEFT,
        )
        lbl.pack(padx=14, pady=8)

    def _add_agent_bubble(self, text: str) -> tk.Frame:
        """渲染 agent 消息气泡（左对齐，深色），返回气泡 frame 以便追加流式内容"""
        row = tk.Frame(self._chat_inner, bg=CHAT_BG)
        row.pack(fill=tk.X, padx=16, pady=(2, 2))

        bubble = tk.Frame(row, bg=AGENT_BUBBLE)
        bubble.pack(side=tk.LEFT, anchor="w")

        lbl = tk.Label(
            bubble, text=self._wrap_text(text, 60), fg=TEXT_PRIMARY,
            bg=AGENT_BUBBLE, font=FONT, justify=tk.LEFT,
        )
        lbl.pack(padx=14, pady=8)
        return row

    def _add_tool_card(self, tool_name: str, params: dict[str, Any]) -> tk.Frame:
        """添加可折叠的工具调用卡片"""
        row = tk.Frame(self._chat_inner, bg=CHAT_BG)
        row.pack(fill=tk.X, padx=32, pady=(4, 2))

        card = tk.Frame(row, bg=TOOL_CARD)
        card.pack(fill=tk.X)

        # 折叠/展开状态
        state = {"expanded": False, "output": "", "is_error": False}

        header = tk.Frame(card, bg=TOOL_CARD, cursor="hand2")
        header.pack(fill=tk.X)

        tool_label = tk.Label(
            header, text=f"🔧 {tool_name}",
            fg=ACCENT_YELLOW, bg=TOOL_CARD, font=FONT_BOLD,
        )
        tool_label.pack(side=tk.LEFT, padx=12, pady=6)

        param_text = json.dumps(params, ensure_ascii=False)
        if len(param_text) > 80:
            param_text = param_text[:77] + "…"
        param_label = tk.Label(
            header, text=param_text, fg=TEXT_SECONDARY, bg=TOOL_CARD, font=FONT_SMALL,
        )
        param_label.pack(side=tk.LEFT, padx=(4, 12), pady=6)

        status_label = tk.Label(
            header, text="running…", fg=ACCENT_YELLOW, bg=TOOL_CARD, font=FONT_SMALL,
        )
        status_label.pack(side=tk.RIGHT, padx=12, pady=6)

        detail = tk.Frame(card, bg=TOOL_CARD)

        def toggle(_e: tk.Event | None = None) -> None:
            if state["expanded"]:
                detail.pack_forget()
                state["expanded"] = False
            else:
                detail.pack(fill=tk.X, after=header)
                state["expanded"] = True

        header.bind("<Button-1>", toggle)

        output_text = tk.Text(
            detail, bg="#1e1e2e", fg=TEXT_SECONDARY, font=FONT_MONO,
            wrap=tk.WORD, height=6, borderwidth=0, padx=10, pady=6,
            relief=tk.FLAT, state=tk.DISABLED,
        )
        output_text.pack(fill=tk.X, padx=12, pady=(0, 10))

        # 存储引用供后续更新
        row._tool_state = state         # type: ignore[attr-defined]
        row._tool_output = output_text  # type: ignore[attr-defined]
        row._tool_status = status_label # type: ignore[attr-defined]
        return row

    @staticmethod
    def _wrap_text(text: str, max_len: int) -> str:
        """简单换行：超过 max_len 字符处插入换行"""
        if len(text) <= max_len:
            return text
        lines = []
        while len(text) > max_len:
            # 尽量在空格处断开
            cut = text.rfind(" ", 0, max_len)
            if cut == -1:
                cut = max_len
            lines.append(text[:cut])
            text = text[cut:].lstrip()
        if text:
            lines.append(text)
        return "\n".join(lines)

    # ── 输入处理 ───────────────────────────────────────────────────────
    def _on_enter(self, event: tk.Event) -> str:
        """Enter 发送消息，Shift+Enter 换行"""
        if event.state & 0x0001:  # Shift
            return ""  # 允许默认换行
        self._send_message()
        return "break"  # 阻止默认换行

    def _send_message(self) -> None:
        content = self._input_text.get("1.0", "end-1c").strip()
        if not content or self._session_id is None:
            return
        self._input_text.delete("1.0", tk.END)

        self._add_user_bubble(content)
        self._scroll_bottom()

        self._run_async("session.send_message", {
            "session_id": self._session_id,
            "content": content,
        })

    # ── 模式切换 ───────────────────────────────────────────────────────
    def _set_mode(self, mode: str) -> None:
        """发送模式切换命令到 daemon"""
        self._run_async("permission.set_mode", {"mode": mode})
        # 本地 UI 即时更新按钮状态
        for m, btn in getattr(self._mode_buttons, "_btns", {}).items():
            if m == mode:
                btn.config(bg={
                    "auto": "#89b4fa", "accept_edits": "#a6e3a1",
                    "plan": "#f9e2af",
                }.get(mode, "#6c7086"), fg=BG)
            else:
                btn.config(bg=SIDEBAR_BG, fg={
                    "auto": "#89b4fa", "accept_edits": "#a6e3a1",
                    "plan": "#f9e2af", "normal": "#6c7086",
                }.get(m, "#6c7086"))
        self._mode = mode

    # ── 连接管理 ───────────────────────────────────────────────────────
    def _start_connection(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

    def _run_async_loop(self) -> None:
        """后台线程：运行 asyncio event loop + 连接 + 事件订阅"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        async def connect_loop() -> None:
            while self._running:
                client = SocketClient(self._host, self._port)
                try:
                    await client.connect()
                except (ConnectionRefusedError, OSError):
                    self._enqueue_ui("status", ("disconnected",))
                    await asyncio.sleep(2)
                    continue

                self._enqueue_ui("status", ("connecting",))
                loop_task = asyncio.ensure_future(client.run_event_loop())

                client.on_event(lambda ev: self._enqueue_ui("event", ev))

                try:
                    await client.send_command("event.subscribe", {
                        "topics": [
                            "session.*", "run.*", "step.*", "tool.*",
                            "llm.token", "llm.usage", "log.*",
                            "permission.*", "context.*", "subagent.*", "skill.*",
                        ],
                        "scope": "global",
                    })
                    created = await client.send_command("session.create", {"mode": "chat"})
                    self._enqueue_ui("session_ready", created)
                    self._enqueue_ui("status", ("ready",))
                    await loop_task
                except IpcError as e:
                    self._enqueue_ui("status", ("error", str(e)))
                finally:
                    if not loop_task.done():
                        loop_task.cancel()
                    self._enqueue_ui("session_lost", None)
                    await client.close()

                self._enqueue_ui("status", ("disconnected",))
                await asyncio.sleep(2)

        loop.run_until_complete(connect_loop())

    def _run_async(self, method: str, params: dict[str, Any]) -> None:
        """从主线程向后台 asyncio 线程派发命令"""
        if self._loop is None:
            return

        async def do() -> None:
            client = SocketClient(self._host, self._port)
            try:
                await client.connect()
                await client.send_command(method, params)
                await client.close()
            except (ConnectionRefusedError, OSError, IpcError) as e:
                self._enqueue_ui("error", str(e))

        asyncio.run_coroutine_threadsafe(do(), self._loop)

    def _enqueue_ui(self, kind: str, data: Any) -> None:
        self._ui_queue.put(_UIEvent(kind, data))

    # ── UI 事件轮询（主线程）───────────────────────────────────────────
    def _poll_ui_queue(self) -> None:
        try:
            while True:
                evt = self._ui_queue.get_nowait()
                self._handle_ui_event(evt)
        except queue.Empty:
            pass
        self.after(50, self._poll_ui_queue)

    def _handle_ui_event(self, evt: _UIEvent) -> None:
        kind = evt.kind

        if kind == "status":
            state = evt.data[0]
            self._set_status(state, extra=evt.data[1] if len(evt.data) > 1 else None)

        elif kind == "session_ready":
            self._session_id = str(evt.data.get("session_id", ""))
            self._session_tokens = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
            self._input_text.config(state=tk.NORMAL)

        elif kind == "session_lost":
            self._session_id = None
            self._input_text.config(state=tk.DISABLED)

        elif kind == "event":
            self._handle_event(evt.data)

        elif kind == "error":
            self._add_agent_bubble(f"⚠️ Error: {evt.data}")

    def _set_status(self, state: str, extra: str | None = None) -> None:
        colors = {
            "ready": ACCENT_GREEN,
            "running": ACCENT_YELLOW,
            "disconnected": ACCENT_RED,
            "connecting": ACCENT_YELLOW,
            "error": ACCENT_RED,
        }
        color = colors.get(state, TEXT_MUTED)
        self._status_dot.itemconfig(self._dot, fill=color)
        text = state
        if extra:
            text += f" ({extra})"
        self._status_label.config(text=text, fg=color)

    # ── 协议事件处理 ──────────────────────────────────────────────────
    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")

        if event_type == "llm.token":
            self._handle_token(event)

        elif event_type == "llm.usage":
            self._handle_usage(event)

        elif event_type == "tool.started":
            self._handle_tool_started(event)

        elif event_type == "tool.finished":
            self._handle_tool_finished(event)

        elif event_type == "run.started":
            self._set_status("running")
            self._add_agent_bubble("🤔 Thinking…")

        elif event_type == "run.finished":
            self._set_status("ready")

        elif event_type == "run.failed":
            self._set_status("ready")
            self._add_agent_bubble(f"❌ Run failed: {event.get('error', 'unknown')}")

        elif event_type == "context.watermark":
            pct = event.get("pct", 0)
            self._add_agent_bubble(f"📊 Context: {pct}% used")

        elif event_type == "permission.requested":
            self._handle_permission_request(event)

        elif event_type == "permission.mode_changed":
            new_mode = event.get("new_mode", "normal")
            if new_mode in ("auto", "accept_edits", "plan", "normal"):
                # 更新本地按钮状态
                for m, btn in getattr(self._mode_buttons, "_btns", {}).items():
                    if m == new_mode:
                        btn.config(bg={
                            "auto": "#89b4fa", "accept_edits": "#a6e3a1",
                            "plan": "#f9e2af",
                        }.get(new_mode, "#6c7086"), fg=BG)
                    else:
                        btn.config(bg=SIDEBAR_BG, fg={
                            "auto": "#89b4fa", "accept_edits": "#a6e3a1",
                            "plan": "#f9e2af", "normal": "#6c7086",
                        }.get(m, "#6c7086"))
                self._mode = new_mode

        elif event_type == "log.message":
            pass  # 日志消息静默忽略（不在 TUI 中显示）

        else:
            # 其他事件在状态栏简略显示
            run_id = event.get("run_id", "")[:8]
            if run_id:
                self._set_status("running", f"run:{run_id} {event_type}")

    def _handle_token(self, event: dict[str, Any]) -> None:
        """流式 token：追加到最后一个 agent bubble"""
        token = event.get("token", "")
        if not token:
            return
        # 找到最后一个 agent bubble 的 label 并追加
        for child in reversed(self._chat_inner.winfo_children()):
            if isinstance(child, tk.Frame):
                for widget in child.winfo_children():
                    if isinstance(widget, tk.Frame) and widget.cget("bg") != USER_BUBBLE and widget.cget("bg") != TOOL_CARD:
                        for lbl in widget.winfo_children():
                            if isinstance(lbl, tk.Label):
                                current = lbl.cget("text")
                                lbl.config(text=current + token)
                                self._scroll_bottom()
                                return
        # 没有现有 bubble 则创建新的
        row = self._add_agent_bubble(token)
        self._scroll_bottom()

    @staticmethod
    def _fmt_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    def _handle_usage(self, event: dict[str, Any]) -> None:
        """LLM 用量统计 — 本轮 + 会话累计"""
        inp = int(event.get("input_tokens") or 0)
        out = int(event.get("output_tokens") or 0)
        cache_read = int(event.get("cache_read_input_tokens") or 0)
        cache_write = int(event.get("cache_creation_input_tokens") or 0)
        model = str(event.get("model") or "")
        pct = float(event.get("context_pct") or 0.0)
        # 累加
        ses = self._session_tokens
        ses["in"] += inp
        ses["out"] += out
        ses["cache_read"] += cache_read
        ses["cache_write"] += cache_write
        # 本轮
        turn = f"in={self._fmt_tokens(inp)}  out={self._fmt_tokens(out)}"
        if cache_read:
            turn += f"  cache↗{self._fmt_tokens(cache_read)}"
        if cache_write:
            turn += f"  cache↖{self._fmt_tokens(cache_write)}"
        # 会话累计
        s_sum = f"in={self._fmt_tokens(ses['in'])}  out={self._fmt_tokens(ses['out'])}"
        if ses["cache_read"]:
            s_sum += f"  cache↗{self._fmt_tokens(ses['cache_read'])}"
        # context 水位条
        filled = int(pct * 10)
        bar = "█" * filled + "░" * (10 - filled)
        ctx = f"ctx {pct * 100:.0f}%"
        self._add_agent_bubble(
            f"📊 turn: {turn}\n"
            f"📁 session: {s_sum}  [{model}]\n"
            f"📏 {ctx}  {bar}"
        )

    def _handle_tool_started(self, event: dict[str, Any]) -> None:
        tool_name = event.get("tool_name", "unknown")
        params = event.get("params", {})
        tool_use_id = event.get("tool_use_id", "")

        row = self._add_tool_card(tool_name, params)
        if tool_use_id:
            self._pending_tools[tool_use_id] = row
        self._scroll_bottom()

    def _handle_tool_finished(self, event: dict[str, Any]) -> None:
        tool_use_id = event.get("tool_use_id", "")
        output = event.get("output", "")
        is_error = event.get("is_error", False)
        elapsed = event.get("elapsed_ms", 0)

        row = self._pending_tools.pop(tool_use_id, None)
        if row is None:
            return

        state = getattr(row, "_tool_state", None)
        output_text = getattr(row, "_tool_output", None)
        status_label = getattr(row, "_tool_status", None)

        if state is not None:
            state["output"] = output
            state["is_error"] = is_error

        if output_text is not None:
            output_text.config(state=tk.NORMAL)
            output_text.delete("1.0", tk.END)
            output_text.insert("1.0", output[:5000])
            output_text.config(state=tk.DISABLED)

        if status_label is not None:
            if is_error:
                status_label.config(text=f"failed ({elapsed}ms)", fg=ACCENT_RED)
            else:
                status_label.config(text=f"done ({elapsed}ms)", fg=ACCENT_GREEN)

        self._scroll_bottom()

    def _handle_permission_request(self, event: dict[str, Any]) -> None:
        """权限审批弹窗"""
        tool_use_id = event.get("tool_use_id", "")
        tool_name = event.get("tool_name", "unknown")
        params = event.get("params", {})

        dialog = tk.Toplevel(self)
        dialog.title("Permission Required")
        dialog.geometry("500x400")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog, text=f"Tool: {tool_name}",
            fg=ACCENT_YELLOW, bg=BG, font=FONT_BOLD,
        ).pack(padx=20, pady=(20, 10))

        param_text = scrolledtext.ScrolledText(
            dialog, bg=INPUT_BG, fg=TEXT_PRIMARY, font=FONT_MONO,
            height=12, borderwidth=0, relief=tk.FLAT,
        )
        param_text.insert("1.0", json.dumps(params, ensure_ascii=False, indent=2))
        param_text.config(state=tk.DISABLED)
        param_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        btn_frame = tk.Frame(dialog, bg=BG)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        def approve() -> None:
            self._run_async("permission.decide", {
                "tool_use_id": tool_use_id,
                "decision": "approve",
            })
            dialog.destroy()

        def deny() -> None:
            self._run_async("permission.decide", {
                "tool_use_id": tool_use_id,
                "decision": "deny",
            })
            dialog.destroy()

        tk.Button(
            btn_frame, text="Approve", command=approve,
            bg=ACCENT_GREEN, fg=BG, font=FONT_BOLD,
            borderwidth=0, padx=16, pady=6, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            btn_frame, text="Deny", command=deny,
            bg=ACCENT_RED, fg=TEXT_PRIMARY, font=FONT_BOLD,
            borderwidth=0, padx=16, pady=6, cursor="hand2",
        ).pack(side=tk.RIGHT)

    # ── 辅助 ──────────────────────────────────────────────────────────
    def _scroll_bottom(self) -> None:
        """滚动聊天区域到底部"""
        self._chat_canvas.update_idletasks()
        self._chat_canvas.yview_moveto(1.0)

    def _on_close(self) -> None:
        self._running = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.destroy()


# ── 启动入口 ─────────────────────────────────────────────────────────────
def run_desktop(host: str, port: int) -> None:
    app = SztuCodeDesktop(host, port)
    app.mainloop()
