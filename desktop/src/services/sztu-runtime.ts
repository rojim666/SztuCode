import { invoke } from "@tauri-apps/api/core";
import { IpcClient } from "../lib/ipc";

export type Workspace = { workspace_id: string; name: string; path: string };
export type NativeSettings = { autostart: boolean; stay_awake: boolean; supported: boolean };
export type WorkspaceNode = { path: string; name: string; kind: "directory" | "file"; children?: WorkspaceNode[] };
export type FileSearchMatch = { path: string; line: number; preview: string };
export type ChangeSummary = {
  path: string; index_status: string; worktree_status: string;
  run_id?: string | null; agent_owned?: boolean; revertible?: boolean;
};
export type Session = {
  session_id: string; title: string; status: string; updated_at: string;
  archived: boolean; pinned: boolean; workspace_id: string | null; latest_run_id?: string | null;
};
export type RuntimeSettings = { provider: "anthropic" | "openai"; model: string; permission_mode: "normal" | "accept_edits" | "plan" | "auto" };
export type ProviderStatus = { api_key_configured: boolean; ready_for_next_run: boolean; skills: Array<{ name: string; description: string }>; mcp_servers: Array<{ name: string; status: string; tool_count?: number }> };

const client = new IpcClient();
let subscribed = false;
client.onDisconnect(() => { subscribed = false; });
const EVENT_TOPICS = [
  "session.*", "run.*", "step.*", "llm.*", "tool.*", "permission.*",
  "plan.*", "test.*", "change.*", "log.*", "subagent.*", "skill.*", "context.*", "denial.*",
];

async function waitForDaemon(): Promise<void> {
  try {
    await invoke("daemon_start");
  } catch {
    // Browser-based UI tests have no Tauri host. The connection attempt below
    // remains the source of truth for runtime availability.
  }
}

export async function getNativeSettings(): Promise<NativeSettings> {
  return await invoke<NativeSettings>("native_settings_get");
}

export async function setNativeSettings(update: { autostart?: boolean; stayAwake?: boolean }): Promise<NativeSettings> {
  return await invoke<NativeSettings>("native_settings_update", update);
}

export async function connectRuntime(): Promise<boolean> {
  await waitForDaemon();
  const attempts = "__TAURI_INTERNALS__" in window ? 12 : 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await client.connect("127.0.0.1", 7437);
      if (!subscribed) {
        await client.request("event.subscribe", { topics: EVENT_TOPICS, scope: "global" });
        subscribed = true;
      }
      return true;
    } catch {
      if (attempt + 1 < attempts) await new Promise((resolve) => window.setTimeout(resolve, 250));
    }
  }
  return false;
}

export function onRuntimeEvent(handler: (event: Record<string, unknown>) => void): () => void {
  return client.onEvent(handler);
}

export function onRuntimeDisconnect(handler: (reason: string) => void): () => void {
  return client.onDisconnect(handler);
}

export async function listWorkspaces(): Promise<Workspace[]> {
  const result = await client.request("workspace.list");
  return (result.workspaces as Workspace[] | undefined) ?? [];
}

export async function listSessions(includeArchived = true): Promise<Session[]> {
  const result = await client.request("session.list", { limit: 100, include_archived: includeArchived });
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

export async function renameSession(sessionId: string, title: string): Promise<Session> {
  const result = await client.request("session.rename", { session_id: sessionId, title });
  return result.session as Session;
}

export async function pinSession(sessionId: string, pinned: boolean): Promise<Session> {
  const result = await client.request("session.pin", { session_id: sessionId, pinned });
  return result.session as Session;
}

export async function archiveSession(sessionId: string): Promise<Session> {
  const result = await client.request("session.archive", { session_id: sessionId });
  return result.session as Session;
}

export async function resumeSession(sessionId: string): Promise<Session> {
  const result = await client.request("session.resume", { session_id: sessionId });
  return result.session as Session;
}

export async function closeSession(sessionId: string): Promise<void> {
  await client.request("session.close", { session_id: sessionId });
}

export async function compactSession(sessionId: string, focus = ""): Promise<{ summary_tokens: number; saved_tokens: number }> {
  return await client.request("session.compact", { session_id: sessionId, focus }) as { summary_tokens: number; saved_tokens: number };
}

export async function replayRun(runId: string): Promise<Record<string, unknown>[]> {
  const result = await client.request("run.replay", { run_id: runId, max_events: 10_000 });
  return (result.events as Record<string, unknown>[] | undefined) ?? [];
}

export async function openWorkspace(path: string): Promise<Workspace> {
  const result = await client.request("workspace.open", { path });
  return result.workspace as Workspace;
}

export async function workspaceTree(workspaceId: string): Promise<WorkspaceNode[]> {
  const result = await client.request("workspace.tree", { workspace_id: workspaceId, path: "", max_depth: 6, max_entries: 1_000 });
  return (result.nodes as WorkspaceNode[] | undefined) ?? [];
}

export async function searchFiles(workspaceId: string, query: string): Promise<FileSearchMatch[]> {
  const result = await client.request("file.search", { workspace_id: workspaceId, query, max_results: 100 });
  return (result.matches as FileSearchMatch[] | undefined) ?? [];
}

export async function readFile(workspaceId: string, path: string): Promise<string> {
  const result = await client.request("file.read", { workspace_id: workspaceId, path });
  return String(result.content ?? "");
}

export async function listChanges(workspaceId: string, runId?: string | null): Promise<ChangeSummary[]> {
  const result = await client.request("change.list", { workspace_id: workspaceId, run_id: runId ?? null });
  return (result.changes as ChangeSummary[] | undefined) ?? [];
}

export async function changeDiff(workspaceId: string, path?: string): Promise<string> {
  const result = await client.request("change.diff", { workspace_id: workspaceId, path: path ?? null });
  return String(result.diff ?? "");
}

export async function revertChanges(workspaceId: string, runId: string, paths: string[]): Promise<{ reverted_paths: string[]; blocked_paths: Record<string, string> }> {
  return await client.request("change.revert", { workspace_id: workspaceId, run_id: runId, paths, confirm: "revert" }) as { reverted_paths: string[]; blocked_paths: Record<string, string> };
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

export async function respondPermission(toolUseId: string, decision: "allow_once" | "always_allow" | "deny_once" | "always_deny"): Promise<void> {
  await client.request("permission.respond", { tool_use_id: toolUseId, decision });
}
