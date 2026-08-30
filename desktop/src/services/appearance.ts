export type ThemePreference = "system" | "light" | "dark";
export type WallpaperStyle = "none" | "mist" | "grid" | "paper" | "custom";
export type AccentColor = "graphite" | "blue" | "jade" | "coral";
export type UiFont = "yahei" | "source" | "deng" | "simhei" | "simsun" | "kaiti" | "fangsong" | "source-serif" | "segoe";
export type CodeFont = "cascadia" | "jetbrains" | "consolas";

export const MIN_UI_FONT_SIZE = 12;
export const MAX_UI_FONT_SIZE = 18;

export const MIN_PARAGRAPH_SPACING = 0.2;
export const MAX_PARAGRAPH_SPACING = 2;

export const MIN_LINE_HEIGHT = 1;
export const MAX_LINE_HEIGHT = 2;

export const uiFontOptions: ReadonlyArray<{ id: UiFont; label: string; family: string }> = [
  { id: "yahei", label: "微软雅黑", family: '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif' },
  { id: "source", label: "思源黑体", family: '"Noto Sans SC", "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei UI", sans-serif' },
  { id: "deng", label: "等线", family: 'DengXian, "等线", "Microsoft YaHei UI", sans-serif' },
  { id: "simhei", label: "黑体", family: 'SimHei, "黑体", "Microsoft YaHei UI", sans-serif' },
  { id: "simsun", label: "宋体", family: 'SimSun, "宋体", serif' },
  { id: "kaiti", label: "楷体", family: 'KaiTi, "楷体", STKaiti, serif' },
  { id: "fangsong", label: "仿宋", family: 'FangSong, "仿宋", STFangsong, serif' },
  { id: "source-serif", label: "思源宋体", family: '"Noto Serif SC", "Source Han Serif SC", "Source Han Serif CN", SimSun, serif' },
  { id: "segoe", label: "Segoe UI", family: '"Segoe UI Variable", "Segoe UI", "Noto Sans SC", "Microsoft YaHei UI", sans-serif' },
];

export type AppearanceSettings = {
  theme: ThemePreference;
  wallpaper: WallpaperStyle;
  customWallpaper: string;
  customWallpaperName: string;
  accent: AccentColor;
  wallpaperIntensity: number;
  chromeTransparency: number;
  conversationTransparency: number;
  composerTransparency: number;
  inspectorTransparency: number;
  uiFont: UiFont;
  codeFont: CodeFont;
  fontSize: number;
  compact: boolean;
  paragraphSpacing: number; 
  paragraphLineHeight: number; 
};

const STORAGE_KEY = "sztu.appearance";

export const defaultAppearanceSettings: AppearanceSettings = {
  theme: "light",
  wallpaper: "none",
  customWallpaper: "",
  customWallpaperName: "",
  accent: "graphite",
  wallpaperIntensity: 28,
  chromeTransparency: 32,
  conversationTransparency: 36,
  composerTransparency: 8,
  inspectorTransparency: 36,
  uiFont: "yahei",
  codeFont: "cascadia",
  fontSize: 14,
  compact: false,
  paragraphSpacing: 0.72,
  paragraphLineHeight: 1.2,
};

const uiFonts = Object.fromEntries(uiFontOptions.map((font) => [font.id, font.family])) as Record<UiFont, string>;
const uiFontIds = new Set<UiFont>(uiFontOptions.map((font) => font.id));

