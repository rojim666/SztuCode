<script setup lang="ts">
import { computed } from "vue";
import { MorphIcon } from "morphicons/vue";
import { iconRegistry } from "./icons.gen";

/**
 * 统一图标组件（lucide 图标数据 + morphicons 弹性变形动画）。
 * - name 见 icons.gen.ts 的 iconRegistry（沿用既有图标名）
 * - name 变化时自动播放 morph 弹性变形动画（如展开/收起箭头、播放/暂停、明暗主题切换）
 * - filled 用于选中/激活态（填充描边呈现实心观感）
 * - 颜色继承 currentColor，明暗主题自适应
 * - reduced-motion="user" 尊重系统"减少动画"设置
 */
const props = withDefaults(
  defineProps<{ name: string; size?: number | string; filled?: boolean }>(),
  { size: 16, filled: false },
);

const entry = computed(() => {
  const icon = iconRegistry[props.name];
  if (!icon) console.warn(`[AppIcon] unknown icon: ${props.name}`);
  return icon;
});
const dim = computed(() => (typeof props.size === "number" ? `${props.size}px` : props.size));
</script>

<template>
  <span class="app-icon" :class="{ 'app-icon--filled': filled }" :style="{ width: dim, height: dim }" aria-hidden="true">
    <MorphIcon v-if="entry" :icon="entry" spring="snappy" reduced-motion="user" />
  </span>
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

/* filled：填充描边呈现实心观感，切换时颜色平滑过渡 */
.app-icon--filled :deep(svg) {
  fill: currentColor;
  transition: fill 160ms ease;
}
</style>
