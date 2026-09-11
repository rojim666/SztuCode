# 提交解析边界

> 何时读取：组件通过本地校验但正式提交解析异常，或容器块退化为纯文本时读取。
>
> 本文只记录无法由本地 schema 完全覆盖的服务端解析边界。表格准入见 `tasks/table_edit.md`；字段与 Mark 契约见 `content_contract.md`；组件语法见 `doc_references.md`。

## 1. 容器子块之间禁止空行

`Callout`、`BlockQuote` 等容器内部，相邻子块之间不能留空行。子块缩进前出现空行时，服务端可能把后续子块识别为缩进代码块，使组件标签退化为正文文本。

容器退化后，内部通常不会留下可供 `update` 的子块 id。提交前应直接生成无空行的合法容器结构，而不是依赖提交后修复。

## 2. dry-run 不等于正式解析

- `submit_review_edit.py --dry-run` / `submit_doc_edit.py --dry-run` 校验本地 action schema、body 翻译、组件顶层结构、Mark 边界和评论锚点。
- `create_doc.py --dry-run` 校验非空、编码、大小，并拒绝 Markdown 正文中的 WorkBuddy 组件标签。
- dry-run 不具备远端目标 block 类型和正式解析上下文；通过 dry-run 不代表正式提交一定成功。

正式失败时按 `error_handling.md` 分类处理，不用真实提交反复试探语法。
