<script setup lang="ts">
import { ref } from "vue";
import { Archive, Ellipsis, Pin, PinOff, RotateCcw, Shrink, XCircle } from "@lucide/vue";
import { archiveSession, closeSession, compactSession, pinSession, renameSession, resumeSession, type Session } from "../../services/sztu-runtime";
const props = defineProps<{ session: Session }>();
const emit = defineEmits<{ changed: []; closed: [] }>();
const open = ref(false);
const renaming = ref(false);
const title = ref(props.session.title);
const busy = ref(false);
const notice = ref("");
async function run(operation: () => Promise<unknown>, closes = false) {
  busy.value = true; notice.value = "";
  try { await operation(); open.value = false; if (closes) emit("closed"); else emit("changed"); }
  catch (error) { notice.value = error instanceof Error ? error.message : String(error); }
  finally { busy.value = false; }
}
async function saveTitle() {
  const next = title.value.trim();
  if (!next) return;
  await run(() => renameSession(props.session.session_id, next));
  renaming.value = false;
}
async function compact() {
  busy.value = true;
  try { const result = await compactSession(props.session.session_id); notice.value = "已压缩上下文，节省 " + result.saved_tokens + " tokens"; emit("changed"); }
  catch (error) { notice.value = error instanceof Error ? error.message : String(error); }
  finally { busy.value = false; }
}
async function close() {
  if (!window.confirm("关闭后该会话将不能继续发送消息。确定关闭？")) return;
  await run(() => closeSession(props.session.session_id), true);
}
</script>
<template>
  <div class="session-actions">
    <button class="icon-button" title="会话操作" aria-label="会话操作" @click="open = !open"><Ellipsis :size="18" /></button>
    <div v-if="open" class="session-menu">
      <form v-if="renaming" @submit.prevent="saveTitle"><input v-model="title" aria-label="会话名称" maxlength="120" autofocus /><button :disabled="busy">保存</button></form>
      <template v-else>
        <button @click="renaming = true">重命名</button>
        <button @click="run(() => pinSession(session.session_id, !session.pinned))"><PinOff v-if="session.pinned" :size="14" /><Pin v-else :size="14" />{{ session.pinned ? '取消置顶' : '置顶' }}</button>
        <button v-if="session.archived || session.status === 'closed'" @click="run(() => resumeSession(session.session_id))"><RotateCcw :size="14" />恢复</button>
        <button v-else @click="run(() => archiveSession(session.session_id), true)"><Archive :size="14" />归档</button>
        <button @click="compact"><Shrink :size="14" />压缩上下文</button>
        <button class="danger" @click="close"><XCircle :size="14" />关闭会话</button>
      </template>
      <p v-if="notice">{{ notice }}</p>
    </div>
  </div>
</template>