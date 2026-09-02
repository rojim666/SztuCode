<script setup lang="ts">
import { computed } from "vue";
import { Braces, CornerDownLeft, Terminal } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { BUILT_IN_SLASH_COMMANDS, slashMenuItems } from "./slash-menu";

const { t } = useI18n({ useScope: "global" });

const props = defineProps<{
  query: string;
  skills: Array<{ name: string; description: string }>;
  connected: boolean;
  activeIndex: number;
}>();
const emit = defineEmits<{
  select: [name: string];
  activate: [index: number];
}>();

const items = computed(() => slashMenuItems(props.query, props.skills, (key) => t(key)));
const commands = computed(() => items.value.filter((item) => item.group === "command"));
const skills = computed(() => items.value.filter((item) => item.group === "skill"));
const itemIndex = (id: string) => items.value.findIndex((item) => item.id === id);
</script>

<template>
  <section class="slash-menu" role="listbox" :aria-label="t('palette.menuAria')">
    <div class="slash-menu__scroll">
      <section v-if="commands.length" class="slash-menu__group" :aria-label="t('palette.commandGroupAria')">
        <h3>{{ t('palette.commandGroupTitle') }} <small>{{ t('palette.commandCount', { matched: commands.length, total: BUILT_IN_SLASH_COMMANDS.length }) }}</small></h3>
        <button
          v-for="item in commands"
          :key="item.id"
          type="button"
          role="option"
          :aria-selected="itemIndex(item.id) === activeIndex"
          :class="{ active: itemIndex(item.id) === activeIndex }"
          @mouseenter="emit('activate', itemIndex(item.id))"
          @mousedown.prevent
          @click="emit('select', item.name)"
        >
          <span class="slash-menu__icon command"><Terminal :size="15" /></span>
          <b>/{{ item.name }}</b>
          <span>{{ item.description }}</span>
          <CornerDownLeft v-if="itemIndex(item.id) === activeIndex" :size="13" />
        </button>
      </section>

      <section v-if="skills.length" class="slash-menu__group" :aria-label="t('palette.skillGroupAria')">
        <h3>{{ t('palette.skillGroupTitle') }} <small>{{ query ? t('palette.skillCountMatched', { n: skills.length }) : t('palette.skillCountAvailable', { n: skills.length }) }}</small></h3>
        <button
          v-for="item in skills"
          :key="item.id"
          type="button"
          role="option"
          :aria-selected="itemIndex(item.id) === activeIndex"
          :class="{ active: itemIndex(item.id) === activeIndex }"
          @mouseenter="emit('activate', itemIndex(item.id))"
          @mousedown.prevent
          @click="emit('select', item.name)"
        >
          <span class="slash-menu__icon"><Braces :size="15" /></span>
          <b>/{{ item.name }}</b>
          <span>{{ item.description || t('palette.invokeSkill') }}</span>
          <CornerDownLeft v-if="itemIndex(item.id) === activeIndex" :size="13" />
        </button>
      </section>

      <div v-if="!items.length" class="slash-menu__empty">
        <Braces :size="20" />
        <b>{{ t('palette.emptyTitle') }}</b>
        <span>{{ t('palette.emptyHint') }}</span>
      </div>
      <p v-if="!connected && !query" class="slash-menu__notice">{{ t('palette.notice') }}</p>
    </div>

    <footer><span><kbd>↑</kbd><kbd>↓</kbd>{{ t('palette.keySelect') }}</span><span><kbd>Enter</kbd>{{ t('palette.keyInvoke') }}</span><span><kbd>Esc</kbd>{{ t('palette.keyClose') }}</span></footer>
  </section>
</template>
