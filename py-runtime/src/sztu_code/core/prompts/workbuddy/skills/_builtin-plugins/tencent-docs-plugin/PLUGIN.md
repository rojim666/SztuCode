# 腾讯文档插件（tencent-docs-plugin）

腾讯文档官方 MCP 插件，封装了 C 端（`docs.qq.com`）和 SaaS 端（`saas.docs.qq.com`）两个 skill，根据用户身份自动选择合适的 skill 调用对应 MCP 服务。

## 插件结构

```
tencent-docs-plugin/
├── .codebuddy-plugin/plugin.json    # 插件清单
├── PLUGIN.md                         # 本文件，路由说明
├── shared/                           # 两个 skill 真正共用的内容
│   └── smartcanvas/template/         # MDX 参考模板（C 端 / B 端 smartcanvas.md 共用）
└── skills/
    ├── tencent-docs/                 # C 端 skill（docs.qq.com）
    │   ├── SKILL.md                  # 入口：导航 + 场景路由 + 调用约定
    │   ├── tencentdocs.py            # tdoc_init/tdoc_call/tdoc_list 入口（纯 Python 标准库，跨平台）
    │   ├── manage.md / smartcanvas.md / smartsheet.md   # 各品类精炼工具表
    │   ├── doc|sheet|slide/{create,edit}.md             # 各品类创建/编辑工具表
    │   ├── smartcanvas/mdx_references.md                # MDX 语法规范
    │   ├── references/{auth,diagram,space,ocr,aipage}_*.md  # 鉴权与独有能力参考
    │   └── ocr.js / aipage_pack.js / import_file.py  # 辅助脚本
    └── tencent-saas-docs/            # SaaS 端 skill（saas.docs.qq.com）
        └── 结构同上，但无 OCR / aipage 辅助脚本与参考（SaaS 不提供这些能力）
```

> doc 专业排版模板、docengine/slideengine 详细工具参考、smartcanvas 模板等公共内容统一放在
> `shared/`，两个 skill 通过相对路径 `../../shared/...` 引用，避免重复维护。

调用方式（CodeBuddy 命名空间规则）：

- C 端 skill：`/tencent-docs-plugin:tencent-docs`
- SaaS 端 skill：`/tencent-docs-plugin:tencent-saas-docs`

## 鉴权说明（环境变量驱动，不落盘）

插件**完全依赖宿主（Workbuddy 等连接器）注入的环境变量**完成鉴权，**不走 OAuth 授权页面**，也**不依赖任何外部命令行工具（无 curl / mcporter / npm）**：调用入口 `tencentdocs.py` 用 Python 3 标准库（`urllib`）调用 MCP HTTP/JSON-RPC 协议，跨平台（Windows / macOS / Linux），所有票据只在调用时通过 HTTP header 即时透传，**不落盘**：

| 环境变量 | 含义 | 透传 header |
|---|---|---|
| `TDOC_OAUTH_ACCESS_TOKEN` | C 端 OAuth access token（个人用户） | `Authorization: Bearer <token>` |
| `TDOC_ONEID_ACCESS_TOKEN` | SaaS 端 OneID access token（企业用户） | `X-Oneid-Access-Token: <token>` |

> 二者可同时存在（双票场景）；服务端 `mcp_dualtoken_middleware` 已支持。

## skill 路由策略（票据驱动的硬校验）

按身份选择 skill，并由 `tencentdocs.py` 在发请求前做**票据类型硬校验**：

- 用户是腾讯文档 C 端用户（个人 QQ / 微信登录） → 走 `tencent-docs` skill；
- 用户是腾讯文档 SaaS 端企业用户 → 走 `tencent-saas-docs` skill；
- 两票同时存在 → 任选一个 skill 即可，`tencentdocs.py` 会把两个 token 一并通过 header 透传到服务端，由服务端 middleware 决定使用哪一个。

> **选错会立即失败而不是 401**：每个 skill 只在拿到自己那类票据时才发请求，否则返回
> `ERROR:identity_mismatch` 并指明应改用的 skill。历史上（issue #76568）个人账号误选
> SaaS skill 会把 C 端 OAuth 票据打到 `saas.docs.qq.com` 拿到 401 `invalid_token`，
> 用户被误导去反复解绑重连腾讯文档连接器——换 token 换不了 endpoint，永远修不好。

## 4 个 MCP endpoint（两个 skill 均按此路由）

每个 skill 内部按工具品类路由到 4 个不同的 MCP endpoint，写类工具仅在特定 endpoint 上提供。
C 端走 `docs.qq.com`，SaaS 端走 `saas.docs.qq.com`：

| 服务名 | C 端 endpoint | SaaS 端 endpoint | 工具范围 |
|---|---|---|---|
| 主服务 | `docs.qq.com/openapi/mcp` | `saas.docs.qq.com/api/v6/open/agent/mcp` | 通用工具（manage / smartcanvas / smartsheet / scrape，C 端另含 OCR） |
| `slide-mcp` | `docs.qq.com/api/v6/slide/mcp` | `saas.docs.qq.com/api/v6/slide/mcp` | `slide_*` 系列幻灯片精细编辑 |
| `doc-mcp` | `docs.qq.com/api/v6/doc/mcp` | `saas.docs.qq.com/api/v6/doc/mcp` | doc 系列 Word 文档精细编辑（工具名无 `doc.` 前缀） |
| `sheet-mcp` | `docs.qq.com/api/v6/sheet/mcp` | `saas.docs.qq.com/api/v6/sheet/mcp` | sheet 系列 Excel 精细编辑（工具名无 `sheet.` 前缀） |

> 主服务的 service 名：C 端为 `tencent-docs`，SaaS 端为 `tencent-saas-docs`；endpoint 由 `tencentdocs.py` 的 `API_BASE` 按端切换（各 skill 内置）。

## 安装与运行

```bash
# 本地测试
codebuddy --plugin-dir ./tencent-docs-plugin

# 调用 skill（tencentdocs.py 纯 Python 标准库，跨平台，无需预装任何外部工具）
/tencent-docs-plugin:tencent-docs
/tencent-docs-plugin:tencent-saas-docs
```

> 调用入口 `tencentdocs.py` 仅依赖 Python 3 标准库（`urllib`），Windows / macOS / Linux 通用，默认走系统代理（`HTTP_PROXY` / `HTTPS_PROXY`），可加 `--no-proxy` 绕过；`import_file.py` 复用它完成本地文件上云。skill 里的 Node.js 脚本（`ocr.js` / `aipage_pack.js`）在调用 MCP 工具时会内部调起 `python3 tencentdocs.py tdoc_call`。本插件不依赖 curl / mcporter / npm 全局包。
