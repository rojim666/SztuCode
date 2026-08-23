<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Archive, ChevronRight, Copy, Ellipsis, Eye, ExternalLink, Pin, PinOff, Pencil, RotateCcw, Share2 } from "@lucide/vue";
import { archiveSession, pinSession, renameSession, resumeSession, type Session } from "../../services/sztu-runtime";

const props = defineProps<{ session: Session; active?: boolean }>();
const emit = defineEmits<{ changed: []; closed: [] }>();
const UNREAD_SESSIONS_KEY = "sztu.unreadSessions";
const UNREAD_CHANGE_EVENT = "sztu:session-unread-change";
type UnreadChangeDetail = { sessionId: string; unread: boolean };
function readUnreadSession(sessionId: string): boolean {
  try {
    const stored = JSON.parse(localStorage.getItem(UNREAD_SESSIONS_KEY) ?? "[]");
    return Array.isArray(stored) && stored.includes(sessionId);
  } catch {
    return false;
  }
}
function writeUnreadSession(sessionId: string, unread: boolean): void {
  try {
    const stored = JSON.parse(localStorage.getItem(UNREAD_SESSIONS_KEY) ?? "[]");
    const ids = new Set<string>(Array.isArray(stored) ? stored.filter((item): item is string => typeof item === "string") : []);
    if (unread) ids.add(sessionId); else ids.delete(sessionId);
    localStorage.setItem(UNREAD_SESSIONS_KEY, JSON.stringify([...ids]));
  } catch {
    // localStorage can be unavailable in an embedded or private webview.
  }
}
function publishUnreadSession(sessionId: string, unread: boolean): void {
  writeUnreadSession(sessionId, unread);
  document.dispatchEvent(new CustomEvent<UnreadChangeDetail>(UNREAD_CHANGE_EVENT, {
    detail: { sessionId, unread },
  }));
}
const open = ref(false);
const renaming = ref(false);
const title = ref(props.session.title);
const pinned = ref(props.session.pinned);
const unread = ref(readUnreadSession(props.session.session_id));
const busy = ref(false);
const notice = ref("");
const trigger = ref<HTMLElement | null>(null);
const menu = ref<HTMLElement | null>(null);
const menuStyle = ref<Record<string, string>>({});
const copyOpen = ref(false);

async function positionMenu(point?: { x: number; y: number }) {
  await nextTick();
  if (!menu.value) return;
  const anchor = point ? { right: point.x, bottom: point.y, top: point.y } : trigger.value?.getBoundingClientRect();
  if (!anchor) return;
  const popup = menu.value.getBoundingClientRect();
  const left = point
    ? Math.max(8, Math.min(point.x, window.innerWidth - popup.width - 8))
    : Math.max(8, Math.min(anchor.right - popup.width, window.innerWidth - popup.width - 8));
  let top = point ? point.y : anchor.bottom + 6;
  if (top + popup.height > window.innerHeight - 8) top = Math.max(8, anchor.top - popup.height - (point ? 0 : 6));
  menuStyle.value = { left: left + "px", top: top + "px" };
}

async function toggleMenu() {
  open.value = !open.value;
  copyOpen.value = false;
  if (open.value) await positionMenu();
}

function closeMenu() {
  open.value = false;
  renaming.value = false;
  copyOpen.value = false;
}

async function togglePinned() {
  const next = !pinned.value;
  busy.value = true;
  notice.value = "";
  try {
    const updated = await pinSession(props.session.session_id, next);
    pinned.value = Boolean(updated.pinned);
    closeMenu();
    emit("changed");
  } catch (error) {
    notice.value = error instanceof Error ? `置顶失败：${error.message}` : `置顶失败：${String(error)}`;
  } finally {
    busy.value = false;
  }
}

async function openContextMenu(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  const owner = target?.closest<HTMLElement>("[data-session-id]")
    ?? target?.closest<HTMLElement>(".sidebar-session, .session-board > article")?.querySelector<HTMLElement>("[data-session-id]");
  if (owner?.dataset.sessionId !== props.session.session_id) return;
  event.preventDefault();
  event.stopPropagation();
  open.value = true;
  renaming.value = false;
  copyOpen.value = false;
  await positionMenu({ x: event.clientX, y: event.clientY });
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

async function markUnread() {
  publishUnreadSession(props.session.session_id, true);
  closeMenu();
  emit("changed");
}

async function copyText(value: string, message = "已复制") {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
    else {
      const input = document.createElement("textarea");
      input.value = value;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
    }
    notice.value = message;
  } catch (error) {
    notice.value = error instanceof Error ? error.message : String(error);
  }
}

