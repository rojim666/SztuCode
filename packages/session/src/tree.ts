import type { SessionEntry, SessionTreeNode } from "./types.js";

export function resolveBranch(entries: SessionEntry[], leafId: string | null = entries.at(-1)?.id ?? null): SessionEntry[] {
  if (leafId === null) return [];
  const byId = new Map(entries.map((entry) => [entry.id, entry])); const result: SessionEntry[] = []; const seen = new Set<string>(); let current: SessionEntry | undefined = byId.get(leafId);
  while (current) {
    if (seen.has(current.id)) throw new Error("session entry parent cycle");
    seen.add(current.id); result.push(current); current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  return result.reverse();
}

export function buildSessionTree(entries: SessionEntry[]): SessionTreeNode[] {
  const nodes = new Map<string, SessionTreeNode>();
  for (const entry of entries) nodes.set(entry.id, { entry, children: [] });
  const roots: SessionTreeNode[] = [];
  for (const entry of entries) {
    const node = nodes.get(entry.id)!; const parent = entry.parentId ? nodes.get(entry.parentId) : undefined;
    if (parent) parent.children.push(node); else roots.push(node);
  }
  return roots;
}
