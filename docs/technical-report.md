# SztuCode 项目技术报告

> **版本** v0.2.0（TypeScript 主线）/ v0.0.1（Python 镜像） · **许可证** MIT · **文档日期** 2026-09-01
> **一句话定位**：本地优先、事件驱动、可审计的 AI Coding Agent 运行时，同一套 daemon/client 架构的 TypeScript 与 Python 双语言实现，定位"Agent 时代的教学操作系统"。

---

## 1. 项目概述

SztuCode 由社区成员发起维护，目标是复现当前 AI Coding Agent 的完整工程链路，而非仅封装模型 API：

```
用户目标 → 项目与会话上下文 → Agent 规划与模型推理
  → 工具调用与权限审批 → 文件修改、测试与结果回填
  → Diff 审阅、Trace 与会话恢复
```

项目遵循"技术民主化"三原则：**访问的民主**（内置免费模型、零配置启动）、**理解的民主**（双语言实现 + 架构文档摊开工程细节）、**创造的民主**（Issue → PR → Review 真实开源协作路径）。

---

## 2. 技术栈

| 层级 | TypeScript 主线 | Python 镜像 |
| --- | --- | --- |
| 桌面端 | Tauri 2 + Vue 3 + Vite | —（复用 TS daemon 桌面端） |
| 终端 | Node CLI（sztu-ts，无 TUI） | Textual TUI（sztu-tui）+ Python CLI |
| 运行时 | Node daemon（127.0.0.1:7438） | Python daemon（127.0.0.1:7437） |
| 契约 | TS 类型包 + 生成 wire-protocol.md | pydantic 模型（core/bus/*） |
| 传输 | TCP / NDJSON / JSON-RPC 2.0 | 同左 |
| 持久化 | ~/.sztu/ | 同左 |
| 依赖管理 | npm workspaces | uv + hatchling（PEP 621） |
| 质量工具 | tsc、tsx --test、Playwright | ruff、mypy(strict)、pytest |

---

## 3. 系统架构

### 3.1 双运行时并行架构

```
┌─ TypeScript 主线 ─────────────────────────────────┐   ┌─ Python 镜像 ───────────────────────────────┐
│ desktop/      Tauri 2 + Vue 3 桌面工作台           │   │ py-runtime/…/tui    Textual 终端 TUI         │
│ packages/cli        Node CLI（sztu-ts）            │   │ py-runtime/…/cli    Python CLI（sztu-py）     │
│ packages/runtime-ts Node daemon ── 127.0.0.1:7438  │   │ py-runtime/…/core   Python daemon ── 7437    │
│ packages/protocol   共享契约（类型包）               │   │ py-runtime/…/bus    pydantic 契约模型        │
└───────────────────────────────────────────────────┘   └──────────────────────────────────────────────┘
```

两套 runtime 使用不同命令名与端口，可并行安装运行；客户端经同一套 JSON-RPC 协议连接，Agent 执行状态以所选 daemon 为准。

### 3.2 TypeScript Package 分层（依赖只允许向下）

```
desktop / packages/cli
  → @sztucode/client
    → @sztucode/protocol

@sztucode/runtime-ts
  → @sztucode/server → @sztucode/protocol
  → @sztucode/session-fs → @sztucode/session → @sztucode/ai
  → @sztucode/agent-core → @sztucode/ai
  → @sztucode/telemetry
```

| Package | 职责 |
| --- | --- |
| `ai` | Provider 无关的模型、消息、流式类型；不依赖 daemon |
| `agent-core` | Agent/tool 基础抽象；不拥有 Socket 或桌面协议 |
| `protocol` | JSON-RPC、NDJSON、事件、Session、Workflow 共享类型与校验 |
| `server` | daemon 进程、套接字与消息分发 |
| `session` / `session-fs` | 会话状态与文件持久化 |
| `telemetry` | 遥测与运行轨迹 |
| `runtime-ts` | 产品运行时：Agent Loop、工具、权限、上下文、记忆、编排 |
| `cli` / `evaluation` | 终端客户端 / 评测 runner |

---

## 4. 通信协议与数据流

- **协议**：JSON-RPC 2.0 封装于 NDJSON，TCP 本地回环。
- **事件流**：daemon 通过事件流持续回传执行状态（token 增量、工具调用、权限请求、进度），客户端据此渲染时间线。
- **文档生成**：`npm run docs:protocol` 从类型契约生成协议文档，保证文档与代码一致。

---

## 5. 核心子系统

### 5.1 Agent Loop（运行时中枢）
- 工具调用、上下文压缩、失败重试、停止条件的核心循环；
- provider usage 校准：服务端真实 input token 修正本地估算；
- 上下文溢出应急通道：检测 `context_length_exceeded` 后强制收缩重试（上限 2 次），不消耗 LLM 失败预算；
- 压缩成本入账：摘要生成消耗的 token 计入运行用量。

### 5.2 上下文管理（评分 85）
- 真实 token 编码、双重累加修复、增量上下文净化；
- 自动压缩（Cooldown/熔断/最小保留 token 策略）+ 后台压缩；
- 压缩失败区分用户取消与质量失败，不误触发熔断。

### 5.3 工具系统（评分 82）
- 文件读写、语义搜索（embedding 索引）、rg 全文搜索、glob；
- bash 后台任务三件套（启动/状态/日志/终止）、工具级超时全线接线；
- 全局早停与工具批量调用。
- **缺口**：Web、LSP、结构化 Diff 读取工具。

### 5.4 权限与安全（评分 72）
- 四级权限模式、范围升级留痕、工作区边界保护；
- 工具权限门控、敏感操作审批、拒绝追踪。
- **缺口**：`always_allow` 字面量匹配、语义级危险命令规则。

### 5.5 记忆系统（评分 81）
- 全局/项目/会话三层内存，会话笔记持久化；
- 评分检索 + run 内活读 + 巩固管道（session → project 上下文，按 note id 去重）；
- **缺口**：基于 Embedding 的语义检索。

### 5.6 编排能力（评分 82）
- 事件驱动调度、spawn_agent 异步化（句柄/状态/结果/取消）；
- planner 输出校验为 WorkflowGraph 后并行执行；
- **缺口**：上游 Agent 失败后的自动降级。

### 5.7 可观测性（评分 80）
- 运行事件、日志、token 用量、上下文占用、时间线追踪；
- **挂账**：O(n²) 序列化三源、trace 轮转。

### 5.8 扩展生态（评分 74）
- MCP：stderr 排空、退避重连、list_changed、并行连接、能力记录；
- Skills 懒加载缓存；
- **缺口**：MCP SSE 传输、ProviderCompat 接线。

### 5.9 成本效率（评分 52）
- token 口径修正、压缩成本入账、rg/skills 减少 IO；
- **挂账**：O(n²) 序列化、cache 负优化、兜底无缓存。

---

## 6. 能力评估（第八轮，2026-08-31）

| 能力维度 | 评分 | 判词 |
| --- | ---: | --- |
| 上下文管理 | 85 | usage 校准 + 溢出应急 + 压缩成本入账 |
| 工具系统 | 82 | rg 后端 + 后台任务 + 超时接线 |
| 权限与安全 | 72 | 本轮未动，语义级规则仍缺 |
| 韧性 | 70 | 529 白名单 + 超时可重试 + 溢出应急 |
| 编排能力 | 82 | 事件驱动 + 异步子 Agent + planner 校验 |
| 可观测性 | 80 | 本轮未动，O(n²) 序列化挂账 |
| 记忆系统 | 81 | 评分检索 + 巩固管道 + 容量上限 |
| 扩展生态 | 74 | MCP 增强 + Skills 懒加载 |
| 成本效率 | 52 | 口径修正 + 压缩入账，负优化挂账 |
| **综合** | **75** | 9 维均值，187/187 测试通过 |

> 评分原则：按**运行时真实行为**标定，不按接口声明；无真实基准数据的项不作产品成绩推断。

---

## 7. 路线图

| 版本 | 目标 | 关键内容 |
| --- | --- | --- |
| v0.1 | 可靠的本地 Agent 闭环 | 统一评测入口、Shell 命令结构化分析、权限策略强化、核心回归测试 |
| v0.2 | 项目级理解与跨语言工具 | 增量符号索引、分层上下文检索、统一 LSP（Python/TS）、Multi-SWE-bench 小规模基线 |
| v0.3 | 领域知识、安全与协作 | 知识库 RAG、静态分析/密钥检测/漏洞扫描、Planner/Coder/Tester/Reviewer 多智能体工作流 |
| v1.0 | 可维护的公开版本 | IPC/配置/数据兼容性政策、安装升级迁移文档、稳定发行目标、安全响应流程 |

---

## 8. 结论

SztuCode 已具备完整的本地 AI Coding Agent 工程闭环：Agent Loop、工具调用、上下文治理、权限审批、会话记忆、多智能体编排、可观测性与评测。作为"教学操作系统"，其双语言实现与摊开的工程细节使它既是可用的开发工具，也是学习 Agent 工程与可信 AI Coding 的真实开源教材。

**主要风险与改进方向**：成本效率偏低（O(n²) 序列化、缓存策略）、权限语义分析精度、上游失败自动降级、Web/LSP/Diff 工具补齐，以及自动化评测基线的建立。
