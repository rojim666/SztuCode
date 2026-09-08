import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

export type ScheduleStatus = "active" | "paused" | "failed" | "waiting_authorization";
export type ScheduleType = "daily" | "weekly" | "monthly";
export type MissedRunPolicy = "run_once" | "skip";
export type ScheduledTask = {
  id: string; name: string; prompt: string; timezone: string;
  schedule_type?: ScheduleType; day_of_week: number; day_of_month?: number;
  hour: number; minute: number; status: ScheduleStatus; missed_run_policy: MissedRunPolicy;
  workspace_id?: string; parent_task_id?: string; budget?: number; next_run_at: string;
  last_run_at?: string; last_trigger_key?: string; lease?: { owner: string; expires_at: string };
  last_result?: "completed" | "failed" | "cancelled" | "needs_attention"; updated_at: string;
};
export type SchedulerHooks = { execute: (task: ScheduledTask, signal: AbortSignal) => Promise<"completed" | "failed" | "cancelled" | "needs_attention">; notify: (task: ScheduledTask, result: string, key: string) => Promise<void> };
export type Clock = () => Date;

export class SchedulerStore {
  constructor(private readonly filePath: string) {}
  private async load(): Promise<ScheduledTask[]> { try { return JSON.parse(await readFile(this.filePath, "utf8")) as ScheduledTask[]; } catch { return []; } }
  private async save(items: ScheduledTask[]) { await mkdir(path.dirname(this.filePath), { recursive: true }); const tmp = `${this.filePath}.${process.pid}.tmp`; await writeFile(tmp, JSON.stringify(items, null, 2)); await rename(tmp, this.filePath); }
  async list() { return this.load(); }
  async get(id: string) { const item = (await this.load()).find((task) => task.id === id); if (!item) throw new Error("scheduled task not found"); return item; }
  async upsert(task: ScheduledTask) { const items = await this.load(); const next = items.some((item) => item.id === task.id) ? items.map((item) => item.id === task.id ? task : item) : [...items, task]; await this.save(next); return task; }
  async delete(id: string) { await this.save((await this.load()).filter((task) => task.id !== id)); }
}

export class LocalScheduler {
  private timer: ReturnType<typeof setInterval> | undefined;
  private readonly owner = randomUUID();
  private readonly running = new Set<string>();
  constructor(private readonly store: SchedulerStore, private readonly hooks: SchedulerHooks, private readonly clock: Clock = () => new Date(), private readonly tickMs = 30_000) {}
  async start() { if (this.timer) return; await this.recoverLeases(); this.timer = setInterval(() => void this.tick(), this.tickMs); this.timer.unref?.(); await this.tick(); }
  stop() { if (this.timer) clearInterval(this.timer); this.timer = undefined; }
  async runNow(id: string) {
    const task = await this.store.get(id);
    if (this.running.has(id)) throw new Error("scheduled task is already running");
    const now = this.clock(); const key = `${task.id}:manual:${now.toISOString()}`;
    const leased = { ...task, lease: { owner: this.owner, expires_at: new Date(now.getTime() + Math.max(60_000, (task.budget ?? 60) * 1_000)).toISOString() }, last_trigger_key: key, updated_at: now.toISOString() };
    await this.store.upsert(leased); this.running.add(id); void this.execute(leased, key); return leased;
  }
  async tick() {
    const now = this.clock();
    for (const task of await this.store.list()) {
      if (task.status !== "active" || new Date(task.next_run_at) > now) continue;
      if (task.lease && new Date(task.lease.expires_at) > now) continue;
      if (this.running.has(task.id)) continue;
      const key = `${task.id}:${task.next_run_at}`;
      if (task.last_trigger_key === key) { await this.store.upsert({ ...task, next_run_at: nextScheduledRun(task, now).toISOString(), updated_at: now.toISOString() }); continue; }
      const leased = { ...task, lease: { owner: this.owner, expires_at: new Date(now.getTime() + Math.max(60_000, (task.budget ?? 60) * 1_000)).toISOString() }, last_trigger_key: key, updated_at: now.toISOString() };
      await this.store.upsert(leased); this.running.add(task.id); void this.execute(leased, key);
    }
  }
  private async execute(task: ScheduledTask, key: string) {
    const controller = new AbortController(); let result: ScheduledTask["last_result"] = "failed";
    try { result = await this.hooks.execute(task, controller.signal); } catch { result = "failed"; }
    const now = this.clock();
    const next = { ...task, status: result === "needs_attention" ? "waiting_authorization" as const : task.status, last_result: result, last_run_at: now.toISOString(), next_run_at: nextScheduledRun(task, now).toISOString(), lease: undefined, updated_at: now.toISOString() };
    await this.store.upsert(next); this.running.delete(task.id);
    if (result === "completed" || result === "failed" || result === "needs_attention") await this.hooks.notify(next, result, `${key}:${result}`);
  }
  private async recoverLeases() {
    const now = this.clock();
    for (const task of await this.store.list()) if (task.lease && new Date(task.lease.expires_at) <= now) await this.store.upsert({ ...task, lease: undefined, next_run_at: task.missed_run_policy === "run_once" ? now.toISOString() : nextScheduledRun(task, now).toISOString(), updated_at: now.toISOString() });
  }
}

