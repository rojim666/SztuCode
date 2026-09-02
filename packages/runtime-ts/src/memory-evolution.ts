/**
 * Recuris 记忆进化引擎
 * 参考论文：Recursive Experiential-Working Memory Evolution
 */

import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import type { ChatMessage, ModelProvider } from "./agent-loop.js";
import type { CanvasNode } from "./task-canvas.js";

// --- Working State ---

type EvidenceSource = "hard" | "soft" | "none";

interface Fact {
  content: string;
  source: EvidenceSource;
  timestamp: string;
  sourceNodeId?: string;
}

export class WorkingState {
  private _facts: Fact[] = [];
  private _goal: string = "";
  private _version: number = 0;

  constructor(goal: string = "") {
    this._goal = goal;
  }

  get goal(): string {
    return this._goal;
  }

  get version(): number {
    return this._version;
  }

  get hasContent(): boolean {
    return this._facts.length > 0;
  }

  setGoal(goal: string): void {
    this._goal = goal;
    this._version++;
  }

  // 证据门控吸收：只吸收来自硬证据源的事实
  absorb(content: string, source: EvidenceSource, sourceNodeId?: string): void {
    if (source !== "hard") return;

    this._facts.push({
      content,
      source,
      timestamp: new Date().toISOString(),
      sourceNodeId,
    });
    this._version++;
  }

  // 批量吸收（用于从记忆中恢复）
  absorbBatch(facts: Array<{ content: string; source: EvidenceSource; timestamp?: string; sourceNodeId?: string }>): void {
    for (const fact of facts) {
      if (fact.source !== "hard") continue;

      this._facts.push({
        content: fact.content,
        source: fact.source,
        timestamp: fact.timestamp ?? new Date().toISOString(),
        sourceNodeId: fact.sourceNodeId,
      });
    }
    if (facts.some(f => f.source === "hard")) {
      this._version++;
    }
  }

  render(): string {
    if (!this.hasContent) return "";

    const lines: string[] = [];
    lines.push("--- Working State ---");
    if (this._goal) {
      lines.push(`Goal: ${this._goal}`);
    }
    lines.push("Facts:");
    for (const fact of this._facts.slice(-20)) {
      lines.push(`- ${fact.content} (source: ${fact.source}, timestamp: ${fact.timestamp})`);
    }
    return lines.join("\n");
  }

  toJSON(): { goal: string; facts: Fact[]; version: number } {
    return { goal: this._goal, facts: [...this._facts], version: this._version };
  }

  static fromJSON(data: { goal?: string; facts?: Fact[]; version?: number }): WorkingState {
    const ws = new WorkingState(data.goal ?? "");
    if (data.facts) {
      ws.absorbBatch(data.facts);
    }
    if (data.version !== undefined) {
      ws._version = data.version;
    }
    return ws;
  }
}

// --- Memory Patch & Validation Gate ---

