# doc 场景示例（可执行合规样例）

> 本目录存放 `submit_review_edit.py` / `submit_doc_edit.py` 的 actions JSON 示例。所有示例都经 `verify_examples.py` 通过脚本 dry-run 校验，是"活的"合规样本。
>
> 规则升级后（例如新加了字段强约束），Agent 或维护者只需跑一次 `verify_examples.py`，即可发现哪些示例老化了。

## 文件清单

| 文件 | 场景 | 提交脚本 |
|---|---|---|
| `example_C_rewrite_block.json` | 整块改写（首选 update + Mark ar 串联） | `submit_review_edit.py` |
| `example_C2_partial_replace.json` | 块内部分文字替换（保留未改文字裸写） | `submit_review_edit.py` |
| `example_D_change_block_type.json` | 换块类型（段落改成二级标题；`delete + insert_after`） | `submit_review_edit.py` |
| `example_E_edit_heading.json` | 修改标题文字 | `submit_review_edit.py` |
| `example_F_reuse_card.json` | 复用上一轮审阅卡片 | `submit_review_edit.py` |
| `example_G_global_review.json` | 全局总评卡（`agent_review_global`） | `submit_review_edit.py` |
| `example_word_selection.json` | 划词修订（改一段文字里的部分内容） | `submit_review_edit.py` |
| `example_comment_revision.json` | 评论修订（把随性引言改正式风格） | `submit_review_edit.py` |

## 使用姿势

**跑单个示例的 dry-run**（客户端模式，需要 token）：

```bash
FAKE_TOKEN="fake-token-1234567890abcdefghijklmnop"
echo "$FAKE_TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_review_edit.py" \
    --token-stdin --page-id "test_page" \
    --summary "$(basename example_C_rewrite_block.json .json)" \
    --actions-file example_C_rewrite_block.json --dry-run
```

**跑全部示例（推荐）**：

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/scripts/examples/verify_examples.py"
```

成功打印 `KS_EXAMPLES_SELFCHECK_OK`；任一示例失败会给出具体 action 与错误码，方便定位。

## 命名规范

- 文件名前缀 `example_<场景 tag>_<snake_case 短描>.json`
- 内容是一个 JSON 数组（等价于 `--actions-file` 输入）
- 审阅模式示例末尾必须有 `card_op`；编辑模式示例禁止 `card_op`
- 示例应该**只用假 blockId**（`blk_*` / `dis_*` 之类），不能包含真实文档数据

## 与 `workflows.md` 的关系

`workflows.md` 承载"何时用哪个示例"的场景说明；本目录承载**示例的真身与自检**。规则升级时先跑 `verify_examples.py`，确定哪些示例需要重写。
