import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
export type DurableOperationStatus = "not_executed" | "running" | "succeeded" | "failed" | "unknown";
export interface DurableOperation { operation_id: string; task_id: string; run_id?: string; session_id?: string; step: number; attempt: number; sequence: number; status: DurableOperationStatus; params_summary: string; external_object_id?: string; result_summary?: string; permission_state?: string; budget_remaining?: number; updated_at: string; }
export class OperationStore {
  private locks = new Set<string>();
  constructor(private readonly filePath: string) {}
  private async load(): Promise<DurableOperation[]> { try { return JSON.parse(await readFile(this.filePath, "utf8")) as DurableOperation[]; } catch { return []; } }
  private async save(items: DurableOperation[]) { await mkdir(path.dirname(this.filePath), { recursive: true }); const tmp = `${this.filePath}.${process.pid}.tmp`; await writeFile(tmp, JSON.stringify(items, null, 2)); await rename(tmp, this.filePath); }
  async list(taskId?: string) { const items = await this.load(); return taskId ? items.filter(i => i.task_id === taskId) : items; }
  async get(operationId: string) { const item = (await this.load()).find(i => i.operation_id === operationId); if (!item) throw new Error("operation not found"); return item; }
  async begin(input: Omit<DurableOperation, "status" | "updated_at">): Promise<DurableOperation> {
    if (this.locks.has(input.task_id)) throw new Error("task recovery already in progress");
    this.locks.add(input.task_id);
    try { const items = await this.load(); const existing = items.find(i => i.operation_id === input.operation_id); if (existing?.status === "succeeded") return existing; if (existing?.status === "unknown") throw new Error("operation result is unknown; reconciliation required"); const value = { ...input, status: "running" as const, updated_at: new Date().toISOString() }; const next = existing ? items.map(i => i.operation_id === input.operation_id ? value : i) : [...items, value]; await this.save(next); return value; } finally { this.locks.delete(input.task_id); }
  }
  async finish(operationId: string, status: Exclude<DurableOperationStatus, "not_executed" | "running">, resultSummary?: string, externalObjectId?: string) { const items = await this.load(); const item = items.find(i => i.operation_id === operationId); if (!item) throw new Error("operation not found"); if (item.status === "succeeded") { if (status !== "succeeded") throw new Error("successful operation cannot be rewritten"); return item; } if (item.status === "unknown") throw new Error("operation result is unknown; reconciliation required"); item.status = status; item.result_summary = resultSummary; if (externalObjectId) item.external_object_id = externalObjectId; item.updated_at = new Date().toISOString(); await this.save(items); return item; }
  async recover(operationId: string) { const item = await this.get(operationId); if (item.status === "running") { item.status = "unknown"; item.updated_at = new Date().toISOString(); const items = await this.load(); await this.save(items.map(i => i.operation_id === operationId ? item : i)); } return item; }
}
