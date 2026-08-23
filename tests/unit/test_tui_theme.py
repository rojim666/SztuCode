from __future__ import annotations

from sztu_code.tui.theme import (
    THEMES,
    WALLPAPER_ORDER,
    c,
    set_active,
    textual_theme,
    wallpaper_markup,
)

_TOKEN_SET = {
    "background", "surface", "surface2", "border", "border2",
    "text", "text-muted", "accent", "ok", "info", "warn", "danger", "danger2",
}


# 功能：验证主题注册表包含明暗两套主题且语义 token 齐全
# 设计：直接检查 THEMES 键与颜色 token 集合，避免依赖 Textual 渲染
def test_theme_registry_has_dark_and_light() -> None:
    assert set(THEMES) == {"dark", "light"}
    for name in THEMES:
        assert _TOKEN_SET <= set(THEMES[name].colors)


# 功能：验证 set_active 切换后 c() 返回对应主题的颜色，未知名称回退 dark
# 设计：对比切换前后同一 token 的 hex 值，确认当前主题生效且非法输入不崩溃
def test_set_active_switches_color_palette() -> None:
    set_active("dark")
    dark_accent = c("accent")
    set_active("light")
    light_accent = c("accent")
    assert dark_accent != light_accent
    set_active("unknown-name")
    assert c("accent") == dark_accent


# 功能：验证 textual_theme 生成可注册的主题对象且变量映射完整
# 设计：检查 name 与 variables 与 THEMES 一致，覆盖 Textual 主题注册的输入契约
def test_textual_theme_maps_tokens_to_variables() -> None:
    theme = textual_theme("dark")
    assert theme.name == "sztu-dark"
    assert theme.variables["accent"] == THEMES["dark"].colors["accent"]
    assert theme.variables["border"] == THEMES["dark"].colors["border"]


# 功能：验证壁纸 markup 生成含色块的渐变文本，none 与非法尺寸返回空串
# 设计：固定尺寸生成后检查全块字符与行数，边界尺寸直接断言空串
def test_wallpaper_markup_generates_gradient_cells() -> None:
    markup = wallpaper_markup("aurora", 40, 8)
    assert "█" in markup
    assert len(markup.splitlines()) == 8
    assert wallpaper_markup("none", 40, 8) == ""
    assert wallpaper_markup("aurora", 0, 8) == ""


# 功能：验证壁纸横向渐变在同一行产生多种颜色（非纯色背景）
# 设计：解析一行 markup 的颜色段并计数，断言颜色数大于 1，防止退化为单色
def test_wallpaper_gradient_has_multiple_colors_per_row() -> None:
    markup = wallpaper_markup("ocean", 60, 4)
    first_row = markup.splitlines()[0]
    colors: set[str] = set()
    for part in first_row.split("["):
        if part.startswith("#") and "]" in part:
            colors.add(part[1:part.index("]")])
    assert len(colors) >= 2


# 功能：验证 /wallpaper 的循环顺序是注册表定义的完整轮换
# 设计：检查 WALLPAPER_ORDER 首尾相连且不含重复项，供 _cycle_wallpaper 使用
def test_wallpaper_order_is_a_complete_cycle() -> None:
    assert WALLPAPER_ORDER[0] == "none"
    assert len(set(WALLPAPER_ORDER)) == len(WALLPAPER_ORDER)
