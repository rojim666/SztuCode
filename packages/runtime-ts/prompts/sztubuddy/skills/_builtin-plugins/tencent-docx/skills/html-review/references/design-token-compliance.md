# design-token 合规性检测规则

**维度权重：25%**

## 检测目标

确保 HTML 中所有样式属性均通过 CSS 变量 `var(--)` 引用 design token，禁止出现裸字面量值。

## 检测项列表

### DT-01：禁止裸色值

style 属性或 `<style>` 标签中不得出现裸色值。

**违规模式：**
- `style="color: #333333"`
- `style="background: #f5f7fa"`
- `style="border-color: rgb(0, 0, 0)"`
- `style="background: rgba(0, 0, 0, 0.5)"`

**合规示例：**
- `style="color: var(--color-text)"`
- `style="background: var(--color-highlight)"`

**例外：** `var(--token, #fallback)` 形式中的 fallback 值允许出现。

---

### DT-02：禁止裸字号

style 属性或 `<style>` 标签中不得出现裸字号。

**违规模式：**
- `style="font-size: 14px"`
- `style="font-size: 12pt"`
- `style="font-size: 1.2em"` （直接在 style 属性中）
- `style="font-size: 1rem"`

**合规示例：**
- `style="font-size: var(--fs-body)"`
- `style="font-size: var(--fs-h2)"`

---

### DT-03：禁止裸间距

style 属性或 `<style>` 标签中不得出现裸 margin/padding 值。

**违规模式：**
- `style="margin: 10px 0"`
- `style="padding: 16px"`
- `style="margin-top: 2em"`

**合规示例：**
- `style="margin-bottom: var(--spacing-paragraph)"`
- `style="padding: var(--spacing-block)"`

---

### DT-04：禁止裸字体族

style 属性中不得直接指定字体族字符串。

**违规模式：**
- `style="font-family: 'SimHei', sans-serif"`
- `style="font-family: 宋体"`

**合规示例：**
- `style="font-family: var(--ff-heading)"`

---

### DT-05：`:root` 变量块必须存在

输出 HTML 的 `<style>` 标签内必须包含 `:root { }` 变量声明块，且至少包含 `--fs-body`、`--color-text`、`--ff-body` 三个基础变量。

**违规模式：**
- HTML 中无 `<style>` 标签
- `<style>` 内无 `:root { }` 块
- `:root` 块为空

---

## 评分标准

| 问题数量 | 得分 |
|---------|------|
| 0 个违规 | 100 |
| 1-2 个违规 | 80 |
| 3-5 个违规 | 60 |
| 6-10 个违规 | 40 |
| >10 个违规 | 20 |

缺少 `:root` 块（DT-05）直接判定该维度 `passed = false`。

## 修正建议格式

```
[DT-0X] {元素描述} 中 {属性名} 使用了裸值 "{裸值}"，请替换为 var(--{对应token名})
```

示例：
- `[DT-01] <p class="summary"> 的 style 属性中 color 使用了裸值 "#333"，请替换为 var(--color-text)`
- `[DT-02] <h2> 的 style 属性中 font-size 使用了裸值 "16pt"，请替换为 var(--fs-h2)`
