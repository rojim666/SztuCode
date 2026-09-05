# 快速开始与故障排查

## 快速开始

```bash
npm ci
npm run office:eval
npm run office:report -- docs/office-agent/evaluation/samples tmp/eval/office-report
npm run build --prefix desktop
```

`office:report` 生成本地 DOCX 并登记成果；连接器默认使用 Fake Feishu，不发送消息。

## 常见问题

- **daemon 未连接**：确认 7438 端口未被旧进程占用，完全退出旧 daemon 后重试。
- **成果显示未验证**：生成只代表文件存在；需运行独立验证并调用 `artifact.verify`。
- **引用失效**：源文件哈希变化后重新索引，旧引用必须标记失效。
- **扫描 PDF 为空**：当前没有 OCR 适配器，不会静默当作成功。
- **未知外部结果**：先执行 `operation.recover` 并人工核对，禁止直接重试。
- **定时任务未补跑**：本地 daemon 停止期间不会执行；重启后按任务 `missed_run_policy` 处理。
