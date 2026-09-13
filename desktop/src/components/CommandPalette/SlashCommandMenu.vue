<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import AppIcon from "../icons/AppIcon.vue";
import { useI18n } from "vue-i18n";
import { slashMenuItems, type SkillSearchEntry } from "./slash-menu";
const { t } = useI18n({ useScope: "global" });
const props = defineProps<{ query: string; skills: SkillSearchEntry[]; connected: boolean; activeIndex: number; loading?: boolean; error?: boolean }>();
const emit = defineEmits<{ select: [name: string]; activate: [index: number] }>();
const items = computed(() => slashMenuItems(props.query, props.skills, key => t(key)));
const commands = computed(() => items.value.filter(item => item.group === "command"));
const skills = computed(() => items.value.filter(item => item.group === "skill"));
const total = computed(() => slashMenuItems("", props.skills, key => t(key)).filter(item => item.group === "skill").length);
const itemIndex = (id: string) => items.value.findIndex(item => item.id === id);
const menu = ref<HTMLElement>();
const availableHeight = ref(360);
let resizeObserver: ResizeObserver | undefined;
function measureSpace() {
  const parent = menu.value?.parentElement;
  if (parent) availableHeight.value = Math.max(120, Math.min(520, parent.getBoundingClientRect().top - 68));
}
onMounted(() => {
  measureSpace();
  resizeObserver = new ResizeObserver(measureSpace);
  if (menu.value?.parentElement) resizeObserver.observe(menu.value.parentElement);
  window.addEventListener('resize', measureSpace);
  window.addEventListener('scroll', measureSpace, true);
});
onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  window.removeEventListener('resize', measureSpace);
  window.removeEventListener('scroll', measureSpace, true);
});
const modeIcons: Record<string, string> = { plan: "ListChecks", edits: "Pencil", auto: "Sparkles" };
watch([() => props.activeIndex, items], async () => {
  await nextTick();
  const option = menu.value?.querySelector<HTMLElement>('[aria-selected="true"]');
  const scroll = menu.value?.querySelector<HTMLElement>('.slash-menu__scroll');
  if (option && scroll?.contains(option)) {
    const a = option.getBoundingClientRect(), b = scroll.getBoundingClientRect();
    if (a.top < b.top) scroll.scrollTop -= b.top - a.top;
    if (a.bottom > b.bottom) scroll.scrollTop += a.bottom - b.bottom;
  }
});
</script>

<template>
  <section ref="menu" class="slash-menu command-picker" :style="{ maxHeight: availableHeight + 'px' }" role="listbox" :aria-label="t('palette.menuAria')" :aria-busy="loading">
    <section v-if="commands.length" class="picker-modes" role="group" :aria-label="t('palette.commandGroupAria')">
      <header>{{ t('palette.modesTitle') }}<small>{{ t('palette.modesHint') }}</small></header>
      <div class="picker-modes__grid">
        <button v-for="item in commands" :key="item.id" type="button" role="option" :aria-selected="itemIndex(item.id) === activeIndex" :title="item.description" @mouseenter="emit('activate', itemIndex(item.id))" @mousedown.prevent @click="emit('select', item.name)">
          <AppIcon :name="modeIcons[item.name]" :size="17" />
          <b>{{ t('palette.modeNames.' + item.name) }}</b><code>/{{ item.name }}</code>
          <small>{{ t('palette.modeHints.' + item.name) }}</small>
        </button>
      </div>
    </section>
    <header class="picker-skill-heading"><span>{{ t('palette.skillGroupTitle') }} <b>{{ skills.length }}</b><small v-if="query"> / {{ total }}</small></span><small>{{ t('palette.searchHint') }}</small></header>
    <div class="slash-menu__scroll">
      <section class="picker-skills" role="group" :aria-label="t('palette.skillGroupAria')">
        <button v-for="item in skills" :key="item.id" type="button" role="option" :aria-selected="itemIndex(item.id) === activeIndex" :title="item.description" @mouseenter="emit('activate', itemIndex(item.id))" @mousedown.prevent @click="emit('select', item.name)">
          <svg class="picker-skill-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="m12 2 7 4v12l-7 4-7-4V6l7-4Z"/><path d="m5 6 7 4 7-4M5 12l7 4 7-4M12 10v12"/></svg>
          <span class="picker-skill-copy"><span class="picker-skill-name"><b>/{{ item.name }}</b><small v-if="item.plugin">{{ item.plugin }}</small></span><span class="picker-skill-description">{{ item.short_description || item.description || t('palette.invokeSkill') }}</span></span>
          <AppIcon class="picker-return" name="CornerDownLeft" :size="14" />
        </button>
      </section>
      <div v-if="!skills.length" class="slash-menu__empty"><AppIcon name="Search" :size="22" /><b>{{ loading ? t('palette.loadingSkills') : t('palette.emptyTitle') }}</b><span>{{ t('palette.emptyHint') }}</span></div>
    </div>
    <p v-if="loading || error || !connected" class="picker-status" role="status">{{ loading ? t('palette.loadingSkills') : error ? t('palette.skillsError') : t('palette.notice') }}</p>
    <footer><span><kbd>↑</kbd><kbd>↓</kbd>{{ t('palette.keySelect') }}</span><span><kbd>Enter</kbd>{{ t('palette.keyInvoke') }}</span><span><kbd>Esc</kbd>{{ t('palette.keyClose') }}</span></footer>
  </section>
