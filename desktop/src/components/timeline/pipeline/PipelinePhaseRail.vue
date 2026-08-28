<script setup lang="ts">
import { Check } from "@lucide/vue";
import { PHASE_META, type PhaseState } from "./phase";

defineProps<{ states: PhaseState[] }>();
</script>

<template>
  <ol class="phase-rail" aria-label="执行阶段">
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
      <span class="phase-rail__label">{{ PHASE_META[item.phase].label }}</span>
      <span class="phase-rail__hint">{{ PHASE_META[item.phase].hint }}</span>
    </li>
  </ol>
</template>