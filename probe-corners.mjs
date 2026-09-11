import { createRequire } from "node:module";
import sharp from "sharp";

const requireFromDesktop = createRequire(new URL("./desktop/package.json", import.meta.url));
const { chromium } = requireFromDesktop("@playwright/test");

const TARGET = "http://127.0.0.1:5173";
const N = 44;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.goto(TARGET, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);
const buf = await page.screenshot({ omitBackground: true });
await browser.close();

const meta = await sharp(buf).metadata();
console.log(`screenshot ${meta.width}x${meta.height} channels=${meta.channels} hasAlpha=${meta.hasAlpha}`);

async function region(left, top, label) {
  const { data, info } = await sharp(buf)
    .ensureAlpha()
    .extract({ left, top, width: N, height: N })
    .raw()
    .toBuffer({ resolveWithObject: true });
  const rows = [];
  for (let y = 0; y < info.height; y++) {
    let line = "";
    for (let x = 0; x < info.width; x++) {
      const a = data[(y * info.width + x) * 4 + 3];
      line += a === 0 ? " " : a === 255 ? "#" : "+";
    }
    rows.push(line);
  }
  const diag = [];
  for (const i of [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]) {
    const idx = (i * info.width + i) * 4;
    diag.push(`(${i},${i})=[${data[idx]},${data[idx + 1]},${data[idx + 2]},a${data[idx + 3]}]`);
  }
  console.log(`\n=== ${label} (${left},${top}) ${N}x${N} — 空格=全透明 #=不透明 +=半透明 ===`);
  console.log(rows.join("\n"));
  console.log(diag.join("  "));
}

await region(0, 0, "左上");
await region(meta.width - N, 0, "右上");
await region(0, meta.height - N, "左下");
await region(meta.width - N, meta.height - N, "右下");
