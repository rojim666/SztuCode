# 风格参考图工作流

适用于用户上传了设计风格图片，并明确表示「作为风格参考」「按这个风格」或「参考这个设计风格」。

整体流程：**提取背景风格 → 一轮问答 → 合成 prompt → 渲染与交付**。

## 1. 提取背景风格

用文件读取工具读取用户的风格参考图，输出一段可直接作为 ImageGen Part A 的英文描述（3–6 句）。只提取：

- 主色、辅色和渐变方向
- 背景材质与纹理
- 几何色块、线条、光点等装饰元素
- 科技、活力、沉稳、潮流等整体氛围

背景风格词必须用 `background` 限定，禁止污染人物：

- ❌ `entire image has vintage grain` → ✅ `background has subtle vintage grain texture`
- ❌ `retro color grading applied to the scene` → ✅ `background uses warm orange-red color palette`
- ❌ `silhouette style` → ✅ `background features city skyline silhouette`

末尾追加：

`ABSOLUTELY NO white panels, NO white rectangles, NO frosted glass windows, NO card shapes anywhere.`

提取完直接进入下一步，不追问风格图该如何使用。

## 2. 收集缺失素材

只询问尚未提供、且无法从上下文可靠推断的信息。把**仍缺失**的项合并到**一次** `AskUserQuestion`（人物与 Logo **分两题**，选项字面量与 [style-selection.md](style-selection.md) Step 1 一致）。

⛔ **本步必须在 `create_design` / ImageGen 之前完成**。人物照片三选项必须包含 `我稍后上传`；prompt 中的讲师/嘉宾姓名不等于已上传照片。用户选「我稍后上传」则停止生图，等待上传后再继续。

禁止再次询问是否采用参考图风格、是否叠字等已经明确的事项。禁止合并人物/Logo 或使用「AI 生成讲师肖像」等自造选项（完整规则见 [style-selection.md](style-selection.md) Step 1）。

## 3. 合成 prompt

加载 [../references/adaptive-sizing.md](../references/adaptive-sizing.md)，根据海报比例确定人物位置和文字留白。

### 有用户人物照片

```
<Part A 背景风格 prompt（来自步骤 1）>

Person (must look exactly like the character in image #1):
- IMPORTANT: The person must be rendered in CLEAN PHOTOREALISTIC style with studio lighting, regardless of the background artistic style. No artistic filters, no silhouette effects, no grain/texture/color grading applied to the person.
- [衣物描述，来自用户照片]
- [位置/姿势，来自自适应比例规则]

The background style and the person's rendering style are SEPARATE. No frames or borders around the person.

No text, no letters, no numbers anywhere in the image.
```

必须设置 `input_fidelity: "high"`。人物段禁止出现 vintage / retro / grain / silhouette / neon 等背景风格词。

### AI 生成人物

使用相同的背景/人物隔离规则，把人物锚点改为明确的外貌、服装和姿势描述，不传 `image`。不得擅自推断真实人物身份或敏感属性。

### 不放人物

只保留 Part A，并追加：

`No text, no letters, no numbers anywhere in the image.`

不得生成空的 Person 段。

## 4. 渲染与交付

Prompt 合成后加载 [../references/render-and-compose.md](../references/render-and-compose.md)，执行建文件、生图、自适应排版和最终验证。
