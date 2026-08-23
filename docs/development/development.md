# 开发环境

[返回文档中心](../README.md)

## TypeScript 主链开发

```bash
git clone https://github.com/rojim666/SztuCode.git
cd SztuCode
npm install
```

常用命令：

```bash
npm run typecheck
npm test
npm run build
```

启动 daemon 进行手动调试：

```bash
npm run daemon
```

另一个终端中：

```bash
npm run cli -- ping
npm run cli -- run --goal "inspect the repository"
npm run cli -- chat
```

## 桌面端开发

前端位于 `desktop/`，技术栈为 Vue 3、TypeScript、Vite 和 Tauri 2。

```bash
cd desktop
npm install
npm run build
npm run tauri dev
```

Rust 桥接层检查：

```bash
cd desktop/src-tauri
cargo check
```

桌面端依赖 TypeScript daemon，Tauri 启动器会运行 `packages/runtime-ts/dist/main.js`。前端开发服务器端口由 `desktop/vite.config.ts` 决定，Tauri 开发入口由 `desktop/src-tauri/tauri.conf.json` 配置。

### macOS

- 先安装 Xcode Command Line Tools：`xcode-select --install`
- 开发流程与上方相同（bash）；不要依赖 Windows 专用路径或 PowerShell 示例
- 本机打包：`cd desktop && npm run tauri build`
- 视觉测试：`npx playwright install chromium && npm run test:visual`
- 详细命令与产物路径见 [Desktop README](../../desktop/README.md)

## 模块修改清单

### 协议层

- 修改 `packages/protocol/src` 的共享类型；
- 更新 TypeScript daemon handler；
- 检查 CLI、TUI 与桌面 Client SDK；
- 重新生成 Wire Protocol；
- 添加 round-trip 和集成测试。

### 工具层

- 实现 TypeScript 参数类型和运行时校验；
- 声明静态权限或实现动态权限分类；
- 注册工具；
- 覆盖参数错误、运行失败、超时和权限拒绝；
- 验证工具不能越过工作区边界。

### UI 层

- 保持事件按 `session_id` / `run_id` 关联；
- 重连和历史 hydrate 不得产生重复状态；
- 覆盖 loading、空、失败、禁用和审批状态；
- 桌面端变更运行 TypeScript 构建与必要的视觉验证。

### 配置层

- 更新 TypeScript Settings 类型、JSON 持久化和环境变量覆盖；
- 更新 `.env.example` 和配置参考；
- 为无效类型、边界值和优先级添加测试；
- 明确是否包含凭据及其持久化方式。

## 数据与调试

开发时常用位置：

```text
~/.sztu/traces/runtime-ts-events.jsonl
~/.sztu/sessions/
```

这些文件可能包含提示词、模型响应、工具输出和 API 配置。提交 Issue 或测试夹具前必须脱敏。

## 完成标准

一项变更在满足以下条件后才适合提交：

- 行为与 Issue/PR 目标一致；
- 相关客户端和协议消费者已同步；
- 适当测试通过；
- 失败和权限路径经过验证；
- 用户文档与配置示例已更新；
- `git diff` 不包含无关生成物或本机数据。
