# 贡献 SztuCode

完整贡献流程见 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)。

开始贡献前，请阅读：

- [社区行为准则](docs/CODE_OF_CONDUCT.md)
- [项目路线图](docs/ROADMAP.md)
- [安全政策](docs/SECURITY.md)
- [开发环境](docs/development/development.md)
- [测试指南](docs/development/testing.md)

快速检查：

```bash
npm install
npm run typecheck
npm test
npm run build
npm run docs:protocol
npm run docs:links
```

Python runtime 位于 `py-runtime/`。修改 Python daemon、CLI 或评测代码时，在该目录环境中运行对应的 pytest、Ruff 和 mypy 检查；TypeScript 主链仍按上面的 npm 命令验证。
