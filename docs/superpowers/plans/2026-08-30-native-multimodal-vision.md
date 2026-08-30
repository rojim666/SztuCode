# 原生多模态/图片理解能力 Enhancement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善SztuCode的多模态能力，补全图片查看、理解、处理的完整链路，让Agent能够像处理文本一样自然地处理工作区中的图片文件，支持截图分析、UI审核、图表理解等场景。

**Architecture:**
- 在`packages/runtime-ts/src/tools.ts`中注册`view_image`内置工具
- 扩展消息content block类型，统一图片表示（base64 vs URL）
- 完善provider层的多模态content转换，确保Anthropic和OpenAI格式都正确
- 在server-service层打通文件读取→图片编码→模型调用的完整链路
- 桌面端添加图片附件上传UI支持
- 与imagegen Skill整合，支持图片编辑参考图输入

**Tech Stack:** TypeScript, sharp (optional image processing), 现有provider架构, Vue 3 (desktop UI)

---

## 问题背景

当前状态：
- Provider层（openai.ts）已支持`image`/`image_url` content block，但缺少暴露给Agent的工具
- server-service.send_message支持`images`参数，但只能由UI在发送消息时附加，Agent无法主动查看图片
- 缺少`view_image`工具，Agent不能主动读取工作区中的图片文件
- file.read对图片文件只返回`media_base64`，但没有自动转为多模态输入的机制
- Anthropic provider的图片支持未验证/可能缺失
- 桌面端UI缺少图片粘贴/拖拽上传功能

对标差距：Claude Code和Codex CLI都支持`view_image`工具，Agent可以主动打开图片分析，用户可以直接粘贴截图到对话。

---

### Task 1: 统一Content Block图片表示并补全Provider支持

**Files:**
- Modify: `packages/runtime-ts/src/context.ts` (ContentBlock类型扩展)
- Modify: `packages/runtime-ts/src/providers/openai.ts`
- Modify: `packages/runtime-ts/src/providers/anthropic.ts`
- Create: `packages/runtime-ts/src/providers/image-utils.ts`

- [ ] **Step 1: 扩展ContentBlock类型定义**

在context.ts中明确图片block类型：

```typescript
// context.ts
export type ContentBlock =
  | { type: "text"; text: string; content?: string }
  | { type: "thinking"; thinking: string; content?: string }
  | { type: "image"; source: { media_type: string; data: string } }  // base64
  | { type: "image_url"; image_url: string }  // http(s) URL or data URL
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string | ContentBlock[]; is_error?: boolean }
  | { type: "file"; file: { filename?: string; data?: string; mime_type?: string; [key: string]: unknown } };
```

- [ ] **Step 2: 创建图片编码工具函数**

```typescript
// image-utils.ts
import { readFile } from "node:fs/promises";

const SUPPORTED_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
]);

const EXTENSION_MIME: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

export function getMimeTypeFromPath(filePath: string): string | null {
  const ext = filePath.toLowerCase().slice(filePath.lastIndexOf("."));
  return EXTENSION_MIME[ext] ?? null;
}

export function isSupportedImageType(mime: string): boolean {
  return SUPPORTED_IMAGE_TYPES.has(mime);
}

export function dataUrlFromBase64(mediaType: string, base64Data: string): string {
  return `data:${mediaType};base64,${base64Data}`;
}

export async function imageToContentBlock(
  filePath: string,
  maxSizeBytes = 20 * 1024 * 1024 // 20MB limit
): Promise<ContentBlock> {
  const data = await readFile(filePath);
  if (data.length > maxSizeBytes) {
    throw new Error(`Image too large: ${data.length} bytes (max ${maxSizeBytes})`);
  }
  const mimeType = getMimeTypeFromPath(filePath);
  if (!mimeType || !isSupportedImageType(mimeType)) {
    throw new Error(`Unsupported image type: ${filePath}`);
  }
  return {
    type: "image",
    source: {
      media_type: mimeType,
      data: data.toString("base64"),
    },
  };
}
```

- [ ] **Step 3: 验证并补全OpenAI Provider图片处理**

检查现有openai.ts的normalizeChatContent：
- 确保`image` block正确转为data URL
- 确保`image_url` block直接传递URL
- Responses API和Chat Completions API两种格式都正确处理

- [ ] **Step 4: 补全Anthropic Provider图片支持**

检查anthropic.ts，添加：
- `image` block转换为Anthropic格式：`{ type: "image", source: { type: "base64", media_type, data } }`
- `image_url` block需要先fetch（限制为可信域名或拒绝），Anthropic不支持直接URL图片
- 测试Anthropic Messages API格式正确性

- [ ] **Step 5: 编写Provider多模态测试**

创建测试：
- 纯文本消息正常工作
- 单张图片+文本消息正确序列化
- 多张图片消息正确序列化
- 不支持的图片格式抛出明确错误
- OpenAI和Anthropic格式输出符合各自API规范

---

### Task 2: 实现view_image内置工具

**Files:**
- Modify: `packages/runtime-ts/src/tools.ts`
- Create: `packages/runtime-ts/src/image-processor.ts` (可选，图片缩略/尺寸校验)

