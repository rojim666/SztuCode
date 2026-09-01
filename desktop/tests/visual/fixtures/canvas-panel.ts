import { createApp, h } from "vue";
import CanvasPanel, { type CanvasDoc } from "../../../src/components/Canvas/CanvasPanel.vue";
import "../../../src/kimi.css";
import "../../../src/appearance.css";
import "../../../src/canvas-panel.css";

// CanvasPanel 组件独立挂载 fixture：覆盖文字/表格/图片/代码块等核心排版与多文档标签。
// 通过 page.goto("/tests/visual/fixtures/canvas-panel.html") 访问。
const now = new Date().toISOString();

// 内联 SVG data URL 图片，避免 fixture 依赖工作区文件
const sampleImage =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120"><rect width="320" height="120" rx="12" fill="#eceef0"/><circle cx="60" cy="60" r="26" fill="#9aa0a6"/><rect x="104" y="40" width="180" height="14" rx="7" fill="#b9bec3"/><rect x="104" y="66" width="120" height="10" rx="5" fill="#cdd2d6"/></svg>`,
  );

const docs: CanvasDoc[] = [
  {
    id: "doc-01",
    title: "竞品分析报告",
    content: [
      "# 竞品分析报告",
      "",
      "本报告对比三款主流 Agent 产品的**画布能力**，供架构选型参考。",
      "",
      "## 核心结论",
      "",
      "> 文档画布是交付质量的关键差异化能力，表格与图片渲染是基线要求。",
      "",
      "## 能力对比",
      "",
      "| 产品 | 文档画布 | 表格 | 图片 | 导出 |",
      "| --- | --- | --- | --- | --- |",
      "| SztuCode | ✅ 本次新增 | ✅ GFM | ✅ 工作区引用 | Markdown |",
      "| Claude | ✅ Artifacts | ✅ | ✅ | 多种格式 |",
      "| ChatGPT | ✅ Canvas | ✅ | 部分 | Markdown |",
      "",
      "## 架构示意",
      "",
      `![画布架构](${sampleImage})`,
      "",
      "## 代码示例",
      "",
      "```ts",
      'const doc = store.create({ title: "报告", content: markdown });',
      'publish("create", doc);',
      "```",
      "",
      "后续计划：",
      "",
      "1. 支持 HTML 文档类型",
      "2. 接入图片生成技能",
      "3. 会话恢复时回放画布文档",
    ].join("\n"),
    version: 2,
    updatedAt: now,
  },
  {
    id: "doc-02",
    title: "发布检查清单",
    content: ["# 发布检查清单", "", "- [x] 单元测试", "- [x] 构建验证", "- [ ] 视觉回归", "", "详见 `docs/runbook.md`。"].join("\n"),
    version: 1,
    updatedAt: now,
  },
];

// 面板是绝对定位元素，宿主容器提供相对定位上下文
const Host = {
  render() {
    return h("div", { style: "position: relative; width: 100%; height: 100vh; background: #f2f3f4; overflow: hidden;" }, [
      h(CanvasPanel, { docs, activeId: "doc-01", workspaceId: undefined, onClose: () => {}, onSelect: () => {} }),
    ]);
  },
};

createApp(Host).mount("#app");
