# WBP 演示 HTML 生成契约（skill 内引用）

> 本文件是供 `md_to_html.py --format presentation` 和 agent 直出演示 HTML 时的**最小契约**。

---

## 0. 定位

当 `md-to-html-flow.md` §3 判定走 **PPT 演示**格式时，`md_to_html.py --format presentation`
生成符合本契约的 WBP native 档 html。产物可被播放器翻页播放（翻页/双屏/激光笔/分步揭示），
后续 `import_html.py` 导入挂载与长页完全一致。

---

## 1. 必须遵守的骨架结构

```html
<!doctype html>
<html lang="zh" data-wbp data-wbp-version="1.1"
      data-aspect="16:9" data-design-w="1280" data-design-h="720">
<head>
  <meta charset="utf-8" />
  <title>{{汇报主题}}</title>
  <meta name="wbp:audience" content="boss|peer|client|public" />
  <meta name="wbp:scene" content="report|decision|pitch|retro" />
  <meta name="wbp:style" content="{{主题名}}" />
  <script type="application/json" id="wbp-meta">{ ... }</script>
  <style>/* 主题皮肤 + .is-active 页内动画 + reduced-motion 降级 */</style>
</head>
<body>
  <main data-wbp-deck>
    <section data-wbp-slide data-slide-id="s1" data-layout="cover"
             data-zone="overview" data-transition="slide-left">
      <h1>核心结论</h1>
      <p class="muted">支撑要点</p>
      <aside data-wbp-notes>逐字稿（150-300 字，口语化，加粗核心词）</aside>
    </section>
    <!-- 更多 slide -->
  </main>
</body>
</html>
```

---

## 2. 属性速查

| 位置 | 属性 | 必填 | 值域 |
|---|---|---|---|
| `<html>` | `data-wbp` | 是 | 存在即可 |
| `<html>` | `data-wbp-version` | 是 | `"1.1"` |
| `<html>` | `data-aspect` | 是 | `16:9`（默认）/ `4:3` / `3:4`（竖屏）/ `1:1`（方图） |
| `<html>` | `data-design-w` / `data-design-h` | 建议 | `1280` / `720`（16:9） |
| `<main>` | `data-wbp-deck` | 建议 | deck 容器 |
| `<section>` | `data-wbp-slide` | 是 | 一页一节 |
| `<section>` | `data-slide-id` | 建议 | 稳定唯一 id（`s1`、`s2`…） |
| `<section>` | `data-layout` | 可选 | `cover` / `kpi` / `bullets` / `chart` / `cta` |
| `<section>` | `data-zone` | 建议 | `overview` / `data` / `logic` / `next`（四区结构） |
| `<section>` | `data-transition` | 可选 | `none` / `slide-left` / `slide-up` / `zoom` |
| 子元素 | `data-wbp-fragment` | 可选 | 页内分步揭示 |
| 子元素 | `data-wbp-no-advance` | 可选 | 单击该元素不翻页（交互区/链接/图表） |
| `<aside>` | `data-wbp-notes` | 建议 | 逐字稿（观众隐藏，演讲者展示）；兼容 `.slide-notes` / `[data-notes]` |

---

## 3. 四区结构（data-zone）

汇报 page 按叙事逻辑分为四区，每页 `data-zone` 标注归属：

| zone | 语义 | 典型内容 |
|---|---|---|
| `overview` | 概览结论 | cover 页 TL;DR、核心数字 |
| `data` | 关键数据 | KPI 卡、图表、增长曲线 |
| `logic` | 论证逻辑 | 原因分析、对比表、技术方案 |
| `next` | 下一步/风险 | 行动项、风险列表、CTA |

---

## 4. 页数与内容约束

- **不超框优先（核心）**：每张 slide 固定 16:9 设计盒（1280×720），内容**不得超出盒子**。
  `md_to_html.py --format presentation` 会按盒子高度**自动分页**——长 section 拆成多张「标题（续）」续页，
  每页内容控制在盒内（长列表按条目跨页拆分）。因此**页数以"装得下"为准，可超过 8**；≤8 只是精简建议，不再强制合并。
- **最少内容**：md < 200 字 → 提示用户补充，不硬生成空架子（`md_to_html.py --format presentation` 已**强校验**：不足 200 字直接返回 `{"error":...}` 提示补充）
- **首页必须是 cover**（`data-layout="cover"` + `data-zone="overview"`），抛核心结论 / TL;DR
- **末页建议 cta**（`data-layout="cta"` + `data-zone="next"`），给下一步或风险

