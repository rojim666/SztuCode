<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import {
  bindWeChatSession,
  cancelWeChatLogin,
  getWeChatStatus,
  startWeChatLogin,
  unbindWeChatSession,
  type WeChatLoginTicket,
  type WeChatStatus,
} from "../../services/wechat-bridge";

interface BridgeSession {
  session_id: string;
  title?: string | null;
  projectName?: string | null;
}

const props = withDefaults(
  defineProps<{
    sessions: readonly BridgeSession[];
    connected?: boolean;
    controlUiUrl?: string;
  }>(),
  { connected: true, controlUiUrl: "http://127.0.0.1:18789/" },
);

const emit = defineEmits<{ close: [] }>();

const { t } = useI18n({ useScope: "global" });

const status = ref<WeChatStatus>({ state: "disconnected", account: null, boundSessionId: null, lastError: null });
const ticket = ref<WeChatLoginTicket | null>(null);
const selectedSessionId = ref("");
const busy = ref(false);
const actionError = ref("");
const pickerOpen = ref(false);
const expandedProjectNames = ref<Set<string>>(new Set());
const groupsInitialized = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const isUnavailable = computed(() => status.value.state === "unavailable");
const isConnected = computed(() => status.value.state === "connected");
const isBound = computed(() => Boolean(status.value.boundSessionId));
const qrIsImage = computed(() => {
  const qr = ticket.value?.qr ?? "";
  return /^data:/.test(qr) || (/^https?:/.test(qr) && qr !== ticket.value?.link);
});
const boundTitle = computed(() => {
  const found = props.sessions.find((item) => item.session_id === status.value.boundSessionId);
  return sessionLabel(found) || status.value.boundSessionId || "";
});
function sessionLabel(item?: BridgeSession): string {
  if (!item) return "";
  const title = item.title?.trim() || item.session_id;
  return item.projectName?.trim() ? `${item.projectName.trim()} / ${title}` : title;
}

const sessionGroups = computed(() => {
  const groups = new Map<string, { name: string; sessions: BridgeSession[] }>();
  for (const session of props.sessions) {
    const name = session.projectName?.trim() || t("app.wechatTemporarySessions");
    const group = groups.get(name) ?? { name, sessions: [] };
    group.sessions.push(session);
    groups.set(name, group);
  }
  return [...groups.values()];
});

const selectedSession = computed(() => props.sessions.find((item) => item.session_id === selectedSessionId.value));
const selectedSessionText = computed(() =>
  selectedSession.value ? sessionLabel(selectedSession.value) : t("app.wechatSelectSession"),
);

watch(
  sessionGroups,
  (groups) => {
    if (groupsInitialized.value || groups.length === 0) return;
    expandedProjectNames.value = new Set(groups.map((group) => group.name));
    groupsInitialized.value = true;
  },
  { immediate: true },
);

function toggleProjectGroup(name: string): void {
  const next = new Set(expandedProjectNames.value);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  expandedProjectNames.value = next;
}

function chooseSession(sessionId: string): void {
  selectedSessionId.value = sessionId;
  pickerOpen.value = false;
}

function closePickerOnEscape(event: KeyboardEvent): void {
  if (event.key === "Escape") pickerOpen.value = false;
}

function closePickerOnOutside(event: PointerEvent): void {
  const target = event.target as HTMLElement | null;
  if (!target?.closest(".wp__session-picker")) pickerOpen.value = false;
}

const stateLabel = computed(() => {
  switch (status.value.state) {
    case "connected":
      return t("app.wechatStateConnected");
    case "pending":
      return t("app.wechatStatePending");
    case "unavailable":
      return t("app.wechatUnavailableShort");
    default:
      return t("app.wechatStateDisconnected");
  }
});

const bindingLabel = computed(() =>
  isBound.value ? t("app.wechatBindingStateBound") : t("app.wechatBindingStateUnbound"),
);

