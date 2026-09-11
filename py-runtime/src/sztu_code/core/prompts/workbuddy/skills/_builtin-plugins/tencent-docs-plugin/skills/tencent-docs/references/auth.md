# 腾讯文档鉴权说明（插件版）

> 本 skill 运行在 `tencent-docs-plugin` 插件中，**不再走 OAuth 授权流程**，所有票据由宿主（如 Workbuddy 连接器）通过环境变量注入，由 `tencentdocs.py` 在调用时通过 HTTP header 透传到服务端。
>
> 调用入口是 `tencentdocs.py`（纯 Python 3 标准库实现，跨平台，Windows 无需 bash/curl）。默认走系统代理（读 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量），可加 `--no-proxy` 绕过。

## 鉴权机制

| 环境变量 | 含义 | 透传 header |
|---|---|---|
| `TDOC_OAUTH_ACCESS_TOKEN` | C 端 OAuth access token | `Authorization: Bearer <token>` |
| `TDOC_ONEID_ACCESS_TOKEN` | SaaS 端 OneID access token | `X-Oneid-Access-Token: <token>` |

> 二者可同时存在（双票场景），由服务端 `mcp_dualtoken_middleware` 决定使用哪一个。

## 调用流程（AI Agent 必读）

### 1. 环境检查（首次调用前执行一次即可）

```bash
python3 tencentdocs.py tdoc_init
```

| 输出 | 处理方式 |
|---|---|
| `READY` | ✅ 环境就绪（至少一个 token 存在），继续执行业务 |
| `ERROR:no_token` | 告知用户：「未检测到腾讯文档登录票据，请在 Workbuddy 中完成授权后重试。」 |

> `tdoc_init` 内部仅检查环境变量 token 是否注入，纯 Python 3 标准库实现，无需安装任何外部工具（不依赖 curl / node / mcporter）。Windows / macOS / Linux 通用。

### 2. 查工具参数定义（调用前必做，勿猜参数）

```bash
python3 tencentdocs.py tdoc_schema <service> <tool>
```

输出该工具的描述与参数（`✓`=必填）。**调用任何工具前必须先执行本步骤**，按返回的参数名/类型/必填项构造 `json_args`，**严禁凭记忆或猜测拼参数**。需要原始 JSON Schema 时加 `--raw`。不确定工具名时先 `tdoc_list <service>`。

### 3. 调用任意 MCP 工具

```bash
python3 tencentdocs.py tdoc_call <service> <tool> [json_args]
```

参数说明：

- `<service>` ∈ `{tencent-docs, slide-mcp, doc-mcp, sheet-mcp}`，按工具品类选择对应 endpoint
- `<tool>` 工具名（小写蛇形或带点号）
- `[json_args]` 工具参数 JSON 字符串，**按上一步 `tdoc_schema` 的定义传**

示例：

```bash
# 通用工具（manage / smartcanvas / smartsheet / OCR / scrape 等）
python3 tencentdocs.py tdoc_call tencent-docs manage.recent_online_file '{"num":10}'
python3 tencentdocs.py tdoc_call tencent-docs create_smartcanvas_by_mdx '{"title":"hello","mdx":"# hi"}'

# 幻灯片精细编辑（slide_* 系列）
python3 tencentdocs.py tdoc_call slide-mcp slide_add_shape '{"file_id":"...","page_index":0,...}'

# Word 文档精细编辑（insert_* / find_* 等）
python3 tencentdocs.py tdoc_call doc-mcp insert_markdown '{"file_id":"...","idx":0,"markdown":"..."}'

# Excel 表格精细编辑（set_cell_value / add_sheet 等）
python3 tencentdocs.py tdoc_call sheet-mcp set_cell_value '{"file_id":"...","sheet_id":"...","row":0,"col":0,"value_type":"STRING","string_value":"hi"}'
```

> ⚠️ 注意：在 `slide-mcp` / `doc-mcp` / `sheet-mcp` 3 个独立 endpoint 上，工具名**不带前缀**（如 `set_cell_value` 而不是 `sheet.set_cell_value`；`insert_markdown` 而不是 `doc.insert_markdown`；`slide_add_shape` 这里 `slide_` 是工具名本身的一部分不是服务名前缀）。调用前可用 `tdoc_list <service>` 查看该 endpoint 上的真实工具名。

### 4. 列出某个 endpoint 上的所有工具（tools/list）

```bash
python3 tencentdocs.py tdoc_list <service>
```

示例：

```bash
python3 tencentdocs.py tdoc_list tencent-docs   # 主入口 ~200 个通用工具
python3 tencentdocs.py tdoc_list slide-mcp      # ~80 个 slide_* 工具
python3 tencentdocs.py tdoc_list doc-mcp        # ~50 个 doc 工具（insert_* / find_* / replace_* 等）
python3 tencentdocs.py tdoc_list sheet-mcp      # ~50 个 sheet 工具（set_cell_value / add_sheet / get_charts 等）
```

返回原始 JSON-RPC 响应，工具列表在 `result.tools[]`，每个包含 `name` / `description` / `inputSchema`。

## 4 个 MCP endpoint 路由说明

| service 名 | endpoint | 适用工具 |
|---|---|---|
| `tencent-docs` | `https://docs.qq.com/openapi/mcp` | 通用工具：`manage.*` / `create_*` / `smartcanvas.*` / `smartsheet.*` / `ocr.*` / `scrape_url` 等 |
| `slide-mcp` | `https://docs.qq.com/api/v6/slide/mcp` | 幻灯片精细编辑：`slide_*` 系列 |
| `doc-mcp` | `https://docs.qq.com/api/v6/doc/mcp` | Word 文档精细编辑：`doc.*` 系列 |
| `sheet-mcp` | `https://docs.qq.com/api/v6/sheet/mcp` | Excel 表格精细编辑：`sheet.*` 系列 |

> 选择规则：**所有 `slide_*` 工具走 `slide-mcp`，所有 `doc.*` 工具走 `doc-mcp`，所有 `sheet.*` 工具走 `sheet-mcp`，其余通用工具一律走 `tencent-docs`**。详见 SKILL.md 的"场景路由表"。

## 错误说明

| 错误 | 含义 | 处理 |
|---|---|---|
| `ERROR:no_token` | 两个环境变量都为空 | 由宿主环境（Workbuddy 等）注入票据 |
| `ERROR:bad_args_json` | args 不是合法 JSON 对象 | 检查 `[json_args]` 是否为合法 `{...}` 字符串 |
| `ERROR:unknown_service` | service 名不在白名单 | 改用 `tencent-docs / slide-mcp / doc-mcp / sheet-mcp` 之一 |
| `ERROR:http_failed` | 网络/HTTP 请求失败 | 检查网络与代理；公司网络下若超时可尝试加 `--no-proxy` 或设置 `HTTPS_PROXY` |
| `Token 鉴权失败 / 400006` | 服务端返回票据无效 | 由宿主环境刷新票据后重试 |
| `VIP 权限不足 / 400007` | 当前操作需要 VIP | 引导用户升级：https://docs.qq.com/vip?immediate_buy=1?part_aid=persnlspace_mcp |