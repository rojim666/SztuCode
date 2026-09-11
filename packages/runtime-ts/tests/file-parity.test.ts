import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createWorkspaceTools } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";

test("file search satisfies the shared Python/TypeScript scenarios", async () => {
  // Set SZTU_PARITY_NO_RG=1 in a fresh process to exercise the fallback backend.
  const previousPath = process.env.PATH;
  if (process.env.SZTU_PARITY_NO_RG === "1") process.env.PATH = "";
  const fixture = JSON.parse(await readFile(new URL("../../../tests/fixtures/runtime-file-parity.json", import.meta.url), "utf8"));
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-parity-"));
  try {
    for (const [name, content] of Object.entries(fixture.files)) {
      await mkdir(path.dirname(path.join(root, name)), { recursive: true });
      await writeFile(path.join(root, name), content as string);
    }
    const tools = createWorkspaceTools();
    const context = { workspace: new Workspace(root) };
    const glob = await tools.get("glob_search")!.invoke({ pattern: fixture.glob.pattern }, context);
    assert.equal(glob.ok, true);
    assert.deepEqual(glob.output.split("\n").sort(), fixture.glob.expected);
    for (const { expected, ...params } of fixture.grep) {
      const result = await tools.get("grep_search")!.invoke(params, context);
      assert.equal(result.ok, true);
      assert.deepEqual(result.output.split("\n").map((line: string) => line.split(":")[0]).sort(), expected);
    }
    const properties = tools.get("grep_search")!.schema.properties as Record<string, unknown>;
    assert.ok(properties.case_sensitive);
  } finally {
    if (previousPath === undefined) delete process.env.PATH;
    else process.env.PATH = previousPath;
    await rm(root, { recursive: true, force: true });
  }
});
