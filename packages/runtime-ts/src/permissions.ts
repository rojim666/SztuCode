import type { PermissionDecision, PermissionMode } from "@sztucode/protocol";
import { EventBus } from "./event-bus.js";
import type { ToolPermission } from "./tools-types.js";
import { defaultPolicyPath, loadPermissionPolicy, savePermissionPolicy, type StoredPermissionDecision } from "./permission-policy.js";
import { NOOP_TELEMETRY_CONTEXT, safeStartSpan, type TelemetryContext } from "@sztucode/telemetry";

type Pending = { resolve: (allowed: boolean) => void; runId: string; toolName: string; params: Record<string, unknown>; permission: ToolPermission; workspaceRoot?: string };
export interface PermissionGate {
  check(runId: string, permissionId: string, toolName: string, params: Record<string, unknown>, permission: ToolPermission, signal?: AbortSignal, workspaceRoot?: string): Promise<boolean>;
}
export class PermissionManager {
  private mode: PermissionMode = "normal";
  private readonly pending = new Map<string, Pending>();
  private readonly persistent: Map<string, StoredPermissionDecision>;
  constructor(private readonly events: EventBus, private readonly timeoutMs = 60_000, private readonly policyPath = defaultPolicyPath(), private readonly telemetry: TelemetryContext = NOOP_TELEMETRY_CONTEXT) { this.persistent = loadPermissionPolicy(policyPath); }
  getMode(): PermissionMode { return this.mode; }
  setMode(mode: PermissionMode): void { const old = this.mode; this.mode = mode; if (old !== mode) this.events.publish({ type: "permission.mode_changed", old_mode: old, new_mode: mode, ts: new Date().toISOString() }); }
  scoped(mode: PermissionMode): PermissionGate { return { check: (runId, permissionId, toolName, params, permission, signal) => this.checkWithMode(mode, runId, permissionId, toolName, params, permission, signal) }; }
  check(runId: string, permissionId: string, toolName: string, params: Record<string, unknown>, permission: ToolPermission, signal?: AbortSignal, workspaceRoot?: string): Promise<boolean> {
    return this.checkWithMode(this.mode, runId, permissionId, toolName, params, permission, signal, workspaceRoot);
  }
  private checkWithMode(mode: PermissionMode, runId: string, permissionId: string, toolName: string, params: Record<string, unknown>, permission: ToolPermission, signal?: AbortSignal, workspaceRoot?: string): Promise<boolean> {
    if (signal?.aborted) return Promise.resolve(false);
    if (mode === "auto" || permission === "read_only" || (mode === "accept_edits" && permission === "workspace_write")) return Promise.resolve(true);
    if (mode === "plan") return Promise.resolve(false);
    const forceAsk = permission === "danger_full_access" || toolName === "bash" && isDangerousCommand(String(params.command ?? ""));
    if (!forceAsk) {
      const stored = findStoredDecision(this.persistent, toolName, params, workspaceRoot);
      if (stored) return Promise.resolve(stored === "allow");
    }
    return this.ask(runId, permissionId, toolName, params, permission, signal, workspaceRoot);
  }
  private ask(runId: string, permissionId: string, toolName: string, params: Record<string, unknown>, permission: ToolPermission, signal?: AbortSignal, workspaceRoot?: string): Promise<boolean> {
    return safeStartSpan(this.telemetry, { name: "permission.request", attributes: { run_id: runId, permission_id: permissionId, tool_name: toolName, permission } }, (span) => new Promise((resolve) => {
      const timer = setTimeout(() => { if (this.pending.delete(permissionId)) resolve(false); }, this.timeoutMs);
      const finish = (allowed: boolean) => { clearTimeout(timer); signal?.removeEventListener("abort", abort); span.setAttributes({ allowed }); resolve(allowed); };
      const abort = () => { if (this.pending.delete(permissionId)) finish(false); };
      this.pending.set(permissionId, { resolve: finish, runId, toolName, params, permission, workspaceRoot });
      signal?.addEventListener("abort", abort, { once: true });
      const paramPreview = preview(toolName, params);
      this.events.publish({ type: "permission.requested", run_id: runId, permission_id: permissionId, tool_use_id: permissionId, tool_name: toolName, params, preview: paramPreview, param_preview: paramPreview, ts: new Date().toISOString() });
    }));
  }
  respond(permissionId: string, decision: PermissionDecision): boolean {
    const pending = this.pending.get(permissionId); if (!pending) return false;
    this.pending.delete(permissionId); const allowed = decision === "allow_once" || decision === "always_allow";
    if ((decision === "always_allow" || decision === "always_deny") && pending.permission !== "danger_full_access") {
      const parameter = pending.toolName === "bash" ? pending.params.command : pending.params.path;
      const rule = pending.workspaceRoot && typeof parameter === "string" ? `${pending.toolName}(${parameter})` : pending.toolName;
      this.persistent.set(scopedRule(rule, pending.workspaceRoot), decision === "always_allow" ? "allow" : "deny");
      try { savePermissionPolicy(this.persistent, this.policyPath); }
      catch { /* the current decision still applies even when persistence is unavailable */ }
    }
    pending.resolve(allowed);
    const ts = new Date().toISOString();
    this.events.publish({ type: "permission.resolved", run_id: pending.runId, permission_id: permissionId, tool_use_id: permissionId, decision, ts });
    this.events.publish({ type: allowed ? "permission.granted" : "permission.denied", run_id: pending.runId, tool_use_id: permissionId, decision, ts }); return true;
  }
  cancelRun(runId: string): void {
    for (const [permissionId, pending] of this.pending) {
      if (pending.runId !== runId) continue;
      this.pending.delete(permissionId);
      pending.resolve(false);
    }
  }
}
const preview = (toolName: string, params: Record<string, unknown>): string => `${toolName}:${String(params[toolName === "bash" ? "command" : "path"] ?? "").slice(0, 120)}`;
const isDangerousCommand = (command: string): boolean => [
  /(^|\s)\//, /(^|\s)~/, /(^|\s)\.\.([/\\]|$)/, /\$\{?(HOME|PWD)\b/, /(^|[;&|])\s*(sudo|cd)\b/, /\bLD_(PRELOAD|LIBRARY_PATH)\b/
].some((pattern) => pattern.test(command));

