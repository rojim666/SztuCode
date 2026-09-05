# 发布前验收报告

环境：Windows、Node.js 本地 workspace，离线模拟连接器；样本为 `docs/office-agent/evaluation/samples`，不调用真实模型或平台。

## 已验证

| 项目 | 结果 | 证据 |
|---|---|---|
| 办公基线 | 9 passed，0 failed，2 unimplemented | `npm run office:eval`；PDF/DOCX/PPTX 生成未实现项按规则保留 |
| 解析与索引 | 8 focused tests passed | PDF/DOCX/XLSX parser、XLSX sheet/source hash、增量删除 |
| 成果与操作账本 | 3 focused tests passed | 版本、越界、重启读取、unknown/幂等 |
| 定时任务 | 1 focused test passed | 可控时钟、租约、去重、补跑、通知去重 |
| 连接器 | 1 focused test passed | Fake Feishu 授权、草稿、回读、幂等、脱敏 |
| 桌面 | 构建通过 | `npm run build --prefix desktop` |
| TypeScript | 类型检查通过 | `npx tsc -p packages/runtime-ts/tsconfig.json --noEmit` |

成功率、成果正确性和引用质量仅对上述合成样本和离线 runner 有效；未进行人工评审或真实平台验证，因此没有真实模型耗时/成本数据。

## 故障路径

已覆盖：权限缺失、草稿版本冲突（适配器测试）、操作未知结果、文件越界/丢失、索引增量更新/删除、调度重叠与补跑、daemon 重启后的成果/账本读取。MCP 网络断开、HTTP 超时和真实飞书 OAuth 尚未在 CI 中验证；现有 MCP 客户端已有超时/重连单测。

## 安装/升级/迁移

```bash
npm ci
npm ci --prefix desktop
npm run typecheck
npm test
npm run office:eval
npm run build
npm run build --prefix desktop
```

运行时数据位于用户 `.sztu` 目录。成果、操作和定时任务使用 JSON 文件原子写入；没有破坏性 schema 迁移，未知旧字段会被忽略。升级失败时保留原数据文件，可回退代码后继续读取。

## 跨平台与可选依赖

核心 TypeScript daemon 使用 Node.js 20+；桌面打包需要 Tauri/Rust 与平台构建依赖。PDF/DOCX/XLSX 解析依赖 `pdf-parse`、`mammoth`、`xlsx`；本阶段不要求 Office 软件、OCR、Chrome 或真实连接器。扫描件无 OCR 时明确失败。

## 未验证

- 真实模型端到端结果、耗时、token 和成本。
- 真实飞书账户授权、刷新、撤销、网络限流和发送/发布。
- Windows/macOS/Linux 三平台均已打包；当前仅本地 Windows 构建实际执行，Linux workflow 保留 CI 入口。
- 云端常驻调度和设备关机期间执行。

## Full suite note

在当前 Windows 工作区运行 `npm test` 时，办公 focused tests 均通过；全套测试仍有既有环境相关失败：`npm-package.test.ts` 中临时 daemon 未在超时内监听端口，`offload.test.ts` 两项断言失败。它们与办公改动无直接关系，发布前需在干净 CI 环境复核，不能标记为全套通过。
