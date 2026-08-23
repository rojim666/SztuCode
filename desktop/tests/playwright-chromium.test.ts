import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { resolveChromiumLaunchOptions } from "./playwright-chromium";

test("default env does not set executablePath", () => {
  const options = resolveChromiumLaunchOptions({});
  assert.deepEqual(options, {});
  assert.equal(options.executablePath, undefined);
});

test("PLAYWRIGHT_CHROMIUM_PATH overrides with resolved path", () => {
  const relative = "browsers/chromium";
  const options = resolveChromiumLaunchOptions({
    PLAYWRIGHT_CHROMIUM_PATH: relative,
  });
  assert.equal(options.executablePath, path.resolve(relative));
});

test("Windows-style path separators are accepted", () => {
  const withBackslashes = "tools\\chromium\\chrome";
  const options = resolveChromiumLaunchOptions({
    PLAYWRIGHT_CHROMIUM_PATH: withBackslashes,
  });
  assert.equal(options.executablePath, path.resolve("tools/chromium/chrome"));
});
