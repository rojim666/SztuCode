<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Check, ChevronDown, CornerUpLeft, ListOrdered, Pencil, Trash2, X } from "@lucide/vue";
import type { QueueDockItem } from "../../utils/composerSubmission";

const props = defineProps<{
  items: QueueDockItem[];
  running: boolean;
  busyId?: string | null;
}>();

const emit = defineEmits<{
  edit: [id: string, text: string];
  remove: [id: string];
  steer: [id: string];
}>();

const expanded = ref(false);
const editingId = ref<string | null>(null);
const editingText = ref("");
const visibleItems = computed(() => props.items.length === 1 || expanded.value ? props.items : []);

watch(() => props.items.length, (length) => {
  if (length <= 1) expanded.value = false;
  if (editingId.value && !props.items.some((item) => item.id === editingId.value)) cancelEdit();
});

function beginEdit(item: QueueDockItem) {
  editingId.value = item.id;
  editingText.value = item.text;
}

function cancelEdit() {
  editingId.value = null;
  editingText.value = "";
}

function commitEdit() {
  const id = editingId.value;
  const text = editingText.value.trim();
  if (!id || !text) return;
  emit("edit", id, text);
  cancelEdit();
}
</script>

<template>
  <section v-if="items.length" class="queue-dock" aria-label="待处理任务">
    <button
      v-if="items.length > 1"
      type="button"
      class="queue-dock__summary"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <ListOrdered :size="14" />
      <span>{{ items.length }} 条待处理</span>
      <ChevronDown :size="14" />
    </button>

    <div v-if="items.length === 1 || expanded" class="queue-dock__items">
      <article v-for="item in visibleItems" :key="item.id" class="queue-dock__item">
        <ListOrdered class="queue-dock__lead" :size="14" />
        <form v-if="editingId === item.id" class="queue-dock__edit" @submit.prevent="commitEdit">
          <input v-model="editingText" autofocus aria-label="编辑待处理任务" @keydown.esc.prevent="cancelEdit" />
          <button type="submit" title="保存" aria-label="保存编辑"><Check :size="13" /></button>
          <button type="button" title="取消" aria-label="取消编辑" @click="cancelEdit"><X :size="13" /></button>
        </form>
        <template v-else>
          <span class="queue-dock__text" :title="item.text">{{ item.text }}</span>
          <small v-if="item.attachmentCount">{{ item.attachmentCount }} 个附件</small>
          <div class="queue-dock__actions">
            <button type="button" title="编辑" aria-label="编辑待处理任务" :disabled="busyId === item.id" @click="beginEdit(item)"><Pencil :size="13" /></button>
            <button type="button" title="删除" aria-label="删除待处理任务" :disabled="busyId === item.id" @click="emit('remove', item.id)"><Trash2 :size="13" /></button>
            <button
              type="button"
              :title="running ? '转入当前轮' : '任务运行时可转入当前轮'"
              aria-label="转入当前轮"
              :disabled="!running || busyId === item.id"
              @click="emit('steer', item.id)"
            ><CornerUpLeft :size="13" /></button>
          </div>
        </template>
      </article>
    </div>
  </section>
</template>
