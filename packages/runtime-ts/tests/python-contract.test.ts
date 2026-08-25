import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

test("TypeScript daemon covers every Python daemon RPC method", async () => {
  const [python, typescript] = await Promise.all([
    readFile(path.join(repositoryRoot, "py-runtime/src/sztu_code/core/app.py"), "utf8"),
    readFile(path.join(repositoryRoot, "packages/runtime-ts/src/server-service.ts"), "utf8"),
  ]);
  const pythonMethods = new Set([...python.matchAll(/server\.register\("([^"]+)"/g)].map((match) => match[1]));
  const typescriptMethods = new Set([...typescript.matchAll(/case "([^"]+)"/g)].map((match) => match[1]));
  const missing = [...pythonMethods].filter((method) => !typescriptMethods.has(method)).sort();

  assert.ok(pythonMethods.size > 50, "Python daemon RPC registry was not detected");
  assert.deepEqual(missing, []);
});
