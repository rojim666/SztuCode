# 直播海报通用渲染与画布流程

任一工作流完成 prompt 合成后加载本文件。文件门禁、工具调用和验证仍以 `ardot-design-core` 为准。

> ⛔⛔⛔ **第零条铁律（贯穿全文件所有步骤）**：ImageGen 的输入图片使用平铺字符串字段 `image1`、`image2`、`image3`，不要传 `image` 数组或 `{item:...}` 外壳。其他工具的 array 类型参数仍写成纯数组 `[...]`，绝对不能套 `{item:[...]}` 外壳。

## 1. 建文件 + 生图

⛔ **时序约束（最高优先级）**：打开画布后**第一步必须调用 ImageGen 生图**，用 `image1`、`image2`、`image3` 参数把人物照片与背景风格 prompt 融合成**一张完整底图**；**严禁把人物照片作为独立图层贴到 Ardot 背景底图上**（两种渲染风格会脱节）。ImageGen 未完成前不做任何画布排版、文字、speaker card、SVG icon 等操作。

先按 `ardot-design-core` 处理 `<ardot_file_directive>`，完成文件门禁并等待 ready context update，再调用 ImageGen。

### ImageGen 调用

```
ToolSearch({ tool_names: ["ImageGen"] })
DeferExecuteTool({
  toolName: "ImageGen",
  params: {
    prompt: "<合成后的完整 prompt>",
    image1: "<人物照片绝对路径1>",
    image2: "<人物照片绝对路径2>",
    input_fidelity: "high",
    size: "<确定的 ImageGen size>",
    quality: "high",
    output_dir: "<工作目录>/.Sztubuddy/generated-images"
  }
})
```

规则：

- `image1`、`image2`、`image3` 只传人物照片，使用绝对路径，最多 3 张
- 图片字段必须从 `image1` 开始连续传入；不能只传 `image2`，也不能跳过 `image2` 直接传 `image3`
- 有人物照片时必须使用 `input_fidelity: "high"`
- 无人物照片时省略 `image1`、`image2`、`image3` 和 `input_fidelity`
- 每个图片字段直接传一条路径字符串，不要传 `image` 数组，也不要使用 `{ "item": ... }` 包装
- 多人照片按 prompt 中 image #1 / #2 / #3 的顺序分别传入 `image1` / `image2` / `image3`

### ⛔ 不要对 `params` 做任何 JSON.stringify

```jsonc
// ✅ 正确：平铺字符串字段
DeferExecuteTool({
  toolName: "ImageGen",
  params: {
    prompt: "...",
    image1: "/abs/photo1.jpg",
    image2: "/abs/photo2.jpg"
  }
})

// ❌ 错误 1：旧的数组参数已移除
image: ["/abs/photo1.jpg", "/abs/photo2.jpg"]

// ❌ 错误 2：使用 item wrapper
image: { "item": ["/abs/photo1.jpg", "/abs/photo2.jpg"] }

// ❌ 错误 3：图片字段跳号
image1: "/abs/photo1.jpg",
image3: "/abs/photo3.jpg"

// ❌ 错误 4：对整个 params 调 JSON.stringify
params: JSON.stringify({ prompt: "...", image1: "/abs/photo1.jpg" })
```

**验证手段**：调用成功时返回 `"status": "completed"` 且 `images[0].localPath` 指向一个真实 PNG。若返回参数校验错误，先确认只使用 `image1`、`image2`、`image3` 字符串字段，并且编号连续；不要通过修改 prompt、size 或 `input_fidelity` 规避图片参数错误。

排查清单：

1. 是否仍在使用旧的 `image` 数组？（改为 `image1`、`image2`、`image3`）
2. 是否把图片放入 `{ "item": ... }` 对象？（移除 wrapper，每个字段直接传字符串）
3. 图片字段是否从 `image1` 开始连续编号？
4. 是否对 `params` 调过 `JSON.stringify`？（删除 stringify，直接传对象字面量）
5. 是否用了 bash / Python 包装参数？（去掉包装层，直接用 `DeferExecuteTool` 调用）

## 2. 生图检查

用文件读取工具读取生成图，仅在以下严重问题出现时重生：

| 需要重生 | 可以接受 |
|----------|----------|
| 人物过大，叠字后会严重遮挡 | 人物大小合理，文字区留白充足 |
| 人物偏到文字区 | 人物在预期区域 |
| 明显白色面板、窗口或边框 | 背景干净 |

最多重生 1 次；第二次无论结果直接使用。小瑕疵不重生。重生时保持相同 `image1`、`image2`、`image3` 与 `size`，只修改 prompt 的构图描述。

## 3. 搭画布

有风格文件时，使用 Part C 排版表；无风格文件时，使用 [adaptive-sizing.md](adaptive-sizing.md) 的对应方向排版。每次调用 `batch_edit` 前加载 `ardot-design-core/tool-usage/batch-edit.md`，DSL 和 schema 均以核心技能为唯一真源。

### 文案映射（有 Part C 时）

| 风格表节点 | 填入内容 |
|------------|----------|
| T01 brand | 用户品牌名；没有则跳过 |
| T02 main title | 直播标题前半段（逗号/顿号前） |
| T03 sub title | 直播标题后半段 |
| T04 english decor | 课程看点英文关键词；没有则 `LIVE` |
| T05 window title | 「课程要点」或用户栏目标题 |
| T06–T09 list items | 用户给几条填几条 |
| T10 speech bubble | 讲师姓名 + 头衔（`｜` 连接） |
| T11 promo band | 直播时间 |
| T12 bottom header | 课程看点/副标题 |
| T13 contact | 用户提供的电话；没有则跳过 |
| T14 contact addr | 用户提供的底部地址；没有则跳过 |