---

## 5. 逐字稿规则

每页 `<aside data-wbp-notes>` 放口语化逐字稿，**目标 150-300 字**：

- 从 md 该 section 原文提炼核心论点 + 转场衔接
- **加粗**关键数字/术语作提示信号
- 不复读正文，而是口语化补充"怎么讲"
- 不要把演讲者旁白写进正文 `<p>`

> **长度约定**：`md_to_html.py` 只产出**草稿逐字稿**（从该节正文提炼，长度随 md 内容而定，可能不足 150 字）；
> 150-300 字是 **agent 富化目标**——agent 应在脚本产物基础上把过短的逐字稿补足到该区间，脚本不强行凑字数。

**逐字稿富化**：逐字稿放 `<aside data-wbp-notes>`，agent 在脚本草稿基础上补足到 150-300 字/页。

---

## 6. 页内动画（.is-active CSS）

> **渲染上下文（关键，决定动画怎么写）**：本 html 在资料库页有**两种渲染态**——
> - **浏览态（默认）**：iframe **直接渲染 html**，所有 `<section data-wbp-slide>` **竖直堆叠成静态长页**，
>   **没有翻页、不会加 `.is-active`**（`.is-active` 只在演示态由 `MindxPresentation` 播放器添加）。
> - **演示态**：点「演示」按钮才挂载播放器，逐页翻页、为当前页加 `.is-active`、走过场动画。
>
> 因此 **绝不能用 `opacity:0` 预隐藏元素**——浏览态没有 `.is-active`，预隐藏会导致**整页白屏**
> （也会破坏 database 快照的无 SDK 兜底）。正确做法：**元素默认可见**，`.is-active` 只用来**重播入场动画**
> （翻到该页时再放一遍），离开/未激活时元素照常显示。

**缓动曲线**：标准入场用 `cubic-bezier(.4,0,.2,1)`；强调/弹出用带回弹的 `cubic-bezier(.22,1.3,.36,1)`。

```css
:root {
  --ease: cubic-bezier(.4,0,.2,1);
  --ease-bounce: cubic-bezier(.22,1.3,.36,1);
}
/* 入场关键帧：升起(带轻缩放+去模糊) / 模糊聚焦 / 缩放弹出 / 封面流光 */
@keyframes wbpRise   { from { opacity:0; transform:translateY(40px) scale(.985); filter:blur(4px); }
                       to   { opacity:1; transform:none; filter:none; } }
@keyframes wbpBlurIn { from { opacity:0; filter:blur(16px); } to { opacity:1; filter:none; } }
@keyframes wbpZoom   { 0% { opacity:0; transform:scale(.86); } 60% { transform:scale(1.03); }
                       100% { opacity:1; transform:scale(1); } }
@keyframes wbpGradFlow { to { background-position:220% center; } }   /* 封面标题三色流光（持续，安全） */

/* 不要写 [data-wbp-slide] h1 { opacity:0 } 之类的预隐藏——浏览态会白屏 */
/* 元素默认可见；仅 .is-active 时重播入场（动画 from 态自带 opacity:0，结束回到可见） */
/* 封面：标题模糊聚焦 + 持续流光；副标题随后升起 */
[data-wbp-slide][data-layout="cover"].is-active h1 {
  animation: wbpBlurIn .8s var(--ease) both, wbpGradFlow 5s var(--ease) .8s infinite;
}
[data-wbp-slide][data-layout="cover"].is-active p.muted { animation: wbpRise .7s var(--ease) .18s both; }
/* 内容页：标题升起 + 要点 stagger 递进（每级 +0.08s） */
[data-wbp-slide].is-active h2 { animation: wbpRise .55s var(--ease) both; }
[data-wbp-slide].is-active p  { animation: wbpRise .55s var(--ease) .12s both; }
[data-wbp-slide].is-active li { animation: wbpRise .5s var(--ease) both; }
[data-wbp-slide].is-active li:nth-child(1) { animation-delay:.12s; }
[data-wbp-slide].is-active li:nth-child(2) { animation-delay:.20s; }
[data-wbp-slide].is-active li:nth-child(3) { animation-delay:.28s; }
[data-wbp-slide].is-active li:nth-child(n+4) { animation-delay:.36s; }
[data-wbp-slide].is-active blockquote,
[data-wbp-slide].is-active figure { animation: wbpZoom .55s var(--ease-bounce) .1s both; }

@media (prefers-reduced-motion: reduce) {
  [data-wbp-slide] * { animation: none !important; }
  [data-wbp-slide] h1 { background-position: 0 center !important; }
}
```

