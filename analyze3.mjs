import sharp from "sharp";

const FILE = "app-window.png";
const meta = await sharp(FILE).metadata();
const { data } = await sharp(FILE).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
const W = meta.width;

const px = (x, y) => {
  const i = (y * W + x) * 4;
  return [data[i], data[i + 1], data[i + 2]];
};
const near = (c, target, tol = 3) => Math.abs(c[0] - target[0]) <= tol && Math.abs(c[1] - target[1]) <= tol && Math.abs(c[2] - target[2]) <= tol;

// 逐行扫描：找出「chrome(#f2f4f5) → 白色(#fff)」的分界 x，看它是否随 y 变化（变化=有圆角弧）
console.log("行 y | 首个白色像素的 x | 该行 x=240..300 的采样");
for (let y = 45; y <= 80; y++) {
  let firstWhite = -1;
  for (let x = 100; x < 500; x++) {
    if (near(px(x, y), [255, 255, 255], 2)) { firstWhite = x; break; }
  }
  const samples = [];
  for (let x = 250; x <= 300; x += 5) samples.push(px(x, y)[0]);
  console.log(`${String(y).padStart(4)} | ${String(firstWhite).padStart(6)} | ${samples.join(" ")}`);
}

// 同时输出 y=60 这一行的颜色分段
console.log("\ny=60 行的颜色分段 (x=0..420):");
let runStart = 0, runColor = px(0, 60);
for (let x = 1; x <= 420; x++) {
  const c = px(x, 60);
  if (!near(c, runColor, 2)) {
    if (x - runStart >= 2) console.log(`  x ${runStart}..${x - 1}  rgb(${runColor.join(",")})`);
    runStart = x; runColor = c;
  }
}
console.log(`  x ${runStart}..420  rgb(${runColor.join(",")})`);