async function share() {
  const url = new URL(window.location.href);
  url.hash = `session=${encodeURIComponent(props.session.session_id)}`;
  const data = { title: props.session.title || "SztuCode 会话", text: props.session.title || "SztuCode 会话", url: url.toString() };
  try {
    const shareApi = (navigator as Navigator & { share?: (payload: ShareData) => Promise<void> }).share;
    if (shareApi) await shareApi.call(navigator, data);
    else await copyText(data.url, "会话链接已复制");
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    notice.value = error instanceof Error ? error.message : String(error);
  }
}

function openInNewWindow() {
  const url = new URL(window.location.href);
  url.hash = `session=${encodeURIComponent(props.session.session_id)}`;
  window.open(url.toString(), "_blank", "noopener,noreferrer");
  closeMenu();
}

function closeOnViewportChange() { if (open.value) closeMenu(); }
function handleUnreadChange(event: Event) {
  const detail = (event as CustomEvent<UnreadChangeDetail>).detail;
  if (detail?.sessionId === props.session.session_id) unread.value = detail.unread;
}

watch(() => props.session.title, (value) => { if (!renaming.value) title.value = value; });
watch(() => props.session.pinned, (value) => { pinned.value = value; });
watch(() => props.active, (value) => {
  if (!value || !unread.value) return;
  publishUnreadSession(props.session.session_id, false);
}, { immediate: true });
onMounted(() => {
  document.addEventListener("pointerdown", handleOutside);
  document.addEventListener("contextmenu", openContextMenu);
  document.addEventListener(UNREAD_CHANGE_EVENT, handleUnreadChange);
  document.addEventListener("scroll", closeOnViewportChange, true);
  window.addEventListener("resize", closeOnViewportChange);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleOutside);
  document.removeEventListener("contextmenu", openContextMenu);
  document.removeEventListener(UNREAD_CHANGE_EVENT, handleUnreadChange);
  document.removeEventListener("scroll", closeOnViewportChange, true);
  window.removeEventListener("resize", closeOnViewportChange);
});
</script>

<template>
  <div class="session-actions" :data-session-id="session.session_id" :data-pinned="pinned" :data-unread="unread && session.status !== 'active'" :data-running="session.status === 'active'" :aria-label="session.status === 'active' ? '运行中' : undefined">
    <button ref="trigger" class="icon-button" title="会话操作" aria-label="会话操作" :aria-expanded="open" @click="toggleMenu"><Ellipsis :size="18" /></button>
    <Teleport to="body">
      <div v-if="open" ref="menu" class="session-menu session-menu--floating" :style="menuStyle" role="menu" @contextmenu.stop>
        <form v-if="renaming" @submit.prevent="saveTitle"><input v-model="title" aria-label="会话名称" maxlength="120" autofocus /><button :disabled="busy">保存</button></form>
        <template v-else>
          <button role="menuitem" :disabled="busy" @click="togglePinned"><PinOff v-if="pinned" :size="19" /><Pin v-else :size="19" />{{ pinned ? '取消置顶' : '置顶' }}</button>
          <button role="menuitem" @click="renaming = true"><Pencil :size="19" />重命名</button>
          <button role="menuitem" @click="markUnread"><Eye :size="19" />标记为未读</button>
          <button v-if="session.archived || session.status === 'closed'" role="menuitem" @click="run(() => resumeSession(session.session_id))"><RotateCcw :size="19" />恢复</button>
          <button v-else role="menuitem" @click="run(() => archiveSession(session.session_id), true)"><Archive :size="19" />归档</button>
          <div class="session-menu__separator" />
          <button role="menuitem" @click="share"><Share2 :size="19" />分享</button>
          <div class="session-menu__copy-wrap">
            <button role="menuitem" :aria-expanded="copyOpen" @click="copyOpen = !copyOpen"><Copy :size="19" /><span>复制</span><ChevronRight class="session-menu__chevron" :size="18" /></button>
            <div v-if="copyOpen" class="session-menu__submenu" role="menu">
              <button role="menuitem" @click="copyText(session.title || '未命名任务', '会话名称已复制')">复制会话名称</button>
              <button role="menuitem" @click="copyText(session.session_id, '会话 ID 已复制')">复制会话 ID</button>
            </div>
          </div>
          <div class="session-menu__separator" />
          <button role="menuitem" @click="openInNewWindow"><ExternalLink :size="19" />在新窗口中打开</button>
        </template>
        <p v-if="notice">{{ notice }}</p>
      </div>
    </Teleport>
  </div>
</template>
