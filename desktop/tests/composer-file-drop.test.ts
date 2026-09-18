import assert from "node:assert/strict";
import test from "node:test";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { createComposerFileDropHandler } from "../src/utils/composerFileDrop.js";

function setup(ratio = 1, failure?: Error) {
  let hover = false;
  const added: string[][] = [];
  const errors: unknown[] = [];
  const handle = createComposerFileDropHandler({
    pixelRatio: () => ratio,
    containsPoint: (x, y) => x >= 100 && x < 300 && y >= 200 && y < 400,
    setHover: (value) => { hover = value; },
    addPaths: async (paths) => {
      if (failure) throw failure;
      added.push(paths);
    },
    onError: (error) => { errors.push(error); },
  });
  return { handle, added, errors, hover: () => hover };
}

test("native file drops preserve full paths at different display scales", async () => {
  for (const ratio of [1, 1.25, 1.5, 2]) {
    const state = setup(ratio);
    const position = new PhysicalPosition(150 * ratio, 250 * ratio);
    const paths = ["C:\\资料\\需求.pdf", "C:\\images\\screen.png"];
    await state.handle({ payload: { type: "enter", paths, position } });
    assert.equal(state.hover(), true);
    await state.handle({ payload: { type: "drop", paths, position } });
    assert.equal(state.hover(), false);
    assert.deepEqual(state.added, [paths]);
  }
});

test("moving outside the composer and leaving clears hover without adding files", async () => {
  const state = setup();
  await state.handle({ payload: { type: "over", position: new PhysicalPosition(150, 250) } });
  assert.equal(state.hover(), true);
  await state.handle({ payload: { type: "over", position: new PhysicalPosition(50, 50) } });
  assert.equal(state.hover(), false);
  await state.handle({ payload: { type: "drop", paths: ["C:\\a.txt"], position: new PhysicalPosition(50, 50) } });
  assert.deepEqual(state.added, []);
  await state.handle({ payload: { type: "over", position: new PhysicalPosition(150, 250) } });
  await state.handle({ payload: { type: "leave" } });
  assert.equal(state.hover(), false);
});

test("empty drops are ignored and read failures are reported with hover cleared", async () => {
  const failure = new Error("file unavailable");
  const state = setup(1, failure);
  const position = new PhysicalPosition(150, 250);
  await state.handle({ payload: { type: "drop", paths: [], position } });
  assert.deepEqual(state.errors, []);
  await state.handle({ payload: { type: "drop", paths: ["C:\\a.txt"], position } });
  assert.deepEqual(state.errors, [failure]);
  assert.equal(state.hover(), false);
});
