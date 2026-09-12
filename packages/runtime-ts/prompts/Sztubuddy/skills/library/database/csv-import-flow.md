# database · CSV 导入流程

> 本文档承载 **「本地 CSV → 结构化数据表（database）」** 的通用处理流程。
> 📎 字段类型配置见 `params-reference.md` §PropertyConfig；写入值结构见 §PropertyValue。

## 目录

- §0 适用范围与输入
- §1 CSV 检查与字段分析
- §2 路径决策
- §3 路径 A · import_csv 直接导入
- §4 路径 B · create_database + 分批 batch_add
- §5 结果契约
- §6 失败与幂等约束

---

## 0. 适用范围与输入

**适用范围**：用户直接提供 CSV，或上游流程已将其它表格格式转换为 CSV，并要求导入成数据表 / database / 在线表 / 多维表。

**输入**：

- CSV 文件路径；
- database 标题，缺省取 CSV 文件名（不含扩展名）；
- 目标位置；
- 可选的值有 `database_id`，用于覆盖导入或继续未完成的写入。

**路径优先级**：用户明确指定导入方式或字段 schema 时，以用户要求为准；否则执行 §1 分析并按 §2 自动决策。

---

## 1. CSV 检查与字段分析

### 1.1 基础检查

- 文件必须存在且为 `.csv` 后缀；
- 文件不能为空；
- CSV 必须包含单行表头，字段名不能为空且不得重复；
- 解析失败、列数不一致或不存在有效数据行时停止该 CSV 的处理并返回错误；
- 记录文件大小和数据行数，供 §2 决策使用。

### 1.2 字段类型推断

读取 CSV **表头 + 前 N 行样本**（建议 N=20~50），结合字段名语义和样本中的非空值推断类型；支持类型及配置结构统一参考 `params-reference.md` §PropertyConfig，本文不重复定义。

- 只有字段语义和值格式均明确时才使用对应的结构化类型；
- 低基数单值列可推断为 `select`，多值列可推断为 `multi_select`；
- 推断不确定或同列类型冲突时，统一降级为 `text`。

---

## 2. 路径决策

同一 CSV 在以下两条路径中选择一条：

| 条件 | 选择 | 理由 |
| --- | --- | --- |
| 列基本都是 `text` / `number` / `date`，无强类型语义诉求 | **路径 A（§3）** | 一次导入，字段类型交后端推断 |
| 行数很大且字段类型要求不高 | **路径 A（§3）** | 避免按 100 行拆成大量写入批次 |
| CSV 超过 50 MiB | **路径 B（§4）或先拆分 CSV** | `import_csv` 单文件上限为 50 MiB |
| 根据表头和样本判断可能存在 `select` / `multi_select` / `currency` / `checkbox` / `person` 类型的列 | **路径 B（§4）** | 进一步分析并精确指定 schema |

---

## 3. 路径 A · import_csv 直接导入

将当前 CSV 交给 `import_csv.py` 直接导入。鉴权与运行模式按 `entry.md` §统一调用约定处理。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/import_csv.py" --token-stdin "<path-to-local.csv>"
# 覆盖已有 Database
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/import_csv.py" --token-stdin "<path-to-local.csv>" --database-id "<existing_database_id>"
# 指定目标位置
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/import_csv.py" --token-stdin "<path-to-local.csv>" --space-id "<target_space_id>" --parent-id "<target_parent_node_id>"
```

- 文件必须不超过 50 MiB；
- 覆盖既有表时传入对应 `database_id`，避免重复建表；
- 成功结果记录 `node_block_id` 和 `url`。

---

## 4. 路径 B · create_database + 分批 batch_add

本路径内部按顺序执行，必须先取得建表结果，再写入记录。

### 4.1 确定 schema

按 §1.2 的类型推断构造 schema（config 结构见 `params-reference.md` §PropertyConfig）。

- `select` / `multi_select` 的 options 应基于完整 CSV 去重值生成，不能只使用样本值；
- person 列在 schema 最终确定前，按 `entry.md` §Person 写入前置解析，将姓名解析为 uid；无法唯一解析时须确认，或在建表前将整列降级为 `text`；
- 不确定或存在混合格式的列使用 `text`。

### 4.2 创建 database

通过 `create_database` 能力创建 database，调用方式参考 `entry.md` §1；以成功响应中的 `database_id`、最终字段 id 和选项 id 为准。

### 4.3 分批写入

把 CSV 数据行映射为 `records`，通过 `batch_add_database_records` 能力循环写入，调用方式参考 `entry.md` §3。

- 每批最多 100 条；
- 记录值结构见 `params-reference.md` §PropertyValue；
- `select` / `multi_select` 可按 schema 使用选项文本；
- 各批次串行执行；
- 逐条失败保留在 `results` 中，继续处理其余有效记录并汇总失败明细。

---

## 5. 结果契约

每个 CSV 返回一个结构化结果，供直接回执或上游流程汇总：

- 路径 A 成功：`{file_name, path:"A", node_block_id, url}`；
- 路径 B 成功：`{file_name, path:"B", database_id, total_count, success_count, failed_count, failures}`；
- 失败：`{file_name, error}`。

---

## 6. 失败与幂等约束

- 单个 CSV 失败不应影响其它 CSV；
- 路径 A 重试时复用已返回的 `database_id` / `node_block_id` 覆盖同一节点，避免重复建表；
- 路径 B 建表成功但写入中断时，复用已创建的 `database_id`，只补写尚未成功的行，不重新建表；
- 重试前保留已成功批次及逐条结果，禁止整表盲目重放造成重复记录。