- 用户给出的文案一字不改
- 标题按第一个逗号/顿号拆分；无分隔符则全放 T02
- 文本超宽时优先缩字号或扩宽度，不改文字

### batch_edit

每次不超过 25 ops，按以下顺序创建：

1. 顶层 Frame：`layout: "none"`、画布尺寸、`clipsContent: true`
2. 底图 rectangle：`x:0, y:0, width:画布宽, height:画布高+100`
3. Logo rectangle（如有）
4. 文字节点
5. 风格文件 `## Icons` 指定的 icon Frame（如有）

字体优先中文 `Noto Sans SC`、英文 `Inter`。创建文字前调用 `get_available_fonts` 确认精确 family/style，不得猜测字体样式名称。

### 图片上传（三段式，顺序不能乱）

把 ImageGen 生成的本地图片传到 Ardot 画布，必须按以下三步执行，缺一不可：

1. **`register_assets`（申请通道）**：调用一次，拿到临时 `uploadUrl` + `downloadUrl`。`contentType` 传真实 MIME（`image/png` / `image/jpeg` / `image/webp`）。URL 有过期时间，过期需重新申请。
2. **`curl PUT` 上传（真正把文件传上去）**：
   ```bash
   curl -s -X PUT "<uploadUrl>" -H "Content-Type: image/png" --data-binary "@/absolute/path/to/image.png" -w "HTTP_STATUS:%{http_code}\n"
   ```
   - **`--data-binary` 的文件路径前必须带 `@` 前缀**。不带 `@` 会把「路径字符串本身」当作数据上传，Ardot 端拿到的是几十字节的文本，imageHash 仍会生成，但图片永远渲染不出来——这是最隐蔽的坑。
   - 必须显式检查返回的 `HTTP_STATUS`，**不是 200 就不要进入下一步**（先查 URL 是否过期、Content-Type 是否匹配）。
   - `Content-Type` 必须与第 1 步 `register_assets` 传的 `contentType` **完全一致**（png 写成 jpeg 会解析失败）。
3. **`upload_images`（绑定 downloadUrl 为 fill）**：`filePath` 只能传第 1 步返回的 `downloadUrl`，**不能传本机文件路径**——传本地路径会静默失败或报错，图片不显示但很难定位原因。`nodeId` 为目标节点（底图 rectangle / Logo rectangle）。

跳过第 2 步直接把本地路径丢给 `upload_images` 是最常见的错法。不能用 batch_edit U() 替代。

`upload_images` 调用格式（2026-08-18 实测成功）：

```jsonc
// ✅ 正确写法 — items 是纯一维数组
DeferExecuteTool({
  toolName: "mcp__ardot__upload_images",
  params: {
    fileUrl: "https://ardot.tencent.com/file/<fileId>",
    items: [
      { nodeId: "3:2", filePath: "<register_assets 返回的 downloadUrl>" }
    ]
  }
})
```

- `items` 必须是**纯一维对象数组** `[{nodeId, filePath}]`
- `filePath` 传 `downloadUrl`（COS 地址），**不能传本机路径**
- 如果 wrapper 报 `items must be array`：检查是否把 items 套成了 `{item: [{...}]}` 对象外壳

#### ❌ 错误思路：用 batch_edit U() 写 IMAGE fill 来「替代」upload_images

### SVG icon

风格文件 `## Icons` 提供 SVG 源码 + 尺寸表时，用独立 `batch_edit` 插入功能性 icon；无 Icons、仅色块占位或 `no icons` 时跳过。禁止 ImageGen 生 icon、Write `.svg` 文件、或把 Part A / prompt 背景描述画成 SVG/rectangle。

```
iconCal=I("<canvasFrameId>",{type:"frame",name:"iconCalendar",x:<X>,y:<Y>,width:<W>,height:<H>,svg:"<svg viewBox='0 0 24 24' ...>...</svg>"})
```

- SVG `width` / `height` 必须等于 Ardot 帧宽高
- icon 尺寸约为承载色块的 50–60%，并居中
- 不给 icon Frame 添加 `fills`

## 4. 验证与交付

按 `ardot-design-core` 执行最终 `capture_screenshot`，并完成以下直播海报专项检查：

- 文字是否被裁切
- 人物与文字是否重叠
- Logo 是否变形
- 水印是否确实位于裁切区外

发现问题最多进行 2 轮集中修复。验证通过后再交付。

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| ImageGen 报图片参数校验错误 | 只使用连续的 `image1`、`image2`、`image3` 字符串字段；不要传旧 `image` 数组或 `{item:...}`，修正后按相同参数重试 1 次 |
| 有人物参考图时 ImageGen 仍失败 | 不得静默去掉 `image1`、`image2`、`image3`；告知用户无法保证人物一致性 |
| 无人物参考图时 ImageGen 失败 | 按相同参数重试 1 次；再失败告知用户 |
| 字体不可用 | 用 `get_available_fonts` 选择可用的中英文回退字体 |
| `Skipped unparseable line` | 按 `ardot-design-core/tool-usage/batch-edit.md` 修正 DSL |
| 底图 / Logo 上传成功但画布不显示图片 | 检查 curl 的 `--data-binary` 是否带 `@` 前缀（不带会传成路径字符串）；确认 `upload_images` 的 `filePath` 传的是 `downloadUrl` 而非本地路径；确认 curl 返回 HTTP 200；确认 Content-Type 与 `register_assets` 一致 |