- [ ] **Step 1: 在tools.ts注册view_image工具**

```typescript
// 在registerBuiltinTools中添加
registry.register({
  name: "view_image",
  description: "View and analyze an image file from the workspace. The image will be sent to the multimodal model for visual understanding. Supported formats: PNG, JPEG, WebP, GIF. Use this to examine screenshots, diagrams, charts, UI mockups, photos, or any visual content.",
  permission: "read_only",
  schema: {
    type: "object",
    properties: {
      path: {
        type: "string",
        description: "Path to the image file, relative to workspace root",
      },
      max_dimension: {
        type: "integer",
        minimum: 512,
        maximum: 4096,
        default: 2048,
        description: "Maximum width/height in pixels (images larger than this will be downscaled to save context)",
      },
    },
    required: ["path"],
  },
  async invoke(params, context) {
    // 实现：
    // 1. 路径安全校验（不逃逸workspace）
    // 2. 读取文件并检查mime type
    // 3. 可选：使用sharp缩放大图片
    // 4. 返回特殊标记让agent-loop将其注入为多模态content
    // 5. 返回摘要信息（尺寸、格式、大小）给调用者
  },
});
```

关键设计：view_image工具返回时，不应只返回文本"Image loaded"，而是需要在tool_result中包含实际的image content block，这样模型才能"看到"图片。这需要修改agent-loop处理tool_result的逻辑。

- [ ] **Step 2: 修改agent-loop支持tool_result中的图片**

