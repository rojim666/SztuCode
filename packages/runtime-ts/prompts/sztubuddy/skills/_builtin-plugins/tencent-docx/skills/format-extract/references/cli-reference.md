# format-extract CLI 与 API 参考

> 供 Expert 在需要自定义输入/输出、批量处理、独立质量评估时渐进加载。
> 日常"docx → HTML 格式提取"直接走 `run.py`，无需阅读本文档。

---

## CLI 统一入口

所有命令固定使用 bundled CLI（随 Skill 预构建，无需 npm 全局安装、不依赖外网）：

```
node ./dist/cli.cjs
```

> 路径以本 Skill 目录为基准，实际调用时替换为你的绝对或相对路径。

---

## convert — docx 转 HTML

### 单文件模式

```bash
node ./dist/cli.cjs convert --input <docx-path> --output <html-path> [--image-base-url <url>]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--input <path>` | 是（与 `--input-dir` 二选一） | 输入 .docx 文件路径 |
| `--output <path>` | 否 | 输出 HTML 路径，默认同名 .html |
| `--image-base-url <url>` | 否 | 图片 src 的相对基础路径，默认 `images` |

### 批量模式

```bash
node ./dist/cli.cjs convert --input-dir <dir> --output-dir <dir> [--image-base-url <url>]
```

仅处理目录**顶层**的 .docx，不递归子目录。`--input` 与 `--input-dir` 互斥。

---

## assess — HTML 质量评估

```bash
node ./dist/cli.cjs assess <html-file> [--output <report-path>]
```

独立评估 HTML 质量，退出码 1 表示未通过检查（非崩溃）。

### 5 项检查维度

| 维度 | 通过条件 |
|------|----------|
| 结构化校验 | 根元素为 `<article class="docx-content">`，标签正确闭合 |
| 样式信噪比 | 文本内容 vs 标记比例 ≥ 50% |
| 表格还原度 | 合并单元格无还原问题 |
| 样式白名单 | 仅保留 `color` / `background-color` / `text-align` / `text-decoration` / `font-weight` / `font-style` / `max-width` |
| 降噪检查 | 无 `mso-*` 属性、无 `MsoXxx` 类名、无空 `<span>` |

> assess 输入必须是 convert 产出的 HTML；不接受原始 .docx。

---

## 编程式 API

### convertDocx

```typescript
function convertDocx(buffer: Buffer, imageBaseUrl?: string): Promise<ConvertResult>

interface ConvertResult {
  html: string;
  images: Array<{ filename: string; data: Buffer }>;
}
```

示例（CommonJS）：

```js
const { convertDocx } = require('@tencent/docs-docx2html');
const fs = require('fs');

const buffer = fs.readFileSync('document.docx');
const result = await convertDocx(buffer, './images');

fs.writeFileSync('output.html', result.html, 'utf-8');
for (const img of result.images) {
  fs.writeFileSync(`./images/${img.filename}`, img.data);
}
```

### assessHtml + generateReport

```typescript
function assessHtml(html: string): AssessResult
function generateReport(result: AssessResult): string

interface AssessResult {
  file: string;
  timestamp: string;
  overall: 'pass' | 'fail';
  checks: CheckResult[];
  summary: { total: number; passed: number; failed: number; warnings: number };
}
```

---

## 退出码与错误

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 失败（文件不存在 / 格式错误 / assess 未通过 / 参数冲突） |

### 常见错误

| 错误关键词 | 处理 |
|------------|------|
| `--input and --input-dir are mutually exclusive` | 二者选其一 |
| `either --input or --input-dir is required` | 至少指定一个 |
| `ENOENT: no such file` | 检查路径拼写，文件 I/O 问题可重试 |
| 损坏的 ZIP / 非 .docx | 不重试，检查输入文件 |

---

## 反模式（避免踩坑）

- 对同一 .docx 反复 convert 而不 assess → 先跑一次 assess 看质量
- 把非 convert 产出的 HTML 交给 assess → assess 只认 `<article class="docx-content">` 结构
- `--image-base-url` 用绝对 URL → 必须相对路径（如 `./images`）
- 期望批量模式递归子目录 → 只处理顶层
- 使用 `npx docx2html` → 本 Skill 已统一 bundled CLI，不再依赖外部包
