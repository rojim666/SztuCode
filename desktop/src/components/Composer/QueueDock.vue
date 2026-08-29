<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ChevronDown, CornerUpLeft, ListOrdered, Pencil, Trash2 } from "@lucide/vue";
import type { QueueDockItem } from "../../utils/composerSubmission";

const props = defineProps<{
  items: QueueDockItem[];
  running: boolean;
  busyId?: string | null;
}>();

const emit = defineEmits<{
  // 编辑不在本组件内做：把整条内容退回下方输入框，由输入框统一承载编辑
  edit: [id: string];
  remove: [id: string];
  steer: [id: string];
}>();

const expanded = ref(false);
const visibleItems = computed(() => props.items.length === 1 || expanded.value ? props.items : []);

watch(() => props.items.length, (length) => {
  if (length <= 1) expanded.value = false;
});
</script>

<template>
  <section class="queue-dock" :class="{ 'queue-dock--queued': items.length || running }">
    <div v-if="items.length" class="queue-dock__queue" aria-label="待处理任务">
      <button
        v-if="items.length > 1"
        type="button"
        class="queue-dock__summary"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        <ListOrdered :size="14" />
        <span>{{ items.length }} 条待处理</span>
        <ChevronDown :size="13" />
      </button>

      <div v-if="items.length === 1 || expanded" class="queue-dock__items">
        <article v-for="item in visibleItems" :key="item.id" class="queue-dock__item">
          <ListOrdered class="queue-dock__lead" :size="13" />
          <span class="queue-dock__text" :title="item.text">{{ item.text }}</span>
          <small v-if="item.attachmentCount">{{ item.attachmentCount }} 个附件</small>
          <div class="queue-dock__actions">
            <button type="button" class="queue-dock__action" title="退回输入框编辑" aria-label="退回输入框编辑" :disabled="busyId === item.id" @click="emit('edit', item.id)"><Pencil :size="13" /></button>
            <button type="button" class="queue-dock__action queue-dock__action--danger" title="删除" aria-label="删除待处理任务" :disabled="busyId === item.id" @click="emit('remove', item.id)"><Trash2 :size="13" /></button>
            <button
              type="button"
              class="queue-dock__action queue-dock__action--accent"
              :title="running ? '转入当前轮' : '任务运行时可转入当前轮'"
              aria-label="转入当前轮"
              :disabled="!running || busyId === item.id"
              @click="emit('steer', item.id)"
            ><CornerUpLeft :size="13" /></button>
          </div>
        </article>
      </div>
    </div>
    <slot />
  </section>
</template>
