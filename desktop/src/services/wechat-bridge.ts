import { invoke } from "../lib/tauri-shim";

/** 微信桥接状态机：未接入 / 未连接 / 等待扫码 / 已连接 */
export type WeChatConnectionState = "unavailable" | "disconnected" | "pending" | "connected";

export interface WeChatStatus {
  state: WeChatConnectionState;
  account: string | null;
  boundSessionId: string | null;
  lastError?: string | null;
}

export interface WeChatLoginTicket {
  /** 二维码内容：data:/http 链接渲染为图片，其余（含终端二维码）按文本展示 */
  qr: string;
  /** OpenClaw 输出的备用扫码链接 */
  link?: string | null;
  expiresAt?: string | null;
}

const UNAVAILABLE_STATUS: WeChatStatus = {
  state: "unavailable",
  account: null,
  boundSessionId: null,
  lastError: null,
};

// 后端命令尚未落地时返回 null 而不是抛错，页面降级为“未接入”而不是整页崩溃
async function call<T>(command: string, args?: Record<string, unknown>): Promise<T | null> {
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    console.warn(`[wechat-bridge] ${command} unavailable`, error);
    return null;
  }
}

export async function getWeChatStatus(): Promise<WeChatStatus> {
  return (await call<WeChatStatus>("wechat_status")) ?? UNAVAILABLE_STATUS;
}

export async function startWeChatLogin(): Promise<WeChatLoginTicket | null> {
  try {
    return await invoke<WeChatLoginTicket | null>("wechat_login_start");
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : String(error));
  }
}

export async function cancelWeChatLogin(): Promise<boolean> {
  return (await call<boolean>("wechat_login_cancel")) ?? false;
}

export async function bindWeChatSession(sessionId: string): Promise<boolean> {
  return (await call<boolean>("wechat_bind_session", { sessionId })) ?? false;
}

export async function unbindWeChatSession(): Promise<boolean> {
  return (await call<boolean>("wechat_unbind_session")) ?? false;
}
