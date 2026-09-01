// 把原始技术错误（IPC/Rust/网络栈）转译为用户可理解的中文提示。
// 原始信息保留在返回值 detail 中，供 title/tooltip 或日志使用。
export type FriendlyError = { message: string; detail: string };

const RULES: Array<{ pattern: RegExp; message: string }> = [
  { pattern: /transformCallback|Cannot read propert|undefined is not an object|null is not an object/i, message: "本地服务响应异常，请尝试重启本地服务" },
  { pattern: /fetch failed|Failed to fetch|NetworkError|ECONNREFUSED|connection refused/i, message: "无法连接本地服务，请确认服务已启动" },
  { pattern: /timed?\s*out|timeout|deadline exceeded/i, message: "操作超时，请稍后重试" },
  { pattern: /EACCES|permission denied|os error 5/i, message: "没有访问权限，请检查文件或目录权限" },
  { pattern: /ENOENT|no such file/i, message: "文件或目录不存在，可能已被移动或删除" },
  { pattern: /ENOSPC|no space left/i, message: "磁盘空间不足，请清理后重试" },
  { pattern: /certificate|SSL|TLS/i, message: "网络安全校验失败，请检查系统时间或代理设置" },
];

export function friendlyError(error: unknown, fallback = "操作失败，请重试"): FriendlyError {
  const detail = (error instanceof Error ? error.message : String(error ?? "")).trim();
  const firstLine = detail.split("\n")[0].slice(0, 200);
  if (!firstLine) return { message: fallback, detail: "" };
  const hit = RULES.find((rule) => rule.pattern.test(firstLine));
  // 命中规则：给友好文案；未命中：保留原文首行（多为后端已本地化的业务错误）
  return { message: hit ? hit.message : firstLine, detail: firstLine };
}
