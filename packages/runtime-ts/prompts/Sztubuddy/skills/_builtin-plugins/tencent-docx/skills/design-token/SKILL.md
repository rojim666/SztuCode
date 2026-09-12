---
name: design-token
description: |
  按文档类型（genre）选择主题并输出标准化设计令牌（Design Tokens），驱动 doc-typeset skill 的所有样式决策。
  支持公文、学术论文、商务报告、创意营销、通用五大场景，输出含 typography/color/spacing/layout 的 W3C DTCG 格式 JSON 和 CSS 变量映射。
  当 doc-formatter 流水线需要确定排版风格、需要字体/颜色/间距/页边距决策时，必须调用此 skill；
  不要跳过它直接写裸值——所有样式决策的唯一入口就是这里。
category: capability
version: "1.0.0"
agent: doc-formatter
tags: [design-tokens, typography, theming, doc-formatting]
disable-user-invocation: true
---

# design-token Skill

## 1. 职责

根据文档类型（genre）选择合适的设计令牌主题和版式规则，输出标准化的 DesignTokenOutput，供 doc-typeset skill 消费。版式规则文件作为补充上下文，描述该 genre 对应的国标排版规范（如 GB/T 9704）。

## 2. 输入/输出

### 输入
```typescript
interface DesignTokenInput {
  genre: string;             // 文档类型，合法值见第 3 节映射表
  scene_type?: string;       // 场景细分（如 "formal"、"creative"），可选，用于未来扩展
  style_reference?: string;  // 风格参考描述（用于细化主题选择），可选
}
```

### 输出
```typescript
interface DesignTokenOutput {
  theme_name: string;                    // 主题名称
  tokens: DesignTokenBundle;            // W3C DTCG 格式 token 集合
  typography_rules: string | null;       // 版式规则 Markdown 路径（可选）
  css_variables: Record<string, string>; // 预转换的 CSS 变量映射
}
```

## 3. Genre → 主题映射

| genre | 说明 | theme_file | 预编译产物（直接查表） | rules_file |
|-------|------|-----------|-----------|-----------|
| `government-doc` | 党政机关公文 | `tokens/themes/formal-government.json` | `tokens/compiled/government-doc.json` | `tokens/rules/gb-t-9704-government.md` |
| `academic-paper` | 学术论文 / 学位论文 | `tokens/themes/academic-paper.json` | `tokens/compiled/academic-paper.json` | `tokens/rules/gb-t-7713-academic.md`（含 7714 引用规则） |
| `business-report` | 商务报告 / 分析报告 | `tokens/themes/business-modern.json` | `tokens/compiled/business-report.json` | — |
| `marketing-doc` | 创意营销 / 活动方案 | `tokens/themes/creative-marketing.json` | `tokens/compiled/marketing-doc.json` | — |
| `general`（默认） | 其他/未明确场景 | `tokens/themes/modern-minimal.json` | `tokens/compiled/general.json` | — |

当 genre 不在上表时，使用 `general` 兜底策略。

## 4. 执行方式（预编译查表，0 次 LLM 往返）

所有主题的 `DesignTokenOutput`（含 `theme_name` / `tokens` / `css_variables` / `typography_rules`）已由 `scripts/build_tokens.py` **预编译**为静态产物，存放在 `tokens/compiled/`。运行时本 skill **只做静态查表**：

1. 按 genre 从 `tokens/compiled/index.json` 定位对应产物文件（未命中 → `general`）；
2. **直接读取该 compiled JSON 作为 `DesignTokenOutput` 返回**，无需任何转换或 LLM 推理。

> 主题 JSON 的字面值已内含精确规范（如 GB/T 9704 页边距、行距磅数），`typography_rules` 仅作可选溯源上下文，运行时**无需读取**。

**CSS 变量命名 = token 路径扁平化**（与 doc-typeset 模板的 token 注入层一致，语义变量 `--fs-*`/`--ff-*` 由模板通过 `var(--typography-*, fallback)` 消费）：

```
typography.fontFamily.heading → --typography-fontFamily-heading
typography.fontSize.h1        → --typography-fontSize-h1
typography.lineHeight.body    → --typography-lineHeight-body
color.primary                 → --color-primary
spacing.paragraph             → --spacing-paragraph
layout.marginTop              → --layout-marginTop
```

> **维护**：修改 `tokens/themes/*.json` 后，须重跑 `python3 scripts/build_tokens.py` 重建 `tokens/compiled/`。

## 5. 文件结构

```
skills/design-token/
├── SKILL.md                          # 本文件
├── scripts/
│   └── build_tokens.py               # 预编译构建脚本（themes → compiled）
└── tokens/
    ├── themes/                       # DTCG 主题源文件（可编辑）
    │   ├── formal-government.json
    │   ├── academic-paper.json
    │   ├── business-modern.json
    │   ├── modern-minimal.json
    │   └── creative-marketing.json
    ├── compiled/                     # 预编译产物（构建生成，运行时查表读取）
    │   ├── index.json                # genre → 产物文件 查表索引
    │   ├── government-doc.json
    │   ├── academic-paper.json
    │   ├── business-report.json
    │   ├── marketing-doc.json
    │   └── general.json
    └── rules/                        # 版式规范（可选溯源上下文）
        ├── gb-t-9704-government.md
        ├── gb-t-7713-academic.md
        └── gb-t-7714-citation.md
```
