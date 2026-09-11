# Prompt 示例：人物替换与多人场景

## 单人：人物替换

**风格文件 Part B 原文（虚拟人物）**：

```
The person: a cute silver metallic cat-eared robot, round head with two
pointed cat-like ears, wearing black over-ear headphones, face is a black
display showing cyan geometric eyes, sleek silver metallic body, raised
left hand making a peace sign. Half-body portrait from waist up, positioned
on the LEFT side taking up 35-40% of canvas width. Photorealistic, studio
lighting.
```

**用户给了照片后合成的 prompt**：

```
The person (must look exactly like the character in image #1): wearing a
navy blue business suit with a white shirt, raised left hand making a peace
sign. Half-body portrait from waist up, positioned on the LEFT side taking
up 35-40% of canvas width. Photorealistic, studio lighting.
```

对照：外貌整段丢弃，只留姿势/位置/画面占比/渲染风格。

---

## 多人（2 人+）

### 核心原则

- 必须 `input_fidelity: "high"`
- 严格保留 Part B 原文的姿势/站位描述
- 禁止添加原文中不存在的视觉元素（window / frame / border / oval shape）
- 人物直接站在背景上，无任何框/窗口/容器包裹

### Prompt 模板

```
<Part A 背景 prompt 完整原文>

<Part B 人物段，做以下替换>:
- 每个人物前加 "(must look exactly like the character in image #N)"
- 衣物描述改为用户照片实际穿着
- 姿势/手势/站位/画面占比/表情/渲染风格 → 照搬原文不改
- 末尾追加："No frames, no borders, no windows around the people - they stand directly on the background."

No text, no letters, no numbers anywhere in the image.
```

### image 参数

```json
"image": ["<人物A路径>", "<人物B路径>"]
```

- 最多 3 张
- 按 prompt 中 image #1 / #2 / #3 顺序对应

### Ardot 端补偿（人物太大时）

保持底图原始比例，不放大人物；通过父 Frame 的 `clipsContent: true`、底图位置和裁切范围调整展示区域。详细规则见 [person-size-control.md](person-size-control.md)。
