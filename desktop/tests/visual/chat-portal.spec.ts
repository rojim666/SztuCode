import { expect, test } from "@playwright/test";

// 正式入口暂时隐藏；开发态查询参数只为完整验证 ChatPortal 交互而开放。
test("Chat portal exposes every tool page and its primary interactions", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/?visual-chat=1", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "更多", exact: true }).click();
  await page.getByRole("button", { name: "通用问答", exact: true }).click();

  await expect(page.getByPlaceholder("输入 / 唤起插件和技能")).toBeVisible();

  // 技能中心：stub 本地运行时，验证技能搜索、启停与安装流程
  await page.evaluate(async () => {
    const { IpcClient } = await import("/src/lib/ipc.ts") as {
      IpcClient: { prototype: { request: (method: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>; connect: () => Promise<void> } };
    };
    const skills: Array<Record<string, unknown>> = [
      { id: "skill-frontend-design", name: "frontend-design", display_name: "frontend-design", description: "设计并实现高质量、可交付的前端界面与交互", short_description: "前端界面设计与实现", source: "user", scope: "personal", path: "", enabled: true, allow_implicit_invocation: false },
      { id: "skill-find-skills", name: "find-skills", display_name: "find-skills", description: "发现适合当前任务的技能并提供安装路径", short_description: "技能发现与安装", source: "user", scope: "personal", path: "", enabled: true, allow_implicit_invocation: false },
      { id: "skill-review-agent", name: "review-agent", display_name: "review-agent", description: "以缺陷和回归风险为优先进行代码审查", short_description: "缺陷优先的代码审查", source: "user", scope: "personal", path: "", enabled: true, allow_implicit_invocation: false },
    ];
    // 进入技能页时 App.vue 会重新 connectRuntime；stub connect 让连接保持成功，
    // 否则 connected 会被打回 false，技能中心只能走离线分支。
    IpcClient.prototype.connect = async () => undefined;
    IpcClient.prototype.request = async (method, params = {}) => {
      if (method === "skill.list") return { skills };
      if (method === "skill.set_enabled") {
        const item = skills.find((skill) => skill.id === params.skill_id);
        if (item) item.enabled = Boolean(params.enabled);
        return { skill: item };
      }
      if (method === "skill.install") {
        const added = { id: "skill-release-notes", name: "release-notes", display_name: "release-notes", description: "从提交历史生成发布说明", short_description: "发布说明生成", source: "user", scope: "personal", path: String(params.source_path ?? ""), enabled: true, allow_implicit_invocation: false };
        skills.push(added);
        return { skill: added };
      }
      if (method === "plugin.list") return { plugins: [] };
      if (method === "plugin.catalog") return { marketplaces: [], plugins: [], supported: true };
      return {};
    };
    const root = document.querySelector("#app") as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    };
    const state = root.__vue_app__?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    state.connected = true;
  });

  await page.getByRole("button", { name: "技能", exact: true }).click();
  const skillCenter = page.getByRole("region", { name: "插件与技能" });
  await expect(skillCenter).toBeVisible();
  await skillCenter.getByRole("button", { name: "技能", exact: true }).click();
  await expect(skillCenter.getByRole("heading", { name: "技能", exact: true })).toBeVisible();

  await page.getByPlaceholder("搜索技能").fill("frontend");
  const catalogRow = page.locator(".catalog-section .capability-row");
  await expect(catalogRow).toHaveCount(1);
  await expect(catalogRow.locator("b")).toHaveText("frontend-design");
  const skillToggle = page.locator(".catalog-section .skill-state");
  await expect(skillToggle).toHaveAttribute("title", "禁用技能");
  await skillToggle.click();
  await expect(skillToggle).toHaveAttribute("title", "启用技能");
  await skillToggle.click();
  await expect(skillToggle).toHaveAttribute("title", "禁用技能");
  await page.getByPlaceholder("搜索技能").fill("");

  await page.getByRole("button", { name: "添加", exact: true }).click();
  await page.getByRole("button", { name: /添加技能/ }).click();
  const installDialog = page.getByRole("dialog", { name: "添加技能" });
  await expect(installDialog).toBeVisible();
  await installDialog.getByPlaceholder("选择或粘贴本地目录路径").fill("./skills/release-notes");
  await installDialog.getByRole("button", { name: "安装", exact: true }).click();
  await expect(installDialog).toBeHidden();
  await page.getByPlaceholder("搜索技能").fill("release-notes");
  await expect(page.locator(".catalog-section .capability-row")).toHaveCount(1);
  await expect(page.locator(".catalog-section .capability-row b")).toHaveText("release-notes");
  await page.getByPlaceholder("搜索技能").fill("");
  await expect(page).toHaveScreenshot("skill-center-1280.png", { fullPage: true });

  await page.getByRole("button", { name: "自动化", exact: true }).click();
  await page.locator(".chat-automations").getByRole("button", { name: "新建任务", exact: true }).click();
  await page.getByPlaceholder("例如：每周项目进展汇总").fill("周报汇总");
  await page.getByRole("button", { name: "保存任务", exact: true }).click();
  await expect(page.getByText("暂无定时任务")).toBeVisible();

  await page.getByRole("button", { name: "通用问答", exact: true }).click();
  const portal = page.locator(".chat-main");
  const tools = [
    ["PPT", "输入你想创作的 PPT 主题"],
    ["集群", "给 AI 团队派个活..."],
    ["深度研究", "描述你的问题，生成深度研究报告"],
    ["文档", "上传文档进行编辑，或从零开始创建"],
    ["网站", "描述你的网站想法，风格、功能、数据库都可以"],
    ["表格", "上传表格进行分析，或从零开始创建"],
  ] as const;
  for (const [label, placeholder] of tools) {
    await portal.getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByPlaceholder(placeholder)).toBeVisible();
    await expect(page.locator(".template-preview").first()).toBeVisible();
    await page.getByRole("button", { name: "返回通用问答" }).click();
  }

  await page.getByRole("button", { name: "选择项目", exact: true }).click();
  await page.getByPlaceholder("取个名字").fill("产品调研");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page.getByRole("heading", { name: "产品调研 已创建" })).toBeVisible();
});
