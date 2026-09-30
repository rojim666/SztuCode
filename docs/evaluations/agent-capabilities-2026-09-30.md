# Agent 能力核对（2026-09-30）

[返回文档中心](../README.md) · [目录地图](../development/repository-layout.md)

## 总体判断

项目已经具备**可在本地项目中执行多步任务的 Coding Agent 工程原型**：模型可读取和搜索文件、编辑代码、执行命令、接收工具结果继续工作，配套会话、权限、压缩、子代理和工作流。它已超出单轮聊天或模型 API 包装器的范围。

目前适合有人监督的代码理解、局部修改、测试排错、结构化工作流和本地文档任务。是否能稳定完成一个具体项目，仍取决于模型、配置、工具权限、依赖环境和可执行的验收条件。
现有证据不足以宣称大型项目长期无人值守交付、任意崩溃后安全续跑、真实外部服务事务完整性，或任何公开 benchmark 排名。

本报告基于当前工作区代码及本次离线测试，包括整理前已有但未提交的改动；不替代发布版本的验收。
不沿用旧评审的“68/100”等主观评分，也不将测试数量换算成任务成功率。

## 先区分两条运行链

- **默认 Python 链**：根 `package.json` 的 `daemon`、`cli` 指向 `py-runtime`，端口 `7437`。核心在 `py-runtime/src/sztu_code/core/`，还有 Python CLI、Textual TUI 和评测 runner。
- **TS 桌面链**：`daemon:ts`、`cli:ts` 指向 TS runtime，端口 `7438`。桌面端是 Tauri + Vue，连接 TS daemon。
- 两条链分别有 Agent Loop、工具、权限、会话和工作流实现。相同名称不保证所有参数、行为、完成验收和恢复机制一致。

入口证据：[根脚本配置](../../package.json)、[Python Runner](../../py-runtime/src/sztu_code/core/runner.py)、[TS ServerService](../../packages/runtime-ts/src/server-service.ts)。旧文档中的“Python 已退役”已不符合当前代码。

## 已经具备什么

### 1. 多步编码执行：已实现，核心路径有离线测试

两条链都具有模型 → 工具 → 结果回填 → 下一步的循环。可以读取、搜索、写入、编辑工作区文件，调用 shell 执行构建或测试；Python 还注册了文件历史等工具。
模型错误、工具错误、步数或预算耗尽、取消和受困情况有相应控制路径。

TS 工具实现已包含 ripgrep 优先搜索、行号读取、精确替换和多处编辑，还支持后台 shell 的状态、日志和停止。
因此旧评审中“缺 rg”不能继续作为当前结论。编辑仍以文本操作为主，本次没有证明完整语言服务器辅助的语义重构。

证据：[Python Loop](../../py-runtime/src/sztu_code/core/loop.py)、[Python 工具](../../py-runtime/src/sztu_code/core/tools/builtin/__init__.py)、[TS 工具](../../packages/runtime-ts/src/tools.ts)、[TS 循环测试](../../packages/runtime-ts/tests/runtime.test.ts)。

### 2. 完成验证与自动修复：Python 已接入，但默认关闭

Python Runner 在 `require_verification` 开启且 Agent 返回成功时执行独立验证；验证失败会追加修复提示并重验。
验证证据与工作区摘要关联，包含陈旧证据降级及修复熔断机制。
配置默认 `require_verification=False`，所以普通 `success` **不能自动理解为测试、类型检查和所有要求均已通过**。
启用后仍取决于 completion contract 中实际定义的验收条件。

TS 工作流要求 Tester/Reviewer 提供结构化交接；本次没有证明 TS 所有普通 run 都强制走同等独立验收链。

证据：[Python 验证入口](../../py-runtime/src/sztu_code/core/runner.py)、[配置默认值](../../py-runtime/src/sztu_code/core/config.py)、[修复与证据逻辑](../../py-runtime/src/sztu_code/core/verification/repair.py)、[验证修复测试](../../py-runtime/tests/unit/test_verification_repair.py)。

