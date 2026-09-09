import { chromium } from "playwright";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const url = pathToFileURL(path.join(dir, "edited-files-card.standalone.html")).href;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 880, height: 520 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: "load" });
await page.waitForSelector(".edited-files-card");
await page.screenshot({ path: path.join(dir, "edited-files-card.png"), fullPage: true });
await browser.close();
console.log(`captured ${path.relative(process.cwd(), path.join(dir, "edited-files-card.png"))} from ${url}`);
