import sharp from "sharp";

const FILE = "app-window.png";
const LEFT = Number(process.argv[2] ?? 200);
const TOP = Number(process.argv[3] ?? 20);
const W = Number(process.argv[4] ?? 200);
const H = Number(process.argv[5] ?? 140);

const meta = await sharp(FILE).metadata();
const { data } = await sharp(FILE)
  .ensureAlpha()
  .extract({ left: LEFT, top: TOP, width: W, height: H })
  .raw()
  .toBuffer({ resolveWithObject: true });

// 按灰度分档，便于看清结构：越亮字符越靠前
const ramp = " .:-=+*#%@";
const rows = [];
for (let y = 0; y < H; y++) {
  let line = "";
  for (let x = 0; x < W; x++) {
    const i = (y * W + x) * 4;
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const lum = (r * 0.299 + g * 0.587 + b * 0.114) / 255;
    // 彩色（饱和度高的）单独标记
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    const sat = mx === 0 ? 0 : (mx - mn) / mx;
    line += sat > 0.25 ? "C" : ramp[Math.min(ramp.length - 1, Math.round((1 - lum) * (ramp.length - 1)))];
  }
  rows.push(line);
}
console.log(`app-window.png ${meta.width}x${meta.height}  区域 (${LEFT},${TOP}) ${W}x${H}`);
console.log("亮→暗: ' ' < . < : < - < = < + < * < # < % < @   C=彩色");
console.log("     " + Array.from({ length: W }, (_, i) => (i % 10 === 0 ? String((i + LEFT) % 100).padStart(2) : "  ")).join("").slice(0, W * 2));
rows.forEach((r, y) => console.log(String(y + TOP).padStart(4) + " " + r));