/** Match parameter-scoped rules such as write_file(/src/**) and bash(git diff:*). */
function findStoredDecision(policy: ReadonlyMap<string, StoredPermissionDecision>, toolName: string, params: Record<string, unknown>, workspaceRoot?: string): StoredPermissionDecision | undefined {
  const prefix = workspaceRoot ? `${encodeURIComponent(workspaceRoot)}::` : "";
  const direct = policy.get(`${prefix}${toolName}`) ?? (prefix ? policy.get(toolName) : undefined); if (direct) return direct;
  const value = toolName === "bash" ? String(params.command ?? "") : String(params.path ?? "");
  for (const [storedKey, decision] of policy) {
    const scoped = !prefix || storedKey.startsWith(prefix); if (!scoped && prefix) continue;
    const key = prefix && scoped ? storedKey.slice(prefix.length) : storedKey;
    const match = key.match(/^([A-Za-z0-9_.-]+)\((.*)\)$/); if (!match || match[1] !== toolName) continue;
    const pattern = (match[2] ?? "").replace(/:\*/g, "*");
    const regex = new RegExp(`^${pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")}$`);
    if (regex.test(value) || (!value.startsWith("/") && regex.test(`/${value}`))) return decision;
  }
  return undefined;
}
const scopedRule = (rule: string, workspaceRoot?: string): string => workspaceRoot ? `${encodeURIComponent(workspaceRoot)}::${rule}` : rule;