async function refresh(): Promise<void> {
  status.value = await getWeChatStatus();
  if (status.value.boundSessionId) selectedSessionId.value = status.value.boundSessionId;
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// 发起扫码登录；二维码出现后轮询状态，连接成功即停止
async function connect(): Promise<void> {
  busy.value = true;
  actionError.value = "";
  try {
    const started = await startWeChatLogin();
    if (!started) {
      ticket.value = null;
      await refresh();
      return;
    }
    ticket.value = started;
    stopPolling();
    pollTimer = setInterval(() => {
      void (async () => {
        await refresh();
        if (isConnected.value) {
          stopPolling();
          ticket.value = null;
        } else if (status.value.state !== "pending") {
          stopPolling();
          ticket.value = null;
        }
      })();
    }, 2000);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
    await refresh();
  } finally {
    busy.value = false;
  }
}

async function disconnect(): Promise<void> {
  busy.value = true;
  actionError.value = "";
  try {
    if (!(await cancelWeChatLogin())) actionError.value = t("app.actionFailed");
    stopPolling();
    ticket.value = null;
    await refresh();
  } finally {
    busy.value = false;
  }
}

// 把微信消息落到选定的既有会话
async function bind(): Promise<void> {
  if (!selectedSessionId.value) return;
  busy.value = true;
  actionError.value = "";
  try {
    if (!(await bindWeChatSession(selectedSessionId.value))) {
      actionError.value = t("app.actionFailed");
      return;
    }
    await refresh();
  } finally {
    busy.value = false;
  }
}

async function unbind(): Promise<void> {
  busy.value = true;
  actionError.value = "";
  try {
    if (!(await unbindWeChatSession())) {
      actionError.value = t("app.actionFailed");
      return;
    }
    await refresh();
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  void refresh();
  document.addEventListener("pointerdown", closePickerOnOutside);
  document.addEventListener("keydown", closePickerOnEscape);
});
onBeforeUnmount(() => {
  stopPolling();
  document.removeEventListener("pointerdown", closePickerOnOutside);
  document.removeEventListener("keydown", closePickerOnEscape);
});
</script>

<template>
  <div class="wp-backdrop" role="presentation" @mousedown.self="emit('close')">
    <section class="wp" role="dialog" aria-modal="true" :aria-label="t('app.wechatPanelTitle')">
      <header class="wp__head">
        <span class="wp__badge"><AppIcon name="MessageCircle" :size="20" /></span>
        <div class="wp__heading">
          <h2>{{ t("app.wechatPanelTitle") }}</h2>
          <span class="wp__pill" :data-state="status.state">
            <i class="wp__dot" />{{ stateLabel }}
          </span>
          <span class="wp__pill wp__pill--binding" :data-bound="isBound">
            <i class="wp__dot" />{{ bindingLabel }}
          </span>
        </div>
        <button type="button" class="wp__close" :aria-label="t('app.wechatClose')" @click="emit('close')">
          <AppIcon name="X" :size="18" />
        </button>
      </header>

      <div class="wp__body">
        <section class="wp__card">
          <header class="wp__card-head">
            <h3>{{ t("app.connectionStatus") }}</h3>
            <span v-if="status.account" class="wp__mono">{{ status.account }}</span>
          </header>
          <p v-if="isUnavailable" class="wp__hint">{{ t("app.wechatUnavailableHint") }}</p>
          <p v-if="status.lastError || actionError" class="wp__error">{{ actionError || status.lastError }}</p>
          <template v-if="!isUnavailable">
            <div class="wp__actions">
              <button
                v-if="!isConnected"
                type="button"
                class="wp__btn wp__btn--primary"
                :disabled="busy"
                @click="connect"
              >
                {{ busy ? t("app.wechatConnecting") : t("app.wechatConnect") }}
              </button>
              <button v-else type="button" class="wp__btn" :disabled="busy" @click="disconnect">
                {{ t("app.wechatDisconnect") }}
              </button>
            </div>
          </template>
        </section>

        <section v-if="ticket" class="wp__card wp__card--center">
          <div class="wp__qr">
            <img v-if="qrIsImage" :src="ticket.qr" :alt="t('app.wechatScanHint')" />
            <pre v-else>{{ ticket.qr }}</pre>
          </div>
          <p class="wp__hint">{{ t("app.wechatScanHint") }}</p>
          <div v-if="ticket.link" class="wp__qr-link">
            <a :href="ticket.link" target="_blank" rel="noreferrer">{{ ticket.link }}</a>
          </div>
        </section>

        <section class="wp__card">
          <header class="wp__card-head">
            <h3>{{ t("app.wechatBindSession") }}</h3>
          </header>
          <div class="wp__session-picker" :class="{ 'is-open': pickerOpen }">
            <button
              type="button"
              class="wp__session-trigger"
              :disabled="busy || !props.connected"
              :aria-expanded="pickerOpen"
              aria-haspopup="listbox"
              @click.stop="pickerOpen = !pickerOpen"
            >
              <span :class="{ muted: !selectedSession }">{{ selectedSessionText }}</span>
              <AppIcon name="ChevronDown" :size="15" />
            </button>
            <div v-if="pickerOpen" class="wp__session-menu" role="listbox" :aria-label="t('app.wechatSelectSession')">
              <div v-if="!sessionGroups.length" class="wp__session-empty">{{ t("app.noSessions") }}</div>
              <section v-for="group in sessionGroups" :key="group.name" class="wp__session-group">
                <button
                  type="button"
                  class="wp__session-group-head"
                  :aria-expanded="expandedProjectNames.has(group.name)"
                  @click="toggleProjectGroup(group.name)"
                >
                  <AppIcon name="ChevronRight" :size="14" :class="{ rotated: expandedProjectNames.has(group.name) }" />
                  <AppIcon :name="group.name === t('app.wechatTemporarySessions') ? 'MessageCircle' : 'Folder'" :size="15" />
                  <span>{{ group.name }}</span>
                  <small>{{ group.sessions.length }}</small>
                </button>
                <div v-if="expandedProjectNames.has(group.name)" class="wp__session-children">
                  <button
                    v-for="item in group.sessions"
                    :key="item.session_id"
                    type="button"
                    role="option"
                    class="wp__session-option"
                    :class="{ selected: selectedSessionId === item.session_id }"
                    :aria-selected="selectedSessionId === item.session_id"
                    @click="chooseSession(item.session_id)"
                  >
                    <span>{{ item.title?.trim() || item.session_id }}</span>
                    <AppIcon v-if="selectedSessionId === item.session_id" name="Check" :size="15" />
                  </button>
                </div>
              </section>
            </div>
          </div>
          <div class="wp__actions">
            <button type="button" class="wp__btn" :disabled="busy || !selectedSessionId" @click="bind">
              {{ t("app.wechatBind") }}
            </button>
            <button
              type="button"
              class="wp__btn wp__btn--ghost"
              :disabled="busy || !status.boundSessionId"
              @click="unbind"
            >
              {{ t("app.wechatUnbind") }}
            </button>
          </div>
          <p v-if="status.boundSessionId" class="wp__bound">
            <AppIcon name="Check" :size="14" />
            {{ t("app.wechatBindingActive", { session: boundTitle }) }}
          </p>
        </section>

        <p class="wp__fallback">{{ t("app.wechatFallbackHint", { url: props.controlUiUrl }) }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.wp-backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(6px);
  animation: wp-fade 0.16s ease;
}

.wp {
  width: min(520px, 100%);
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow: hidden;
  background: var(--surface, #ffffff);
  border: 1px solid var(--border, rgba(127, 127, 127, 0.24));
  box-shadow: 0 28px 72px rgba(0, 0, 0, 0.5);
  animation: wp-rise 0.18s ease;
}

.wp__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border, rgba(127, 127, 127, 0.2));
  background: linear-gradient(180deg, rgba(7, 193, 96, 0.08), transparent);
}

