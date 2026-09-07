import type { RuntimeEvent } from "@sztucode/protocol";
import { appendFile, mkdir } from "node:fs/promises";
import { readFileSync } from "node:fs";
import path from "node:path";

export type EventListener = (event: RuntimeEvent) => void;

export class EventBus {
  private readonly listeners = new Set<EventListener>();
  private readonly history: RuntimeEvent[] = [];
  // Trace writes are serialized. Streaming events are buffered briefly so a
  // token stream does not open and append a file once per token.
  private traceReady: Promise<void> | null = null;
  private traceWrite: Promise<void> = Promise.resolve();
  private streamRows: string[] = [];
  private streamTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly streamWindowMs = 75;
  constructor(private readonly tracePath = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "traces", "runtime-ts-events.jsonl")) {
    try {
      const rows = readFileSync(this.tracePath, "utf8").split(/\r?\n/).filter(Boolean).slice(-10_000);
      for (const row of rows) {
        try { this.history.push(JSON.parse(row) as RuntimeEvent); } catch { /* ignore a partial final row */ }
      }
    } catch { /* first start has no trace */ }
  }

  subscribe(listener: EventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  publish(event: RuntimeEvent): void {
    this.history.push(event);
    if (this.history.length > 10_000) this.history.splice(0, this.history.length - 10_000);
    const row = `${JSON.stringify(event)}\n`;
    if (event.type === "llm.token" || event.type === "llm.thinking") {
      this.streamRows.push(row);
      if (!this.streamTimer) {
        this.streamTimer = setTimeout(() => {
          this.streamTimer = null;
          this.flushStreamRows();
        }, this.streamWindowMs);
        this.streamTimer.unref?.();
      }
    } else {
      this.flushStreamRows();
      this.enqueueTrace(row);
    }
    for (const listener of this.listeners) listener(event);
  }

  private enqueueTrace(row: string): void {
    if (!this.traceReady) this.traceReady = mkdir(path.dirname(this.tracePath), { recursive: true }).then(() => undefined).catch(() => undefined);
    this.traceWrite = this.traceWrite.then(async () => {
      await this.traceReady;
      await appendFile(this.tracePath, row, "utf8");
    }).catch(() => undefined);
  }

  private flushStreamRows(): void {
    if (!this.streamRows.length) return;
    const rows = this.streamRows.join("");
    this.streamRows = [];
    this.enqueueTrace(rows);
  }

  // 等待 trace 写入链排空（测试/关闭场景：确保 appendFile 全部落盘后再清理目录）
  async flush(): Promise<void> {
    if (this.streamTimer) {
      clearTimeout(this.streamTimer);
      this.streamTimer = null;
    }
    this.flushStreamRows();
    await this.traceWrite;
  }

  replay(maxEvents = 2_000): RuntimeEvent[] {
    return this.history.slice(-Math.max(1, Math.min(maxEvents, 10_000)));
  }
  replayRun(runId: string, maxEvents = 2_000): RuntimeEvent[] {
    return this.history.filter((event) => "run_id" in event && event.run_id === runId).slice(-Math.max(1, Math.min(maxEvents, 10_000)));
  }
}