type ZonedParts = { year: number; month: number; day: number; hour: number; minute: number };
function partsInTimeZone(date: Date, timezone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(date);
  const value = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return { year: value("year"), month: value("month"), day: value("day"), hour: value("hour"), minute: value("minute") };
}
function zonedDateToUtc(parts: ZonedParts, timezone: string): Date {
  const wallClock = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, 0, 0); let candidate = wallClock;
  for (let attempt = 0; attempt < 3; attempt += 1) { const actual = partsInTimeZone(new Date(candidate), timezone); const represented = Date.UTC(actual.year, actual.month - 1, actual.day, actual.hour, actual.minute, 0, 0); candidate += wallClock - represented; }
  return new Date(candidate);
}
function daysInMonth(year: number, month: number): number { return new Date(Date.UTC(year, month, 0)).getUTCDate(); }

export function nextScheduledRun(task: Pick<ScheduledTask, "schedule_type" | "timezone" | "day_of_week" | "day_of_month" | "hour" | "minute">, from: Date): Date {
  const timezone = task.timezone || "UTC"; const local = partsInTimeZone(from, timezone); const scheduleType = task.schedule_type ?? "weekly";
  const calendar = new Date(Date.UTC(local.year, local.month - 1, local.day, task.hour, task.minute, 0, 0));
  if (scheduleType === "weekly") calendar.setUTCDate(calendar.getUTCDate() + (task.day_of_week - calendar.getUTCDay() + 7) % 7);
  else if (scheduleType === "monthly") calendar.setUTCDate(Math.min(task.day_of_month ?? 1, daysInMonth(calendar.getUTCFullYear(), calendar.getUTCMonth() + 1)));
  const convert = () => zonedDateToUtc({ year: calendar.getUTCFullYear(), month: calendar.getUTCMonth() + 1, day: calendar.getUTCDate(), hour: task.hour, minute: task.minute }, timezone);
  let next = convert();
  if (next <= from) {
    if (scheduleType === "daily") calendar.setUTCDate(calendar.getUTCDate() + 1);
    else if (scheduleType === "weekly") calendar.setUTCDate(calendar.getUTCDate() + 7);
    else { calendar.setUTCMonth(calendar.getUTCMonth() + 1, 1); calendar.setUTCDate(Math.min(task.day_of_month ?? 1, daysInMonth(calendar.getUTCFullYear(), calendar.getUTCMonth() + 1))); }
    next = convert();
  }
  return next;
}
export function nextWeekly(task: Pick<ScheduledTask, "day_of_week" | "hour" | "minute">, from: Date): Date { return nextScheduledRun({ ...task, schedule_type: "weekly", timezone: "UTC" }, from); }
