import assert from "node:assert/strict";
import test from "node:test";
import { isMacOSPlatform, isTauriRuntime } from "../src/lib/platform";

test("detects Tauri runtime markers", () => {
  assert.equal(isTauriRuntime({ __TAURI_INTERNALS__: {} }), true);
  assert.equal(isTauriRuntime({ __TAURI__: {} }), true);
  assert.equal(isTauriRuntime({}), false);
});

test("macOS chrome only applies inside Tauri", () => {
  assert.equal(
    isMacOSPlatform(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
      "MacIntel",
      true,
    ),
    true,
  );
  assert.equal(
    isMacOSPlatform(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
      "MacIntel",
      false,
    ),
    false,
  );
});

test("rejects iOS and non-Mac platforms even in Tauri", () => {
  assert.equal(
    isMacOSPlatform(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
      "iPhone",
      true,
    ),
    false,
  );
  assert.equal(
    isMacOSPlatform(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Win32",
      true,
    ),
    false,
  );
  assert.equal(
    isMacOSPlatform(
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
      "Linux x86_64",
      true,
    ),
    false,
  );
});
