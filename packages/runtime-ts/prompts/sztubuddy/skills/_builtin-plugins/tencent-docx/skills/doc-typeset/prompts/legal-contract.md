# doc-typeset / legal-contract prompt

继承 `base.md` 的全部规则，并应用以下合同专属排版规范。

## 额外 CSS 变量

```css
--signature-block-gap: var(--spacing-section);
--seal-size: 120px;
```

## 条款编号层级

| 层级 | 格式 | 样式 |
|------|------|------|
| 章（h2） | 第一章、第二章… | `<strong>`，顶格 |
| 条（h3） | 第一条、第二条… | `<strong>`，顶格 |
| 款（h4） | （一）（二）… | 正常，缩进 2 字符 |
| 项（列表） | 1. 2. 3. | 缩进 4 字符 |

## 甲乙方信息表

使用如下结构：

```html
<table class="party-info">
  <thead>
    <tr><th>项目</th><th>甲方</th><th>乙方</th></tr>
  </thead>
  <tbody>
    <tr><th scope="row">名称</th><td>{{party_a_name}}</td><td>{{party_b_name}}</td></tr>
    <tr><th scope="row">统一社会信用代码</th><td>{{party_a_code}}</td><td>{{party_b_code}}</td></tr>
    <tr><th scope="row">法定代表人</th><td>{{party_a_rep}}</td><td>{{party_b_rep}}</td></tr>
    <tr><th scope="row">地址</th><td>{{party_a_address}}</td><td>{{party_b_address}}</td></tr>
    <tr><th scope="row">联系方式</th><td>{{party_a_contact}}</td><td>{{party_b_contact}}</td></tr>
  </tbody>
</table>
```

## 签章区布局

使用 flex 双列布局，每方含签名线和盖章占位圆：

```html
<div class="signature-block">
  <div class="signature-party">
    <p><strong>甲方（盖章）：</strong></p>
    <div class="seal-placeholder"></div>
    <p>法定代表人（签字）：_______________</p>
    <p>日期：_______________</p>
  </div>
  <div class="signature-party">
    <p><strong>乙方（盖章）：</strong></p>
    <div class="seal-placeholder"></div>
    <p>法定代表人（签字）：_______________</p>
    <p>日期：_______________</p>
  </div>
</div>
```

`.seal-placeholder` 为圆形虚线边框：`width: var(--seal-size); height: var(--seal-size); border-radius: 50%; border: 2px dashed var(--color-border);`

## 页脚页码

合同为正式法律文件，用页脚居中"第 X 页 / 共 Y 页"，便于核对完整性。在 `<style>` 内声明 `@page`（参见 SKILL.md「页面模型规范」）：

```html
<style>
  @page { @bottom-center { content: "第 " counter(page) " 页 / 共 " counter(pages) " 页"; } }
</style>
```

## 装饰组件触发规则

| 触发内容 | 组件 | variant |
|---------|------|---------|
| 违约责任、赔偿条款 | callout | warning |
| 严禁、禁止事项 | callout | danger |
| 保密条款、知识产权 | callout | info |
| 章与章之间 | divider | section-break |