const codeFonts: Record<CodeFont, string> = {
  cascadia: '"Cascadia Code", "Cascadia Mono", Consolas, monospace',
  jetbrains: '"JetBrains Mono", "Cascadia Mono", Consolas, monospace',
  consolas: 'Consolas, "SFMono-Regular", monospace',
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function normalizedAppearance(value: Partial<AppearanceSettings>): AppearanceSettings {
  const merged = { ...defaultAppearanceSettings, ...value };
  const customWallpaper = typeof merged.customWallpaper === "string" && merged.customWallpaper.startsWith("data:image/")
    ? merged.customWallpaper
    : "";
  const wallpaper = ["none", "mist", "grid", "paper", "custom"].includes(merged.wallpaper) ? merged.wallpaper : "none";
  return {
    theme: ["system", "light", "dark"].includes(merged.theme) ? merged.theme : "light",
    wallpaper: wallpaper === "custom" && !customWallpaper ? "none" : wallpaper,
    customWallpaper,
    customWallpaperName: typeof merged.customWallpaperName === "string" ? merged.customWallpaperName.slice(0, 160) : "",
    accent: ["graphite", "blue", "jade", "coral"].includes(merged.accent) ? merged.accent : "graphite",
    wallpaperIntensity: clamp(Number(merged.wallpaperIntensity) || 0, 0, 100),
    chromeTransparency: clamp(Number(merged.chromeTransparency) || 0, 0, 80),
    conversationTransparency: clamp(Number(merged.conversationTransparency) || 0, 0, 80),
    composerTransparency: clamp(Number(merged.composerTransparency) || 0, 0, 80),
    inspectorTransparency: clamp(Number(merged.inspectorTransparency) || 0, 0, 80),
    uiFont: uiFontIds.has(merged.uiFont) ? merged.uiFont : "yahei",
    codeFont: ["cascadia", "jetbrains", "consolas"].includes(merged.codeFont) ? merged.codeFont : "cascadia",
    fontSize: clamp(Number(merged.fontSize) || 14, MIN_UI_FONT_SIZE, MAX_UI_FONT_SIZE),
    compact: Boolean(merged.compact),
    paragraphSpacing: clamp(Number(merged.paragraphSpacing) || 0.72, MIN_PARAGRAPH_SPACING, MAX_PARAGRAPH_SPACING),
    paragraphLineHeight: clamp(Number(merged.paragraphLineHeight) || 1.2, MIN_LINE_HEIGHT, MAX_LINE_HEIGHT),
  };
}

export function loadAppearanceSettings(): AppearanceSettings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? normalizedAppearance(JSON.parse(stored) as Partial<AppearanceSettings>) : { ...defaultAppearanceSettings };
  } catch {
    return { ...defaultAppearanceSettings };
  }
}

export function applyAppearanceSettings(settings: AppearanceSettings): void {
  const root = document.documentElement;
  const resolvedTheme = settings.theme === "system"
    ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : settings.theme;
  root.dataset.appTheme = resolvedTheme;
  root.dataset.themePreference = settings.theme;
  root.dataset.wallpaper = settings.wallpaper;
  root.dataset.accent = settings.accent;
  root.dataset.density = settings.compact ? "compact" : "comfortable";
  root.style.setProperty("--font-ui", uiFonts[settings.uiFont]);
  root.style.setProperty("--font-code", codeFonts[settings.codeFont]);
  root.style.setProperty("--text-display-title", `${settings.fontSize + 28}px`);
  root.style.setProperty("--text-hero-title", `${settings.fontSize + 12}px`);
  root.style.setProperty("--text-page-title", `${settings.fontSize + 8}px`);
  root.style.setProperty("--text-brand-title", `${settings.fontSize + 3}px`);
  root.style.setProperty("--text-section-title", `${settings.fontSize + 2}px`);
  root.style.setProperty("--text-item-title", `${settings.fontSize}px`);
  root.style.setProperty("--text-body", `${settings.fontSize}px`);
  root.style.setProperty("--text-control", `${Math.max(11, settings.fontSize - 1)}px`);
  root.style.setProperty("--text-caption", `${Math.max(10, settings.fontSize - 2)}px`);
  root.style.setProperty("--text-micro", `${Math.max(9, settings.fontSize - 3)}px`);
  root.style.setProperty("--markdown-paragraph-spacing", `${settings.paragraphSpacing}em`);
  root.style.setProperty("--markdown-list-item-spacing", `${(settings.paragraphSpacing * 0.39).toFixed(3)}em`);
  root.style.setProperty("--markdown-line-height", String(settings.paragraphLineHeight));
  const wallpaperOpacity = settings.wallpaperIntensity / 100;
  root.style.setProperty("--wallpaper-opacity", String(wallpaperOpacity));
  root.style.setProperty("--wallpaper-opacity-dark", String(Math.min(1, wallpaperOpacity * 2.5)));
  root.style.setProperty("--chrome-surface-opacity", `${100 - settings.chromeTransparency}%`);
  root.style.setProperty("--conversation-surface-opacity", `${100 - settings.conversationTransparency}%`);
  root.style.setProperty("--composer-surface-opacity", `${100 - settings.composerTransparency}%`);
  root.style.setProperty("--inspector-surface-opacity", `${100 - settings.inspectorTransparency}%`);
  root.style.setProperty(
    "--custom-wallpaper-image",
    settings.customWallpaper ? `url(${JSON.stringify(settings.customWallpaper)})` : "none",
  );
}

export function saveAppearanceSettings(settings: AppearanceSettings): AppearanceSettings {
  const normalized = normalizedAppearance(settings);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  applyAppearanceSettings(normalized);
  return normalized;
}

export function initializeAppearance(): void {
  applyAppearanceSettings(loadAppearanceSettings());
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const settings = loadAppearanceSettings();
    if (settings.theme === "system") applyAppearanceSettings(settings);
  });
}
