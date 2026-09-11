# 文体契合度检测规则

**维度权重：20%**

## 检测目标

根据文档 genre 检查是否包含该文体的必需结构元素。缺少必需元素直接判定该维度 `passed = false`。

## 必需结构元素表

| genre | 必需元素 | 检测方式 |
|-------|---------|---------|
| `government-doc` | 发文字号区、红头标题、落款区 | 见 GF 规则 |
| `legal-contract` | 当事人信息区、条款编号区、签章区 | 见 LC 规则 |
| `academic-paper` | 摘要区、参考文献区 | 见 AP 规则 |
| `stock-research` | 摘要框、风险提示区、免责声明区 | 见 SR 规则 |
| `business-report` | 执行摘要区、至少一个数据表格 | 见 BR 规则 |
| `meeting-minutes` | 出席人列表、议题列表、决议区 | 见 MM 规则 |
| `general` / 其他 | 无强制要求 | 直接通过，score=100 |

---

## GF — government-doc 规则

### GF-01：发文字号区
HTML 中必须含有 `.doc-number` 或包含"〔"+"〕"+"号"文字模式的元素。

### GF-02：红头标题
必须含有 `.doc-issuer` 或 `.gov-doc-header`，且其文字颜色应引用 `var(--color-gov-red)`。

### GF-03：落款区
必须含有 `.doc-footer-sign` 或 `.issuer-sign` 元素，且位于文档末尾。

### GF-04：公文标题居中
`<h1>` 或 `.gov-doc-title` 必须有 `text-align: center` 或对应 CSS class。

---

## LC — legal-contract 规则

### LC-01：当事人信息区
必须含有 `.party-info` 表格，且包含甲方/乙方相关内容。

### LC-02：条款编号
正文中必须含有"第"+"条"或"第"+"章"的条款编号结构（`<h2>/<h3>` 内）。

### LC-03：签章区
必须含有 `.signature-block` 和 `.signature-party` 元素。

---

## AP — academic-paper 规则

### AP-01：摘要区
必须含有 `.abstract` 或 `<section aria-label="摘要">` 且包含 `.abstract-text`。

### AP-02：参考文献区
必须含有 `.references` 或 `<section aria-label="参考文献">` 且包含 `.reference-list`。

### AP-03：IMRaD 结构建议
建议（非强制）含有 `#section-introduction`、`#section-conclusion` 等 IMRaD 节点。缺少时记入 issues 但不降低 passed。

---

## SR — stock-research 规则

### SR-01：摘要框（核心观点）
必须含有 `.abstract-box` 或 `.research-abstract` 元素。

### SR-02：风险提示区（强制）
必须含有 `data-component="callout" data-variant="warning"` 且内含"风险"二字。

**缺少风险提示直接判定该维度 `passed = false`，无论其他项得分如何。**

### SR-03：免责声明区
必须含有 `.disclaimer` 元素，位于文档末尾。

---

## BR — business-report 规则

### BR-01：执行摘要区
必须含有 `.executive-summary` 元素。

### BR-02：数据表格
文档中至少含有 1 个 `<table>` 或 `data-component="data-card"` 元素。

---

## MM — meeting-minutes 规则

### MM-01：出席人列表
必须含有 `.attendee-table` 或包含"姓名"/"部门"列头的表格。

### MM-02：议题列表
必须含有 `.agenda-list` 或 `.agenda-item` 元素。

### MM-03：决议区
必须含有 `.resolution-list` 或 `.resolution-item` 元素，或包含"决议"文字的节区。

---

## 评分标准

| 情况 | 得分 | passed |
|------|------|--------|
| 所有必需元素均存在 | 100 | true |
| 缺少 1 个非关键必需元素 | 70 | false |
| 缺少 2 个必需元素 | 50 | false |
| 缺少关键必需元素（SR-02 风险提示等） | 0 | false |
| genre = general | 100 | true |

## 修正建议格式

```
[GF/LC/AP/SR/BR/MM-0X] 缺少 {元素名称}，请按 {规则说明} 补充对应结构
```

示例：
- `[SR-02] 缺少风险提示区（callout warning），研报必须包含风险提示，请在免责声明前添加 <div data-component="callout" data-variant="warning">风险提示：...</div>`
- `[AP-01] 缺少摘要区，请在正文前添加 <section class="abstract" aria-label="摘要">...</section>`
