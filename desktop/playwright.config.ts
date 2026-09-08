import { defineConfig, type PlaywrightTestConfig } from "@playwright/test";
import { resolveChromiumLaunchOptions } from "./tests/playwright-chromium";

const chromiumLaunchOptions = resolveChromiumLaunchOptions(process.env);

export default defineConfig({
  testDir: "./tests/visual",
  timeout: 30_000,
  expect: { timeout: 8_000, toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  use: {
    baseURL: "http://127.0.0.1:1424",
    browserName: "chromium",
    colorScheme: "dark",
    deviceScaleFactor: 1,
    // 会话总结的“复制整段总结”按钮依赖 navigator.clipboard.writeText，无头模式下默认拒绝
    permissions: ["clipboard-read", "clipboard-write"],
    ...(Object.keys(chromiumLaunchOptions).length
      ? { launchOptions: chromiumLaunchOptions }
      : {}),
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 1424",
    url: "http://127.0.0.1:1424",
    reuseExistingServer: !process.env.CI,
    // predev 会先构建并复制随安装包分发的 TS runtime；冷启动在 Windows
    // 上可能超过 30 秒，过短会把尚未启动完成误报成页面功能失败。
    timeout: 120_000,
  },
} satisfies PlaywrightTestConfig);
