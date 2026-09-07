#!/usr/bin/env node
import { createRequire } from "node:module";
import process from "node:process";

const require = createRequire(import.meta.url);
let sharp;
try {
  sharp = require("sharp");
} catch {
  console.error("This helper requires the `sharp` package in the active Node.js environment.");
  process.exit(2);
}

const args = process.argv.slice(2);
if (args.length < 2 || args.includes("--help")) {
  console.log("Usage: node raster-fit.mjs <input> <output> --width <px> --height <px> [--fit cover|contain] [--position center|attention|entropy|north|south|east|west]");
  process.exit(args.includes("--help") ? 0 : 1);
}

const [input, output, ...rest] = args;
const option = (name, fallback) => {
  const i = rest.indexOf(`--${name}`);
  return i >= 0 && rest[i + 1] ? rest[i + 1] : fallback;
};
const width = Number(option("width", ""));
const height = Number(option("height", ""));
const fit = option("fit", "cover");
const position = option("position", "center");

if (!Number.isInteger(width) || width <= 0 || !Number.isInteger(height) || height <= 0) {
  console.error("--width and --height must be positive integer pixel values.");
  process.exit(1);
}
if (!new Set(["cover", "contain"]).has(fit)) {
  console.error("--fit must be `cover` or `contain`.");
  process.exit(1);
}

await sharp(input)
  .rotate()
  .resize({ width, height, fit, position, withoutEnlargement: false, background: { r: 255, g: 255, b: 255, alpha: 1 } })
  .toFile(output);

const metadata = await sharp(output).metadata();
if (metadata.width !== width || metadata.height !== height) {
  throw new Error(`Unexpected output size: ${metadata.width}x${metadata.height}`);
}
console.log(`${output}\t${metadata.width}x${metadata.height}\t${fit}\t${position}`);
