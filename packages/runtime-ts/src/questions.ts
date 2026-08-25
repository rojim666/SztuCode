import { randomUUID } from "node:crypto";
import { EventBus } from "./event-bus.js";
export type Question = { id: string; header?: string | null; question: string; options: Array<{ label: string; description?: string | null }>; multi_select: boolean };
type Pending = { rpc_id: string; session_id: string; run_id: string; questions: Question[]; resolve: (answers: unknown[]) => void };
export class QuestionManager {
  private readonly pending = new Map<string, Pending>();
  constructor(private readonly events?: EventBus) {}
  ask(sessionId: string, runId: string, questions: Question[]): Promise<unknown[]> { const rpcId = `question-${randomUUID()}`; this.events?.publish({ type: "question.requested", rpc_id: rpcId, session_id: sessionId, run_id: runId, questions: questions as Array<Record<string, unknown>>, ts: new Date().toISOString() }); return new Promise((resolve) => this.pending.set(rpcId, { rpc_id: rpcId, session_id: sessionId, run_id: runId, questions, resolve })); }
  list(sessionId?: string | null): Array<Omit<Pending, "resolve">> { return [...this.pending.values()].filter((item) => !sessionId || item.session_id === sessionId).map(({ resolve: _resolve, ...item }) => item); }
  respond(rpcId: string, sessionId: string, answers: unknown[]): boolean { const item = this.pending.get(rpcId); if (!item || item.session_id !== sessionId) return false; this.pending.delete(rpcId); this.events?.publish({ type: "question.resolved", rpc_id: rpcId, session_id: sessionId, run_id: item.run_id, outcome: "answered", ts: new Date().toISOString() }); if (this.events) void this.events.flush().then(() => item.resolve(answers), () => item.resolve(answers)); else item.resolve(answers); return true; }
  cancelRun(runId: string): void { for (const [rpcId, item] of this.pending) { if (item.run_id !== runId) continue; this.pending.delete(rpcId); this.events?.publish({ type: "question.resolved", rpc_id: rpcId, session_id: item.session_id, run_id: runId, outcome: "cancelled", ts: new Date().toISOString() }); if (this.events) void this.events.flush().then(() => item.resolve([{ cancelled: true }]), () => item.resolve([{ cancelled: true }])); else item.resolve([{ cancelled: true }]); } }
}