> 单页同时启用的入场类型建议 ≤2 种（如「标题升起 + 要点 stagger」），混太多会乱。
> 持续型装饰动画（封面流光 `wbpGradFlow`、微光扫过）只在不隐藏内容的前提下使用，浏览态也安全。

---

## 7. 设计系统（一键可视化视觉基线）

> 这是「一键可视化」生成 HTML（**长页与演示通用**）的杂志级设计系统：排版 / 间距 / 表面材质 /
> 阴影层次 / 布局美学 / 微交互 / 背景氛围 / 色彩精度。演示场景在此基线上叠加 WBP 固定设计盒适配。
> **每页 / 每屏最多启用 2~3 种技法**，否则过度设计。

### 7.1 排版体系

| 层级 | 用途 | font-size | font-weight | line-height |
|---|---|---|---|---|
| Display | slide 标题 | 42-48px | 700 | 1.2 |
| Heading | section 标题 | 28-32px | 600 | 1.3 |
| Subheading | KPI 标签/要点 | 18-22px | 500 | 1.4 |
| Body | 正文/逐字稿 | 16-18px | 400 | 1.6 |
| Caption | 辅助说明 | 13-14px | 400 | 1.5 |

### 7.2 间距系统

基数 8px，全部用 8 的倍数：`8 / 16 / 24 / 32 / 48 / 64 / 96`。

### 7.3 表面材质（slide 卡片样式）

```css
/* 毛玻璃面板 — 深色主题 slide 背景 */
[data-wbp-slide] {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

/* KPI 卡片 — 品牌色发光边框 */
.kpi-card {
  border: 1px solid rgba(var(--accent-rgb), 0.3);
  box-shadow:
    inset 0 0 6px rgba(var(--accent-rgb), 0.15),
    0 0 24px rgba(var(--accent-rgb), 0.12);
}
```

### 7.4 色彩系统（CSS 变量）

```css
:root {
  /* 由 --style 参数映射出三色品牌渐变（accent → accent2 → accent3） */
  --accent: var(--theme-accent);
  --accent2: var(--theme-accent2);
  --accent3: var(--theme-accent3);
  --accent-rgb: var(--theme-accent-rgb);   /* 同理 --accent2-rgb / --accent3-rgb */
  --grad: linear-gradient(120deg, var(--accent), var(--accent2) 55%, var(--accent3));

  /* 中性色阶（Off-Black，非纯黑） */
  --bg: #08090a;
  --bg-elevated: #0d0f14;
  --surface: rgba(255,255,255,0.03);
  --border: rgba(255,255,255,0.08);

  /* 文字色阶（3 级，必须同时使用才有层次） */
  --text: rgba(255,255,255,0.85);
  --text-secondary: rgba(255,255,255,0.55);
  --text-tertiary: rgba(255,255,255,0.35);
}
```

> **三色渐变用途**：封面标题流光、`h2` 标题条、列表标记、有序号徽标、CTA。正文/要点用 `--text` 中性色，
> 品牌色只用于功能性强调（不用于正文），保证可读层次。三色须在同一冷/暖色相内过渡，避免脏。

### 7.5 主题映射（三色品牌渐变）

| --style | accent | accent2 | accent3 | 气质 |
|---|---|---|---|---|
| `business` | `#4f8cff` | `#9d8cff` | `#ff8cc8` | 商务蓝紫粉 · 结论先行 |
| `tech` | `#22d3ee` | `#34d399` | `#60a5fa` | 科技青绿蓝 · 前沿感 |
| `fresh` | `#34d399` | `#6ee7b7` | `#a3e635` | 清新绿 · 简洁清爽 |
| `warm` | `#fb923c` | `#fbbf24` | `#fb7185` | 暖橙琥珀粉 · 数据厚重 |

> 背景底色（`--bg` / `--panel`）随 style 取对应色相的 Off-Black 暗调，slide 叠径向光晕（见 §7.7）。

### 7.6 阴影层次系统（深色，偏品牌色暗调，非纯黑）

```css
/* Level 1 — 轻悬浮（标签/小卡片） */ box-shadow: 0 2px 8px rgba(0,0,0,0.3);
/* Level 2 — 标准 slide 卡片 */       box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.06);
/* Level 3 — 浮层/强调 KPI */         box-shadow: 0 16px 48px rgba(0,0,0,0.5);
```

