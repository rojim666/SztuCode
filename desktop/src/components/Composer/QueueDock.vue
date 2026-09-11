<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import type { QueueDockItem } from "../../utils/composerSubmission";

const { t } = useI18n({ useScope: "global" });

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

// 当前置顶的卡片下标；滚轮在卡片堆上前后切换
const active = ref(0);
let lastSwitchAt = 0;

watch(
  () => props.items.length,
  (count) => {
    if (active.value >= count) active.value = Math.max(0, count - 1);
  },
);

// 相对当前卡片的层深：0 = 最前，越大越靠后；循环取模，滚轮可无限前后翻
function depthOf(index: number): number {
  const count = props.items.length;
  if (count <= 1) return 0;
  return (index - active.value + count) % count;
}

function onWheel(event: WheelEvent) {
  const count = props.items.length;
  if (count <= 1) return;
  event.preventDefault();
  const now = Date.now();
  if (now - lastSwitchAt < 200) return;
  lastSwitchAt = now;
  const step = event.deltaY > 0 ? 1 : -1;
  active.value = (active.value + step + count) % count;
}
</script>

<template>
  <section class="queue-dock" :class="{ 'queue-dock--queued': items.length > 0 }">
    <div v-if="items.length" class="queue-dock__queue" aria-label="待处理任务">
      <div class="queue-dock__deck" @wheel="onWheel">
        <article
          v-for="(item, index) in items"
          :key="item.id"
          class="queue-dock__item"
          :class="{ 'queue-dock__item--front': depthOf(index) === 0, 'queue-dock__item--hidden': depthOf(index) > 2 }"
          :style="{ '--depth': Math.min(depthOf(index), 2), zIndex: items.length - depthOf(index) }"
        >
          <AppIcon name="Circle" class="queue-dock__lead" :size="16" />
          <span class="queue-dock__text" :title="item.text">{{ item.text }}</span>
          <small v-if="item.attachmentCount">{{ item.attachmentCount }} 个附件</small>
          <div v-if="depthOf(index) === 0" class="queue-dock__actions">
            <button type="button" class="queue-dock__action" :title="t('composer.edit')" :aria-label="t('composer.edit')" :disabled="busyId === item.id" @click="emit('edit', item.id)"><AppIcon name="Pencil" :size="16" /></button>
            <button type="button" class="queue-dock__action queue-dock__action--danger" :title="t('composer.remove')" :aria-label="t('composer.removeAria')" :disabled="busyId === item.id" @click="emit('remove', item.id)"><AppIcon name="X" :size="16" /></button>
            <button
              type="button"
              class="queue-dock__action queue-dock__action--accent"
              :title="running ? t('composer.steer') : t('composer.steerHint')"
              :aria-label="t('composer.steer')"
              :disabled="!running || busyId === item.id"
              @click="emit('steer', item.id)"
            ><AppIcon name="ArrowUp" :size="16" /></button>
          </div>
        </article>
      </div>
      <span v-if="items.length > 1" class="queue-dock__counter">{{ active + 1 }}/{{ items.length }}</span>
    </div>
    <slot />
  </section>
</template>
