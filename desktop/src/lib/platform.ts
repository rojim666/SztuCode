/** True when the UI runs inside a Tauri webview (not Vite browser preview / Playwright). */
export function isTauriRuntime(
  globalObject: Record<string, unknown> | undefined =
    typeof globalThis !== "undefined" ? (globalThis as Record<string, unknown>) : undefined,
): boolean {
  if (!globalObject) return false;
  return "__TAURI_INTERNALS__" in globalObject || "__TAURI__" in globalObject;
}

/** Detect macOS for native titlebar layout. Browser visual tests stay on the custom controls path. */
export function isMacOSPlatform(
  userAgent = typeof navigator !== "undefined" ? navigator.userAgent : "",
  platform = typeof navigator !== "undefined" ? navigator.platform : "",
  inTauri = isTauriRuntime(),
): boolean {
  if (!inTauri) return false;
  const haystack = `${platform} ${userAgent}`.toUpperCase();
  return haystack.includes("MAC") && !haystack.includes("LIKE MAC");
}
