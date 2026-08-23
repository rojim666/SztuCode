# 安装与启动

[返回文档中心](../README.md)

## 环境要求

- Node.js 20+
- Python 3.12 与 `uv`（使用 Python runtime 时）
- Git
- Anthropic 或 OpenAI-compatible API 凭据
- 桌面安装包当前还要求系统可执行 `node`（Node.js 20+）；开发构建另需 Rust 与平台对应的 Tauri 依赖

## 安装 TypeScript 运行时

```bash
git clone https://github.com/rojim666/SztuCode.git
cd SztuCode
npm install
npm run build
```

确认命令可用：

```bash
npm run cli:ts -- --version
npm run cli:py -- --version
```

## 两个运行时入口

安装后的命令互不冲突：

```bash
# TypeScript，默认端口 7438
sztu-ts core start
sztu-ts chat

# Python，默认端口 7437
sztu-py core start
sztu-py chat
```

源码开发时使用 `npm run daemon:ts` / `npm run cli:ts -- ...`，或
`npm run daemon:py` / `npm run cli:py -- ...`。Python 脚本通过锁定的
`uv` 环境运行。仓库默认入口 `npm run daemon` / `npm run cli` 已切换到 Python 内核。

## 配置模型

```bash
cp .env.example .env
```

在 `.env` 中配置 Provider、模型 ID 和凭据。不要提交 `.env`。完整字段见 [配置参考](configuration.md)。

## 启动终端客户端

当前默认内核为 Python：

```bash
npm run daemon
```

另一个终端使用 Python 终端客户端：

```bash
npm run cli -- ping
npm run cli -- run --goal "inspect the repository"
npm run cli -- chat
```

也可以手动分开运行 daemon 和客户端：

```bash
# 终端 1
npm run daemon

# 终端 2
npm run cli -- chat
```

全局安装的 npm 包会在需要时自动启动随包发布的 TypeScript daemon，并复用当前端口上已经运行的 SztuCode daemon：

```bash
npm install --global sztucode-tui
sztu-ts /path/to/project
sztucode ping
sztucode run --goal "inspect the repository"
sztucode core status
sztucode core stop
```

## 启动桌面端

桌面工作台会从安装资源启动 TypeScript daemon；当前版本需要系统 PATH 中存在 Node.js 20+。也可手动分开调试：

```bash
# 终端 1：仓库根目录
npm run build
npm run daemon:ts

# 终端 2
cd desktop
npm install
npm run tauri dev
```

Tauri 在不同操作系统上的系统依赖不同，请按 [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) 安装对应工具链。

### macOS 补充

- 安装 Xcode Command Line Tools：`xcode-select --install`
- 需要 Node.js 20+ 与 Rust stable（`rustup`）
- 本机打包：`cd desktop && npm run tauri build`，产物通常在 `desktop/src-tauri/target/release/bundle/macos/`（`.app`）与 `bundle/dmg/`（若生成）
- 更完整的桌面端说明见 [Desktop README](../../desktop/README.md)

## 验证连通性

```bash
npm run cli -- ping
```

TypeScript 默认服务地址为 `127.0.0.1:7438`，Python 默认为 `127.0.0.1:7437`。若端口冲突，可分别通过 `SZTU_TS_PORT` 和 `SZTU_PORT` 修改，daemon 与对应客户端必须使用相同配置。

## 下一步

- [配置参考](configuration.md)
- [运维手册](../operations/runbook.md)
- [安全策略](../SECURITY.md)
- [贡献指南](../CONTRIBUTING.md)