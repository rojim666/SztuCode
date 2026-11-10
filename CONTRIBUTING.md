# 贡献 SztuCode

第一次参与？只需 **选一个小任务 → 修改并验证 → 提交 PR**。

- 错别字、文档、小范围修复可以直接提交 PR，不必先开 Issue 或等待认领批准。
- 已有 Issue：先留言说明准备做哪一部分，检查是否有人正在处理；有明确范围即可开始。
- 新功能、架构调整或较大研究实验：先用 Issue 对齐问题、范围和验收标准，再动手。

完整步骤、按改动选择的检查和合并要求见 [贡献指南](docs/CONTRIBUTING.md)。
当前默认 Agent/daemon/CLI 是 Python；桌面工作台使用 TypeScript daemon。文档或纯 Python 改动不必安装桌面环境；桌面构建还需 Python/uv 文档解析依赖。

只改文档时，在仓库根目录运行：

```bash
npm ci
npm run docs:links
git diff --check
```

提交使用 `git commit -s` 保留 DCO 声明。不要提交凭据、私有内容或未脱敏日志。
安全漏洞请按 [安全政策](docs/SECURITY.md) 私密报告，交流请遵守 [行为准则](docs/CODE_OF_CONDUCT.md)。
