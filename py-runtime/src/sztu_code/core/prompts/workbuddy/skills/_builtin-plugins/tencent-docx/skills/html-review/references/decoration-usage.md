# 装饰使用合理性检测规则

**维度权重：10%**

## 检测目标

确保装饰组件（callout / divider / section-marker / data-card）使用合理，不过度装饰，语义匹配正确。

## 检测项列表

### DU-01：callout 频率控制

全文 `data-component="callout"` 数量不得超过 **5 个**。

**违规模式：** 文档中有 6 个及以上 callout 组件

**修正方向：** 合并相邻同类 callout，或将普通说明改为正文段落，只保留最重要的提示。

---

### DU-02：data-card 内容非空

所有 `data-component="data-card"` 内必须包含实际内容（`.card-value` 或 `.card-kv-list`），不得为空壳。

**违规模式：**
```html
<div data-component="data-card" data-title="指标">
  <!-- 空内容 ❌ -->
</div>
```

**修正方向：** 填充实际数据值，或删除无内容的 data-card。

---

### DU-03：callout-danger 语义匹配

`data-variant="danger"` 的 callout 只能用于真正的危险/禁止内容（含"禁止"、"严禁"、"不得"、"危险"等关键词），不得用于普通提示。

**违规模式：**
```html
<div data-component="callout" data-variant="danger">
  请注意保存文件。  ❌（普通提示不应用 danger）
</div>
```

**修正方向：** 将普通提示改为 `data-variant="info"` 或 `data-variant="warning"`。

---

### DU-04：禁止连续使用 divider

相邻两个 `data-component="divider"` 之间必须有实质内容（至少一个非空 `<p>`、标题或其他内容元素）。

**违规模式：**
```html
<div data-component="divider"></div>
<div data-component="divider"></div>  ❌（连续分隔线）
```

---

### DU-05：section-marker 层级对齐

`data-component="section-marker"` 的 `data-level` 属性应与紧邻的标题层级一致。

**违规模式：**
```html
<div data-component="section-marker" data-level="h2" data-number="1">
  <!-- 但实际内容只是 h3 级别的小节 ❌ -->
</div>
```

**检测方式：** section-marker 的 data-level 值应与其后紧跟的标题元素（h2/h3/h4）一致。

---

### DU-06：装饰组件总密度

装饰组件总数（callout + section-marker + data-card + divider）不得超过文档 `<p>` 数量的 **50%**（装饰组件过多会压过正文）。

**计算公式：**
```
decoration_density = (callout数 + section-marker数 + data-card数) / p元素数
```

`decoration_density > 0.5` 时发出 WARNING（不影响 passed，但计入 issues）。

divider 不计入分子，因为 divider 是结构性而非内容性装饰。

---

## 评分标准

| 违规类型 | 扣分 |
|---------|------|
| DU-01 callout 超限（每超出 1 个） | -10 |
| DU-02 data-card 空内容（每处） | -15 |
| DU-03 danger 语义不匹配（每处） | -15 |
| DU-04 连续 divider（每处） | -10 |
| DU-05 section-marker 层级不对（每处） | -10 |
| DU-06 装饰密度过高（WARNING） | -0 |

初始分 100，扣分后最低 0。综合分 < 70 则该维度 `passed = false`（装饰维度容忍度略高于结构维度）。

## 修正建议格式

```
[DU-0X] {问题描述}，建议 {具体修正方式}
```

示例：
- `[DU-01] 文档包含 7 个 callout，超出上限 5 个，请将第 4-5 个普通 info callout 合并或改为正文`
- `[DU-03] 第 2 个 callout 使用了 danger 变体但内容为普通注意事项，请改为 data-variant="info"`
- `[DU-04] 第 15 行和第 16 行出现连续两个 divider，请删除其中一个`
