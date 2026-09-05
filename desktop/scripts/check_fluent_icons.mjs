import fs from "node:fs";
import path from "node:path";

const dir = path.resolve(process.cwd(), "node_modules/@fluentui/svg-icons/icons");
const all = fs.readdirSync(dir);

// lucide 名 → fluent 候选 base 名（按优先级）
const candidates = {
  AlertTriangle: ["warning"],
  AppWindow: ["app_recent", "window"],
  AlertCircle: ["error_circle"],
  Archive: ["archive"],
  ArrowLeft: ["arrow_left"],
  ArrowRight: ["arrow_right"],
  ArrowRightLeft: ["arrow_swap"],
  ArrowUp: ["arrow_up"],
  ArrowUpRight: ["arrow_up_right"],
  Beaker: ["beaker"],
  BookOpen: ["book_open"],
  Bot: ["bot"],
  Braces: ["braces"],
  Brain: ["brain_circuit", "brain"],
  BrainCircuit: ["brain_circuit"],
  CalendarClock: ["calendar_clock"],
  Check: ["checkmark"],
  CheckCircle2: ["checkmark_circle"],
  ChevronDown: ["chevron_down"],
  ChevronLeft: ["chevron_left"],
  ChevronRight: ["chevron_right"],
  Circle: ["circle"],
  CircleAlert: ["error_circle"],
  CircleDotDashed: ["circle_hint"],
  CirclePlay: ["play_circle"],
  CirclePlus: ["add_circle"],
  Compose: ["compose"],
  CircleX: ["dismiss_circle"],
  Clipboard: ["clipboard"],
  Clock: ["clock"],
  Clock3: ["clock"],
  Code: ["code"],
  Code2: ["code"],
  Coins: ["money", "currency_dollar_circle"],
  Copy: ["copy"],
  CornerDownLeft: ["arrow_turn_down_left", "arrow_turn_left_down"],
  CornerUpLeft: ["arrow_turn_up_left", "arrow_turn_left_up", "arrow_reply"],
  Cpu: ["developer_board"],
  FileClock: ["document_text_clock"],
  FileCode2: ["code_block"],
  DevTools: ["window_dev_tools"],
  FileImage: ["image"],
  ImageIcon: ["image"],
  Download: ["arrow_download"],
  Edit3: ["edit"],
  Ellipsis: ["more_horizontal"],
  ExternalLink: ["open"],
  Eye: ["eye"],
  EyeOff: ["eye_off"],
  FileDiff: ["document_text", "code_text"],
  FileLock2: ["document_lock"],
  FilePenLine: ["document_edit"],
  FileSearch: ["document_search"],
  FileText: ["document_text"],
  FileWarning: ["document_error", "warning"],
  FileX2: ["document_dismiss"],
  Folder: ["folder"],
  FolderOpen: ["folder_open"],
  FolderPlus: ["folder_add"],
  Folders: ["folder_list", "folder_multiple"],
  GitBranch: ["branch"],
  GitCommitHorizontal: ["commit", "line_horizontal_1_dot", "record"],
  GitFork: ["branch_fork"],
  Globe2: ["globe"],
  Image: ["image"],
  Info: ["info"],
  Languages: ["local_language", "translate"],
  LayoutDashboard: ["board", "glance", "grid"],
  Link2: ["link"],
  ListChecks: ["text_bullet_list_checkmark", "task_list_ltr", "tasks_app"],
  ListOrdered: ["text_number_list_ltr"],
  Loader2: ["spinner_ios"],
  LoaderCircle: ["spinner_ios"],
  LocateFixed: ["my_location"],
  Maximize2: ["full_screen_maximize"],
  MessageCircle: ["chat"],
  MessageSquare: ["chat"],
  MessageSquarePlus: ["chat_add"],
  Minimize2: ["full_screen_minimize"],
  Minus: ["subtract"],
  Monitor: ["desktop"],
  Moon: ["weather_moon"],
  MousePointer2: ["cursor"],
  Music2: ["music_note_2"],
  Network: ["cloud_flow", "plug_connected"],
  Package: ["box"],
  PackageOpen: ["box_open", "box"],
  Palette: ["color"],
  PanelLeftClose: ["panel_left_contract"],
  PanelLeftOpen: ["panel_left_expand"],
  PanelRightClose: ["panel_right_contract"],
  Paperclip: ["attach"],
  Pause: ["pause"],
  Pencil: ["edit", "pen"],
  Pin: ["pin"],
  PinOff: ["pin_off"],
  Play: ["play"],
  Plug: ["plug_connected"],
  Plus: ["add"],
  Power: ["power"],
  Presentation: ["presentation", "slide_content", "slide_layout"],
  Puzzle: ["puzzle_piece"],
  Radio: ["radio_button", "live", "stream"],
  RefreshCw: ["arrow_sync"],
  RotateCcw: ["arrow_counterclockwise"],
  RotateCw: ["arrow_clockwise"],
  ScrollText: ["document_bullet_list", "document_text"],
  Search: ["search"],
  Server: ["server"],
  Settings: ["settings"],
  Settings2: ["settings_cog_multiple", "settings"],
  Share2: ["share"],
  ShieldAlert: ["shield_error", "shield_dismiss"],
  ShieldCheck: ["shield_checkmark", "shield_task"],
  SlidersHorizontal: ["options"],
  Sparkles: ["sparkle", "sparkles"],
  Square: ["stop", "square"],
  SquareShape: ["square"],
  SquareCheckbox: ["checkbox_unchecked"],
  SquareTerminal: ["window_console"],
  Sun: ["weather_sunny"],
  Table2: ["table"],
  Terminal: ["window_console"],
  TerminalSquare: ["window_console"],
  Timer: ["timer"],
  Trash2: ["delete"],
  Type: ["text_font"],
  Unlink: ["link_dismiss"],
  Upload: ["arrow_upload"],
  Video: ["video"],
  WandSparkles: ["wand", "auto_fix", "sparkle"],
  Wrench: ["wrench"],
  X: ["dismiss"],
  XCircle: ["dismiss_circle"],
  ZoomIn: ["zoom_in"],
  ZoomOut: ["zoom_out"],
};

