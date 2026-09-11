import { createRequire } from "node:module";
import sharp from "sharp";

const requireFromDesktop = createRequire(new URL("./desktop/package.json", import.meta.url));
const { chromium } = requireFromDesktop("@playwright/test");

const TARGET = "http://127.0.0.1:5173";
const LEFT = Number(process.argv[2] ?? 200);
const TOP = Number(process.argv[3] ?? 30);
const W = Number(process.argv[4] ?? 90);
const H = Number(process.argv[5] ?? 70);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.goto(TARGET, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(2500);

// 同时报告该区域上各元素的几何与圆角，便于和像素对照
const dom = await page.evaluate(([left, top, w, h]) => {
  const out = [];
  const cx = left + w / 2, cy = top + h / 2;
  for (const el of document.querySelectorAll("*")) {
    const r = el.getBoundingClientRect();
    if (r.right < left || r.bottom < top || r.left > left + w || r.top > top + h) continue;
    const cs = getComputedStyle(el);
    if (cs.borderRadius === "0px" && cs.backgroundColor === "rgba(0, 0, 0, 0)") continue;
    out.push({
      sel: el.tagName.toLowerCase() + "." + String(el.className).split(" ").slice(0, 2).join("."),
      box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)].join(","),
      radius: cs.borderRadius,
      bg: cs.backgroundColor,
      overflow: cs.overflow
    });
  }
  return { cx, cy, hit: document.elementFromPoint(cx, cy)?.className, out: out.slice(0, 14) };
}, [LEFT, TOP, W, H]);

const buf = await page.screenshot({ omitBackground: true });
await browser.close();

const { data, info } = await sharp(buf)
  .ensureAlpha()
  .extract({ left: LEFT, top: TOP, width: W, height: H })
  .raw()
  .toBuffer({ resolveWithObject: true });

const legend = new Map();
const key = (i) => `${data[i]},${data[i + 1]},${data[i + 2]},${data[i + 3]}`;
const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const rows = [];
for (let y = 0; y < info.height; y++) {
  let line = "";
  for (let x = 0; x < info.width; x++) {
    const k = key((y * info.width + x) * 4);
    if (!legend.has(k)) legend.set(k, chars[legend.size] ?? "?");
    line += legend.get(k);
  }
  rows.push(line);
}

console.log(`region (${LEFT},${TOP}) ${W}x${H} — 每个字符代表一种 RGBA`);
console.log(rows.join("\n"));
console.log("\n图例:");
for (const [k, ch] of legend) console.log(`  ${ch} = ${k}`);
console.log("\nDOM 命中:", JSON.stringify(dom, null, 1));
