---
name: tencent-pptx
description: 创建专业的 PowerPoint 演示文稿。适用于根据主题、大纲、文档、数据或参考材料生成完整 .pptx；在新建演示文稿时参考上传PPTX 的视觉风格；也可基于材料或旧 PPT 内容重新生成一版演示文稿。
version: v20260825
---

# Tencent-PPTX Skill

## 快速导航
| 任务类型 | 执行路径 |
|---| --- | 
| 从零开始创建、生成PPT      | 阅读 [create-from-scratch](references/create-from-scratch.md) |
| 基于上传的参考材料创建、生成PPT | 阅读 [create-from-material](references/create-from-material.md) |

**核心原则：倘若基于选择的参考材料的生成PPT时，严格使用本SKILL的材料解析能力，避免寻求外部解析能力。**


## PPTX文件的编辑

**核心原则：PPTX 文件完全生成后，所有后续的内容修改/编辑通过阅读使用 `tencent-local-office-edit` SKILL完成。禁止回退到 SlideDSL 源文件进行修改。**

## 需求澄清

1. **只问缺失的，文字提问 ≤ 3 个**，一轮问完，禁止多轮追问
2. **风格预览卡按需触发**：默认弹出，但当用户已明确风格偏好、要求快速出稿、或命中预设风格分支时可跳过（详见 human-alignment.md §2.3）

沟通术语统一用「页 / 封面 / 目录 / 这一页」，不暴露内部实现。

完整对齐逻辑与关键信息优先级见 [human-alignment.md](references/human-alignment.md)。


## 目录结构规范

每个 PPT 对应一个独立的 `project_dir`，多个 PPT 项目并存于用户的 `workspace_dir` 下：

```markdown
<workspace_dir>/                    # 用户工作目录，可包含多个 PPT 项目
├── <project_dir>/                  # 单个 PPT 的完整工作目录（目录名 = pptx 文件名去后缀）
│   ├── DESIGN.md                   # PPT 视觉设计文档
│   ├── STORY.md                    # PPT 内容叙事文档
│   ├── assets/                     # PPT 页面引用的静态资源文件
│   ├── slides/                     # PPT 页面，即 SlideDSL 源文件（每页一个 .slide 文件）
│   │   ├── 01.slide
│   │   ├── 02.slide
│   │   └── 03.slide
│   └── <pptx_name>.pptx           # 生成的演示文稿
```

命名约定：
- 项目目录名：与 pptx 文件名去 `.pptx` 后缀一致（如文件名 `季度汇报.pptx` → 目录名 `季度汇报/`）。
- 页面文件：`{两位序号}.slide`，如 `01.slide`。
- 资源文件：禁用中文、空格、特殊字符。

## 环境介绍

slidep create, slidep upsert-dsl, slidep-validate 已经被安装到 Node 托管环境中，可以直接使用。
