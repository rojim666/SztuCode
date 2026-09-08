<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import {
  createScheduledTask, deleteScheduledTask, listScheduledTasks, pauseScheduledTask, runScheduledTask, updateScheduledTask,
  type ScheduledTask, type ScheduleType,
} from "../../services/sztu-runtime";

const props = defineProps<{ connected: boolean; workspaceId?: string | null }>();
const { t, locale } = useI18n({ useScope: "global" });
const tasks = ref<ScheduledTask[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const formOpen = ref(false);
const editingId = ref<string | null>(null);
const filter = ref<"all" | "active" | "paused">("all");
const name = ref("");
const prompt = ref("");
const scheduleType = ref<ScheduleType>("daily");
const time = ref("09:00");
const scheduleDay = ref(1);
const missedRunPolicy = ref<"run_once" | "skip">("run_once");
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const weekdays = computed(() => ["sun", "mon", "tue", "wed", "thu", "fri", "sat"].map((day) => t(`chat.weekday.${day}`)));
const visibleTasks = computed(() => tasks.value.filter((task) => filter.value === "all" || (filter.value === "active" ? task.status !== "paused" : task.status === "paused")));

function nextRun(type = scheduleType.value, clock = time.value, day = scheduleDay.value): Date {
  const [hour, minute] = clock.split(":").map(Number);
  const now = new Date();
  const next = new Date(now);
  next.setSeconds(0, 0);
  next.setHours(hour, minute, 0, 0);
  if (type === "daily" && next <= now) next.setDate(next.getDate() + 1);
  if (type === "weekly") {
    let offset = (day - now.getDay() + 7) % 7;
    if (!offset && next <= now) offset = 7;
    next.setDate(now.getDate() + offset);
  }
  if (type === "monthly") {
    next.setDate(Math.min(day, new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate()));
    if (next <= now) {
      next.setMonth(next.getMonth() + 1, 1);
      next.setDate(Math.min(day, new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate()));
    }
  }
  return next;
}

function formatDate(value?: string | Date) {
  if (!value) return t("chat.notRunYet");
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return t("chat.notRunYet");
  return new Intl.DateTimeFormat(locale.value, { month: "short", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

function summary(type: ScheduleType, clock: string, day: number) {
  if (type === "daily") return t("chat.scheduleSummaryDaily", { time: clock });
  if (type === "weekly") return t("chat.scheduleSummaryWeekly", { weekday: weekdays.value[day], time: clock });
  return t("chat.scheduleSummaryMonthly", { day, time: clock });
}

function taskSchedule(task: ScheduledTask) {
  return summary(task.schedule_type ?? "weekly", `${String(task.hour).padStart(2, "0")}:${String(task.minute).padStart(2, "0")}`, task.schedule_type === "monthly" ? task.day_of_month ?? 1 : task.day_of_week);
}

async function load() {
  if (!props.connected) { tasks.value = []; error.value = t("chat.notConnected"); return; }
  loading.value = true; error.value = "";
  try { tasks.value = (await listScheduledTasks()).sort((a, b) => new Date(a.next_run_at).getTime() - new Date(b.next_run_at).getTime()); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; }
}

function resetForm() {
  formOpen.value = false; editingId.value = null; name.value = ""; prompt.value = "";
  scheduleType.value = "daily"; time.value = "09:00"; scheduleDay.value = 1; missedRunPolicy.value = "run_once";
}

function openForm(task?: ScheduledTask) {
  editingId.value = task?.id ?? null;
  name.value = task?.name ?? ""; prompt.value = task?.prompt ?? "";
  scheduleType.value = task?.schedule_type ?? "daily";
  time.value = task ? `${String(task.hour).padStart(2, "0")}:${String(task.minute).padStart(2, "0")}` : "09:00";
  scheduleDay.value = task ? (scheduleType.value === "monthly" ? task.day_of_month ?? 1 : task.day_of_week) : 1;
  missedRunPolicy.value = task?.missed_run_policy ?? "run_once";
  formOpen.value = true; notice.value = ""; error.value = "";
}

async function save() {
  if (!name.value.trim() || !prompt.value.trim() || !props.connected) return;
  saving.value = true; error.value = "";
  const [hour, minute] = time.value.split(":").map(Number);
  const existing = tasks.value.find((task) => task.id === editingId.value);
  const payload = {
    ...(existing ?? {}), name: name.value.trim(), prompt: prompt.value.trim(), timezone,
    schedule_type: scheduleType.value, day_of_week: scheduleType.value === "weekly" ? scheduleDay.value : 0,
    day_of_month: scheduleType.value === "monthly" ? scheduleDay.value : undefined,
    hour, minute, status: existing?.status ?? "active" as const, missed_run_policy: missedRunPolicy.value,
    workspace_id: props.workspaceId ?? undefined, budget: existing?.budget ?? 300,
    next_run_at: nextRun().toISOString(),
  };
  try {
    if (existing) await updateScheduledTask({ ...existing, ...payload }); else await createScheduledTask(payload);
    notice.value = t(existing ? "chat.taskUpdated" : "chat.taskCreated"); resetForm(); await load();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { saving.value = false; }
}

async function toggle(task: ScheduledTask) {
  error.value = "";
  try {
    if (task.status === "paused") {
      const next = new Date(task.next_run_at) <= new Date() ? nextRun(task.schedule_type ?? "weekly", `${String(task.hour).padStart(2, "0")}:${String(task.minute).padStart(2, "0")}`, task.schedule_type === "monthly" ? task.day_of_month ?? 1 : task.day_of_week).toISOString() : task.next_run_at;
      await updateScheduledTask({ ...task, status: "active", next_run_at: next });
    } else await pauseScheduledTask(task.id);
    await load();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
}

async function remove(task: ScheduledTask) {
  if (!window.confirm(t("chat.deleteTaskConfirm", { name: task.name }))) return;
  try { await deleteScheduledTask(task.id); await load(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
}

async function runNow(task: ScheduledTask) {
  if (!props.connected) { error.value = t("chat.notConnected"); return; }
  error.value = "";
  try { await runScheduledTask(task.id); notice.value = t("chat.taskSubmitted", { name: task.name }); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
}

function statusLabel(task: ScheduledTask) {
  if (task.status === "paused") return t("chat.statusPaused");
  if (task.status === "waiting_authorization") return t("chat.statusWaitingAuthorization");
  if (task.status === "failed" || task.last_result === "failed") return t("chat.statusFailed");
  return t("chat.statusRunning");
}

onMounted(load);
watch(() => props.connected, load);
</script>

<template>
  <section class="chat-automations" aria-labelledby="automation-title">
    <header class="automation-header">
      <div><span class="automation-kicker">LOCAL SCHEDULES</span><h1 id="automation-title">{{ t("chat.automationsTitle") }}</h1><p>{{ t("chat.automationsDesc") }}</p></div>
      <div class="automation-header-actions">
        <button type="button" class="automation-icon-button" :aria-label="t('app.refresh')" :disabled="loading" @click="load"><AppIcon name="RefreshCw" :size="16" :class="{ spin: loading }" /></button>
        <button type="button" class="automation-primary" @click="formOpen ? resetForm() : openForm()"><AppIcon :name="formOpen ? 'X' : 'Plus'" :size="16" />{{ formOpen ? t("chat.cancel") : t("chat.newTask") }}</button>
      </div>
    </header>

    <p v-if="notice" class="automation-notice" role="status"><AppIcon name="CheckCircle2" :size="15" />{{ notice }}</p>
    <p v-if="error" class="automation-error" role="alert"><AppIcon name="AlertCircle" :size="15" />{{ error }}</p>

    <form v-if="formOpen" class="automation-form" @submit.prevent="save">
      <div class="automation-form-title"><span>{{ editingId ? "EDIT" : "NEW" }}</span><div><h2>{{ t(editingId ? "chat.editAutomation" : "chat.createAutomation") }}</h2><p>{{ t("chat.automationFormHint") }}</p></div></div>
      <div class="automation-form-grid">
        <section><h3>{{ t("chat.taskSection") }}</h3><label>{{ t("chat.nameLabel") }}<input v-model="name" required autofocus :placeholder="t('chat.namePlaceholder')" /></label><label>{{ t("chat.contentLabel") }}<textarea v-model="prompt" required rows="6" :placeholder="t('chat.contentPlaceholder')" /></label></section>
        <section><h3>{{ t("chat.scheduleSection") }}</h3><nav class="automation-schedule-tabs" aria-label="执行频率"><button v-for="item in ([['daily','scheduleDaily'],['weekly','scheduleWeekly'],['monthly','scheduleMonthly']] as const)" :key="item[0]" type="button" :class="{ active: scheduleType === item[0] }" @click="scheduleType = item[0]; scheduleDay = 1">{{ t(`chat.${item[1]}`) }}</button></nav><div class="automation-fields"><label v-if="scheduleType === 'weekly'">{{ t("chat.weekdayLabel") }}<select v-model.number="scheduleDay"><option v-for="(day, index) in weekdays" :key="day" :value="index">{{ day }}</option></select></label><label v-else-if="scheduleType === 'monthly'">{{ t("chat.dateLabel") }}<select v-model.number="scheduleDay"><option v-for="day in 28" :key="day" :value="day">{{ t("chat.dayOfMonth", { day }) }}</option></select></label><label>{{ t("chat.timeLabel") }}<input v-model="time" type="time" required /></label></div><label class="automation-policy"><input v-model="missedRunPolicy" type="checkbox" true-value="run_once" false-value="skip" /><span><b>{{ t("chat.catchUpMissed") }}</b><small>{{ t("chat.catchUpMissedHint") }}</small></span></label><div class="automation-next"><span>{{ t("chat.nextRunLabel") }}</span><b>{{ formatDate(nextRun()) }}</b><small>{{ summary(scheduleType, time, scheduleDay) }} · {{ timezone }}</small></div></section>
      </div>
      <footer><button type="button" @click="resetForm">{{ t("chat.cancel") }}</button><button type="submit" class="automation-primary" :disabled="saving || !name.trim() || !prompt.trim()"><AppIcon name="Check" :size="15" />{{ t(editingId ? "chat.saveChanges" : "chat.createTask") }}</button></footer>
    </form>

    <template v-else>
      <div class="automation-toolbar"><span>{{ t("chat.taskCount", { n: tasks.length }) }}</span><nav><button v-for="item in ([['all','filterAll'],['active','filterRunning'],['paused','filterPaused']] as const)" :key="item[0]" :class="{ active: filter === item[0] }" @click="filter = item[0]">{{ t(`chat.${item[1]}`) }}</button></nav></div>
      <div v-if="visibleTasks.length" class="automation-list">
        <article v-for="task in visibleTasks" :key="task.id" class="automation-card" :class="task.status">
          <div class="automation-card-top"><span class="automation-status"><i />{{ statusLabel(task) }}</span><div><button :title="t('chat.runNow')" :disabled="task.status === 'paused'" @click="runNow(task)"><AppIcon name="Play" :size="14" /></button><button :title="t('chat.edit')" @click="openForm(task)"><AppIcon name="Pencil" :size="14" /></button><button :title="t('chat.remove')" @click="remove(task)"><AppIcon name="Trash2" :size="14" /></button></div></div>
          <h2>{{ task.name }}</h2><p>{{ task.prompt }}</p>
          <dl><div><dt>{{ t("chat.frequencyLabel") }}</dt><dd>{{ taskSchedule(task) }}</dd></div><div><dt>{{ t("chat.lastRunLabel") }}</dt><dd>{{ formatDate(task.last_run_at) }}</dd></div><div><dt>{{ t("chat.nextRunTimeLabel") }}</dt><dd>{{ formatDate(task.next_run_at) }}</dd></div></dl>
          <footer><span>{{ task.timezone }}</span><button @click="toggle(task)"><AppIcon :name="task.status === 'paused' ? 'Play' : 'Pause'" :size="13" />{{ t(task.status === "paused" ? "chat.resumeTask" : "chat.pauseTask") }}</button></footer>
        </article>
      </div>
      <div v-else class="automation-empty"><span><AppIcon name="CalendarClock" :size="28" /></span><h2>{{ t(tasks.length ? "chat.noMatchTasks" : "chat.noTasks") }}</h2><p>{{ t(tasks.length ? "chat.noMatchHint" : "chat.noTasksHint") }}</p><button v-if="!tasks.length" class="automation-primary" @click="openForm()"><AppIcon name="Plus" :size="15" />{{ t("chat.createTask") }}</button></div>
    </template>
  </section>
</template>

<style scoped>
.chat-automations{height:100%;overflow:auto;padding:42px clamp(24px,5vw,72px) 64px;color:var(--text);background:var(--surface)}
.automation-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;max-width:1120px;margin:0 auto 28px}.automation-header h1{margin:5px 0 6px;font-size:32px;letter-spacing:-.04em}.automation-header p{margin:0;color:var(--text-muted)}.automation-kicker{font:700 10px/1.2 ui-monospace,monospace;letter-spacing:.16em;color:#26845e}.automation-header-actions{display:flex;gap:9px}.automation-primary,.automation-icon-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:0;border-radius:9px;cursor:pointer}.automation-primary{min-height:38px;padding:0 15px;color:#fff;background:#202825;font-weight:650}.automation-primary:hover{background:#101613}.automation-primary:disabled{opacity:.45;cursor:not-allowed}.automation-icon-button{width:38px;height:38px;color:var(--text);background:var(--surface-soft)}
.automation-notice,.automation-error{display:flex;align-items:center;gap:8px;max-width:1120px;margin:0 auto 14px;padding:10px 13px;border-radius:9px;font-size:13px}.automation-notice{color:#237454;background:#edf8f2}.automation-error{color:#a94343;background:#fff0ef}.automation-form{max-width:1120px;margin:0 auto;padding:24px;border:1px solid var(--border);border-radius:16px;background:var(--surface-elevated);box-shadow:0 16px 48px rgb(20 30 25/7%)}.automation-form-title{display:flex;gap:14px;align-items:flex-start;padding-bottom:18px;border-bottom:1px solid var(--border)}.automation-form-title>span{padding:5px 7px;border-radius:5px;color:#237454;background:#e9f6ef;font:700 10px/1 ui-monospace,monospace;letter-spacing:.12em}.automation-form h2,.automation-form h3,.automation-form p{margin:0}.automation-form-title h2{font-size:19px}.automation-form-title p{margin-top:4px;color:var(--text-muted);font-size:13px}.automation-form-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.8fr);gap:36px;padding:24px 0}.automation-form section{display:grid;align-content:start;gap:15px}.automation-form h3{font-size:12px;letter-spacing:.08em;text-transform:uppercase}.automation-form label{display:grid;gap:7px;color:var(--text-muted);font-size:12px;font-weight:600}.automation-form input,.automation-form textarea,.automation-form select{width:100%;box-sizing:border-box;padding:10px 12px;color:var(--text);background:var(--surface);border:1px solid var(--border);border-radius:9px;font:inherit;outline:none}.automation-form textarea{resize:vertical;line-height:1.55}.automation-form input:focus,.automation-form textarea:focus,.automation-form select:focus{border-color:#5fa989;box-shadow:0 0 0 3px rgb(72 158 119/12%)}.automation-schedule-tabs{display:grid;grid-template-columns:repeat(3,1fr);padding:3px;border-radius:9px;background:var(--surface-soft)}.automation-schedule-tabs button,.automation-toolbar button{border:0;cursor:pointer;color:var(--text-muted);background:transparent;border-radius:7px}.automation-schedule-tabs button{padding:8px}.automation-schedule-tabs button.active{color:var(--text);background:var(--surface);box-shadow:0 1px 5px rgb(20 30 25/8%)}.automation-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.automation-policy{grid-template-columns:auto 1fr!important;align-items:flex-start}.automation-policy input{width:16px;height:16px;margin:2px 0}.automation-policy span{display:grid;gap:2px}.automation-policy small{font-weight:400}.automation-next{display:grid;gap:4px;padding:14px;border-radius:11px;background:#eef7f2}.automation-next span,.automation-next small{color:#668074;font-size:11px}.automation-next b{color:#245d47;font-size:16px}.automation-form>footer{display:flex;justify-content:flex-end;gap:9px;padding-top:18px;border-top:1px solid var(--border)}.automation-form>footer>button:not(.automation-primary){padding:0 14px;border:0;color:var(--text-muted);background:transparent;cursor:pointer}
.automation-toolbar{display:flex;align-items:center;justify-content:space-between;max-width:1120px;margin:0 auto 14px}.automation-toolbar>span{color:var(--text-muted);font-size:12px}.automation-toolbar nav{display:flex;gap:3px;padding:3px;background:var(--surface-soft);border-radius:9px}.automation-toolbar button{padding:7px 12px}.automation-toolbar button.active{color:var(--text);background:var(--surface)}.automation-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:13px;max-width:1120px;margin:0 auto}.automation-card{display:grid;gap:13px;min-width:0;padding:18px;border:1px solid var(--border);border-radius:14px;background:var(--surface-elevated);transition:transform .18s ease,box-shadow .18s ease}.automation-card:hover{transform:translateY(-2px);box-shadow:0 12px 30px rgb(20 30 25/7%)}.automation-card-top,.automation-card-top>div,.automation-card footer{display:flex;align-items:center;justify-content:space-between;gap:6px}.automation-status{display:inline-flex;align-items:center;gap:7px;color:#277454;font-size:11px;font-weight:650}.automation-status i{width:7px;height:7px;border-radius:50%;background:#43a77d;box-shadow:0 0 0 4px rgb(67 167 125/12%)}.automation-card.paused .automation-status{color:var(--text-muted)}.automation-card.paused .automation-status i{background:#9aa19d;box-shadow:none}.automation-card.failed .automation-status,.automation-card.waiting_authorization .automation-status{color:#b06932}.automation-card.failed .automation-status i,.automation-card.waiting_authorization .automation-status i{background:#d68b45}.automation-card-top button{display:grid;width:29px;height:29px;place-items:center;border:0;border-radius:7px;color:var(--text-muted);background:transparent;cursor:pointer}.automation-card-top button:hover{color:var(--text);background:var(--surface-soft)}.automation-card-top button:disabled{opacity:.35;cursor:not-allowed}.automation-card h2{margin:0;font-size:17px}.automation-card>p{display:-webkit-box;overflow:hidden;margin:0;color:var(--text-muted);font-size:13px;line-height:1.55;-webkit-line-clamp:3;-webkit-box-orient:vertical}.automation-card dl{display:grid;gap:8px;margin:0;padding:12px 0;border-block:1px solid var(--border)}.automation-card dl div{display:flex;justify-content:space-between;gap:18px;font-size:12px}.automation-card dt{color:var(--text-muted)}.automation-card dd{margin:0;text-align:right}.automation-card footer>span{overflow:hidden;color:var(--text-muted);font-size:10px;text-overflow:ellipsis}.automation-card footer button{display:inline-flex;align-items:center;gap:6px;padding:7px 9px;border:0;border-radius:7px;color:var(--text);background:var(--surface-soft);cursor:pointer}.automation-empty{display:grid;justify-items:center;max-width:520px;margin:90px auto 0;text-align:center}.automation-empty>span{display:grid;width:58px;height:58px;place-items:center;border-radius:18px;color:#348463;background:#eaf6f0}.automation-empty h2{margin:18px 0 7px}.automation-empty p{margin:0 0 20px;color:var(--text-muted)}
@media(max-width:760px){.chat-automations{padding:28px 18px 48px}.automation-header{align-items:flex-start}.automation-header-actions{flex-shrink:0}.automation-form-grid{grid-template-columns:1fr}.automation-list{grid-template-columns:1fr}}
:global([data-app-theme="dark"]) .automation-next,:global([data-app-theme="dark"]) .automation-empty>span,:global([data-app-theme="dark"]) .automation-form-title>span{background:#20382e;color:#88c9aa}:global([data-app-theme="dark"]) .automation-next b{color:#9ed7bb}:global([data-app-theme="dark"]) .automation-primary{color:#17231e;background:#8fcfb0}
</style>
