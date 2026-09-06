<script setup lang="ts">
import { ref } from "vue";
import AppIcon from "../icons/AppIcon.vue";

const props = defineProps<{ connected: boolean }>();
const emit = defineEmits<{ submit: [content: string] }>();

const prompt = ref("");

function submit() {
  const value = prompt.value.trim();
  if (!value) return;
  emit("submit", value);
  prompt.value = "";
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.isComposing) return;
  if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
  event.preventDefault();
  submit();
}
</script>

<template>
  <section class="chat-workspace">
    <div class="chat-welcome-heading">
      <h1>Run it, Prove it</h1>
    </div>
    <form class="chat-composer" @submit.prevent="submit">
      <textarea
        v-model="prompt"
        placeholder="输入你的任务..."
        rows="3"
        @keydown="onComposerKeydown"
      />
      <div class="chat-toolbar">
        <span />
        <button
          class="chat-send"
          type="submit"
          :disabled="!prompt.trim() || !connected"
        >
          <AppIcon name="ArrowUp" :size="20" />
        </button>
      </div>
    </form>
  </section>
</template>
