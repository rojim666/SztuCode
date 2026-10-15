# 在桌面端查看图片

桌面端连接 TypeScript daemon 时，可以在输入框粘贴、拖入或选择 PNG、JPEG、WebP、静态 GIF。选用支持视觉的模型后发送，图片会随文字进入模型上下文；不支持视觉的模型会提示改用 OCR 或切换模型。

Agent 也可以调用 `view_image`，读取工作区中的图片。`path` 必须位于工作区内，`max_dimension` 可设为 512–4096，默认长边最多 2048 像素。上传和工具读取都会校验实际格式并保持比例缩放；单图输入限制 20 MiB，单条消息图片总量限制 32 MiB。动画 GIF 暂不支持。

工具图片会显示在调用详情里，点击缩略图打开大图，方向键切换，Escape 关闭。OpenAI Chat Completions、Responses 和 Anthropic Messages 都收到图片内容，而不是 base64 文本。Chat Completions 的图片紧跟整组工具结果，避免破坏并行调用的对应关系。

大于 100 KiB 的图片单独保存在会话 `images/` 目录，历史与事件只保存引用；相同内容复用同一文件。重启、恢复和分叉会话后仍可读取图片。尺寸信息参与本地 token 预算估算，该估算不等于服务商实际计费。

这条链路适用于 `npm run daemon:ts` 和桌面端；Python daemon 的图片能力不由本文描述。
