---
name: generate-fillable-contract-html
description: 生成适于 HTML 转 DOCX 的中文待填合同、报价单和授权委托书 HTML。用户要求创建待填业务文档模板、合同填空或可按书签填写的 HTML 时使用。
disable-user-invocation: true
---

# 待填合同 HTML 生成

生成完整、真实的中文业务 HTML，适合交给 `html-to-docx` 转换。

## 待填字段规则

硬性要求：

- 表格里面不要用横线当书签，用空格当书签。
- 书签必须换成中文名。

每个字段保留稳定的英文 `data-docx-field`，并使用 `data-docx-bookmark` 指定唯一中文书签名。重复业务字段在中文名后添加 `_01`、`_02`。

```html
<p>甲方名称：<span data-docx-field="buyer_name" data-docx-bookmark="甲方名称">________________</span></p>
```

表格字段使用 `&nbsp;` 提供可见空白书签范围，不使用下划线：

```html
<tr>
  <th>软件名称</th>
  <td><span data-docx-field="software_name" data-docx-bookmark="软件名称">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span></td>
</tr>
```

不得使用正文普通空格、只有冒号的空值、`请输入`/`待填写` 提示文案、英文书签名或表格下划线书签。

## 输出要求
- 输出完整 HTML5 文档，包含 `html`、`head`、`style` 与 `body`。


## 自检
- 每个字段同时包含英文 `data-docx-field` 和唯一中文 `data-docx-bookmark`。
- 正文书签范围使用连续下划线；表格书签范围只使用 `&nbsp;`。
- 中文书签名无空格；重复字段使用 `_01`、`_02` 区分。
- 不含提示性占位文案、正文普通空格填空或表格下划线书签。
