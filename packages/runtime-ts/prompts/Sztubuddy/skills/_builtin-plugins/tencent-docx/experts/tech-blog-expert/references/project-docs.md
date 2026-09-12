# 项目文档写作指南

> 来源标准：GitHub 开源项目最佳实践 + Make a README

## Goal

帮助创作让用户"30秒能跑起来"的项目文档——降低使用门槛，提升项目采纳率。

## Pre-Writing Questions

1. **项目类型**：CLI工具 / 库(library) / 框架 / 应用？
2. **目标用户**：谁会用这个项目？开发者经验如何？
3. **核心卖点**：用3个词概括项目的差异化优势
4. **安装复杂度**：简单(npm install) / 中等(需要配置) / 复杂(需要多步骤)？

## README 结构模板

### 版本 1：开源库/工具 README

```markdown
# Project Name
> 一句话描述（不超过20字）

[![License](badge)](link) [![npm](badge)](link) [![CI](badge)](link)

## ✨ Features
- 🚀 特性 1（一句话描述价值）
- 📦 特性 2
- 🔧 特性 3

## 🚀 Quick Start（30秒能跑起来）
\`\`\`bash
npm install your-package
\`\`\`
\`\`\`javascript
import { something } from 'your-package';
// 最简示例
\`\`\`

## 📦 Installation
### 环境要求
### 安装步骤

## 🔧 Usage
### 基础用法
### 高级配置
### 完整 API

## 📖 Documentation
[链接到详细文档]

## 🤝 Contributing
[贡献指南链接]

## 📄 License
[许可证信息]
```

### 版本 2：内部项目/服务文档

```markdown
# 项目名

## 简介
## 快速开始（开发环境搭建）
## 目录结构
## 核心模块说明
## 配置说明
## 部署指南
## 常见问题
## 联系方式
```

## README 写作原则

1. **30秒原则**：用户能否在30秒内理解项目做什么、怎么用
2. **复制即运行**：Quick Start 的代码复制粘贴就能跑
3. **渐进式深度**：Quick Start → Basic Usage → Advanced → Full API
4. **Badge 不超5个**：CI/版本/License/下载量/覆盖率
5. **保持更新**：文档和代码版本同步

## Quality Checklist

- [ ] Quick Start 的代码是否可直接复制运行？
- [ ] 版本要求是否明确标注？
- [ ] 是否有从简到繁的递进层次？
- [ ] Badge 信息是否准确且有意义？
- [ ] 是否包含 Contributing 和 License？

## Example Bank

- `examples/readme-library.md` — 开源库 README 范例
