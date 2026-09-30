# ADR-0003：提示词目录与按需注入 Harness

- 状态：accepted
- 日期：2026-08-17

## 背景

系统提示词已按[旧提示词参考](../archive/legacy-prompts.md)拆分为多个 Markdown 原子，但各章节曾各自解析
`index.json`、校验状态并缓存正文。主 Agent、子 Agent、斜杠命令、压缩器和工具注册表
也分别负责拼接提示词，容易造成重复注入、引用顺序依赖和无消费者提示词进入上下文。

## 决策

使用 `PromptCatalog` 统一解析、校验、缓存和按稳定 ID 读取提示词元数据。章节模块保留
兼容 API，但只声明该章节的 ID、启用状态和命令映射契约。

使用 `PromptHarness` 根据真实运行能力组合动态提示词。目前它只处理权限模式和会话记忆：

- `auto` 权限模式注入 `safety-prompts/auto-mode`；
- 同时具备 `Session` 与 `SessionStore` 时注入 `memory-system-prompts/auto-memory`；
- `reference-only` 内容可查询，但不得由 Harness 自动注入。

静态主提示词保持稳定顺序；斜杠命令、子 Agent 角色、压缩器和工具描述只在对应消费者
实际运行时按 ID 读取。确定性权限、沙箱和命令检查继续由代码负责，提示词不能替代它们。

## 后果

新增提示词必须先写原子 Markdown 和索引元数据，再在唯一真实消费者处引用稳定 ID。若新增
跨运行状态的动态规则，应扩展 `PromptRuntimeContext` 和 `PromptHarness` 并覆盖“未满足条件时
不注入”的测试。修改内置 Markdown 后需重启 daemon 以清除进程级缓存。