const missing = [];
const result = {};
for (const [lucide, opts] of Object.entries(candidates)) {
  let picked = null;
  for (const base of opts) {
    const reg = all.includes(`${base}_20_regular.svg`);
    const fill = all.includes(`${base}_20_filled.svg`);
    if (reg || fill) { picked = { base, reg, fill }; break; }
  }
  if (!picked) {
    const suggestions = all.filter((f) => f.startsWith(opts[0].split("_")[0])).slice(0, 12);
    missing.push({ lucide, opts, suggestions });
  } else {
    result[lucide] = picked;
  }
}

console.log("=== RESOLVED ===");
for (const [k, v] of Object.entries(result)) console.log(`${k}\t${v.base}\tregular:${v.reg}\tfilled:${v.fill}`);
console.log("=== MISSING ===");
for (const m of missing) console.log(`${m.lucide}\ttried:[${m.opts}]\n  similar: ${m.suggestions.join(", ")}`);

if (missing.length === 0) {
  const bases = [...new Set(Object.values(result).map((r) => r.base))];
  const lines = [];
  lines.push("// 由 scripts/check_fluent_icons.mjs 生成，请勿手改。新增图标请先改脚本再重新生成。");
  for (const base of bases) {
    lines.push(`import ic_${base}_regular from "@fluentui/svg-icons/icons/${base}_20_regular.svg?raw";`);
    lines.push(`import ic_${base}_filled from "@fluentui/svg-icons/icons/${base}_20_filled.svg?raw";`);
  }
  lines.push("");
  lines.push("// @fluentui/svg-icons 原始文件不带 fill，必须在根节点注入 currentColor 才能跟随主题");
  lines.push("const tint = (svg: string) => svg.replace(/#212121/gi, \"currentColor\").replace(/<svg /, '<svg fill=\"currentColor\" ');");
  lines.push("");
  lines.push("export type IconEntry = { regular: string; filled: string };");
  lines.push("");
  lines.push("/** key 沿用原 lucide 图标名，filled 变体用于选中/激活态 */");
  lines.push("export const iconRegistry: Record<string, IconEntry> = {");
  for (const [lucide, v] of Object.entries(result)) {
    lines.push(`  ${lucide}: { regular: tint(ic_${v.base}_regular), filled: tint(ic_${v.base}_filled) },`);
  }
  lines.push("};");
  lines.push("");
  const out = path.resolve(process.cwd(), "src/components/icons/icons.gen.ts");
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, lines.join("\n"), "utf8");
  console.log(`\nWROTE ${out} (${Object.keys(result).length} icons, ${bases.length} unique bases)`);
}