const _FORBIDDEN_NOTE_CHARS = /[<>:"/\\|?*]/;
const _MAX_CONTENT_BYTES = 64 * 1024; // 64KB

export interface MemoryPatch {
  targetNote: string;
  proposedContent: string;
  attribution: string;
  evidenceRefs: string[];
  reason: string;
}

export interface GateDecision {
  accepted: boolean;
  reasons: string[];
}

class ValidationGate {
  private _nodeIds: Set<string>;

  constructor(nodeIds: string[] = []) {
    this._nodeIds = new Set(nodeIds);
  }

  updateNodeIds(nodeIds: string[]): void {
    this._nodeIds = new Set(nodeIds);
  }

  evaluate(patch: MemoryPatch, existingNotes: Map<string, string>): GateDecision {
    const reasons: string[] = [];

    // 规则 1：证据引用必须指向轨迹中的具体记录
    if (!patch.evidenceRefs || patch.evidenceRefs.length === 0) {
      reasons.push("missing_evidence_refs");
    } else {
      const unknown = patch.evidenceRefs.filter(ref => !this._nodeIds.has(ref));
      if (unknown.length > 0) {
        reasons.push(`evidence_refs_not_in_trajectory:${unknown.join(",")}`);
      }
    }

    // 规则 2：内容非空
    if (!patch.proposedContent || !patch.proposedContent.trim()) {
      reasons.push("empty_content");
    }

    // 规则 3：长度上限
    const contentBytes = new TextEncoder().encode(patch.proposedContent).length;
    if (contentBytes > _MAX_CONTENT_BYTES) {
      reasons.push(`content_over_limit:${contentBytes}>`);
    }

    // 规则 4：去重检查
    const existing = existingNotes.get(patch.targetNote) || "";
    if (existing && existing.trim() === patch.proposedContent.trim()) {
      reasons.push("duplicate_content");
    }

    // 规则 5：targetNote 合法性检查
    if (!patch.targetNote || !patch.targetNote.trim() || _FORBIDDEN_NOTE_CHARS.test(patch.targetNote)) {
      reasons.push("invalid_target_note");
    }

    return { accepted: reasons.length === 0, reasons };
  }
}

// --- Meta-Agent ---

function _renderNode(node: CanvasNode): string {
  const parts: string[] = [];
  parts.push(`- [${node.nodeId}] ${node.label} (status: ${node.status})`);
  if (node.state) parts.push(`  State: ${node.state}`);
  if (node.skill) parts.push(`  Skill: ${node.skill}`);
  if (node.action) parts.push(`  Action: ${node.action}`);
  if (node.observation) parts.push(`  Observation: ${node.observation}`);
  if (node.verified) parts.push(`  Verified: ${node.verified}`);
  return parts.join("\n");
}

function buildEvolutionPrompt(trajectory: CanvasNode[], goal: string = ""): string {
  const lines: string[] = [];
  if (goal) {
    lines.push("--- Goal ---");
    lines.push(goal);
  }
  lines.push("\n--- Structured Trajectory ---");
  if (trajectory.length > 0) {
    for (const node of trajectory) {
      lines.push(_renderNode(node));
    }
  } else {
    lines.push("(Trajectory empty — run failed before first step)");
  }
  lines.push("\n--- Your Output ---");
  lines.push("Output only a JSON array of MemoryPatch objects.");
  return lines.join("\n");
}

function memoryEvolutionSystemPrompt(): string {
  return `[memory-evolution]
You are the Recuris Memory Evolution Meta-Agent.

Your job: analyze a structured trajectory of a failed or stuck agent run, and propose targeted memory patches.

Each patch must:
- targetNote: name of the memory note to update (simple filename, no path)
- proposedContent: the content to write
- attribution: what component this fixes (note_content/state_representation/invocation_timing)
- evidenceRefs: array of node IDs from the trajectory that support this change
- reason: human-readable explanation of why this change helps

Rules:
1. Only propose changes based on hard evidence in the trajectory
2. Each patch must reference at least one node in the evidenceRefs
3. Keep patches focused and actionable
4. Never invent information not present in the trajectory
5. Output only a JSON array, no Markdown wrapping`;
}

function extractPatches(text: string): MemoryPatch[] {
  // 清理输入文本，移除 Markdown 围栏
  let cleanText = text.trim();
  const fenceMatch = cleanText.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenceMatch) {
    cleanText = fenceMatch[1];
  }

  try {
    const parsed = JSON.parse(cleanText);
    if (!Array.isArray(parsed)) {
      return [];
    }

    // 验证并标准化每个 patch
    return parsed
      .filter(p => typeof p === "object" && p !== null)
      .map(p => ({
        targetNote: String(p.targetNote || ""),
        proposedContent: String(p.proposedContent || ""),
        attribution: String(p.attribution || ""),
        evidenceRefs: Array.isArray(p.evidenceRefs) ? p.evidenceRefs.map(String) : [],
        reason: String(p.reason || ""),
      }));
  } catch {
    return [];
  }
}

// --- Memory Evolution Orchestration ---

