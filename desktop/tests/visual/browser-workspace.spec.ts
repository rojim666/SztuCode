import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("browser menu overlays the page and tabs preserve existing page instances", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 });
  await page.goto("/");
  await page.evaluate(async () => {
    const { IpcClient } = await import("/src/lib/ipc.ts");
    IpcClient.prototype.connect = async () => undefined;
    IpcClient.prototype.request = async (method: string) => {
      if (method === "workspace.profile") {
        return {
          profile: {
            root_path: "C:/test",
            monorepo: false,
            scan_limited: false,
            projects: [],
            evidence: [],
          },
        };
      }
      if (method === "change.list") return { changes: [] };
      return {};
    };

    const root = document.querySelector("#app") as HTMLElement & { __vue_app__?: { unmount(): void } };
    root.__vue_app__?.unmount();
    document.documentElement.style.height = "100%";
    document.body.style.height = "100%";
    root.style.width = "100%";
    root.style.height = "100vh";
    const { createApp } = await import("/node_modules/.vite/deps/vue.js");
    const { default: ProjectInspector } = await import("/src/components/Inspector/ProjectInspector.vue");
    const { i18n } = await import("/src/i18n/index.ts");
    createApp(ProjectInspector, {
      workspaceId: "browser-regression",
      workspaceName: "Browser regression",
      workspacePath: "C:/test",
      steps: [],
    }).use(i18n).mount(root);
  });

  await page.getByRole("button", { name: "浏览器", exact: true }).click();
  const address = page.locator(".browser-address-input");
  await address.fill("https://example.com");
  await address.press("Enter");

  const firstPage = page.locator(".browser-renderer").first();
  await expect(firstPage).toBeVisible();
  await expect(firstPage.locator("iframe")).toHaveCount(1);
  await firstPage.evaluate((element) => element.setAttribute("data-instance", "preserved"));

  await page.getByRole("button", { name: "更多功能" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await expect(firstPage).toBeVisible();
  await expect(firstPage).toHaveAttribute("data-instance", "preserved");

  await page.getByRole("button", { name: "新建浏览器标签页" }).click();
  await expect(page.locator(".workspace-open-tab")).toHaveCount(2);
  await expect(page.locator(".browser-empty")).toBeVisible();

  await page.locator(".workspace-open-tab").first().click();
  await expect(address).toHaveValue("https://example.com/");
  await expect(firstPage).toBeVisible();
  await expect(firstPage).toHaveAttribute("data-instance", "preserved");

  await page.getByRole("button", { name: "更多功能" }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await expect(firstPage).toBeVisible();
});

test("native menu visibility never hides the active page", async () => {
  const source = readFileSync(
    path.resolve(import.meta.dirname, "../../src/components/Inspector/ProjectInspector.vue"),
    "utf8",
  );
  expect(source).toContain("(menuOverlayNative || !browserMenuOpen)");
  expect(source).toContain('<template v-for="tab in browserTabs" :key="tab.id">');
  expect(source).not.toContain("(!browserMenuOpen || browserMenuNativeActive) && !obscured");
});