### 3. 子代理和多 Agent 编排：已实现，不能只说“同步子代理”

Python 支持前台和后台派生子代理、角色工具约束、深度限制和后台任务注册。
TS 支持独立子会话、父子关联、立即返回后台句柄以及结果查询和取消。
两条链都有 DAG 调度；任务依赖、并发限制、任务预算、重试及失败传播已经有离线测试。
TS 调度器可在任务完成后立刻补充就绪节点。

限制：进程内后台句柄不构成跨重启任务恢复；角色提示词和 JSON 交接校验也不能证明 Reviewer 的判断准确。
真实模型下的协作效率、合并冲突处理和端到端成本尚未由本次测试证明。

证据：[Python 子代理](../../py-runtime/src/sztu_code/core/subagent/tool.py)、[Python DAG 测试](../../py-runtime/tests/unit/test_workflow_orchestrator.py)、[TS 子代理](../../packages/runtime-ts/src/subagent.ts)、[TS 子会话测试](../../packages/runtime-ts/tests/subagent-session.test.ts)、[TS 调度测试](../../packages/runtime-ts/tests/workflow-scheduler.test.ts)。

### 4. 上下文与记忆：已实现，长期效果尚未证明

两条链都有上下文压缩、工具输出控制、持久化会话及记忆读取路径。
TS 记忆分为全局、项目和会话层，支持按需读取、笔记版本以及显式 `memory_consolidate`。
Python 还包含 WorkingState，以及失败轨迹 → MemoryPatch → ValidationGate → Ledger 的记忆进化机制。

这些模块的存在和确定性测试证明机制可执行，不证明长期学习质量。摘要仍可能遗漏信息；记忆是否持续提高任务成功率、是否引入错误事实，需要跨任务真实评测。

证据：[Python 记忆进化](../../py-runtime/src/sztu_code/core/memory/evolution.py)、[Python 进化测试](../../py-runtime/tests/unit/test_memory_evolution.py)、[TS 记忆](../../packages/runtime-ts/src/memory.ts)、[TS 上下文](../../packages/runtime-ts/src/context.ts)。

### 5. 会话、审计与权限：已实现；保存记录不等于恢复执行

两条链都能保存会话和运行状态，有事件、trace、权限审批与工作区边界检查。
TS 能保存 context checkpoint，从会话文件回放事件，并提供 operation 查询和恢复状态接口。
`OperationStore` 会把恢复时仍为 running 的 operation 标为 unknown，要求 reconciliation。
这属于持久化和对账基础设施，不能理解为完整工具执行事务。

Python `RunStore.reconcile()` 将 daemon 重启遗留的 running 记录标为 cancelled，原因是 `daemon_restarted`。
当前核对的命令分发没有通用 `run.resume`；TS `run.replay` 回放记录，不重建并继续 AgentLoop。
不能承诺断电后自动继续，而且不重复外部写入。
权限层有审批与路径约束，但本次没有进行完整安全审计，也不能把它当作 OS 级隔离沙箱。

证据：[Python RunStore](../../py-runtime/src/sztu_code/core/run_store.py)、[TS replay 分发](../../packages/runtime-ts/src/server-service.ts)、[TS OperationStore](../../packages/runtime-ts/src/operation-store.ts)、[checkpoint 测试](../../packages/runtime-ts/tests/durable-checkpoint.test.ts)。

### 6. 模型、Skills 和 MCP：扩展入口已实现，能力依赖实际接入

有 OpenAI/兼容接口及 Anthropic 等 provider 路径，角色提示词、Skills/插件资源和 MCP 工具接入。
TS 的 OpenAI 连接逻辑覆盖自定义地址、显式端口、网关前缀、接口探测、SSE 分片和部分输出失败处理；本次通过本地 HTTP mock 网关测试。
这证明本地适配契约，没有证明某个真实远程端口已经连通。

