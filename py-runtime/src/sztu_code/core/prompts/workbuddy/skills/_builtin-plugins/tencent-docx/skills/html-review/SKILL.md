---
name: html-review
description: |
  HTML 质量门禁 skill（路线 A + 路线 B 共享）。对 doc-typeset（路线 A）或 doc-edit（路线 B）输出的 HTML 进行 5 维度质量检测（design-token 合规性、结构完整性、排版合理性、文体契合度、装饰使用合理性），输出结构化检测报告，不通过则打回上游做一次定向修正（不循环）。
  在 doc-formatter 路线 A 和路线 B 流水线中，每次 HTML 输出后必须调用此 skill；
  当需要检查 HTML 是否存在裸样式值、标题跳级、缺少必需文体元素、装饰过度等问题时，都应使用此 skill 而非手动检查。
category: capability
version: "1.0.0"
agent: doc-formatter
tags: [html-review, quality-gate, typesetting, doc-formatting]
disable-user-invocation: true
---

# html-review Skill

## 何时使用本 Skill

在 `doc-formatter` 的**路线 A** 和**路线 B** 流水线中，每次 HTML 输出后调用本 skill 执行质量门禁：
- **路线 A**：每次 `doc-typeset` 输出 HTML 后调用
- **路线 B**：每次 `doc-edit` 输出 HTML 后调用

若检测不通过，将修正反馈返回对应 skill（路线 A → `doc-typeset`；路线 B → `doc-edit`）做**一次**定向修正，修正后直接输出，不再复检、不循环。

## 职责

执行 6 维度 HTML 质量门禁检测，输出结构化 `HtmlReviewReport`。安全性维度（SC-01~SC-06）为一票否决维度；其余 5 维度参与综合分计算。检测不通过时，生成可操作的修正建议返回给上游 skill。

## 执行方式（脚本化，0 次 LLM 往返）

6 个维度的检测项全部为确定性规则（正则匹配、标签计数、结构解析、class/属性存在性判断），**已由 `scripts/review_html.py` 完整实现**（纯 Python 3 标准库，零第三方依赖）。本 skill **直接运行脚本并解析其 JSON 输出**作为 `HtmlReviewReport`，**无需读取 `references/` 逐条人工检测，无需任何 LLM 推理往返**。

```bash
python3 scripts/review_html.py --html <html_path> --genre <genre>
# 或从 stdin 读取：
cat <html_path> | python3 scripts/review_html.py --stdin --genre <genre>
```

- stdout 输出即为完整 `HtmlReviewReport`（JSON）。
- 退出码：`0` = 通过（`passed=true`）；`1` = 不通过（`passed=false`）；`2` = 运行错误（输入缺失/为空）。
- 脚本失败（退出码 2 或异常）→ 视为 `review_skill_failed`，由 doc-formatter 输出当前最佳 HTML（见 doc-formatter §7）。

`references/` 目录下的规则文件是脚本实现的**规则来源与说明**，仅供维护脚本时对照，**运行时无需加载**。

## 输入契约

```typescript
interface HtmlReviewInput {
  html: string;           // doc-typeset 输出的完整 HTML 字符串
  design_tokens: object;  // 与排版时相同的 design token 对象
  genre: string;          // 文档类型（government-doc / legal-contract / academic-paper 等）
}
```

## 输出契约

```typescript
interface HtmlReviewReport {
  passed: boolean;          // 整体是否通过（score ≥ 80 且所有维度 passed）
  score: number;            // 综合质量分 0-100（安全性维度不参与计算）
  dimensions: {
    design_token_compliance: DimensionResult;
    structural_integrity:    DimensionResult;
    typographic_quality:     DimensionResult;
    genre_fit:               DimensionResult;
    decoration_usage:        DimensionResult;
    security:                DimensionResult;  // 一票否决维度
  };
  actionable_feedback: string[];  // 可操作的修正建议列表（优先级排序）
}

interface DimensionResult {
  passed: boolean;
  score: number;    // 该维度得分 0-100
  issues: string[]; // 发现的问题列表
}
```

## 6 维度检测规则

各维度的详细检测项、评分标准和修正建议格式见 `references/` 目录下的对应文件——这些是 `scripts/review_html.py` 的**实现依据**，运行时由脚本统一执行，无需人工读取：

| 维度 | 权重 | 规则文件（脚本实现依据） |
|------|------|---------|
| design-token 合规性 | 25% | `references/design-token-compliance.md` |
| 结构完整性 | 25% | `references/structural-integrity.md` |
| 排版合理性 | 20% | `references/typographic-quality.md` |
| 文体契合度 | 20% | `references/genre-fit.md` |
| 装饰使用合理性 | 10% | `references/decoration-usage.md` |
| 安全性审查（XSS 防护） | 一票否决 | `references/security-check.md` |

综合分 = Σ(前 5 维度分 × 权重)（安全性维度不参与综合分计算）

## 通过门槛

- `score ≥ 80`
- 所有维度的 `passed` 均为 `true`

任一维度 `passed = false` 则整体 `passed = false`，无论综合分高低。

安全性维度（SC-01~SC-06）任意触发 → 整体 `passed = false`，不受 score 影响。

## 打回修正逻辑（一次，不循环）

```
result = review(html)            # 只检测一次
if result.passed:
    return html                  # 通过 → 直接输出

# 不通过 → 回上游做一次定向修正后直接输出，不再复检
#   路线 A: doc_typeset.revise(html, result.actionable_feedback)
#   路线 B: doc_edit.revise(html, result.actionable_feedback)
html = upstream_skill.revise(html, result.actionable_feedback)
return html
```

## 不可还原 inline badge 检测（SI-07）

`<span>` + `background` + `padding`/`border-radius`/`inline-block` 组合在 docx 中不可还原。检测到即报 Error，改用 `<p>` 纯字体属性或 `<table><td>` 承载底纹。

## actionable_feedback 格式规范

每条反馈须满足：
1. 指明**问题位置**（CSS 属性名、HTML 元素、class 名等）
2. 给出**具体修正方式**（替换为什么、添加什么）
3. 使用中文，简洁明了

示例：
- ✅ `style="font-size: 14px" 中存在裸字号，请替换为 style="font-size: var(--fs-body)"`
- ✅ `<h1> 后直接出现 <h3>，标题层级跳级，请补充 <h2> 层级`
- ❌ `存在样式问题` （过于模糊）
