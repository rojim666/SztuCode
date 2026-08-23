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

专业 artifact Skill 若修改了 Python helper，应按对应 Skill 文档运行其自带检查；项目主链不需要 Python、uv、Ruff、mypy 或 pytest。
