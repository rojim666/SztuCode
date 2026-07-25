# SztuCode

从零实现一个本地 Claude Code Agent 系统（mini 版）—— 不只是调用大模型 API，而是搭建一个完整的本地 Agent 运行时。

## 这是什么？

SztuCode 是一个**双进程本地 AI Agent 系统**。它把 Claude Code 这类 AI 编程 Agent 最核心的运行机制拆解出来，用 Python 从零实现：

- **Agent Loop**：ReAct 模式，模型思考 → 工具调用 → 结果回填 → 下一步规划
- **工具安全**：参数校验 → 权限审批 → 失败分类 → 自动重试
- **事件流**：token 流、工具调用、权限审批、上下文水位，全部实时推送到 TUI
- **会话记忆**：session / thread / notes 三层体系，跨轮对话保持上下文
- **上下文治理**：水位检测、tool_result 截断、自动/手动 compact
- **扩展边界**：Skills、Subagents、MCP 外部工具统一接入

你学完之后，再看 Claude Code、Codex、Cursor 这些 AI 编程工具，就能看懂它背后那条工程主线：

**用户目标 → Agent Loop → 模型思考 → 工具调用 → 结果回填 → 事件展示 → 会话续航**

## 架构

```
sztu-code (daemon)
  └─ 监听 127.0.0.1:7437 (TCP)
       ↑ JSON-RPC 2.0 NDJSON
sztu (CLI)   sztu-tui (TUI)
```

```
用户目标 → CLI / TUI → JSON-RPC → sztu-code daemon
  → AgentRunner → AgentLoop → LLM Provider
  → ToolRegistry → PermissionManager
  → EventBus → TUI 实时渲染 / events.jsonl / trace 回放
  → Session Store → 跨轮记忆
```

核心模块：

| 模块 | 职责 |
| --- | --- |
| `core/bus/` | JSON-RPC 2.0 类型化协议（Pydantic v2 模型） |
| `core/transport/` | TCP NDJSON 传输层、IPC 事件广播 |
| `core/loop.py` | ReAct Agent Loop 主循环 |
| `core/llm/` | LLM Provider 抽象层（Anthropic / OpenAI 双协议） |
| `core/tools/` | 工具注册、调用、参数校验 |
| `core/permissions/` | 权限管理器、审批策略 |
| `core/session/` | Session 持久化与恢复 |
| `core/compact/` | 上下文压缩 |
| `core/skills/` | Skill 加载与匹配 |
| `core/subagent/` | 子 Agent 派生与调度 |
| `core/mcp/` | MCP 外部工具协议 |
| `core/trace/` | 三层 trace（IPC / EventBus / LLM） |
| `tui/` | Textual 终端 UI |

## 快速开始

### 环境要求

- Python >= 3.12, < 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装与运行

```bash
# 克隆仓库
git clone <repo-url>
cd SztuCode

# 安装依赖
uv sync

# 配置 LLM
cp .env.example .env
# 编辑 .env，选择 LLM provider（见下方）

# 启动 daemon（后台进程）
uv run sztu-code

# 新终端：发送 ping 测试
uv run sztu ping

# 运行一次 Agent 任务
uv run sztu run --goal "创建一个 hello.py 文件，打印 Hello World"

# 启动 TUI（终端 UI）
uv run sztu-tui
```

### LLM Provider 选择

项目支持两种 LLM 后端协议，通过 `SZTU_LLM_PROVIDER` 环境变量切换：

**Anthropic（默认）** — 无需额外配置，沿用原有设置：

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
SZTU_LLM_DEFAULT_MODEL=claude-sonnet-4-6
# SZTU_LLM_PROVIDER 留空或设为 anthropic
```

**OpenAI 兼容（DeepSeek / GPT 等）** — 设置 `SZTU_LLM_PROVIDER=openai`：

```bash
# .env — DeepSeek 示例
SZTU_LLM_PROVIDER=openai
SZTU_LLM_DEFAULT_MODEL=deepseek-chat
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com
```

```bash
# .env — OpenAI 官方示例
SZTU_LLM_PROVIDER=openai
SZTU_LLM_DEFAULT_MODEL=gpt-4o
OPENAI_API_KEY=sk-xxx
```

Provider 在内部自动完成 Anthropic ↔ OpenAI 消息格式转换，上层 Agent Loop、工具调用、TUI 渲染均不受影响。

### 可用命令

```bash
uv run sztu ping              # 测试 daemon 连通性
uv run sztu run --goal "..."  # 执行 Agent 任务
uv run sztu chat              # 多轮对话
uv run sztu core start        # 后台启动 daemon
uv run sztu core stop         # 停止 daemon
uv run sztu core status       # 查看 daemon 状态
uv run sztu trace [run_id]    # 查看 trace 记录
uv run sztu --version         # 查看版本
```

### 开发命令

```bash
# 代码检查
uv run ruff check src tests scripts
uv run mypy src

