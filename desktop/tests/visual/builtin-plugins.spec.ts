import { expect, test } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const pluginRoot = path.resolve(import.meta.dirname, "../../../packages/runtime-ts/plugins");
// Use the shipped manifests, not a second hard-coded UI catalog.
const plugins = readdirSync(pluginRoot).map((name) => {
  const root = path.join(pluginRoot, name);
  const manifest = JSON.parse(readFileSync(path.join(root, "plugin.json"), "utf8"));
  const roots = Array.isArray(manifest.skills) ? manifest.skills : [manifest.skills];
  const skills = roots.flatMap((dir: string) => readdirSync(path.join(root, dir)));
  return { ...manifest, id: `builtin:${name}`, source: "builtin", path: root, skills, installed: true, enabled: true, display_name: manifest.interface.displayName, brand_color: manifest.interface.brandColor };
});

test("built-in plugins expose their skills, origin and effective enabled state", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.evaluate(async (initialPlugins) => {
    const { IpcClient } = await import("/src/lib/ipc.ts");
    const entries = structuredClone(initialPlugins);
    IpcClient.prototype.connect = async () => undefined;
    IpcClient.prototype.request = async (method: string, params: Record<string, unknown> = {}) => {
      if (method === "plugin.list") return { plugins: entries };
      if (method === "plugin.catalog") return { marketplaces: [], plugins: [], supported: true };
      if (method === "plugin.set_enabled") {
        const plugin = entries.find((p) => p.id === params.plugin_id)!;
        plugin.enabled = Boolean(params.enabled);
        return { plugin };
      }
      if (method === "skill.list") return { skills: [...entries.flatMap((p) => p.skills.map((name: string) => ({
        id: `builtin-plugin:${p.name}:${name}`, name, display_name: name, description: p.description,
        short_description: p.description, source: `builtin-plugin:${p.name}`, scope: "system", plugin: p.name,
        enabled: p.enabled, path: "", allow_implicit_invocation: true,
      }))), {
        id: "user:personal-note", name: "personal-note", display_name: "personal-note",
        description: "A personal note-taking workflow.", short_description: "A personal note-taking workflow.",
        source: "user", scope: "personal", plugin: null, enabled: true, path: "C:/skills/personal-note/SKILL.md",
        allow_implicit_invocation: true,
      }] };
      return {};
    };
    const root = document.querySelector("#app") as any;
    root.__vue_app__.unmount();
    const { createApp } = await import("/node_modules/.vite/deps/vue.js");
    const { default: SkillCenter } = await import("/src/components/Skills/SkillCenter.vue");
    const { i18n } = await import("/src/i18n/index.ts");
    createApp(SkillCenter, { connected: true }).use(i18n).mount(root);
  }, plugins);
  const center = page.getByRole("region", { name: "插件与技能" });
  await expect(center.locator(".plugin-capsule-card")).toHaveCount(6);
  const word = center.locator(".plugin-capsule-card").filter({ has: page.locator(".capsule-name", { hasText: /^Word$/ }) });
  await word.click();
  const detail = center.locator(".plugin-detail-dialog");
  await expect(detail.getByText("内置插件", { exact: true })).toBeVisible();
  await expect(detail.getByRole("link", { name: "来源", exact: true })).toHaveAttribute("href", /JetBrains\/skills/);
  await detail.getByRole("button", { name: "查看 1 个技能" }).click();
  const doc = center.locator(".skill-grid .skill-card");
  await expect(doc).toHaveCount(1);
  await expect(doc.getByText("Word", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await doc.click();
  const skillDetail = center.locator(".skill-detail-dialog");
  await expect(skillDetail.getByRole("heading", { name: "技能描述" })).toBeVisible();
  await expect(skillDetail).toContainText("Word 文档处理工具");
  await expect(skillDetail.getByRole("button", { name: "删除技能" })).toHaveCount(0);
  await skillDetail.getByRole("button", { name: "关闭" }).click();
  await center.locator(".skill-tabs").getByRole("button", { name: "已启用", exact: true }).click();
  await center.locator(".skill-card").filter({ hasText: "personal-note" }).click();
  await expect(skillDetail).toContainText("A personal note-taking workflow.");
  await expect(skillDetail.getByRole("button", { name: "删除技能" })).toBeVisible();
  await page.screenshot({ path: "test-results/builtin-plugins.png", fullPage: true });
  await skillDetail.getByRole("button", { name: "关闭" }).click();
  await center.getByRole("button", { name: "插件", exact: true }).click();
  await word.click();
  await detail.getByRole("switch").click();
  await expect(detail.getByRole("switch")).toHaveAttribute("aria-checked", "false");
});
