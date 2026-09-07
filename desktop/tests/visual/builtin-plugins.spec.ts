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
  return { ...manifest, id: `builtin:${name}`, source: "builtin", path: root, skills, installed: true, enabled: true, display_name: manifest.interface.displayName };
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
      if (method === "skill.list") return { skills: entries.flatMap((p) => p.skills.map((name: string) => ({
        id: `builtin-plugin:${p.name}:${name}`, name, display_name: name, description: p.description,
        short_description: p.description, source: `builtin-plugin:${p.name}`, scope: "system", plugin: p.name,
        enabled: p.enabled, path: "", allow_implicit_invocation: true,
      }))) };
      return {};
    };
    const root = document.querySelector("#app") as any;
    root.__vue_app__._instance.setupState.connected = true;
  }, plugins);
  await page.getByRole("button", { name: "更多", exact: true }).click();
  await page.getByRole("button", { name: "技能", exact: true }).click();
  const center = page.getByRole("region", { name: "插件与技能" });
  await expect(center.locator(".bundled-plugin")).toHaveCount(6);
  const word = center.locator(".bundled-plugin").filter({ has: page.locator("b", { hasText: /^Word$/ }) });
  await expect(word.getByText("内置插件", { exact: true })).toBeVisible();
  await expect(word.getByRole("link", { name: "来源", exact: true })).toHaveAttribute("href", /JetBrains\/skills/);
  await word.getByRole("button", { name: "查看 1 个技能" }).click();
  const doc = center.locator(".catalog-section .capability-row");
  await expect(doc).toHaveCount(1);
  await expect(doc.getByText("来自插件：Word", { exact: true })).toBeVisible();
  await center.getByRole("button", { name: "插件", exact: true }).click();
  await word.getByRole("switch").click();
  await expect(word.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  await word.getByRole("button", { name: "查看 1 个技能" }).click();
  await expect(doc.locator(".skill-state")).toBeDisabled();
  await center.getByRole("button", { name: "插件", exact: true }).click();
  await page.screenshot({ path: "test-results/builtin-plugins.png", fullPage: true });
});
