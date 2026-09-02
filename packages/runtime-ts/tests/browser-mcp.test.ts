// 浏览器 MCP 集成测试（路线 1 持续迭代用）
// 默认跳过：需要本机装有 Chrome，且首次运行 npx 会下载 chrome-devtools-mcp
// 启用：PowerShell 下 `$env:SZTU_TEST_BROWSER_MCP="1"; npm test`，或直接 `npx tsx --test tests/browser-mcp.test.ts`
// 路线 2（连接真实 Chrome）：先 `npm run browser:launch`，再设 SZTU_BROWSER_MCP_CONFIG 指向 attached 配置
import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { McpManager } from "../src/mcp.js";
import type { Tool, ToolContext } from "../src/tools.js";

const enabled = process.env.SZTU_BROWSER_MCP === "1" || process.env.SZTU_TEST_BROWSER_MCP === "1";
const packageRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const configPath = process.env.SZTU_BROWSER_MCP_CONFIG ?? path.join(packageRoot, "mcp.chrome-devtools.json");
const context = { signal: AbortSignal.timeout(60_000) } as ToolContext;

const invoke = async (tool: Tool, params: Record<string, unknown>): Promise<string> => {
  const result = await tool.invoke(params, context);
  assert.ok(result.ok, `${tool.name} 失败: ${result.error ?? result.output}`);
  return result.output;
};

// 页面内含表单：输入框 + 按钮 + 结果区，用于覆盖 snapshot → fill → click → evaluate 的完整交互链路
const formPage = `data:text/html,<title>sztu-form</title><input id="name" placeholder="type here"><button id="go" onclick="document.getElementById('out').textContent='hello '+document.getElementById('name').value">go</button><div id="out"></div>`;

test("browser MCP chain: connect -> tools -> page -> snapshot -> fill -> click -> evaluate", { skip: !enabled && "set SZTU_TEST_BROWSER_MCP=1 to enable (requires local Chrome)", timeout: 180_000 }, async () => {
  const manager = new McpManager(configPath);
  try {
    await manager.load();
    const server = manager.status().find((item) => item.name === "chrome-devtools");
    assert.ok(server?.connected, `chrome-devtools 连接失败: ${server?.error ?? "unknown"}`);

    const tools = manager.listTools();
    const byName = (suffix: string): Tool => {
      const tool = tools.find((item) => item.name === `mcp__chrome-devtools__${suffix}`);
      assert.ok(tool, `缺少工具 ${suffix}`);
      return tool;
    };

    const pageOutput = await invoke(byName("new_page"), { url: formPage });
    const pageId = /^(\d+): .*\[selected\]/m.exec(pageOutput)?.[1];
    assert.ok(pageId, `无法解析 pageId:\n${pageOutput.slice(0, 300)}`);
    const page = { pageId: Number(pageId) };

    // 快照必须包含无障碍树中的输入框与按钮，并给出可操作的 uid
    const snapshot = await invoke(byName("take_snapshot"), page);
    const inputUid = /uid=(\S+) textbox/.exec(snapshot)?.[1];
    const buttonUid = /uid=(\S+) button "go"/.exec(snapshot)?.[1];
    assert.ok(inputUid && buttonUid, `快照缺少 textbox/button uid:\n${snapshot.slice(0, 400)}`);

    // 权限细分：只读工具免确认，写操作保持询问
    assert.equal(byName("take_screenshot").permission, "read_only");
    assert.equal(byName("take_snapshot").permission, "read_only");
    assert.equal(byName("click").permission, "workspace_write");
    assert.equal(byName("fill").permission, "workspace_write");

    // 填表 → 点击 → 读取 DOM 断言交互真实生效
    await invoke(byName("fill"), { ...page, uid: inputUid, value: "sztu" });
    await invoke(byName("click"), { ...page, uid: buttonUid });
    const evaluated = await invoke(byName("evaluate_script"), { ...page, function: "() => document.getElementById('out').textContent" });
    assert.match(evaluated, /hello sztu/);

    // 截图以结构化 images 返回（供桌面端展示），base64 不进入 LLM 文本上下文
    const shotResult = await byName("take_screenshot").invoke(page, context);
    assert.ok(shotResult.ok, `take_screenshot 失败: ${shotResult.error ?? shotResult.output}`);
    assert.ok(shotResult.images?.length, "截图应以结构化 images 返回");
    assert.ok(shotResult.images[0]!.data.length > 1000, "截图数据异常");
    assert.match(shotResult.output, /\[图片/);
    assert.ok(!shotResult.output.includes(shotResult.images[0]!.data), "base64 不应进入文本输出");
  } finally {
    await manager.close();
  }
});