.wp__badge {
  flex: none;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  color: #0a8f4d;
  background: rgba(7, 193, 96, 0.14);
  border: 1px solid rgba(7, 193, 96, 0.28);
}

.wp__heading {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.wp__heading h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.wp__close {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--text-muted, #8a8f98);
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.wp__close:hover {
  background: rgba(127, 127, 127, 0.16);
  color: inherit;
}

.wp__pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-muted, #8a8f98);
  background: rgba(127, 127, 127, 0.14);
}

.wp__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.wp__pill[data-state="connected"] {
  color: #0a8f4d;
  background: rgba(7, 193, 96, 0.16);
}

.wp__pill[data-state="pending"] {
  color: #b7791f;
  background: rgba(237, 137, 54, 0.16);
}

.wp__pill[data-state="unavailable"] {
  color: #c05621;
  background: rgba(214, 108, 60, 0.14);
}

.wp__pill--binding[data-bound="true"] {
  color: #087a43;
  background: rgba(7, 193, 96, 0.12);
}

.wp__pill--binding[data-bound="false"] {
  color: var(--text-muted, #8a8f98);
}

.wp__body {
  min-width: 0;
  min-height: 0;
  padding: 16px 18px 18px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wp__card {
  box-sizing: border-box;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.2));
  background: rgba(127, 127, 127, 0.05);
}

.wp__card--center {
  align-items: center;
}

.wp__card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.wp__card-head h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-muted, #8a8f98);
  text-transform: uppercase;
}

.wp__mono {
  font-size: 12px;
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text-muted, #8a8f98);
}

.wp__hint {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted, #8a8f98);
}

.wp__error {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  color: #b42318;
  background: rgba(214, 69, 69, 0.1);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.wp__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.wp__btn {
  appearance: none;
  padding: 7px 14px;
  border-radius: 9px;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.3));
  background: rgba(127, 127, 127, 0.1);
  color: inherit;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, opacity 0.16s ease;
}

.wp__btn:hover:not(:disabled) {
  background: rgba(127, 127, 127, 0.2);
}