### 7.7 背景氛围（slide 不用纯色，叠氛围层）

```css
/* cover / overview 页：径向光晕（已内置于 [data-wbp-slide]） */
background:
  radial-gradient(ellipse 80% 50% at 50% -10%, rgba(var(--accent-rgb),0.12), transparent),
  var(--panel);

/* data 页双光点（可选，仅 KPI/图表页点缀） */
background:
  radial-gradient(ellipse 60% 40% at 20% 0%, rgba(var(--accent-rgb),0.08), transparent),
  radial-gradient(ellipse 50% 50% at 80% 100%, rgba(var(--accent-rgb),0.05), transparent),
  var(--panel);
```

> 虹彩渐变（conic-gradient + blur(80px)）仅 cover 首屏点缀，禁止大面积使用。

### 7.8 KPI 数字滚动计数（data 区专属微交互）

数据亮点用数字滚动动画，从 0 跳到目标值（`easeOutExpo`，约 2000ms）。
**触发挂在 `.is-active`**（容器翻到该页才启动），不用 `onload`，并做 reduced-motion 降级直接显示终值：

```css
[data-wbp-slide].is-active .kpi-num { animation: wbpScaleIn .5s ease both; }
@media (prefers-reduced-motion: reduce) { [data-wbp-slide] .kpi-num { animation: none !important; } }
```

> 计数 JS 若要写，须由容器在 `.is-active` 时驱动；HTML 侧**不写翻页/播放控制 JS**（WBP 契约 §6）。

### 7.9 布局美学（slide 版式参考）

| data-layout | 版式技法 | 适用 |
|---|---|---|
| `cover` | 非对称 Hero（左文右视觉，左对齐不居中） | 首页结论 |
| `kpi` | Bento Grid（大小卡混排） / KPI 卡横排 | 核心指标页 |
| `bullets` | 单列要点 + 视觉锚点 | 论证逻辑页 |
| `chart` | 2 列交替（Zig-Zag，图文左右） | 数据图表页 |
| `cta` | 居中收束 + 大字行动项 | 下一步/风险页 |

> 固定设计盒 1280×720，内容不超框（scale 档超框是 bug）。

---

## 8. 防捏造 / 来源溯源

- 无出处数据 → 文案「待补充」+ 属性 `data-wbp-todo`，**不要编**：
```html
<div class="kpi-num" data-wbp-todo>待补充</div>
```
- 关键数字/结论来源登记在 meta JSON 岛 `slides[].sources`

---

## 9. database 绑定标注

仅当演示档作为**动态数据页**（走 `data-page-flow.md`，数据来自 database）时适用：按 `data-page-flow.md` §1.5.5 对文本直接来自或间接派生自 database 的元素加 database 绑定标注。演示档典型命中元素：slide 标题、正文段落 / bullets、KPI 数字（间接派生）、图片 `<img>`。

> 纯静态演示档（md→html 分支，`import_html.py` 直接导入、不接 database）无需此标注。

---

## 10. Do / Don't 速查

**Do**
- 一页一个 `<section data-wbp-slide>`，给稳定 `data-slide-id`
- 首屏先抛结论（`data-zone="overview"`）
- 页内动画用 `.is-active` CSS，分步用 `data-wbp-fragment`
- 逐字稿放 `<aside data-wbp-notes>`（150-300 字/页）
- `prefers-reduced-motion` 降级必做
- 固定 16:9 设计盒（1280×720），不超框
- 无出处数据标 `data-wbp-todo`，显示「待补充」
- 动态数据页中来源于（含统计派生）database 的元素按 `data-page-flow.md` §1.5.5 加绑定标注（静态演示档免）

**Don't**
- 写翻页 / 分步 / 自动播放的 JS（容器职责）
- 把演讲者旁白写进正文
- 超出设计盒 1280×720
- 捏造没有出处的数字
- 大面积使用虹彩渐变（仅 cover 点缀）
- 页数超 8 页

---

## 11. meta JSON 岛（可选）

```json
{
  "title": "Q2 增长复盘",
  "audience": "boss",
  "scene": "report",
  "style": "business",
  "slideCount": 4,
  "slides": [
    { "id": "s1", "layout": "cover", "zone": "overview", "title": "核心结论", "sources": ["source.md#L1"], "todos": [] },
    { "id": "s2", "layout": "kpi", "zone": "data", "title": "核心指标", "sources": [], "todos": [] }
  ]
}
```
