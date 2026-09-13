import DOMPurify from "dompurify";
import { marked } from "marked";

// 推理折叠摘要工具（借鉴 dsh ui-conversation ReasoningRow）：
// 流式中显示最后一行非空文本跟随输出，结算后显示首行作为稳定标题 ——
// 折叠态渲染代价恒定，与文本总长度无关；纯函数便于单测

// 取首行：无换行时返回全文
export function firstLine(text: string): string {
  const newline = text.indexOf("\n");
  return newline === -1 ? text : text.slice(0, newline);
}

// 取最后一行非空文本：先去掉尾部空白（流式文本常以换行/空白结尾），再找最后一个换行
export function latestLine(text: string): string {
  const visible = text.trimEnd();
  const newline = visible.lastIndexOf("\n");
  return newline === -1 ? visible : visible.slice(newline + 1);
}

// 按运行态选择折叠摘要：running 时跟随最新一行，结算后定格首行；纯空白返回空串
export function reasoningSummary(text: string, running: boolean): string {
  if (!text.trim()) return "";
  return running ? latestLine(text) : firstLine(text);
}

/** 将思考区域中的 Markdown 转成安全的内联 HTML。 */
export function renderReasoningMarkdown(text: string): string {
  if (!text) return "";
  const html = marked.parse(text, { async: false, breaks: true }) as string;
  return DOMPurify.sanitize(html);
}