.wp__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wp__btn:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.6);
  outline-offset: 2px;
}

.wp__btn--primary {
  border-color: rgba(7, 193, 96, 0.5);
  background: rgba(7, 193, 96, 0.16);
  color: #0a8f4d;
}

.wp__btn--primary:hover:not(:disabled) {
  background: rgba(7, 193, 96, 0.26);
}

.wp__btn--ghost {
  background: transparent;
}

.wp__session-picker {
  min-width: 0;
}

.wp__session-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 9px;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.3));
  background: var(--surface, #ffffff);
  color: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.wp__session-trigger:hover:not(:disabled),
.wp__session-picker.is-open .wp__session-trigger {
  border-color: rgba(7, 193, 96, 0.55);
  box-shadow: 0 0 0 3px rgba(7, 193, 96, 0.1);
}

.wp__session-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.wp__session-trigger span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wp__session-trigger .muted {
  color: var(--text-muted, #8a8f98);
}

.wp__session-menu {
  box-sizing: border-box;
  width: 100%;
  margin-top: 6px;
  padding: 5px;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.3));
  border-radius: 10px;
  background: var(--surface, #ffffff);
  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.22);
}

.wp__session-group + .wp__session-group {
  margin-top: 3px;
  padding-top: 3px;
  border-top: 1px solid var(--border, rgba(127, 127, 127, 0.15));
}

.wp__session-group-head,
.wp__session-option {
  display: flex;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
  gap: 8px;
  border: 0;
  color: inherit;
  background: transparent;
  text-align: left;
  justify-content: flex-start !important;
  text-align: left !important;
  cursor: pointer;
}

.wp__session-group-head {
  min-height: 34px;
  padding: 6px 8px;
  color: var(--text, #3f4549);
  font-size: 12px;
  font-weight: 650;
  border-radius: 7px;
}

.wp__session-group-head svg:first-child {
  flex: none;
  transition: transform 0.16s ease;
}

.wp__session-group-head svg:nth-child(2) {
  flex: none;
  color: var(--text-muted, #7b8389);
}

.wp__session-group-head svg.rotated {
  transform: rotate(90deg);
}

.wp__session-group-head span {
  min-width: 0;
  flex: 1;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wp__session-group-head small {
  margin-left: auto;
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(127, 127, 127, 0.12);
  text-align: center;
  font-size: 10px;
  font-weight: 600;
}

.wp__session-group-head:hover,
.wp__session-option:hover {
  background: rgba(7, 193, 96, 0.08);
}

.wp__session-children {
  position: relative;
  margin: 1px 0 5px 16px;
  padding: 1px 0 2px 15px;
  border-left: 1px solid rgba(127, 127, 127, 0.2);
}

.wp__session-option {
  min-height: 32px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.35;
}

.wp__session-option span {
  min-width: 0;
  flex: 1;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wp__session-option svg {
  flex: none;
}

.wp__session-option.selected {
  color: #087a43;
  background: rgba(7, 193, 96, 0.12);
}

.wp__session-empty {
  padding: 14px 10px;
  color: var(--text-muted, #8a8f98);
  font-size: 12px;
  text-align: center;
}

.wp__qr {
  display: grid;
  place-items: center;
  padding: 12px;
  border-radius: 12px;
  background: rgba(127, 127, 127, 0.1);
  border: 1px dashed rgba(127, 127, 127, 0.35);
}

.wp__qr img {
  width: 208px;
  height: 208px;
  image-rendering: pixelated;
  border-radius: 8px;
  background: #fff;
}

.wp__qr pre {
  margin: 0;
  max-width: 100%;
  overflow: auto;
  font-size: 11px;
  line-height: 1.05;
}

.wp__qr-link {
  width: 100%;
  font-size: 11.5px;
  line-height: 1.4;
  word-break: break-all;
  text-align: center;
}

.wp__qr-link a {
  color: #0a8f4d;
  text-decoration: underline;
}

.wp__bound {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  color: #0a8f4d;
}

.wp__fallback {
  margin: 0;
  padding-top: 4px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-muted, #8a8f98);
  word-break: break-all;
}

@keyframes wp-fade {
  from {
    opacity: 0;
  }
}

@keyframes wp-rise {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.99);
  }
}

@media (max-width: 480px) {
  .wp-backdrop {
    padding: 10px;
  }

  .wp__head {
    gap: 9px;
    padding: 13px 14px;
  }

  .wp__body {
    padding: 12px 14px 14px;
  }

  .wp__card {
    padding: 12px;
  }

  .wp__pill--binding {
    flex-basis: 100%;
    width: fit-content;
  }
}
</style>
