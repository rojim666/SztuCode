# 内置插件

客户端的插件页面展示完整插件包，点击“查看 N 个技能”进入该包的技能列表。
技能条目和来源筛选显示“来自插件：名称”。禁用插件后，其技能仍可在目录查看，
但不能调用；重新启用插件不会覆盖用户单独禁用技能的设置。

## 随客户端提供的六个包

- **PDF Monster**：项目已有 MIT 快照，提取文本、OCR、页面图像和嵌入图片。
  [登记页](https://hol.org/registry/plugins/johnny-bae%2Fpdf-monster) 指向的上游仓库
  在 2026-09-07 返回 404，因此不声称这是最新或已核实提交的上游版本。
  依赖 Python，以及 PyMuPDF 或 Poppler；OCR 另需 Tesseract 和语言数据。
  中文 OCR 使用 `--ocr-lang chi_sim+eng`。默认产物位于系统临时目录，只有
  `--save-to` 才持久化；Windows 返回 PowerShell 清理命令。
- **Word**：OpenAI `doc`，使用 python-docx 读取、创建和编辑 DOCX。
  渲染检查另需 LibreOffice、Poppler 和 pdf2image。
- **Excel**：OpenAI `spreadsheet`，使用 openpyxl 处理 XLSX，涵盖公式、格式和图表。
  pandas 是可选分析工具。openpyxl 不计算公式；需要实际重算时使用可用的表格引擎。
  此包不宣称提供已连接的 Excel 实时控制服务。
- **高质量 PPT（PPTX 版）**：保留项目已有 `jingmei-ppt` 视觉配方，新增 OpenAI
  `slides` 的 PptxGenJS 制作及渲染、字体和溢出检查工具。需要 Node、PptxGenJS；
  渲染脚本还需要 Python、Pillow、LibreOffice 和 Poppler。
- **前端设计工具集**：Anthropic frontend-design 与现有 UICraft/Impeccable 衍生技能，
  覆盖视觉方向、排版、动效、交互、响应式、质量检查和设计系统。
- **GitHub**：SztuCode 的 git/gh 入口，加上 OpenAI `gh-address-comments`、`gh-fix-ci`。
  需要安装 GitHub CLI 并由用户登录；插件不包含账号凭据或专用连接器。

Word、Excel、slides 和两个 GitHub 专项技能来自
[JetBrains 技能库的固定提交](https://github.com/JetBrains/skills/tree/e0f258b5cfed145015cb3e48da9a97947f7c4ed7)，
保留 Apache-2.0 许可证。Word/Excel 的临时和最终输出约定已适配本地客户端。
两个用户指定的 Trae 同名官方包未能公开核实，因此集成包明确标记为非 Trae 官方包。
各包的 `SOURCE.md` 记录来源、改动和依赖，不将名称匹配视为作者认证。

## 开发与分发

Python 源位于 `py-runtime/src/sztu_code/core/skills/builtin-plugins`；
桌面 TypeScript 兼容副本位于 `packages/runtime-ts/plugins`。
`plugin.json` 指定技能根目录、名称、说明和来源元数据。
修改时保持两个副本一致，测试会比较清单。

Word、Excel 和 GitHub 使用 `bundled-skills` 中的可分发版本。原有 `skills`
研究副本不参与发现、不进入桌面产物，Python wheel/sdist 同样排除这些目录。
桌面打包通过 `scripts/prepare-plugin-assets.js` 只复制清单选中的技能根目录。
这些插件包提供工作流与脚本；上述外部文档引擎和账号登录不因启用插件而自动安装。

验证命令：

```sh
python -m pytest py-runtime/tests/unit/test_skill_loader.py py-runtime/tests/unit/test_builtin_plugin_catalog.py
npm exec -- tsx --test packages/runtime-ts/tests/plugins.test.ts packages/runtime-ts/tests/builtin-plugin-assets.test.ts
# From desktop/:
npm exec -- playwright test --config=playwright.plugins.config.ts
```

浏览器交互回归位于 `desktop/tests/visual/builtin-plugins.spec.ts`，使用真实内置清单和
模拟 IPC，覆盖列表、来源、进入包内技能及父插件禁用后的状态。原生客户端仍应使用
重新构建的运行时验收，旧 daemon 不会自动获得新增资源。
