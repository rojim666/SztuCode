import { defineConfig } from "@playwright/test";

const chromiumPath = "C:/Users/Mozero/AppData/Local/ms-playwright/chromium-1045/chrome-win/chrome.exe";

export default defineConfig({
  testDir: "./tests/visual",
  timeout: 30_000,
  expect: { timeout: 8_000, toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  use: {
    baseURL: "http://127.0.0.1:1423",
    browserName: "chromium",
    launchOptions: { executablePath: chromiumPath },
    colorScheme: "dark",
    deviceScaleFactor: 1,
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 1423",
    url: "http://127.0.0.1:1423",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
