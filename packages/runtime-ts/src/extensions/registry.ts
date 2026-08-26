import type { RuntimeEvent } from "@sztucode/protocol";
import path from "node:path";
import type { Tool } from "../tools.js";
import type { BeforeToolCallResult, ExtensionAPI, ExtensionContext, ExtensionDefinition, ExtensionDiagnostic, ExtensionDiagnosticPhase, ExtensionHook, ExtensionHookHandler, ExtensionHookPayload, ExtensionResource, ExtensionScope, PromptTemplate, SessionEventListener, SlashCommand, ToolPromptContribution, Unregister } from "./types.js";

type Loaded = { definition: ExtensionDefinition; context: ExtensionContext; api: ExtensionAPI; hooks: Map<ExtensionHook, Set<ExtensionHookHandler>>; tools: Map<string, Tool>; commands: Map<string, SlashCommand>; templates: Map<string, PromptTemplate>; resources: Map<string, ExtensionResource>; contributions: Set<ToolPromptContribution>; listeners: Set<SessionEventListener>; };
const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);

export class ExtensionRegistry {
  private readonly loaded = new Map<string, Loaded>();
  private readonly errors: ExtensionDiagnostic[] = [];

  async load(definition: ExtensionDefinition): Promise<boolean> {
    if (this.loaded.has(definition.id)) { this.record(definition, "load", `Extension already loaded: ${definition.id}`); return false; }
    const hooks = new Map<ExtensionHook, Set<ExtensionHookHandler>>();
    const loaded = {} as Loaded;
    const context: ExtensionContext = Object.freeze({ extensionId: definition.id, scope: definition.scope, workspaceRoot: definition.root });
    const api: ExtensionAPI = {
      context,
      on: (hook, handler) => { const set = hooks.get(hook) ?? new Set(); set.add(handler); hooks.set(hook, set); return () => set.delete(handler); },
      registerTool: (tool) => this.add(loaded.tools, tool.name, tool, definition, "tool"),
      registerSlashCommand: (command) => this.add(loaded.commands, command.name, command, definition, "slash command"),
      registerPromptTemplate: (template) => this.add(loaded.templates, template.name, template, definition, "prompt template"),
      registerResource: (resource) => this.add(loaded.resources, resource.name, resource, definition, "resource"),
      registerToolPromptContribution: (contribution) => { loaded.contributions.add(contribution); return () => loaded.contributions.delete(contribution); },
      onSessionEvent: (listener) => { loaded.listeners.add(listener); return () => loaded.listeners.delete(listener); },
    };
    loaded.definition = definition; loaded.context = context; loaded.api = api; loaded.hooks = hooks; loaded.tools = new Map(); loaded.commands = new Map(); loaded.templates = new Map(); loaded.resources = new Map(); loaded.contributions = new Set(); loaded.listeners = new Set();
    try { await definition.activate(api); } catch (error) { this.record(definition, "activate", errorMessage(error), error); return false; }
    this.loaded.set(definition.id, loaded); return true;
  }

  async unload(id: string): Promise<boolean> {
    const loaded = this.loaded.get(id); if (!loaded) return false;
    try { await loaded.definition.deactivate?.(loaded.api); } catch (error) { this.record(loaded.definition, "deactivate", errorMessage(error), error); }
    this.loaded.delete(id); return true;
  }
  async unloadAll(): Promise<void> { for (const id of [...this.loaded.keys()]) await this.unload(id); }
  get(id: string): ExtensionDefinition | undefined { return this.loaded.get(id)?.definition; }
  list(): ExtensionDefinition[] { return [...this.loaded.values()].map((item) => item.definition); }
  diagnostics(): ExtensionDiagnostic[] { return [...this.errors]; }
  recordLoad(id: string, modulePath: string, scope: ExtensionScope, error: unknown): void { this.errors.push({ extensionId: id, path: modulePath, scope, phase: "load", message: errorMessage(error), error }); }

