# 运维与故障排查

[返回文档中心](../README.md)

## 启动与检查

前台启动 daemon：

```bash
npm run build
npm run daemon
```

默认监听 `127.0.0.1:7438`。验证连通性：

```bash
npm run cli -- ping
```

由 CLI 管理后台进程：

```bash
npm run cli -- core start
npm run cli -- ping
```

前台进程使用 `Ctrl+C` 优雅退出。开发时优先使用项目提供的 `core stop`，不要依赖只适用于某个操作系统的进程查找命令。

## 配置检查

配置优先级和完整字段见 [配置参考](../getting-started/configuration.md)。排查时重点确认：

- daemon 与客户端的 `SZTU_HOST` / `SZTU_PORT` 一致；
- `SZTU_LLM_PROVIDER`、模型 ID、Base URL 和 API Key 属于同一服务商；
- `.env` 未被另一个系统环境变量覆盖；
- `~/.sztu/runtime-settings.json` 是否包含桌面端最近保存的设置；
- 系统环境变量是否覆盖了 `.env` 中的同名配置。

临时改用其他端口：

```powershell
$env:SZTU_PORT = "8000"
npm run daemon
```

```bash
SZTU_PORT=8000 npm run daemon
```

## 日志与 Trace

默认位置：

```text
~/.sztu/traces/runtime-ts-events.jsonl
```

实时查看系统 Trace：

```bash
Get-Content ~/.sztu/traces/runtime-ts-events.jsonl -Wait
```

Trace 可能包含提示词、模型响应和工具参数。共享前按 [安全政策](../SECURITY.md) 脱敏。

## 本地数据与备份

执行升级、迁移或大规模历史操作前，建议备份：

```text
~/.sztu/runtime-settings.json
~/.sztu/model-profiles.json
~/.sztu/sessions/
~/.sztu/workspaces.json
```

工作区代码应通过 Git 分支或其他备份机制保护。SztuCode 的会话数据不能替代源代码备份。

## 常见问题

### `core already running`

指定地址已有服务。先执行：

```bash
npm run cli -- ping
```

如果是 SztuCode daemon，复用或停止它；如果是其他程序，修改 `SZTU_PORT`。

### `core not running` 或客户端持续重连

```bash
npm run daemon
```

检查 daemon 终端输出和 `~/.sztu/traces/runtime-ts-events.jsonl`。确认防火墙没有阻止 loopback TCP，并核对客户端端口。

### Provider 未就绪

确认模型 ID 不为空、凭据有效、Base URL 可访问，并检查 Provider 与 API 协议是否匹配。OpenAI-compatible 服务必须设置 `SZTU_LLM_PROVIDER=openai`。

### 权限请求没有继续执行

确认客户端仍连接，且响应针对当前 `tool_use_id`。检查是否有多个客户端同时展示同一请求，并核对当前权限模式。

### 桌面端无法连接

Tauri 启动器会拉起 TypeScript daemon。手动调试时先在仓库根目录运行 `npm run build && npm run daemon`，再启动 `npm run tauri dev`。

### 协议类型校验失败

运行 `npm run typecheck`，并从 `packages/protocol/src` 修复共享契约及其客户端消费者。

## 恢复与升级

- 升级前记录当前 commit，并备份 `.sztu` 用户数据。
- 拉取代码后运行 `npm install && npm run build`。专业 artifact Skill 的 Python helper 按对应 Skill 文档准备，不影响 daemon 启动。
- 配置解析失败时，不要直接删除配置；先复制备份并按错误字段修正。
- 会话或工作区数据异常时，保留原始文件用于复现，不要在未备份时批量清理。
- 仓库公共分支发生历史重写后，协作者应重新 fetch，并根据自己的未推送提交选择 rebase、cherry-pick 或重新克隆；不要盲目 hard reset 有本地工作的目录。

## 报告问题

普通故障按 [贡献指南](../CONTRIBUTING.md) 提交 Issue，并附带脱敏的版本、环境和复现步骤。权限绕过、目录逃逸、命令注入或凭据泄漏按 [安全政策](../SECURITY.md) 私下报告。