[agent-loop.ts](file:///f:/Learning/codinganget/SztuCode/packages/runtime-ts/src/agent-loop.ts) 当前可能假设tool_result content是string，需要修改为：
- 支持tool_result content为ContentBlock数组
- view_image返回时，content是`[ { type: "text", text: "Image: path/to/file.png (1920x1080 PNG)" }, { type: "image", source: {...} } ]`
- 这样图片会被加入对话历史供后续轮次理解

- [ ] **Step 3: 路径安全与大小限制**

复用现有的workspace路径校验逻辑：
- 绝对路径逃逸检查（与read_file一致）
- 符号链接检查
- 文件大小限制（默认20MB）
- 图片尺寸自动缩放（避免4k+图片消耗过多token）

- [ ] **Step 4: （可选）集成sharp进行图片预处理**

添加sharp作为可选依赖：
- 大图片自动缩放到max_dimension
- 格式统一转换为JPEG/PNG
- 可选压缩质量控制
- 如果sharp不可用（原生依赖问题），降级为原样发送base64，由模型侧处理

```bash
npm install sharp
npm install --save-dev @types/sharp
```

---

### Task 3: 修改file.read自动返回图片给Agent

**Files:**
- Modify: `packages/runtime-ts/src/server-service.ts`
- Modify: `packages/runtime-ts/src/agent-session.ts`

- [ ] **Step 1: file.read返回图片时自动附加content block**

当`file.read`读取到支持的图片类型时：
- 当前返回`{ media_base64, mime_type }`但Agent无法直接使用
- 修改为：当工具调用者是Agent（通过tool调用而非UI RPC），直接在tool_result中返回image content block
- 保持向后兼容：RPC层仍返回media_base64字段供UI显示

- [ ] **Step 2: Agent智能提示**

当Agent尝试用`read_file`读取图片时（得到binary提示）：
- 在输出中提示："This is an image file. Use `view_image` to analyze its visual content."
- 引导Agent使用正确工具

---

### Task 4: 完善Session层图片消息支持

**Files:**
- Modify: `packages/runtime-ts/src/session-store.ts`
- Modify: `packages/runtime-ts/src/context.ts`
- Modify: `packages/runtime-ts/src/memory.ts` (检查memory中是否需要排除图片)

- [ ] **Step 1: Session存储正确序列化图片blocks**

检查session-store：
- 确保image content blocks能正确序列化/反序列化到JSONL
- 图片base64数据可能很大，考虑：
  - 选项A：直接存储（简单，base64膨胀33%）
  - 选项B：图片offload到单独文件，消息中只存引用（推荐，避免session文件过大）
- 选择选项B：图片大于100KB时自动offload到runDir/refs/images/，消息中存ref_path

- [ ] **Step 2: 上下文压缩时保留图片引用**

检查context.ts compact逻辑：
- 压缩历史时，图片block不应被丢弃或摘要
- 保留图片的引用信息（路径、类型），但可以卸载base64数据
- 摘要中注明"[Image referenced from previous turn: path/to/image.png]"

---

### Task 5: 桌面端图片上传与粘贴UI

**Files:**
- Modify: `desktop/src/components/Composer/` (输入框组件)
- Modify: `desktop/src/services/sztu-runtime.ts` (RPC客户端)
- Modify: `desktop/src/components/timeline/ToolCallCard.vue` (图片展示)
- Create: `desktop/src/components/Composer/ImagePreview.vue`

- [ ] **Step 1: 输入框支持粘贴/拖拽图片**

在聊天输入框组件中：
- 监听paste事件，检测剪贴板中的图片
- 监听drag/drop事件，支持拖入图片文件
- 支持点击附件按钮选择图片文件
- 支持常见格式：PNG, JPEG, WebP, GIF

- [ ] **Step 2: 图片预览与发送**

创建ImagePreview组件：
- 发送前显示缩略图预览
- 支持移除已选图片
- 显示文件名和大小
- 多图支持（一次最多5张）
- 点击预览可以查看大图

- [ ] **Step 3: 图片通过session.send_message发送**

修改sztu-runtime.ts：
- sendMessage方法支持images参数
- 将图片读取为base64，附加到RPC调用
- 与现有images参数对接

- [ ] **Step 4: 对话中图片展示**

修改消息渲染：
- 用户发送的图片在聊天气泡中显示
- Agent通过view_image查看的图片可以显示（可折叠，默认显示缩略图）
- 点击图片在lightbox中查看原图
- 暗色主题适配

---

### Task 6: 图片尺寸/Token消耗优化

**Files:**
- Create: `packages/runtime-ts/src/image-processor.ts`
- Modify: `packages/runtime-ts/src/agent-loop.ts`

- [ ] **Step 1: 实现智能图片缩放**

```typescript
// image-processor.ts
export interface ProcessedImage {
  data: Buffer;
  media_type: string;
  width: number;
  height: number;
  original_size: number;
}

export async function processImageForLLM(
  input: Buffer | string,
  options: {
    maxLongEdge?: number;  // default: 2048 (GPT-4V recommends under 2000)
    maxShortEdge?: number; // default: 768
    quality?: number;      // JPEG quality 0-100, default: 82
  }
): Promise<ProcessedImage>;
```

处理规则：
- 保持宽高比
- 长边超过maxLongEdge时缩放
- 短边超过maxShortEdge时也缩放
- 统一转为JPEG（照片）或PNG（截图/图表/透明）
- 目标：单张图片不超过~1MB，控制token消耗

- [ ] **Step 2: Token计数支持图片**

修改TokenCounter：
- 当前只计算文本token
- 添加图片token估算（按分辨率/尺寸，参考各模型计费规则）
- usageSnapshot中区分text tokens和image tokens
- 上下文预算计算时包含图片token

---

### Task 7: 与imagegen Skill整合

**Files:**
- Modify: `packages/runtime-ts/skills/imagegen/SKILL.md`
- Modify: 相关工具集成

- [ ] **Step 1: 支持参考图输入**

imagegen编辑模式：
- 用户上传图片作为编辑参考时，自动作为image block加入上下文
- image_gen工具调用时支持传入参考图
- 不需要Agent手动base64编码，由工具框架处理

- [ ] **Step 2: 生成图片自动展示**

image_gen返回的图片：
- 自动在对话中展示
- 自动保存到工作区（如果是项目相关）
- Agent可以view_image查看生成结果继续迭代

---

### Task 8: 测试与验证

**Files:**
- Create: `packages/runtime-ts/tests/multimodal.test.ts`
- Create: `desktop/tests/` (UI测试)
- Create: `packages/runtime-ts/tests/fixtures/images/` (测试图片)

- [ ] **Step 1: 添加测试图片夹具**

添加几个小测试图片：
- `test.png` (100x100 纯色PNG)
- `test.jpg` (小尺寸JPEG照片)
- `test-screenshot.png` (模拟UI截图)

- [ ] **Step 2: 编写工具测试**

测试覆盖：
- view_image成功读取并返回image block
- 路径逃逸检查正确拒绝非法路径
- 大图片自动缩放
- 不支持的格式返回明确错误
- tool_result中图片能正确传递到provider
- session保存/加载后图片仍可访问（或正确offload）

- [ ] **Step 3: Provider集成测试**

- OpenAI Chat Completions API图片格式正确
- OpenAI Responses API图片格式正确
- Anthropic Messages API图片格式正确
- 混合文本+多图消息正确序列化

- [ ] **Step 4: 端到端手动验证**

Run:
```text
npm run dev:desktop
```

手动验证场景：
1. 粘贴截图到输入框发送，Agent能描述截图内容
2. 拖入图片文件到对话，Agent能分析
3. Agent用view_image查看工作区中的图片
4. Agent能用read_file读取图片时收到正确提示
5. 连续多轮对话包含图片时上下文正常
6. 重启后session中的图片仍可查看（或优雅降级）

---

## 验收标准

- [ ] `view_image`工具可读取工作区图片并让模型"看到"
- [ ] 用户可粘贴/拖拽图片到聊天输入
- [ ] 桌面端对话中图片正确显示
- [ ] OpenAI和Anthropic provider都正确支持图片输入
- [ ] 图片自动缩放控制token消耗
- [ ] 大图片自动offload不膨胀session存储
- [ ] 所有现有文本功能不受影响
- [ ] 测试覆盖核心路径，TypeScript编译零错误

## 非目标（本阶段不做）

- 视频/GIF动画理解（只取首帧）
- 图片编辑/绘制（保留imagegen Skill）
- OCR文字识别（依赖模型原生能力，不添加tesseract.js）
- 图片标注/画图交互
- 批量图片相册管理
