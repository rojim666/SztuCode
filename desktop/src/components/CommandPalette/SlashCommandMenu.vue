<script setup lang="ts">
import { computed } from "vue";
import { Braces, CornerDownLeft, Terminal } from "@lucide/vue";
import { BUILT_IN_SLASH_COMMANDS, slashMenuItems } from "./slash-menu";

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

const items = computed(() => slashMenuItems(props.query, props.skills));
const commands = computed(() => items.value.filter((item) => item.group === "command"));
const skills = computed(() => items.value.filter((item) => item.group === "skill"));
const itemIndex = (id: string) => items.value.findIndex((item) => item.id === id);
</script>

<template>
  <section class="slash-menu" role="listbox" aria-label="斜杠命令与技能">
    <div class="slash-menu__scroll">
      <section v-if="commands.length" class="slash-menu__group" aria-label="命令">
        <h3>命令 <small>{{ commands.length }}/{{ BUILT_IN_SLASH_COMMANDS.length }}</small></h3>
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

      <section v-if="skills.length" class="slash-menu__group" aria-label="技能">
        <h3>技能 <small>{{ skills.length }}{{ query ? ' 项匹配' : ' 项可用' }}</small></h3>
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
          <span>{{ item.description || '调用已安装技能' }}</span>
          <CornerDownLeft v-if="itemIndex(item.id) === activeIndex" :size="13" />
        </button>
      </section>

      <div v-if="!items.length" class="slash-menu__empty">
        <Braces :size="20" />
        <b>没有匹配的命令或技能</b>
        <span>换一个名称或功能关键词试试</span>
      </div>
      <p v-if="!connected && !query" class="slash-menu__notice">正在使用内建技能目录，连接本地服务后会同步项目与用户技能</p>
    </div>

    <footer><span><kbd>↑</kbd><kbd>↓</kbd>选择</span><span><kbd>Enter</kbd>调用</span><span><kbd>Esc</kbd>关闭</span></footer>
  </section>
</template>