  toolsForWorkspace(workspaceRoot: string, reserved = new Set<string>()): Tool[] {
    const result: Tool[] = [];
    for (const item of this.visible(workspaceRoot)) for (const [name, tool] of item.tools) {
      if (reserved.has(name) || result.some((candidate) => candidate.name === name)) { this.record(item.definition, "register", `Tool name conflict: ${name}`); continue; }
      result.push(tool);
    }
    return result;
  }
  getTools(workspaceRoot: string, reserved = new Set<string>()): Tool[] { return this.toolsForWorkspace(workspaceRoot, reserved); }
  slashCommands(workspaceRoot: string): SlashCommand[] { return this.visible(workspaceRoot).flatMap((item) => [...item.commands.values()]); }
  getSlashCommands(workspaceRoot: string): SlashCommand[] { return this.slashCommands(workspaceRoot); }
  promptTemplates(workspaceRoot: string): PromptTemplate[] { return this.visible(workspaceRoot).flatMap((item) => [...item.templates.values()]); }
  getPromptTemplates(workspaceRoot: string): PromptTemplate[] { return this.promptTemplates(workspaceRoot); }
  resources(workspaceRoot: string): ExtensionResource[] { return this.visible(workspaceRoot).flatMap((item) => [...item.resources.values()]); }
  getResources(workspaceRoot: string): ExtensionResource[] { return this.resources(workspaceRoot); }
  toolPromptContributions(workspaceRoot: string): ToolPromptContribution[] { return this.visible(workspaceRoot).flatMap((item) => [...item.contributions]); }
  getToolPromptContributions(workspaceRoot: string): ToolPromptContribution[] { return this.toolPromptContributions(workspaceRoot); }

  async dispatch(hook: ExtensionHook, payload: ExtensionHookPayload, workspaceRoot: string, extra: Partial<ExtensionContext> = {}): Promise<BeforeToolCallResult | undefined> {
    let merged: BeforeToolCallResult | undefined;
    for (const item of this.visible(workspaceRoot)) for (const handler of item.hooks.get(hook) ?? []) {
      try { const result = await handler(payload, { ...item.context, workspaceRoot, ...extra }); if (hook === "before_tool_call" && result) merged = { ...(merged ?? {}), ...result }; }
      catch (error) { this.record(item.definition, "hook", errorMessage(error), error, hook); }
    }
    return merged;
  }
  async dispatchAll(hook: ExtensionHook, payload: ExtensionHookPayload, extra: Partial<ExtensionContext> = {}): Promise<void> {
    for (const item of this.loaded.values()) for (const handler of item.hooks.get(hook) ?? []) {
      try { await handler(payload, { ...item.context, ...extra }); }
      catch (error) { this.record(item.definition, "hook", errorMessage(error), error, hook); }
    }
  }
  async renderToolPromptContributions(workspaceRoot: string, extra: Partial<ExtensionContext> = {}): Promise<string[]> {
    const output: string[] = [];
    for (const item of this.toolPromptContributions(workspaceRoot)) {
      try { output.push(typeof item.content === "function" ? await item.content({ extensionId: "prompt", scope: "global", workspaceRoot, ...extra }) : item.content); }
      catch (error) { const owner = this.visible(workspaceRoot).find((candidate) => candidate.contributions.has(item)); if (owner) this.record(owner.definition, "hook", errorMessage(error), error); }
    }
    return output;
  }
  async emitSessionEvent(event: RuntimeEvent, workspaceRoot: string, extra: Partial<ExtensionContext> = {}): Promise<void> {
    for (const item of this.visible(workspaceRoot)) for (const listener of item.listeners) try { await listener(event, { ...item.context, workspaceRoot, ...extra }); } catch (error) { this.record(item.definition, "hook", errorMessage(error), error); }
  }

  private visible(root: string): Loaded[] { const resolved = path.resolve(root); return [...this.loaded.values()].filter((item) => item.definition.scope === "global" || path.resolve(item.definition.root) === resolved); }
  private add<T>(map: Map<string, T>, key: string, value: T, definition: ExtensionDefinition, kind: string): Unregister { if (map.has(key)) { this.record(definition, "register", `${kind} already registered: ${key}`); return () => {}; } map.set(key, value); return () => map.delete(key); }
  private record(definition: ExtensionDefinition, phase: ExtensionDiagnosticPhase, message: string, error?: unknown, hook?: ExtensionHook): void { this.errors.push({ extensionId: definition.id, path: definition.root, scope: definition.scope, phase, hook, message, error }); }
}

export type ExtensionRunner = ExtensionRegistry;
