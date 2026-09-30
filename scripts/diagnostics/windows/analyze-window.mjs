import sharp from "sharp";

const FILE = "app-window.png";
const N = 36;

const meta = await sharp(FILE).metadata();
console.log(`app-window.png ${meta.width}x${meta.height} channels=${meta.channels}`);

async function corner(left, top, label) {
  const { data, info } = await sharp(FILE)
    .ensureAlpha()
    .extract({ left, top, width: N, height: N })
    .raw()
    .toBuffer({ resolveWithObject: true });
  const legend = new Map();
  const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  const rows = [];
  for (let y = 0; y < info.height; y++) {
    let line = "";
    for (let x = 0; x < info.width; x++) {
      const i = (y * info.width + x) * 4;
      const k = `${data[i]},${data[i + 1]},${data[i + 2]}`;
      if (!legend.has(k)) legend.set(k, chars[legend.size] ?? "?");
      line += legend.get(k);
    }
    rows.push(line);
  }
  console.log(`\n=== ${label} (${left},${top}) ${N}x${N} ===`);
  console.log(rows.join("\n"));
  const leg = [...legend.entries()].map(([k, ch]) => `${ch}=rgb(${k})`).join("  ");
  console.log("图例: " + leg);
}

await corner(0, 0, "窗口左上");
await corner(meta.width - N, 0, "窗口右上");
await corner(0, meta.height - N, "窗口左下");
await corner(meta.width - N, meta.height - N, "窗口右下");

// 中线参考色
const { data } = await sharp(FILE).raw().toBuffer({ resolveWithObject: true });
const px = (x, y) => {
  const i = (y * meta.width + x) * 4;
  return `rgb(${data[i]},${data[i + 1]},${data[i + 2]})`;
};
console.log(`\n参考点: 中心=${px(Math.round(meta.width / 2), Math.round(meta.height / 2))}  (2,2)=${px(2, 2)}  (${meta.width - 3},2)=${px(meta.width - 3, 2)}`);
