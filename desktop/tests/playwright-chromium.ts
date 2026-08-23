import path from "node:path";

export type ChromiumLaunchOptions = {
  executablePath?: string;
};

/**
 * Resolve Chromium launch options for visual tests.
 * Default: let Playwright use its installed browser (no executablePath).
 * Override: set PLAYWRIGHT_CHROMIUM_PATH to any absolute or relative path.
 */
export function resolveChromiumLaunchOptions(
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): ChromiumLaunchOptions {
  const raw = env.PLAYWRIGHT_CHROMIUM_PATH?.trim();
  if (!raw) return {};
  // Normalize separators so Windows-style paths work when provided via env on any OS.
  const executablePath = path.resolve(raw.replace(/\\/g, "/"));
  return { executablePath };
}