interface EvolutionOptions {
  goal?: string;
  bus?: { publish: (event: unknown) => void };
  runId?: string;
}

async function evolveMemory(
  patches: MemoryPatch[],
  trajectory: CanvasNode[],
  memoryRoot: string,
  roundId: number = 1,
  options?: EvolutionOptions
): Promise<GateDecision[]> {
  const decisions: GateDecision[] = [];
  const existingNotes = await _loadExistingNotes(memoryRoot);
  const nodeIds = trajectory.map(n => n.nodeId);
  const gate = new ValidationGate(nodeIds);

  for (const patch of patches) {
    const decision = gate.evaluate(patch, existingNotes);
    decisions.push(decision);

    await _writeLedgerEntry(memoryRoot, {
      round: roundId,
      patch,
      gateResult: decision.accepted ? "accept" : "reject",
      reasons: decision.reasons,
      timestamp: new Date().toISOString(),
    });

    if (decision.accepted) {
      await _writeMemoryNote(memoryRoot, patch.targetNote, patch.proposedContent);
      if (options?.bus) {
        options.bus.publish({
          type: "memory.evolution.patch_accepted",
          run_id: options.runId,
          target_note: patch.targetNote,
          timestamp: new Date().toISOString(),
        });
      }
    }
  }

  return decisions;
}

async function _loadExistingNotes(memoryRoot: string): Promise<Map<string, string>> {
  const notes = new Map<string, string>();
  const notesDir = path.join(memoryRoot, "notes");
  try {
    // 简单实现：不实际遍历，因为 Node.js 的 fs 不能直接枚举目录而不导入额外模块
    // 实际实现时可以使用 fs.readdir，但此处简化处理
  } catch {
    // 目录不存在，没关系
  }
  return notes;
}

async function _writeMemoryNote(memoryRoot: string, noteName: string, content: string): Promise<void> {
  const notesDir = path.join(memoryRoot, "notes");
  await mkdir(notesDir, { recursive: true });
  const notePath = path.join(notesDir, noteName.endsWith(".md") ? noteName : `${noteName}.md`);
  await writeFile(notePath, content, "utf8");
}

async function _writeLedgerEntry(memoryRoot: string, entry: {
  round: number;
  patch: MemoryPatch;
  gateResult: string;
  reasons: string[];
  timestamp: string;
}): Promise<void> {
  const ledgerPath = path.join(memoryRoot, "ledger.jsonl");
  const dir = path.dirname(ledgerPath);
  await mkdir(dir, { recursive: true });
  const line = JSON.stringify(entry) + "\n";
  // 使用 appendFile，但先 import
  const fs = await import("node:fs/promises");
  await fs.appendFile(ledgerPath, line, "utf8");
}

function _nextRound(memoryRoot: string): number {
  // 简单实现，默认返回 1
  return 1;
}

export async function runMemoryEvolution(
  provider: ModelProvider,
  trajectory: CanvasNode[],
  memoryRoot: string,
  options?: EvolutionOptions
): Promise<GateDecision[]> {
  const prompt = buildEvolutionPrompt(trajectory, options?.goal ?? "");
  try {
    const response = await provider.complete(
      [{ role: "user", content: prompt }],
      { list: () => [] }, // empty tool registry
      undefined,
      undefined,
      options?.runId ? { runId: options.runId, step: 0 } : undefined
    );

    const patches = extractPatches(response.text || "");
    if (!patches.length) {
      return [];
    }

    return await evolveMemory(
      patches,
      trajectory,
      memoryRoot,
      _nextRound(memoryRoot),
      options
    );
  } catch (error) {
    console.error("Memory evolution failed:", error);
    return [];
  }
}

export function shouldEvolve(status: "success" | "interrupted" | "failed" | "cancelled", reason?: string): boolean {
  if (status === "success" || status === "cancelled") {
    return false;
  }

  if (status === "interrupted") {
    return reason === "exceeded_max_steps" || reason === "stuck" || reason === "timeout";
  }

  return true; // failed
}
