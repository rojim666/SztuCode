import test from "node:test"; import assert from "node:assert/strict"; import { mkdtemp, rm } from "node:fs/promises"; import os from "node:os"; import path from "node:path"; import { SchedulerStore, LocalScheduler, nextScheduledRun, nextWeekly, type ScheduledTask } from "../src/scheduler.js";
test("scheduler leases, deduplicates triggers, recovers missed runs and deduplicates notifications", async () => { const root = await mkdtemp(path.join(os.tmpdir(), "sztu-scheduler-")); try { let now = new Date("2026-09-06T10:00:00Z"); const store = new SchedulerStore(path.join(root, "tasks.json")); const task: ScheduledTask = { id: "weekly", name: "周报", prompt: "生成草稿", timezone: "Asia/Shanghai", day_of_week: 0, hour: 10, minute: 0, status: "active", missed_run_policy: "run_once", next_run_at: now.toISOString(), budget: 30, updated_at: now.toISOString() }; await store.upsert(task); let executions = 0; const notifications: string[] = []; const scheduler = new LocalScheduler(store, { execute: async () => { executions++; return "completed"; }, notify: async (_t, _r, key) => { notifications.push(key); } }, () => now, 60_000); await scheduler.tick(); await new Promise(r => setTimeout(r, 50)); await scheduler.tick(); assert.equal(executions, 1); assert.equal(notifications.length, 1); const saved = await store.get("weekly"); assert.equal(saved.last_result, "completed"); now = new Date(saved.next_run_at); await scheduler.tick(); await new Promise(r => setTimeout(r, 50)); assert.equal(executions, 2); assert.equal(nextWeekly(task, now).getUTCDay(), 0); } finally { await rm(root, { recursive: true, force: true }); } });

test("daily and monthly schedules honor the selected local timezone", () => {
  const daily = nextScheduledRun({ schedule_type: "daily", timezone: "Asia/Shanghai", day_of_week: 0, hour: 9, minute: 30 }, new Date("2026-09-08T00:00:00Z"));
  assert.equal(daily.toISOString(), "2026-09-08T01:30:00.000Z");
  const monthly = nextScheduledRun({ schedule_type: "monthly", timezone: "Asia/Shanghai", day_of_week: 0, day_of_month: 15, hour: 18, minute: 0 }, new Date("2026-09-16T00:00:00Z"));
  assert.equal(monthly.toISOString(), "2026-10-15T10:00:00.000Z");
});

test("manual runs execute immediately without waiting for the next schedule", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-scheduler-manual-"));
  try {
    const now = new Date("2026-09-08T08:00:00Z"); const store = new SchedulerStore(path.join(root, "tasks.json"));
    await store.upsert({ id: "manual", name: "手动验证", prompt: "检查状态", timezone: "Asia/Shanghai", schedule_type: "daily", day_of_week: 0, hour: 20, minute: 0, status: "active", missed_run_policy: "run_once", next_run_at: "2026-09-08T12:00:00.000Z", updated_at: now.toISOString() });
    let executions = 0; const scheduler = new LocalScheduler(store, { execute: async () => { executions += 1; return "completed"; }, notify: async () => undefined }, () => now);
    await scheduler.runNow("manual"); await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(executions, 1); assert.equal((await store.get("manual")).last_result, "completed");
  } finally { await rm(root, { recursive: true, force: true }); }
});

