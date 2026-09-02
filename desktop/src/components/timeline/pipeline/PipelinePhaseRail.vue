<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { Check } from "@lucide/vue";
import { buildPhaseMeta, type PhaseState } from "./phase";

defineProps<{ states: PhaseState[] }>();
const { t } = useI18n({ useScope: "global" });
// 阶段 label/hint 依赖语言包，computed 包裹工厂函数保证切换语言时重建
const phaseMeta = computed(() => buildPhaseMeta((key) => t(key)));
</script>

<template>
  <ol class="phase-rail" :aria-label="t('timeline.phase.railAria')">
    <li
      v-for="item in states"
      :key="item.phase"
      class="phase-rail__item"
      :class="{ 'is-reached': item.reached, 'is-active': item.active }"
      :aria-current="item.active ? 'step' : undefined"
    >
      <span class="phase-rail__dot" aria-hidden="true">
        <Check v-if="item.reached && !item.active" :size="10" :stroke-width="3" />
      </span>
      <span class="phase-rail__label">{{ phaseMeta[item.phase].label }}</span>
      <span class="phase-rail__hint">{{ phaseMeta[item.phase].hint }}</span>
    </li>
  </ol>
</template>
