# 配置参考

[返回文档中心](../README.md)

## 配置来源

TypeScript daemon 的配置来源按字段分层：

1. 内置默认值先由启动进程环境初始化；
2. 当前工作目录的 `.env` 只填充系统环境中尚未设置的变量；
3. `~/.sztu/runtime-settings.json` 中由桌面端或 RPC 保存的 Provider、模型和权限设置覆盖初始化值；
4. 已保存 API Key 为空时，Provider 才回退到对应的系统环境变量或 `.env` 值。

`.env` 不会覆盖已经存在的系统环境变量。它适用于从仓库或终端启动 daemon；桌面安装包通常通过模型管理页或系统环境配置。运行时设置可能包含 API Key，属于本机明文文件；不要提交或分享它。模型列表和当前模型 ID 保存在 `~/.sztu/model-profiles.json`。

## Provider

Anthropic：

```dotenv
SZTU_LLM_PROVIDER=anthropic
SZTU_LLM_DEFAULT_MODEL=<your-provider-model-id>
ANTHROPIC_API_KEY=<your-api-key>
ANTHROPIC_BASE_URL=https://api.anthropic.com/v1
```

OpenAI-compatible：

```dotenv
SZTU_LLM_PROVIDER=openai
SZTU_LLM_DEFAULT_MODEL=<your-provider-model-id>
OPENAI_API_KEY=<your-api-key>
OPENAI_BASE_URL=https://api.example.com/v1
```

免密 OpenAI-compatible 端点必须显式启用 keyless：

```dotenv
SZTU_LLM_PROVIDER=openai
SZTU_LLM_DEFAULT_MODEL=mimo-v2.5-free
OPENAI_BASE_URL=https://opencode.ai/zen/v1
SZTU_LLM_KEYLESS=true
```

桌面模型管理页也提供 opencode Zen 与 Pollinations 的内置免费 profile。选择内置项会自动设置 keyless，无需手工编辑 `.env`：

- opencode Zen（`https://opencode.ai/zen/v1`）：`big-pickle`、`ling-3.0-flash-fin-free`、`mimo-v2.5-free`、`nemotron-3-ultra-free`、`nemotron-3.5-lightning-free`
- Pollinations（`https://text.pollinations.ai/openai`）：`openai-fast`（匿名 tier 限流较严）

模型管理页的服务商目录也标注了各平台的免费额度（OpenRouter、Google AI Studio、Groq、Cerebras、Mistral、GitHub Models、NVIDIA NIM、智谱、硅基流动等），点击"获取 API 密钥"可跳转官网注册领取，再粘贴密钥即可接入。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SZTU_HOST` / `SZTU_TS_HOST` | `127.0.0.1` | daemon 监听地址 |
| `SZTU_PORT` / `SZTU_TS_PORT` | `7438` | daemon 与客户端端口 |
| `SZTU_DATA_DIR` | `~/.sztu` | 会话、设置、工作区和 trace 根目录 |
| `SZTU_TRACE_ENABLED` | `true` | 是否写入 TypeScript 结构化 IPC/Event/LLM trace |
| `SZTU_TRACE_FILE` | `~/.sztu/traces/runtime-ts.jsonl` | TypeScript 结构化 trace 路径 |
| `SZTU_TRACE_INCLUDE_LLM_PAYLOAD` | `true` | 是否在结构化 trace 中保留完整 LLM 请求和响应 |
| `SZTU_LLM_PROVIDER` | `openai` | `openai` 或 `anthropic` |
| `SZTU_LLM_DEFAULT_MODEL` / `SZTU_MODEL` | `gpt-4o-mini` | Provider 模型 ID |
| `SZTU_LLM_CONTEXT_WINDOW` | `128000` | 上下文窗口估算值 |
| `SZTU_MAX_STEPS` | `100` | TypeScript 主 Agent 步数上限；`0` 表示不限步数 |
| `SZTU_COMPACT_THRESHOLD` | `0.70` | 自动上下文压缩阈值；`0` 表示禁用 |
| `SZTU_SLIDING_WINDOW_SIZE` | `5` | 压缩后完整保留的最近 turn 数 |
| `SZTU_COMPACT_COOLDOWN` | `3` | 两次自动压缩尝试的最小步数间隔 |
| `SZTU_COMPACT_CIRCUIT_BREAKER` | `3` | 连续压缩失败达到该次数后，本次 run 停止自动压缩 |
| `SZTU_COMPACT_MIN_OLD_TOKENS` | `2000` | 旧 turn 达到该 token 数后才生成摘要 |
| `SZTU_LLM_KEYLESS` | `false` | 允许 OpenAI-compatible 请求不发送 Authorization |
| `SZTU_PERMISSION_MODE` | `normal` | `normal`、`plan`、`accept_edits`、`auto` |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | 未设置 | OpenAI-compatible 凭据 |
| `OPENAI_BASE_URL` / `DEEPSEEK_BASE_URL` | Provider 默认 | OpenAI-compatible 端点 |
| `ANTHROPIC_API_KEY` | 未设置 | Anthropic 凭据 |
| `ANTHROPIC_BASE_URL` | Provider 默认 | Anthropic 端点 |
| `SZTU_MCP_CONFIG` | 未设置 | MCP JSON 配置文件 |
| `SZTU_CCSWITCH_DB` | 自动发现 | cc-switch SQLite 数据库 |
| `SZTU_BUILTIN_SKILLS` | 包内 Skills | 覆盖内置 Skills 根目录，主要用于开发测试 |

## MCP Server

`SZTU_MCP_CONFIG` 指向 JSON 文件。stdio 示例：

```json
{
  "mcpServers": {
    "example": {
      "command": "example-mcp-server",
      "args": ["--stdio"],
      "env": { "EXAMPLE_MODE": "local" }
    }
  }
}
```

TCP 示例：

```json
{
  "mcpServers": {
    "example-tcp": { "host": "127.0.0.1", "port": 3000 }
  }
}
```

浏览器自动化（chrome-devtools-mcp）示例，见 `packages/runtime-ts/mcp.chrome-devtools.json`：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--headless", "--isolated"],
      "timeout_ms": 120000
    }
  }
}
```

