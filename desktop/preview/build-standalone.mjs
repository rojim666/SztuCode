import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(dir, "dist");

const html = readFileSync(path.join(dist, "edited-files-card.html"), "utf8");
const css = readFileSync(path.join(dist, "app.css"), "utf8");
const js = readFileSync(path.join(dist, "app.js"), "utf8").replace(/<\/script>/g, "<\\/script>");

// 用函数替换，避免 JS 里的 `$&`/`` $` `` 等被当作替换模式解释；
// 内联脚本必须放到 </body> 前，否则在 head 中先于 #app 执行会挂载失败。
const out = html
  .replace('<link rel="stylesheet" crossorigin href="./app.css">', () => `<style>\n${css}\n</style>`)
  .replace('<script type="module" crossorigin src="./app.js"></script>', () => "")
  .replace("</body>", () => `  <script>\n${js}\n  </script>\n</body>`);

const target = path.join(dir, "edited-files-card.standalone.html");
writeFileSync(target, out);
console.log(`wrote ${path.relative(process.cwd(), target)} (${out.length} bytes)`);
