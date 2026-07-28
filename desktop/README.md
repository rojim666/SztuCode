# SztuCode Desktop Workbench

这是 SztuCode 的现代图形客户端：Tauri 2 负责原生窗口、系统目录选择与受控 TCP 桥；React 负责任务时间线、会话历史、工作区、审批与变更审阅。

## 开发

```powershell
cd desktop
npm install
npm run tauri dev
```

先在另一个终端启动 Python daemon：

```powershell
uv run sztu-code
```

桌面端通过一个持久 TCP 连接与 daemon 通信。Rust 桥只转发 NDJSON 帧，所有 JSON-RPC 请求关联、事件订阅与重连状态由 `src/lib/ipc.ts` 集中处理。

## 验证

```powershell
npm run build
cd src-tauri
cargo check
```

旧的 Tkinter `sztu-desktop` 保留为兼容入口；新功能应优先加入此目录的 Tauri + React 客户端与共享 IPC 协议。