# 运行测试
uv run pytest tests/unit -v           # 单元测试
uv run pytest tests/integration -v    # 集成测试
uv run pytest tests/ -v               # 全部测试

# 更新协议文档
uv run python scripts/gen_protocol_doc.py
```

## 开发阶段

项目分 8 个阶段，每个阶段解决一个真实的 Agent 工程问题：

| 阶段 | 主题 | 解决的问题 |
| --- | --- | --- |
| **S0** | 骨架与协议契约 | CLI ↔ daemon 通过 TCP NDJSON + JSON-RPC 2.0 完成 IPC 通信 |
| **S1** | Agent 最小闭环 | goal → ReAct Loop → LLM → 工具调用 → 事件文件，完整跑通 |
| **S2** | 事件流外化 | AgentRunner 迁入 daemon，CLI/TUI 通过 IPC 订阅事件流 |
| **S3** | 自主规划与 TUI | Agent 用任务工具拆解复杂目标，TUI 实时展示执行过程 |
| **Trace** | 系统级时间线 | IPC / EventBus / LLM 三层数据流可追踪、可回放 |
| **S4** | 会话与记忆 | 多轮 run 共享 session，thread + notes 分层记忆 |
| **S5** | 工具安全 | 参数校验 → 权限审批 → 失败分类 → 自动重试 |
| **S6** | 上下文治理 | 水位检测、tool_result 截断、自动/手动 compact |
| **S7** | 扩展边界 | Skills 工作流、Subagents 派生、MCP 外部工具接入 |

## 配置

四级配置优先级（后者覆盖前者）：

1. 内建默认值
2. `~/.sztu/config.toml`（全局）
3. `.sztu/config.toml`（项目本地）
4. `.env` / 系统环境变量

主要环境变量：

```bash
# Core
SZTU_HOST=127.0.0.1
SZTU_PORT=7437
SZTU_LOG_LEVEL=INFO

# LLM Provider（自动选择）
SZTU_LLM_PROVIDER=anthropic        # anthropic（默认）| openai
SZTU_LLM_DEFAULT_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...       # Anthropic 用户的 key
ANTHROPIC_BASE_URL=...             # Anthropic 自定义 endpoint
OPENAI_API_KEY=sk-...              # OpenAI / DeepSeek 用户的 key
OPENAI_BASE_URL=...                # OpenAI 自定义 endpoint（如 api.deepseek.com）

# Agent
SZTU_MAX_STEPS=20
```

## 协议

所有 IPC 消息使用 Pydantic v2 模型，基于 `type` 字段做**可区分联合**。详见 [`WIRE_PROTOCOL.md`](WIRE_PROTOCOL.md)。

添加新命令/事件只需：
1. 在 `commands.py` 或 `events.py` 中新增模型类
2. 扩展 `Command` / `Event` 联合类型
3. 运行 `scripts/gen_protocol_doc.py` 重新生成协议文档

## 项目亮点

- **双进程架构**：daemon + 多客户端，TUI 崩溃不影响 Agent 任务
- **类型化 IPC**：JSON-RPC 2.0 + NDJSON，所有消息走 Pydantic 校验
- **ReAct AgentLoop**：模型自主规划 → 工具调用 → 结果回填多步循环
- **事件驱动**：EventBus 贯穿全链路，token 流、工具执行、权限审批实时可见
- **工具安全**：参数强校验、权限按策略审批、失败自动分类与重试
- **分层记忆**：session → thread → notes 三层体系 + 上下文水位 + compact
- **可扩展**：Skills 编排、Subagents 派生、MCP 外部工具，统一运行链路
- **可观测**：三层 trace 追踪（IPC / EventBus / LLM），支持回放
- **工程质量**：mypy strict 类型检查、ruff 代码规范、pytest 全覆盖

## License

MIT
