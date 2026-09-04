<script setup lang="ts">
import { computed } from "vue";
import { iconRegistry } from "./icons.gen";

/**
 * 统一图标组件（Fluent System Icons 体系）。
 * - name 沿用原 lucide 图标名，见 icons.gen.ts 的 iconRegistry
 * - filled 用于选中/激活态（微软办公风的 regular→filled 切换）
 * - 颜色继承 currentColor，明暗主题自适应
 */
const props = withDefaults(
  defineProps<{ name: string; size?: number | string; filled?: boolean }>(),
  { size: 16, filled: false },
);

const entry = computed(() => iconRegistry[props.name]);
const svg = computed(() => {
  if (!entry.value) {
    console.warn(`[AppIcon] unknown icon: ${props.name}`);
    return "";
  }
  return props.filled ? entry.value.filled : entry.value.regular;
});
const dim = computed(() => (typeof props.size === "number" ? `${props.size}px` : props.size));
</script>

<template>
  <span class="app-icon" :style="{ width: dim, height: dim }" aria-hidden="true" v-html="svg" />
</template>

<style scoped>
.app-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  line-height: 0;
  color: inherit;
}

.app-icon :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
