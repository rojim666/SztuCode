import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const capability = JSON.parse(readFileSync(new URL("../src-tauri/capabilities/default.json", import.meta.url), "utf8"));
const manifests = JSON.parse(readFileSync(new URL("../src-tauri/gen/schemas/acl-manifests.json", import.meta.url), "utf8"));

test("tray actions have permission to hide the menu and restore the main window", () => {
  assert.ok(capability.webviews.includes("tray-menu"));
  const granted = new Set<string>(capability.permissions);
  for (const group of ["window", "webview", "event"]) {
    for (const permission of manifests[`core:${group}`].default_permission.permissions) {
      granted.add(`core:${group}:${permission}`);
    }
  }
  for (const permission of [
    "core:window:allow-hide",
    "core:window:allow-show",
    "core:window:allow-is-minimized",
    "core:window:allow-unminimize",
    "core:window:allow-set-focus",
    "core:event:allow-emit",
  ]) assert.ok(granted.has(permission), `Missing tray permission: ${permission}`);
});
