<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ChevronDown, CornerUpLeft, ListOrdered, Pencil, Trash2 } from "@lucide/vue";
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

const expanded = ref(false);
const visibleItems = computed(() => props.items.length === 1 || expanded.value ? props.items : []);

watch(() => props.items.length, (length) => {
  if (length <= 1) expanded.value = false;
});
</script>

<template>
  <section class="queue-dock" :class="{ 'queue-dock--queued': items.length > 0 }">
    <div v-if="items.length" class="queue-dock__queue" aria-label="待处理任务">
      <button
        v-if="items.length > 1"
        type="button"
        class="queue-dock__summary"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        <ListOrdered :size="14" />
        <span>{{ t("composer.queueSummary", { n: items.length }) }}</span>
        <ChevronDown :size="13" />
      </button>

      <div v-if="items.length === 1 || expanded" class="queue-dock__items">
        <article v-for="item in visibleItems" :key="item.id" class="queue-dock__item">
          <ListOrdered class="queue-dock__lead" :size="13" />
          <span class="queue-dock__text" :title="item.text">{{ item.text }}</span>
          <small v-if="item.attachmentCount">{{ item.attachmentCount }} 个附件</small>
          <div class="queue-dock__actions">
            <button type="button" class="queue-dock__action" :title="t('composer.edit')" :aria-label="t('composer.edit')" :disabled="busyId === item.id" @click="emit('edit', item.id)"><Pencil :size="13" /></button>
            <button type="button" class="queue-dock__action queue-dock__action--danger" :title="t('composer.remove')" :aria-label="t('composer.removeAria')" :disabled="busyId === item.id" @click="emit('remove', item.id)"><Trash2 :size="13" /></button>
            <button
              type="button"
              class="queue-dock__action queue-dock__action--accent"
              :title="running ? t('composer.steer') : t('composer.steerHint')"
              :aria-label="t('composer.steer')"
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
