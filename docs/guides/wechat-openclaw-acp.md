# 通过 OpenClaw 微信插件接入 SztuCode

本文说明如何让 SztuCode 通过 OpenClaw 的微信（Weixin）渠道插件接收和回复微信消息。

SztuCode 不直接对接微信协议，也不在运行时内嵌 OpenClaw。它对外暴露一个标准的
**ACP（Agent Client Protocol）** agent，由微信接入插件通过 stdio 拉起。这样复用了
腾讯官方维护的微信登录与消息通道，SztuCode 只负责推理与执行。

```
微信 App
  │  iLink（扫码登录，由插件保存凭证）
  ▼
OpenClaw Gateway + 微信渠道插件        ← 腾讯官方 @tencent-weixin/openclaw-weixin
  │  spawn(ACP over stdio)
  ▼
sztu-py acp                            ← 本仓库提供
  │  JSON-RPC 2.0（127.0.0.1:7437）
  ▼
SztuCode core daemon（Agent Loop / 工具 / 会话）
```

## 为什么用 ACP

微信渠道插件有多种“接入后端”的方式，当前生态（腾讯官方插件、以及支持多后端的
`weixin-agent-gateway`）统一转向 ACP 来连接外部编码 agent（Codex、Claude Code 等）。
SztuCode 实现 ACP 后即可作为一个平级后端被同一个微信入口驱动，无需自行实现微信协议。

参考：

- 协议规范：<https://agentclientprotocol.com>
- 腾讯官方微信插件：<https://github.com/Tencent/openclaw-weixin>
- 多后端网关（含 Codex/Claude 等 ACP 后端）：<https://github.com/BytePioneer-AI/weixin-agent-gateway>

## 前置条件

| 组件 | 说明 |
| --- | --- |
| Node.js ≥ 22.13 | OpenClaw Gateway 与微信插件的运行环境 |
| OpenClaw ≥ 2026.3.22 | 微信插件在启动时校验宿主版本 |
| SztuCode (Python) | 本仓库 `py-runtime`，入口命令 `sztu-py` |
| 一个微信小号 | 个人微信自动化存在风控风险，建议使用专用账号 |

## 步骤

### 1. 启动 SztuCode core daemon

ACP 服务通过 IPC 复用 daemon 的 Agent Loop，因此 daemon 必须处于运行状态：

```bash
sztu-py core start
sztu-py core status   # 期望输出 running (127.0.0.1:7437)
```

也可以先跳过这一步：`initialize` 握手不需要 daemon，只有第一个 `session/new`
才会连接；未启动时会返回明确的错误提示。

### 2. 安装并登录微信渠道插件

官方单后端方式：

```bash
openclaw plugins install "@tencent-weixin/openclaw-weixin"
openclaw config set plugins.entries.openclaw-weixin.enabled true
openclaw channels login --channel openclaw-weixin   # 扫码登录
```

若需要“一个微信入口对接多个后端”，改用多后端网关（安装时会引导配置后端）：

```bash
openclaw plugins install "@bytepioneer-ai/weixin-agent-gateway"
openclaw config set plugins.entries.openclaw-weixin.enabled false
openclaw config set plugins.entries.weixin-agent-gateway.enabled true
openclaw channels login --channel weixin-agent-gateway
```

### 3. 把 SztuCode 注册为 ACP 后端

让插件以 `sztu-py acp` 启动 agent（等价于 `python -m sztu_code.core.acp`）。
在网关的 backend 配置中把命令指向该入口，工作目录设为可写的项目目录。
未安装控制台脚本时，使用完整形式：

```bash
python -m sztu_code.core.acp
```

### 4. 重启并验证

```bash
openclaw gateway restart
openclaw channels status
```

向登录的微信发送一条文本消息，应收到 SztuCode 的回复；需要审批的工具调用
会以 `session/request_permission` 推送到微信侧，由用户选择允许或拒绝。

## 协议映射

| ACP 方法 / 通知 | SztuCode 行为 |
| --- | --- |
| `initialize` | 返回 `protocolVersion: 1`、`loadSession: false`、图像输入能力；不访问 daemon |
| `session/new` | 调用 daemon `session.create`（chat 模式），返回其 `sessionId` |
| `session/prompt` | 调用 `session.send_message`，流式转发事件，返回 `stopReason` |
| `session/cancel` | 调用 `run.cancel`，本次 turn 以 `stopReason: cancelled` 结束 |
| `session/update`（agent→client） | `llm.token`→`agent_message_chunk`；`llm.thinking`→`agent_thought_chunk`；`tool.*`→`tool_call`/`tool_call_update`；`plan.updated`→`plan`；`llm.usage`→`usage_update` |
| `session/request_permission`（agent→client） | 由 `permission.requested` 触发，用户选择映射为 allow_once / always_allow / deny_once / always_deny |
| `session/load`、`session/resume` | 不支持，返回 `-32601` |

实现位于 `py-runtime/src/sztu_code/core/acp/`：
[`protocol.py`](../../py-runtime/src/sztu_code/core/acp/protocol.py) 负责报文集、
[`bridge.py`](../../py-runtime/src/sztu_code/core/acp/bridge.py) 负责 ACP 会话到
daemon 会话的映射、[`stdio.py`](../../py-runtime/src/sztu_code/core/acp/stdio.py)
负责 stdio 传输、[`backend.py`](../../py-runtime/src/sztu_code/core/acp/backend.py)
封装 daemon IPC。

## 安全与合规

- 个人微信自动化不受腾讯官方支持，存在账号风控/封禁风险；请使用专用账号，
  并遵守微信与 OpenClaw 的相关条款。
- 工具执行仍受 SztuCode 的权限策略约束：默认需要审批的写操作、命令执行等
  在微信场景下同样会请求确认，不会静默放行。
- 微信登录凭证由渠道插件保存在本机，SztuCode 不接触这些凭证。
- daemon 监听 `127.0.0.1`，不要将其暴露到公网。

## 验证

```bash
cd py-runtime
python -m pytest tests/unit/test_acp_bridge.py -q
```

也可以手工握手（无需 daemon）：

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1}}' | python -m sztu_code.core.acp
```
