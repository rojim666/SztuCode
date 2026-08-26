from __future__ import annotations

from dataclasses import dataclass, field

from textual.theme import Theme as TextualTheme

# SztuCode TUI 主题系统：语义 token 驱动的明暗双主题与程序化背景壁纸。
# CSS 通过 Textual 的 $variable 引用颜色（见 textual_theme 的 variables），
# rich markup 内的颜色则用 c() 取当前主题的 hex，保证两处一致。

# 主题注册顺序：/theme 命令按此顺序循环
THEME_ORDER: tuple[str, ...] = ("dark", "light")

# 壁纸样式注册顺序：/wallpaper 命令按此顺序循环
WALLPAPER_ORDER: tuple[str, ...] = ("none", "aurora", "ocean", "sunset")


@dataclass(frozen=True)
class Theme:
    # 主题名与语义颜色 token（hex，不含 # 前缀），is_dark 标识明暗
    name: str
    colors: dict[str, str] = field(default_factory=dict)
    is_dark: bool = True


THEMES: dict[str, Theme] = {
    "dark": Theme(
        name="dark",
        colors={
            "background": "#0E1013",
            "surface": "#16191D",
            "surface2": "#1D2127",
            "border": "#2A2F37",
            "border2": "#3A414B",
            "text": "#E6E9ED",
            "text-muted": "#8A9199",
            "accent": "#F2BB6C",
            "ok": "#76D6C1",
            "info": "#84B8FF",
            "warn": "#E8C468",
            "danger": "#D96A6A",
            "danger2": "#7A353A",
        },
        is_dark=True,
    ),
    "light": Theme(
        name="light",
        colors={
            "background": "#F4F1EC",
            "surface": "#FFFFFF",
            "surface2": "#EFEAE2",
            "border": "#D8D2C8",
            "border2": "#C4BCAE",
            "text": "#23262B",
            "text-muted": "#6B6F76",
            "accent": "#B45309",
            "ok": "#0F766E",
            "info": "#1D4ED8",
            "warn": "#B7791F",
            "danger": "#B91C1C",
            "danger2": "#9F1239",
        },
        is_dark=False,
    ),
}

# 当前激活主题名（进程级，供 rich markup 取色）
_active_name: str = "dark"


# 将语义 token 名映射为 Textual 主题名（避免与内置主题冲突）
def textual_name(name: str) -> str:
    return f"sztu-{name}"


# 切换当前激活主题；未知名称回退到 dark
def set_active(name: str) -> None:
    global _active_name
    _active_name = name if name in THEMES else "dark"


# 返回当前激活的主题对象
def active() -> Theme:
    return THEMES[_active_name]


# 返回当前激活主题名
def active_name() -> str:
    return _active_name


# 返回当前激活主题中某语义 token 的颜色（含 # 前缀），用于 rich markup
def c(token: str) -> str:
    return active().colors.get(token, active().colors["text"])


# 将 SztuCode 主题转换为 Textual 可注册的主题对象，语义 token 全部映射为 $variable
def textual_theme(name: str) -> TextualTheme:
    theme = THEMES[name]
    colors = theme.colors
    return TextualTheme(
        name=textual_name(name),
        primary=colors["accent"],
        secondary=colors["info"],
        warning=colors["warn"],
        error=colors["danger"],
        success=colors["ok"],
        accent=colors["accent"],
        foreground=colors["text"],
        background=colors["background"],
        surface=colors["surface"],
        panel=colors["surface"],
        dark=theme.is_dark,
        variables=dict(colors),
    )


# --- 壁纸渐变生成 ------------------------------------------------------------


# 各壁纸样式的横向三段色标（左→中→右），生成时再按行纵向压暗
_WALLPAPER_STOPS: dict[str, tuple[str, str, str]] = {
    "aurora": ("#0F4C4A", "#23305C", "#4A2A5C"),
    "ocean": ("#0A2A4A", "#0F3D5C", "#14506B"),
    "sunset": ("#4A1F14", "#5C2A14", "#6B3A1A"),
}

# 壁纸纵向压暗幅度：底部比顶部暗的比例
_WALLPAPER_VERTICAL_DIM = 0.35


# 将 #rrggbb 拆为 (r, g, b)
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


# 在两个 hex 颜色间按 t∈[0,1] 线性插值
def _lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"{r:02x}{g:02x}{bl:02x}"


# 在横向三段色标上按 t∈[0,1] 取色
def _gradient_color(stops: tuple[str, str, str], t: float) -> str:
    if t <= 0.5:
        return _lerp_hex(stops[0], stops[1], t * 2)
    return _lerp_hex(stops[1], stops[2], (t - 0.5) * 2)


# 按系数整体压暗一个 hex 颜色（factor∈[0,1]）
def _shade(hex_color: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = round(r * factor)
    g = round(g * factor)
    bl = round(b * factor)
    return f"{r:02x}{g:02x}{bl:02x}"


# 生成指定壁纸样式的整屏渐变 markup；none 或非法尺寸返回空串
def wallpaper_markup(style: str, width: int, height: int) -> str:
    stops = _WALLPAPER_STOPS.get(style)
    if stops is None or width <= 0 or height <= 0:
        return ""
    rows: list[str] = []
    for y in range(height):
        dim = 1.0 - _WALLPAPER_VERTICAL_DIM * (y / max(1, height - 1))
        cells: list[tuple[str, int]] = []
        for x in range(width):
            color = _shade(_gradient_color(stops, x / max(1, width - 1)), dim)
            if cells and cells[-1][0] == color:
                cells[-1] = (color, cells[-1][1] + 1)
            else:
                cells.append((color, 1))
        rows.append("".join(f"[#{color}]{'█' * n}[/#{color}]" for color, n in cells))
    return "\n".join(rows)
