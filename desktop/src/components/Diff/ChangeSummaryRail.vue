<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  paths: string[];
}>();

const changedFileCount = computed(() => new Set(props.paths).size);
</script>

<template>
  <section class="change-summary-rail" aria-label="本轮文件修改数量" aria-live="polite">
    <span class="change-summary-rail__line"><span>修改了</span><strong>{{ changedFileCount }}</strong><span>个文件</span></span>
  </section>
</template>
