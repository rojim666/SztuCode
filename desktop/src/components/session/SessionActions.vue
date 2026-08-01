<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Archive, Ellipsis, Pin, PinOff, RotateCcw, Shrink, XCircle } from "@lucide/vue";
import { archiveSession, closeSession, compactSession, pinSession, renameSession, resumeSession, type Session } from "../../services/sztu-runtime";

const props = defineProps<{ session: Session }>();
const emit = defineEmits<{ changed: []; closed: [] }>();
const open = ref(false);
const renaming = ref(false);
const title = ref(props.session.title);
const busy = ref(false);
const notice = ref("");
const trigger = ref<HTMLElement | null>(null);
const menu = ref<HTMLElement | null>(null);
const menuStyle = ref<Record<string, string>>({});

async function positionMenu() {
  await nextTick();
  if (!trigger.value || !menu.value) return;
  const anchor = trigger.value.getBoundingClientRect();
  const popup = menu.value.getBoundingClientRect();
  const left = Math.max(8, Math.min(anchor.right - popup.width, window.innerWidth - popup.width - 8));
  let top = anchor.bottom + 6;
  if (top + popup.height > window.innerHeight - 8) top = Math.max(8, anchor.top - popup.height - 6);
  menuStyle.value = { left: left + "px", top: top + "px" };
}

async function toggleMenu() {
  open.value = !open.value;
  if (open.value) await positionMenu();
}

function closeMenu() {
  open.value = false;
  renaming.value = false;
}

function handleOutside(event: PointerEvent) {
  const target = event.target as Node;
  if (!open.value || trigger.value?.contains(target) || menu.value?.contains(target)) return;
  closeMenu();
}

async function run(operation: () => Promise<unknown>, closes = false) {
  busy.value = true;
  notice.value = "";
  try {
    await operation();
    closeMenu();
    if (closes) emit("closed");
    else emit("changed");
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

async function saveTitle() {
  const next = title.value.trim();
  if (!next) return;
  await run(() => renameSession(props.session.session_id, next));
}

async function compact() {
  busy.value = true;
  try {
    const result = await compactSession(props.session.session_id);
    notice.value = "已压缩上下文，节省 " + result.saved_tokens + " tokens";
    emit("changed");
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

async function close() {
  if (!window.confirm("关闭后该会话将不能继续发送消息。确定关闭？")) return;
  await run(() => closeSession(props.session.session_id), true);
}

function closeOnViewportChange() { if (open.value) closeMenu(); }

watch(() => props.session.title, (value) => { if (!renaming.value) title.value = value; });
onMounted(() => {
  document.addEventListener("pointerdown", handleOutside);
  document.addEventListener("scroll", closeOnViewportChange, true);
  window.addEventListener("resize", closeOnViewportChange);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleOutside);
  document.removeEventListener("scroll", closeOnViewportChange, true);
  window.removeEventListener("resize", closeOnViewportChange);
});
</script>

<template>
  <div class="session-actions">
    <button ref="trigger" class="icon-button" title="会话操作" aria-label="会话操作" :aria-expanded="open" @click="toggleMenu"><Ellipsis :size="18" /></button>
    <Teleport to="body">
      <div v-if="open" ref="menu" class="session-menu session-menu--floating" :style="menuStyle">
        <form v-if="renaming" @submit.prevent="saveTitle"><input v-model="title" aria-label="会话名称" maxlength="120" autofocus /><button :disabled="busy">保存</button></form>
        <template v-else>
          <button @click="renaming = true"><span class="rename-mark">T</span>重命名</button>
          <button @click="run(() => pinSession(session.session_id, !session.pinned))"><PinOff v-if="session.pinned" :size="14" /><Pin v-else :size="14" />{{ session.pinned ? '取消置顶' : '置顶' }}</button>
          <button v-if="session.archived || session.status === 'closed'" @click="run(() => resumeSession(session.session_id))"><RotateCcw :size="14" />恢复</button>
          <button v-else @click="run(() => archiveSession(session.session_id), true)"><Archive :size="14" />归档</button>
          <button @click="compact"><Shrink :size="14" />压缩上下文</button>
          <button class="danger" @click="close"><XCircle :size="14" />关闭会话</button>
        </template>
        <p v-if="notice">{{ notice }}</p>
      </div>
    </Teleport>
  </div>
</template>