# 运维手册（RUNBOOK）

## 日常操作

### 启动守护进程

```bash
npm run daemon
```

默认监听 `127.0.0.1:7438`，按 `Ctrl+C` 优雅退出。

### 验证连通

```bash
npm run cli -- ping
```

### 停止守护进程

```bash
npm run cli -- core stop
```

---

## 配置

运行时设置保存在 `~/.sztu/runtime-settings.json`，可由桌面端或设置 RPC 更新。监听地址读取系统环境变量或当前目录 `.env`；已持久化的 Provider、模型和权限设置覆盖环境初始化值。

### 系统环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SZTU_DATA_DIR` | `~/.sztu` | 运行时设置、会话和 trace 数据目录 |
| `SZTU_TS_HOST` / `SZTU_HOST` | `127.0.0.1` | TCP 监听地址 |
| `SZTU_TS_PORT` / `SZTU_PORT` | `7438` | TCP 监听端口 |
| `SZTU_LLM_PROVIDER` | `openai` | Provider 类型 |
| `SZTU_LLM_DEFAULT_MODEL` / `SZTU_MODEL` | `gpt-4o-mini` | 默认模型 |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | 无 | Provider 凭据，不提交到 Git |

---

## 开发

```bash
npm run typecheck                     # 类型检查
npm test                              # TypeScript 主链测试
npm run build                         # 构建 runtime、CLI 和协议包
npm run docs:protocol                 # 重新生成协议文档
npm run docs:links                    # 检查 Markdown 本地链接
```

Legacy Python 测试和脚本仅用于兼容 fixture 与专业 artifact；产品 daemon 和 CLI 不依赖 Python。

---

## 日志

```bash
Get-Content ~/.sztu/traces/runtime-ts-events.jsonl -Wait
```

---

## 常见错误

| 报错 | 原因 | 处理 |
|------|------|------|
| `core already running at 127.0.0.1:7438` | 已有守护进程在运行 | `npm run cli -- core stop` |
| `core not running` | 未启动守护进程 | `npm run daemon` |
| `Address already in use` | 端口被其他进程占用 | `SZTU_PORT=8000 npm run daemon` |
| `Invalid port` 或无法监听 | 环境变量中端口值无效 | 检查 `SZTU_TS_PORT` / `SZTU_PORT` 的值 |
