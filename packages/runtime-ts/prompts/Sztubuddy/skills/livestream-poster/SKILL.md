---
name: livestream-poster
description: >
  生成直播宣传海报：支持风格文件/视觉大类和用户风格参考图两种工作流，收集人物、Logo、文案与比例后，用 ImageGen 生成底图并在 Ardot 画布完成排版。
  当用户提到「直播海报」「直播宣传图」「直播预告海报」「线上直播海报」「livestream poster」，或引用直播海报风格文件时使用。
disable-model-invocation: true
user-invocable: false
agent_created: true
---

# Livestream Poster — 直播海报生成

本技能用于生成直播宣传海报。文件创建/打开、工具调用、画布 schema 和基础验证以 `ardot-design-core` 为准；本技能负责工作流选择和直播海报业务规则。

## 工作流选择

| 条件 | 加载的 workflow |
|------|-----------------|
| 用户上传设计风格图，并明确说「作为风格参考」「按这个风格」或「参考这个设计风格」 | [workflows/style-reference.md](workflows/style-reference.md) |
| 其他：引用风格文件、选择视觉大类、无风格偏好 | [workflows/style-selection.md](workflows/style-selection.md) |

风格参考图工作流必须同时满足：

1. 用户上传了图片
2. 用户明确表示该图片是背景/设计风格参考，而不是人物照片

仅上传图片但未说明用途时，按人物照片处理，使用风格选择工作流。

**每次任务只加载一个 workflow。** 确定后按该 workflow 顺序执行，不要同时加载两个工作流。

## 共享参考（按 workflow 指示加载）

| 文件 | 用途 |
|------|------|
| [references/render-and-compose.md](references/render-and-compose.md) | 两个工作流共享的建文件、生图、画布排版和验证 |
| [references/adaptive-sizing.md](references/adaptive-sizing.md) | 无风格文件或使用风格参考图时的自适应构图 |
| [references/person-size-control.md](references/person-size-control.md) | 人物/IP 画面占比控制 |
| [references/prompt-examples.md](references/prompt-examples.md) | 单人替换与多人 prompt 示例 |

## 全局硬规则

1. ImageGen 默认调用 1 次；仅严重构图问题允许重生 1 次
2. 有用户人物照片时必须通过 ImageGen `image1`、`image2`、`image3` 参数融合，不能直接贴到画布
3. 人物参考图失败时不得静默移除 `image1`、`image2`、`image3`，否则无法保证人物一致性
4. Logo 不传给 ImageGen；在 Ardot 中作为独立图层上传
5. 不改用户提供的文案；溢出时调整字号、宽度或排版
6. 对话中不暴露 `.md`、内部路径、DSL、`batch_edit` 等实现细节
7. 禁止 spawn 子 agent；遵循 `ardot-design-core` 的文件门禁和验证规则
8. 底图与 Part A 背景装饰均由 ImageGen 生成；Ardot 只做底图 fill、文字、Logo，以及风格文件 `## Icons` 的功能性 SVG icon（禁止把背景 prompt 描述画成 SVG/rectangle）
9. 素材收集与 `AskUserQuestion` 选项以所加载 workflow 的 Step 1 为准，不得跳过、合并或改写
