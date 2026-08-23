import type { ToolPermission } from "./tools-types.js";

const readOnlyCommands = new Set([
  "cat", "head", "tail", "ls", "dir", "grep", "rg", "wc", "file", "stat",
  "which", "where", "whereis", "type", "echo", "printf", "date", "pwd", "whoami", "uname", "cls",
]);
const readOnlyGitCommands = new Set(["status", "diff", "log", "show", "grep", "blame", "rev-parse", "ls-files", "ls-tree", "describe"]);

export function classifyBashPermission(params: Record<string, unknown>): ToolPermission {
  const command = typeof params.command === "string" ? params.command.trim() : "";
  if (!command || hasUnsafeShellSyntax(command)) return "danger_full_access";
  const segments = splitCommand(command);
  if (!segments?.length || segments.some((tokens) => !isReadOnlySegment(tokens))) return "danger_full_access";
  return "workspace_write";
}

function hasUnsafeShellSyntax(command: string): boolean {
  if (/\r|\n|`|\$\(|\$\{|\$[A-Za-z_]|%[A-Za-z_][A-Za-z0-9_]*%|\$env:|\b(?:sudo|runas)\b/i.test(command)) return true;
  if (/(^|[\s"'=])(?:~|[/\\]|[A-Za-z]:[/\\])/.test(command)) return true;
  if (/(^|[/\\])\.\.($|[/\\])/.test(command)) return true;
  let quote = ""; let escaped = false;
  for (const char of command) {
    if (escaped) { escaped = false; continue; }
    if (char === "\\" && quote !== "'") { escaped = true; continue; }
    if (quote) { if (char === quote) quote = ""; continue; }
    if (char === "'" || char === '"') { quote = char; continue; }
    if (char === ">" || char === "<" || char === "(" || char === ")") return true;
  }
  return Boolean(quote || escaped);
}

function splitCommand(command: string): string[][] | null {
  const segments: string[][] = []; let tokens: string[] = []; let token = ""; let quote = ""; let escaped = false;
  const pushToken = () => { if (token) { tokens.push(token); token = ""; } };
  const pushSegment = () => { pushToken(); if (!tokens.length) return false; segments.push(tokens); tokens = []; return true; };
  for (let index = 0; index < command.length; index += 1) {
    const char = command[index]!;
    if (escaped) { token += char; escaped = false; continue; }
    if (char === "\\" && quote !== "'") { token += char; escaped = true; continue; }
    if (quote) { if (char === quote) quote = ""; else token += char; continue; }
    if (char === "'" || char === '"') { quote = char; continue; }
    if (/\s/.test(char)) { pushToken(); continue; }
    if (char === ";" || char === "|") {
      if (!pushSegment()) return null;
      if (char === "|" && command[index + 1] === "|") index += 1;
      continue;
    }
    if (char === "&" && command[index + 1] === "&") { if (!pushSegment()) return null; index += 1; continue; }
    if (char === "&") return null;
    token += char;
  }
  if (quote || escaped || !pushSegment()) return null;
  return segments;
}

function isReadOnlySegment(tokens: string[]): boolean {
  const rawName = tokens[0] ?? "";
  if (!rawName || rawName.includes("/") || rawName.includes("\\") || /^[A-Za-z_][A-Za-z0-9_]*=/.test(rawName)) return false;
  const name = rawName.toLowerCase().replace(/\.exe$/, "");
  if (readOnlyCommands.has(name)) return true;
  if (name !== "git") return false;
  const args = tokens.slice(1).filter((arg) => !arg.startsWith("-C") && !arg.startsWith("--git-dir=") && !arg.startsWith("--work-tree="));
  // --no-index 模式把两个路径当普通文件对比，可读工作区外任意文件，视为危险
  if (args.includes("--no-index")) return false;
  const subcommand = args.find((arg) => !arg.startsWith("-"))?.toLowerCase();
  return Boolean(subcommand && readOnlyGitCommands.has(subcommand));
}
