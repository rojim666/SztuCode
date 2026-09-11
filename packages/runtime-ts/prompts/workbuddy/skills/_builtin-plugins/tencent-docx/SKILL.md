---
name: tencent-docx
description: "专业 Word 文档（.docx）创作与美化助手。用于生成研报、论文、公文、合同等垂类专业 Word 文档，或对已有 .docx 进行排版美化。当用户需要写文档、生成 Word、排版或美化 .docx 时调用。"
version: "0.4.1"
---
# 腾讯文档 Doc 智能体 —— 专业 Word / Docx / DOCX 文档创作与美化

> 端到端 **Word / Docx / DOCX 文档（.docx）** 智能体：从**专业创作 → 专业美化 → 输出交付**全流程自动编排。 覆盖：**生成专业 Word 文档、专业美化 Word / Docx / DOCX 文档、导出 .docx** 全部场景。 必须依赖 [tdoc-orchestrator SKILL](./skills/tdoc-orchestrator/SKILL.md)

---

## ⛔ 强制执行规则（MUST — 不可跳过、不可简化、不可"觉得简单就直接做"）

**空白文档例外**：若用户仅要求新建空白本地 Word/DOCX（无内容创作或排版需求），不进入本插件编排，转交 `tencent-local-office-edit` 使用 `create_doc` 创建空白模板。

**本 Skill 被加载后，你的下一步动作必须是：Read `./skills/tdoc-orchestrator/SKILL.md` 并严格按其 Stage 0 流程执行。**

### 禁止行为（违反即视为 Bug）

1. **禁止跳过 orchestrator 直接调用 MCP 编辑工具** — 无论任务多简单（哪怕只是"加粗一个字"），都必须先走 orchestrator 的 Stage 0 入口判断。唯一例外：`open_file`、`close_file`、`save_file`、`get_pool_status` 等纯文件管理操作可直接调用
2. **禁止在 thinking 中自行判断"这个任务简单，不需要走流程"** — 简单/复杂由 orchestrator 内部的 Phase 2 Classify 决定，不是你决定
3. **禁止直接调用 `tencent-local-office-edit` skill / `Bash python-docx`** — 所有文档操作必须经 orchestrator 路由到正确的下游 Skill 后才能调用工具
4. **禁止"先调一下 MCP 看看再说"** — 任何试探性调用都违反流程
### 正确的执行顺序（唯一合法路径）

```
1. Read ./skills/tdoc-orchestrator/SKILL.md        ← 你现在必须做这一步
2. 按 orchestrator Stage 0 判断入口类型
3. 按 Stage 链路由到对应 Agent/Skill
4. 由下游 Skill（doc-typeset / html-to-docx 等）决定具体工具调用
```

## 能力覆盖 —— 专业 Word / Docx / DOCX 文档全流程

1. **生成专业 Word / Docx / DOCX 文档**：从头创作研报 / 年报 / 论文 / 公文 / 合同 / 商务报告 / 会议纪要等垂类专业 .docx，自动生成封面、目录、专业排版。
2. **专业美化 Word / Docx / DOCX 文档**：对已有 Word 文档进行专业排版美化 —— 调整版式结构、优化视觉层级、统一字体字号、规范表格与图片、生成专业级视觉呈现。
3. **专业输出交付**：导出本地专业级 .docx / Word 文档，可直接分发或投稿。
---

**现在立即执行：Read `./skills/tdoc-orchestrator/SKILL.md`**

