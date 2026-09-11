<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import { getWeChatStatus, type WeChatStatus } from "../../services/wechat-bridge";

const props = withDefaults(
  defineProps<{
    connected?: boolean;
    controlUiUrl?: string;
    panelOpen?: boolean;
  }>(),
  { connected: true, controlUiUrl: "http://127.0.0.1:18789/", panelOpen: false },
);

const emit = defineEmits<{ "open-panel": [] }>();

const { t } = useI18n({ useScope: "global" });

const status = ref<WeChatStatus>({ state: "disconnected", account: null, boundSessionId: null });

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

onMounted(async () => {
  status.value = await getWeChatStatus();
});
</script>

<template>
  <article class="wxc">
    <span class="wxc__badge"><AppIcon name="MessageCircle" :size="22" /></span>

    <div class="wxc__content">
      <header class="wxc__head">
        <h3 class="wxc__title">{{ t("app.wechatTitle") }}</h3>
        <span class="wxc__pill" :data-state="status.state">
          <i class="wxc__dot" />{{ stateLabel }}
        </span>
      </header>

      <p class="wxc__desc">{{ t("app.wechatDesc") }}</p>

      <p v-if="status.account" class="wxc__account">{{ status.account }}</p>

      <div class="wxc__actions">
        <button type="button" class="wxc__btn wxc__btn--primary" @click="emit('open-panel')">
          {{ props.panelOpen ? t("app.wechatClosePanel") : t("app.wechatOpenPanel") }}
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.wxc {
  display: flex;
  gap: 14px;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.22));
  background: linear-gradient(180deg, rgba(127, 127, 127, 0.06), transparent 70%),
    var(--surface, #ffffff);
  transition: border-color 0.18s ease, transform 0.18s ease;
}

.wxc:hover {
  border-color: rgba(7, 193, 96, 0.45);
}

.wxc__badge {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  color: #0a8f4d;
  background: rgba(7, 193, 96, 0.14);
  border: 1px solid rgba(7, 193, 96, 0.28);
}

.wxc__content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.wxc__head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.wxc__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.wxc__desc {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-muted, #8a8f98);
}

.wxc__account {
  margin: 0;
  font-size: 12px;
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text-muted, #8a8f98);
}

.wxc__pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-muted, #8a8f98);
  background: rgba(127, 127, 127, 0.14);
}

.wxc__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.wxc__pill[data-state="connected"] {
  color: #0a8f4d;
  background: rgba(7, 193, 96, 0.16);
}

.wxc__pill[data-state="pending"] {
  color: #b7791f;
  background: rgba(237, 137, 54, 0.16);
}

.wxc__pill[data-state="unavailable"] {
  color: #c05621;
  background: rgba(214, 108, 60, 0.14);
}

.wxc__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.wxc__btn {
  appearance: none;
  padding: 7px 14px;
  border-radius: 9px;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, opacity 0.16s ease;
}

.wxc__btn:focus-visible {
  outline: 2px solid rgba(7, 193, 96, 0.6);
  outline-offset: 2px;
}

.wxc__btn--primary {
  border: 1px solid rgba(7, 193, 96, 0.5);
  background: rgba(7, 193, 96, 0.16);
  color: #0a8f4d;
}

.wxc__btn--primary:hover {
  background: rgba(7, 193, 96, 0.26);
}
</style>
