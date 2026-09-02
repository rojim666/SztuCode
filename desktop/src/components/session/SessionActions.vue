<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Archive, ChevronRight, Copy, Ellipsis, Eye, ExternalLink, Folder, Pin, PinOff, Pencil } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { archiveSession, listWorkspaces, moveSession, pinSession, renameSession, type Session, type Workspace } from "../../services/sztu-runtime";
import { friendlyError } from "../../utils/errorNotice";

const { t } = useI18n({ useScope: "global" });

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
const projectOpen = ref(false);
const projects = ref<Workspace[]>([]);

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
  projectOpen.value = false;
  if (open.value) await positionMenu();
}

function closeMenu() {
  open.value = false;
  renaming.value = false;
  copyOpen.value = false;
  projectOpen.value = false;
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
    notice.value = t("session.pinFailed", { message: friendlyError(error).message });
  } finally {
    busy.value = false;
  }
}

async function archive() {
  if (props.session.archived || busy.value) return;
  await run(() => archiveSession(props.session.session_id), true);
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
    notice.value = friendlyError(error).message;
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

async function toggleProjectMenu() {
  projectOpen.value = !projectOpen.value;
  copyOpen.value = false;
  if (projectOpen.value) projects.value = (await listWorkspaces()).filter((item) => !item.archived);
}

async function assignProject(workspaceId: string | null) {
  await run(() => moveSession(props.session.session_id, workspaceId));
}

async function copyText(value: string, message = t("session.copied")) {
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
    notice.value = t("session.copyFailed", { message: friendlyError(error).message });
  }
}

async function share() {
  const url = new URL(window.location.href);
  url.hash = `session=${encodeURIComponent(props.session.session_id)}`;
  const defaultTitle = t("session.defaultShareTitle");
  const data = { title: props.session.title || defaultTitle, text: props.session.title || defaultTitle, url: url.toString() };
  try {
    const shareApi = (navigator as Navigator & { share?: (payload: ShareData) => Promise<void> }).share;
    if (shareApi) await shareApi.call(navigator, data);
    else await copyText(data.url, t("session.linkCopied"));
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    notice.value = t("session.shareFailed", { message: friendlyError(error).message });
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
  <div class="session-actions" :data-session-id="session.session_id" :data-pinned="pinned" :data-unread="unread && session.status !== 'active'" :data-running="session.status === 'active'">
    <button ref="trigger" class="icon-button" :title="session.status === 'active' ? t('session.archiveBlockedTitle') : t('session.archiveTitle')" :aria-label="t('session.archiveTitle')" :disabled="busy || session.status === 'active'" @click="archive"><Archive :size="17" /></button>
    <Teleport to="body">
      <div v-if="open" ref="menu" class="session-menu session-menu--floating" :style="menuStyle" role="menu" @contextmenu.stop>
        <form v-if="renaming" @submit.prevent="saveTitle"><input v-model="title" :aria-label="t('session.nameLabel')" maxlength="120" autofocus /><button :disabled="busy">{{ t('session.save') }}</button></form>
        <template v-else>
          <button role="menuitem" :disabled="busy" @click="togglePinned"><PinOff v-if="pinned" :size="19" /><Pin v-else :size="19" />{{ pinned ? t('session.unpin') : t('session.pin') }}</button>
          <button role="menuitem" @click="renaming = true"><Pencil :size="19" />{{ t('session.rename') }}</button>
          <button role="menuitem" @click="markUnread"><Eye :size="19" />{{ t('session.markUnread') }}</button>
          <div class="session-menu__separator" />
          <div class="session-menu__copy-wrap">
            <button role="menuitem" :aria-expanded="projectOpen" @click="toggleProjectMenu"><Folder :size="19" /><span>{{ t('session.project') }}</span><ChevronRight class="session-menu__chevron" :size="18" /></button>
            <div v-if="projectOpen" class="session-menu__submenu" role="menu">
              <button role="menuitem" :class="{ active: !session.workspace_id }" @click="assignProject(null)">{{ t('session.noProject') }}</button>
              <button v-for="project in projects" :key="project.workspace_id" role="menuitem" :class="{ active: project.workspace_id === session.workspace_id }" @click="assignProject(project.workspace_id)">{{ project.name }}</button>
            </div>
          </div>
          <div class="session-menu__separator" />
          <div class="session-menu__copy-wrap">
            <button role="menuitem" :aria-expanded="copyOpen" @click="copyOpen = !copyOpen; projectOpen = false"><Copy :size="19" /><span>{{ t('session.copy') }}</span><ChevronRight class="session-menu__chevron" :size="18" /></button>
            <div v-if="copyOpen" class="session-menu__submenu" role="menu">
              <button role="menuitem" @click="copyText(session.title || t('session.untitled'), t('session.nameCopied'))">{{ t('session.copyName') }}</button>
              <button role="menuitem" @click="copyText(session.session_id, t('session.idCopied'))">{{ t('session.copyId') }}</button>
            </div>
          </div>
          <div class="session-menu__separator" />
          <button role="menuitem" @click="openInNewWindow"><ExternalLink :size="19" />{{ t('session.openInNewWindow') }}</button>
        </template>
        <p v-if="notice" role="alert">{{ notice }}</p>
      </div>
    </Teleport>
  </div>
</template>
