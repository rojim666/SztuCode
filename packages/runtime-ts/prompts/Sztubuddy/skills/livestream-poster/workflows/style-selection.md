# 风格文件或视觉大类工作流

适用于用户引用直播海报风格文件、选择视觉大类，或没有上传明确的设计风格参考图。

## 1. 收集缺失素材

只询问用户尚未提供、且无法从上下文可靠推断的信息。把**仍缺失**的项合并到**一次** `AskUserQuestion`（多题并列，每题独立选项列表）。

⛔ **本步必须在 `create_design` / ImageGen / 画布排版之前完成**。

### 必问字段与选项（字面量不可改）

| 字段 | 何时跳过 | 选项（必须原样出现） |
|------|----------|----------------------|
| 人物照片 | 当前轮已上传人物照，或用户明确「用这张当讲师/嘉宾照片」 | `我稍后上传` / `没有，用 AI 生成人物` / `没有，海报不放人物` |
| 品牌 Logo | 已上传 Logo，或用户明确不要 Logo | `我稍后上传` / `不需要 Logo` |
| 文案 | 用户给出完整可直接使用的文案 | `我稍后提供完整文案（一字不改直接用）` / `我提供关键信息、其余 AI 补` / `全部由 AI 创意生成` |
| 海报比例 | 用户已指定比例（如「竖版 9:16」） | `横版 16:9` / `横版 4:3` / `竖版 9:16` / `竖版 3:4` / `方形 1:1` |
| 视觉风格 | 用户已引用风格文件，或 `<ardot_design_style>` 已选定子模板，或用户已明确大类 | `卡通 IP` / `双人对谈` / `科技深空` / `轻盈科技` / `年轻活力` / `设计创意` / `新包豪斯` / `卡通波谱风` |

已明确提供的字段不得重复询问。选项使用自然语言，禁止向用户暴露 `.md`、文件路径或工具语法。

### 标准问法示例（人物 + Logo 分两题）

```
AskUserQuestion({
  questions: [
    {
      header: "人物照片",
      question: "海报中的人物形象如何处理？",
      options: [
        { label: "我稍后上传", description: "上传讲师/嘉宾肖像，通过 AI 融合进底图，保证人物一致。" },
        { label: "没有，用 AI 生成人物", description: "不上传照片，由 AI 生成中性专业人物形象。" },
        { label: "没有，海报不放人物", description: "纯背景与排版，画面中不出现人物。" }
      ]
    },
    {
      header: "品牌 Logo",
      question: "是否需要加入品牌 Logo？",
      options: [
        { label: "我稍后上传", description: "上传 Logo 文件，在画布中单独排版。" },
        { label: "不需要 Logo", description: "海报不含品牌标识。" }
      ]
    }
  ]
})
```

### 禁止的反模式

- ❌ 合并人物与 Logo 为一题，或使用「AI 生成讲师肖像」「不放讲师肖像」等自造文案
- ❌ 因 prompt 含讲师姓名就默认 AI 生成或跳过人物题
- ❌ 省略「我稍后上传」（AskUserQuestion 无法代用户传文件，但必须保留该选项以触发等待上传流程）

### 「我稍后上传」后续

- **人物照片**：告知用户请上传肖像；下一轮收到图片且非风格参考图后，按「有用户人物照片」合成 prompt，ImageGen 必须从 `image1` 开始连续传入图片字段。
- **Logo**：告知用户请上传 Logo；收到后在 Ardot 单独上传，不传给 ImageGen。

## 2. 匹配风格

优先使用用户明确引用的风格文件。否则，仅当技能包或用户提供的位置中确实存在直播海报风格库时，才按视觉大类进入对应目录：

- 仅 1 个子风格 → 直接使用
- 多个子风格 → 按人数/配色偏好自动匹配，无法判断再追问一次
- 只在已知风格库根目录内查找名称包含 `.livestream` 的 Markdown 文件
- 禁止无边界扫描用户磁盘

当前技能包没有内置 `styles/` 时，不得假装匹配到文件；直接把用户选择的大类作为视觉方向，并加载 [../references/adaptive-sizing.md](../references/adaptive-sizing.md)。

对话中只说「已选定 XX 风格」，不暴露内部文件名或路径。

## 3. 获取风格规则

### 有风格文件

读取完整文件或足以覆盖以下区块的范围，不使用固定行数截断：

| 提取项 | 位置 | 用途 |
|--------|------|------|
| 画布尺寸 | 顶部 `Canvas` 行 | Ardot Frame w/h |
| ImageGen 尺寸 | 顶部 `ImageGen size` 行 | ImageGen `size` |
| Part A | `## A` | 背景 prompt |
| Part B | `## B` | 人物动作/位置（外貌待替换） |
| Part C | `## C` 表格 | 文字节点与排版 |

用户选择比例时，直接覆盖风格文件尺寸：

| 比例 | 画布 | ImageGen size |
|------|------|---------------|
| 横版 16:9 | 1920×1080 | `1536x1024` |
| 横版 4:3 | 1440×1080 | `1536x1024` |
| 竖版 9:16 | 1080×1920 | `1024x1536` |
| 竖版 3:4 | 1080×1440 | `1024x1536` |
| 方形 1:1 | 1080×1080 | `1024x1024` |

未选比例时使用风格文件原始尺寸。

### 无风格文件

加载 [../references/adaptive-sizing.md](../references/adaptive-sizing.md)，按用户选择的视觉大类替换模板中的背景、材质、配色和装饰描述。

## 4. 合成 prompt

### 有用户人物照片

风格文件 Part B 写死虚拟人物时，必须替换外貌：

| 字段 | 处理 |
|------|------|
| 外貌 | 丢弃原文 → `must look exactly like the character in image #1` |
| 衣物 | 按用户照片重写；看不清则 `professional attire` |
| 动作/姿势/手势 | 保留原文 |
| 位置/画面占比 | 保留原文 |
| 表情/情绪/渲染风格/光线 | 保留原文 |

```
<Part A 背景 prompt>

<Part B 人物段，仅替换外貌和衣物>
No frames, no borders, no windows around the people - they stand directly on the background.

No text, no letters, no numbers anywhere in the image.
```

禁止添加原文没有的视觉元素、缩小原有景别或自由发挥姿势。示例见 [../references/prompt-examples.md](../references/prompt-examples.md)。

### AI 生成人物

- 有风格文件 → 保留 Part B 人物描述，不传 `image`
- 无风格文件 → 根据直播主题生成中性、专业的人物描述并套用自适应构图
- 不得擅自推断真实人物身份或敏感属性

### 不放人物

跳过 Part B，只使用 Part A，并追加：

`No text, no letters, no numbers anywhere in the image.`

## 5. 渲染与交付

Prompt 合成后加载 [../references/render-and-compose.md](../references/render-and-compose.md)，执行建文件、生图、画布排版和最终验证。