插件目录、提示词资源或 MCP server 配置不能直接算作已可用的外部业务能力：还需要实际服务、认证、依赖和端到端验收。
本次没有访问真实模型、浏览器 MCP、微信或任何第三方业务账户。

证据：[Python provider](../../py-runtime/src/sztu_code/core/llm/openai_provider.py)、[Python MCP](../../py-runtime/src/sztu_code/core/mcp/client.py)、[TS 网关测试](../../packages/runtime-ts/tests/openai-connection.test.ts)、[资源集成说明](../reference/workbuddy-prompts.md)。

### 7. Office、检索与业务连接器：实现程度不一

Python 有本地文档读写与 Office 工具，TS 也有 Office、文档解析、词法/向量/混合检索模块及测试文件。
这些源文件属于实现证据；本次未对所有格式、版式、检索质量和外部依赖执行完整验收。
Jev 在项目中明确是实验路径，不能把实验或评测计划当作稳定默认行为。

TS `connectors.ts` 的飞书实现是 `FakeFeishuConnector`，在内存里模拟授权、草稿和提交。
它可测试接口和幂等语义，**不代表已连接真实飞书账户**。

证据：[Python Office](../../py-runtime/src/sztu_code/core/office.py)、[TS Office 测试](../../packages/runtime-ts/tests/office-tools.test.ts)、[TS 检索测试](../../packages/runtime-ts/tests/hybrid-search.test.ts)、[飞书模拟实现](../../packages/runtime-ts/src/connectors.ts)、[Jev 实验说明](../architecture/experimental-jev.md)。

## 本次验证记录

所有模型调用均为 mock；没有运行真实模型 benchmark。本次只选已有离线测试验证上述关键运行机制，没有修改测试或核心实现。

Python：**146 passed**。

```powershell
uv run --project py-runtime --offline pytest py-runtime/tests/unit/test_loop.py py-runtime/tests/unit/test_workflow_orchestrator.py py-runtime/tests/unit/test_verification_repair.py py-runtime/tests/unit/test_run_store.py py-runtime/tests/unit/test_memory_evolution.py py-runtime/tests/unit/test_subagent_registry.py -q --tb=short
```

TS：第一组 **57 passed**，第二组 **11 passed**。

```powershell
node --import tsx --test packages/runtime-ts/tests/runtime.test.ts packages/runtime-ts/tests/openai-connection.test.ts
node --import tsx --test packages/runtime-ts/tests/subagent-session.test.ts packages/runtime-ts/tests/workflow-scheduler.test.ts packages/runtime-ts/tests/durable-checkpoint.test.ts packages/runtime-ts/tests/operation-store.test.ts
```

以上共 **214 项专项离线测试通过**，不代表全仓测试、发布验收或真实任务成功率。未在本次运行全量 `npm test`、公开 benchmark、真实模型 E2E 或崩溃故障注入。
文档调整另外运行 `npm run docs:links`；核心文件完整性另做移动前后的 SHA-256 比对。

## 能力提升最值得优先验证的方向

1. **统一完成语义**：明确区分模型结束、任务结束和验收通过；确认 Python 独立验证如何启用，以及 TS 普通 run 的验收边界。
2. **跨进程安全续跑**：贯通 provider/tool intent-result 记录、未知副作用对账和恢复执行，并做崩溃注入验收。
3. **真实任务回归**：选择有固定验收条件的仓库任务，记录成功率、测试结果、耗时、成本和重复副作用；分别评估 Python 与 TS。
4. **扩展服务实测**：飞书模拟替换为实际适配前，先验收认证、限流、读回校验、错误恢复；Office 和检索也应分别验收。

当前最准确的定位是：**有较完整工具与编排机制、可辅助完成本地开发任务的 Agent 原型；离可靠的长期无人值守执行仍缺跨进程恢复和真实任务质量证据。**
