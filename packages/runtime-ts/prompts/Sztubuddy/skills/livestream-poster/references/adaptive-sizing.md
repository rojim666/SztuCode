# 自适应尺寸与构图

无可用风格文件或使用风格参考图工作流时加载。有风格文件时保留其视觉规则，仅用本文件覆盖用户指定的尺寸。

## 尺寸映射

| 比例 | 画布 | ImageGen size |
|------|------|---------------|
| 横版 16:9 | 1920×1080 | `1536x1024` |
| 横版 4:3 | 1440×1080 | `1536x1024` |
| 竖版 9:16 | 1080×1920 | `1024x1536` |
| 竖版 3:4 | 1080×1440 | `1024x1536` |
| 方形 1:1 | 1080×1080 | `1024x1024` |
| 自定义 W×H | 用户指定值 | 取最接近的支持尺寸 |

用户指定比例时直接使用该映射，不与风格文件原尺寸反复确认。

## 通用 ImageGen prompt

按方向替换 `[ORIENTATION]`、`[PERSON_PLACEMENT]` 和 `[QUIET_AREA]`：

```text
[STYLE DESCRIPTION], [ORIENTATION] composition. Medium-wide editorial shot captured from 2-3 meters away with a wide-angle lens.

Background:
- [BACKGROUND COLOR / MATERIAL / ATMOSPHERE]
- Decorative geometric shapes: [根据风格或用户偏好填入]
- ABSOLUTELY NO white panels, NO white rectangles, NO frosted glass windows, NO card shapes anywhere.

Person:
- [PERSON_PLACEMENT]
- Half-body or three-quarter portrait, [pose description].
- Clean photorealistic rendering with bright studio lighting.
- Nothing between the viewer and the person.

Reserved text area:
- [QUIET_AREA]

No text, no letters, no numbers, no logos, no watermarks anywhere.
```

| 方向 | ORIENTATION | PERSON_PLACEMENT | QUIET_AREA |
|------|-------------|------------------|------------|
| 横版 | `horizontal [RATIO] landscape` | 人物较小地位于左侧，身体四周有充足留白 | 整个右侧保持安静、干净 |
| 竖版 | `vertical [RATIO] portrait` | 人物较小地位于右下，左侧和上方有充足留白 | 左上、左中和左下保留标题、时间与 CTA 空间 |
| 方形 | `square 1:1` | 人物位于左下或右下，按标题方向选择对角位置 | 对角区域保持安静、干净 |

人物尺寸必须使用摄影语言控制，不在 ImageGen prompt 中混入百分比、像素或 bounding box。需要进一步调整时加载 [person-size-control.md](person-size-control.md)。

## Ardot 排版

### 横版：左图右文

文字区域从 `W*0.48` 开始：

| 元素 | x | y | fontSize |
|------|---|---|----------|
| 主标题 | `W*0.48` | `H*0.15` | 60–90 |
| 副标题 | `W*0.48` | `H*0.35` | 28–36 |
| 时间卡 | `W*0.48` | `H*0.50` | 48–64 / 24–28 |
| 讲师卡 | `W*0.48` | `H*0.70` | 36–48 / 22–26 |
| CTA | `W*0.48` | `H*0.88` | 22–26 |

### 竖版：上文下图

| 元素 | x | y | fontSize |
|------|---|---|----------|
| 副标题 | `W*0.10` | `H*0.08` | 24–28 |
| 主标题行 1 | `W*0.08` | `H*0.14` | 72–100 |
| 主标题行 2 | `W*0.08` | `H*0.24` | 72–100 |
| 课程描述 | `W*0.08` | `H*0.35` | 24–32 |
| 时间卡 | `W*0.08` | `H*0.41` | 48–72 / 26–32 |
| 讲师名片 | `W*0.60` | `H*0.57` | 36–52 / 22–26 |
| 讲师头衔 | `W*0.58` | `H*0.67` | 32–42 / 24–28 |
| CTA | `W*0.05` | `H*0.89` | 22–26 |
| LIVE 徽章 | `W*0.72` | `H*0.88` | 26–30 |

方形版根据人物所在下角，将标题放到对角上方；字号按竖版基准乘 `actualWidth / 1080`。

## 通用约束

1. 人物与文字零重叠
2. 装饰元素克制，只使用已选风格中的元素
3. `fontSize = baseFontSize × (actualWidth / 1080)`，向下取整到偶数
4. 不改用户文案；溢出时调整字号、宽度或换行
