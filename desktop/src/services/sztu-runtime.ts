import { IpcClient } from "../lib/ipc";

export type Workspace = { workspace_id: string; name: string; path: string };
export type Session = {
  session_id: string; title: string; status: string; updated_at: string;
  archived: boolean; pinned: boolean; workspace_id: string | null; latest_run_id?: string | null;
};
export type RuntimeSettings = { provider: "anthropic" | "openai"; model: string; permission_mode: "normal" | "accept_edits" | "plan" | "auto" };
export type ProviderStatus = { api_key_configured: boolean; ready_for_next_run: boolean; skills: Array<{ name: string; description: string }>; mcp_servers: Array<{ name: string; status: string; tool_count?: number }> };

const client = new IpcClient();

export async function connectRuntime(): Promise<boolean> {
  try {
    await client.connect("127.0.0.1", 7437);
    await client.request("event.subscribe", { topics: ["session.*", "run.*", "llm.*", "permission.*"], scope: "global" });
    return true;
  } catch { return false; }
}

export function onRuntimeEvent(handler: (event: Record<string, unknown>) => void): () => void {
  return client.onEvent(handler);
}

export async function listWorkspaces(): Promise<Workspace[]> {
  const result = await client.request("workspace.list");
  return (result.workspaces as Workspace[] | undefined) ?? [];
}

export async function listSessions(): Promise<Session[]> {
  const result = await client.request("session.list", { limit: 12 });
  return (result.sessions as Session[] | undefined) ?? [];
}

export async function createSession(workspace: Workspace | null): Promise<string> {
  const result = await client.request("session.create", { mode: "chat", workspace_id: workspace?.workspace_id });
  return String(result.session_id);
}

export async function sessionHistory(sessionId: string): Promise<unknown[]> {
  const result = await client.request("session.get_history", { session_id: sessionId });
  return (result.messages as unknown[] | undefined) ?? [];
}

export async function sendPrompt(sessionId: string, message: string): Promise<string> {
  const result = await client.request("session.send_message", { session_id: sessionId, content: message });
  return String(result.run_id ?? "");
}

export async function updateSession(sessionId: string, action: "pin" | "archive", value = true): Promise<void> {
  await client.request(action === "pin" ? "session.pin" : "session.archive", { session_id: sessionId, [action === "pin" ? "pinned" : "archived"]: value });
}

export async function getRuntimeSettings(): Promise<RuntimeSettings | null> {
  const result = await client.request("settings.get");
  return (result.settings as RuntimeSettings | undefined) ?? null;
}

export async function setRuntimeSettings(update: Partial<RuntimeSettings>): Promise<RuntimeSettings | null> {
  const result = await client.request("settings.update", update);
  return (result.settings as RuntimeSettings | undefined) ?? null;
}

export async function getProviderStatus(): Promise<ProviderStatus | null> {
  const result = await client.request("provider.status");
  return result as unknown as ProviderStatus;
}

export async function respondPermission(toolUseId: string, decision: "allow_once" | "deny_once"): Promise<void> {
  await client.request("permission.respond", { tool_use_id: toolUseId, decision });
}