接入后 Agent 可获得 29 个浏览器工具（导航、点击、填表、快照、截图、console/network 抓取等），工具名前缀为 `mcp__chrome-devtools__`。Windows 下 `npx` 这类 `.cmd` shim 会由运行时自动经 shell 启动。可用 `npm run verify:browser-mcp`（在 `packages/runtime-ts` 下）验证连接、工具列表和真实页面导航链路。

### 浏览器两种模式

- **隔离模式（默认）**：`mcp.chrome-devtools.json` 使用 `--headless --isolated`，每次启动干净的临时浏览器，适合 headless/CI 和不需要登录态的任务。
- **附着模式（复用登录态）**：`mcp.chrome-devtools.attached.json` 通过 `--browserUrl` 连接已运行的真实 Chrome。先运行 `npm run browser:launch` 启动带 CDP 调试端口（默认 9222，可用 `SZTU_CHROME_DEBUG_PORT` 覆盖）的 Chrome，默认使用持久 agent profile（`SZTU_DATA_DIR/chrome-agent-profile`，登录一次后登录态跨会话保留，与日常 Chrome 互不干扰）；`npm run browser:launch:system` 改用系统真实 profile（需先完全退出日常 Chrome）。然后用 `npm run verify:browser-mcp:attached` 验证链路，或将 `SZTU_MCP_CONFIG` 指向 attached 配置启动 runtime。

浏览器集成测试默认跳过，PowerShell 下用 `$env:SZTU_TEST_BROWSER_MCP="1"; npx tsx --test tests/browser-mcp.test.ts` 启用（覆盖连接、建页、快照、填表、点击、DOM 断言、截图完整链路）；设 `SZTU_BROWSER_MCP_CONFIG` 可切换测试目标为 attached 配置。

MCP 工具按只读/写操作细分授权：快照、截图、列表、查询类工具为 `read_only` 免确认，点击、填表、导航等写操作保持 `workspace_write` 询问（`annotations.readOnlyHint=true` 或命名启发式判定）。截图等图片内容以结构化 `images` 随 `tool.call_finished` 事件下发，desktop 时间线的工具卡片中可展开查看，不占用模型上下文 token。

不要运行来源不明的 MCP Server。stdio 服务会继承 daemon 环境，并可能获得本机访问能力。

## 权限模式

| 模式 | 用途 |
| --- | --- |
| `normal` | 根据风险请求审批 |
| `plan` | 只读分析和规划 |
| `accept_edits` | 自动允许受控工作区编辑，高风险命令仍审批 |
| `auto` | 自动批准工具调用，仅用于可信且可恢复环境 |

## 本地数据

| 路径 | 内容 |
| --- | --- |
| `~/.sztu/runtime-settings.json` | Provider、模型、权限和凭据 |
| `~/.sztu/model-profiles.json` | 模型 profile 与当前 profile ID |
| `~/.sztu/sessions/` | 会话、消息与运行记录 |
| `~/.sztu/workspaces.json` | 最近和归档工作区 |
| `~/.sztu/plugin-settings.json` | 插件启用状态 |
| `~/.sztu/plugin-marketplaces.json` | 插件市场配置 |
| `~/.sztu/traces/runtime-ts-events.jsonl` | runtime 事件回放日志 |
| `~/.sztu/traces/runtime-ts.jsonl` | IPC、EventBus、LLM 三层结构化审计 trace |

这些文件可能包含凭据、源码片段、提示词和模型响应。备份或共享前先脱敏。