</template>

<style>
.sztu-composer .command-picker { display: flex; flex-direction: column; max-height: min(520px, 65vh); color: var(--text, #30343a); }
.command-picker .picker-modes { flex: none; padding: 12px 12px 10px; border-bottom: 1px solid var(--border, #edf0f4); }
.command-picker .picker-modes header, .command-picker .picker-skill-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--text-muted, #808995); font-size: 11px; font-weight: 500; }
.command-picker .picker-modes header small, .command-picker .picker-skill-heading small { font-size: 10px; font-weight: 400; }
.command-picker .picker-modes__grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin-top: 9px; }
.command-picker .picker-modes button { display: grid; grid-template-columns: 19px 1fr; gap: 5px 5px; min-width: 0; padding: 10px 8px; border: 1px solid var(--border, #e7ebf0); border-radius: 9px; color: inherit; background: transparent; text-align: left; cursor: pointer; }
.command-picker .picker-modes button > .app-icon { grid-row: span 2; color: #75869c; }
.command-picker .picker-modes button b { font-size: 12px; font-weight: 600; }
.command-picker .picker-modes button code { font-size: 10px; color: var(--text-muted, #85909e); }
.command-picker .picker-modes button small { grid-column: 1 / -1; font-size: 10px; line-height: 1.5; color: var(--text-muted, #85909e); }
.command-picker .picker-modes button[aria-selected="true"], .command-picker .picker-modes button:hover { border-color: #2583e960; background: #2583e90c; color: #2583e9; }
.command-picker .picker-skill-heading { flex: none; padding: 11px 16px 6px; }
.command-picker .picker-skill-heading b { margin-left: 5px; color: #2583e9; font-weight: 600; }
.sztu-composer .command-picker .slash-menu__scroll { flex: 1 1 auto; min-height: 0; max-height: none; padding: 0 7px 7px; }
.command-picker .picker-skills button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 9px; border: 0; border-radius: 8px; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.command-picker .picker-skills button:hover, .command-picker .picker-skills button[aria-selected="true"] { background: #2583e910; }
.command-picker .picker-skill-icon { flex: none; color: #2583e9; }
.command-picker .picker-skill-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.command-picker .picker-skill-name { display: flex; min-width: 0; gap: 8px; align-items: center; }
.command-picker .picker-skill-name b { font-size: 13px; font-weight: 550; overflow-wrap: anywhere; }
.command-picker .picker-skill-name small { color: var(--text-muted, #85909e); font-size: 10px; max-width: 35%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.command-picker .picker-skill-description { color: var(--text-muted, #85909e); font-size: 11px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.command-picker .picker-return { flex: none; opacity: 0; color: #2583e9; }
.command-picker [aria-selected="true"] .picker-return { opacity: 1; }
.command-picker [aria-selected="true"] .picker-skill-name b { color: #2583e9; }
.command-picker .picker-status { flex: none; margin: 0; padding: 7px 14px; color: var(--text-muted, #85909e); font-size: 10px; line-height: 1.5; border-top: 1px solid var(--border, #edf0f4); }
.command-picker button:focus-visible { outline: 2px solid #2583e9; outline-offset: -2px; }
.sztu-composer .command-picker > footer { flex: none; }
:root[data-app-theme="dark"] .command-picker { --text-muted: #9ba8b9; }
@container composer (max-width: 340px) {
  .command-picker .picker-modes { padding: 9px; }
  .command-picker .picker-modes header small, .command-picker .picker-skill-heading > small { display: none; }
  .command-picker .picker-modes button { padding: 7px 5px; grid-template-columns: 1fr; }
  .command-picker .picker-modes button > .app-icon { display: none; }
}
</style>
