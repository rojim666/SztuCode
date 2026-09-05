<script setup lang="ts">
import AppIcon from "../icons/AppIcon.vue";
import { computed, useId } from "vue";
import { useI18n } from "vue-i18n";
import type { RuntimeSettings } from "../../services/sztu-runtime";

type Effort = RuntimeSettings["reasoning_effort"];
const props = defineProps<{ modelValue: Effort; disabled?: boolean; compact?: boolean; modelName?: string; statusText?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: Effort]; change: [value: Effort] }>();
const { t } = useI18n({ useScope: "global" });
const id = useId();
const levels = ["", "low", "medium", "high", "xhigh", "max"] as const;
const position = computed(() => Math.max(0, levels.indexOf(props.modelValue)));
const label = computed(() => t(`model.reasoning.${props.modelValue || "default"}`));
function choose(value: Effort) {
  if (props.disabled) return;
  emit("update:modelValue", value);
  emit("change", value);
}
function update(event: Event, commit = false) {
  const value = levels[Number((event.target as HTMLInputElement).value)];
  if (value === undefined || props.disabled) return;
  emit("update:modelValue", value);
  if (commit) emit("change", value);
}
</script>

<template>
  <div class="reasoning-slider" :class="{ 'reasoning-slider--compact': compact, 'reasoning-slider--disabled': disabled }">
    <div class="reasoning-slider-card">
      <div class="reasoning-slider-heading">
        <span v-if="compact" class="reasoning-slider-caption">{{ t("model.reasoningLabel") }}</span>
        <span v-if="compact" class="reasoning-slider-status" role="status" :aria-label="t('model.reasoningSaveStatus')">{{ statusText }}</span>
        <button type="button" class="reasoning-slider-level" :disabled="disabled" :aria-label="t('model.reasoningNext')"
          @click="choose(levels[(position + 1) % levels.length])">
          <span>{{ t(`model.reasoningShort.${modelValue || 'default'}`) }}</span><AppIcon name="ChevronRight" :size="16" />
        </button>
        <button type="button" class="reasoning-slider-reset" :disabled="disabled || !modelValue" :title="t('model.reasoningReset')"
          :aria-label="t('model.reasoningReset')" @click="choose('')"><AppIcon name="RotateCcw" :size="20" /></button>
        <p v-if="!compact" class="reasoning-slider-model" :title="modelName">{{ modelName || t("model.reasoningLabel") }}</p>
      </div>
      <div class="reasoning-slider-track" :style="{ '--reasoning-progress': `calc(${compact ? 16 : 22}px + (100% - ${compact ? 32 : 44}px) * ${position / (levels.length - 1)})` }">
        <div class="reasoning-slider-rail" aria-hidden="true" />
        <div class="reasoning-slider-ticks" aria-hidden="true">
          <i v-for="(level, index) in levels" :key="level" :class="{ filled: index < position }" />
        </div>
        <input :id="id" class="reasoning-slider-input" type="range" min="0" :max="levels.length - 1" step="1"
          :value="position" :disabled="disabled" :aria-label="t('model.reasoningLabel')" :aria-valuetext="label"
          :aria-describedby="compact ? undefined : `${id}-hint`"
          @input="update($event)" @change="update($event, true)" />
      </div>
    </div>
    <p v-if="!compact" :id="`${id}-hint`" class="reasoning-slider-hint">{{ t("model.reasoningHint") }}</p>
  </div>
</template>

<style scoped>
.reasoning-slider { --reasoning-blue: #3498ff; display: grid; gap: 8px; min-width: 0; }
.reasoning-slider-card { position: relative; padding: 14px 18px 12px; background: var(--surface, #fff); border: 1px solid var(--border, #e3e3e6); border-radius: 22px; box-shadow: 0 2px 5px #00000004; }
.reasoning-slider-heading { position: relative; display: grid; justify-items: center; gap: 3px; min-width: 0; padding: 0 24px; }
.reasoning-slider-level { display: inline-flex; align-items: center; justify-content: center; gap: 4px; min-height: 27px; padding: 0 4px; background: transparent; border: 0; border-radius: 6px; color: var(--reasoning-blue); font-size: 19px; font-weight: 600; cursor: pointer; }
.reasoning-slider-level .app-icon { color: var(--text-muted, #949497); }
.reasoning-slider-reset { position: absolute; top: 0; right: -6px; display: grid; place-items: center; width: 28px; height: 28px; padding: 0; border: 0; border-radius: 50%; background: transparent; color: var(--text-muted, #949497); cursor: pointer; }
.reasoning-slider-reset:hover:enabled { background: var(--border, #eeeeef); }
.reasoning-slider-reset:disabled { opacity: 0.4; cursor: default; }
.reasoning-slider-model { margin: 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted, #77777c); font-size: 14px; line-height: 22px; }
.reasoning-slider-track { position: relative; height: 44px; margin-top: 14px; }
.reasoning-slider-rail { position: absolute; inset: 4px 0; border-radius: 999px; background: linear-gradient(to right, var(--reasoning-blue) var(--reasoning-progress), var(--border, #e7e7e9) var(--reasoning-progress)); box-shadow: inset 0 0 0 1px #00000004; }
.reasoning-slider-ticks { position: absolute; inset: 0 19px; display: flex; align-items: center; justify-content: space-between; pointer-events: none; }
.reasoning-slider-ticks i { width: 6px; height: 6px; border-radius: 50%; background: #b3b3b8; }
.reasoning-slider-ticks i.filled { background: #ffffff55; }
.reasoning-slider-input {
  appearance: none; -webkit-appearance: none; position: absolute; inset: 0; box-sizing: border-box;
  width: 100%; height: 44px; margin: 0; padding: 0; border: 0; border-radius: 999px; cursor: pointer; background: transparent;
}
.reasoning-slider-input::-webkit-slider-thumb {
  appearance: none; width: 44px; height: 44px; border-radius: 50%; background: #fff; border: 1px solid #dedee2;
  box-shadow: 0 1px 3px #00000018;
}
.reasoning-slider-input::-moz-range-thumb { box-sizing: border-box; width: 44px; height: 44px; border-radius: 50%; background: #fff; border: 1px solid #dedee2; box-shadow: 0 1px 3px #00000018; }
.reasoning-slider-input:focus-visible, .reasoning-slider-level:focus-visible, .reasoning-slider-reset:focus-visible { outline: 2px solid var(--reasoning-blue); outline-offset: 3px; }
.reasoning-slider-hint { margin: 0; color: var(--text-muted, #6b7280); font-size: 12px; line-height: 1.5; }
.reasoning-slider--compact .reasoning-slider-hint { padding-inline: 2px; font-size: 11px; }
.reasoning-slider--disabled { opacity: 0.6; }
.reasoning-slider-input:disabled, .reasoning-slider-level:disabled { cursor: wait; }
.reasoning-slider-status { flex-shrink: 0; color: var(--reasoning-blue); font-size: 11px; }
.reasoning-slider--compact { gap: 4px; }
.reasoning-slider--compact .reasoning-slider-card { padding: 0; background: transparent; border: 0; border-radius: 0; box-shadow: none; }
.reasoning-slider--compact .reasoning-slider-heading { display: flex; align-items: center; gap: 6px; padding: 0; }
.reasoning-slider-caption { margin-right: auto; color: var(--text, #30343a); font-size: 12px; font-weight: 500; }
.reasoning-slider--compact .reasoning-slider-level { min-height: 26px; font-size: 14px; }
.reasoning-slider--compact .reasoning-slider-reset { position: static; width: 26px; height: 26px; }
.reasoning-slider--compact .reasoning-slider-track { margin-top: 4px; }
.reasoning-slider--compact .reasoning-slider-rail { inset-block: 10px; }
.reasoning-slider--compact .reasoning-slider-input::-webkit-slider-thumb { width: 32px; height: 32px; }
.reasoning-slider--compact .reasoning-slider-input::-moz-range-thumb { width: 32px; height: 32px; }
.reasoning-slider--compact .reasoning-slider-ticks { inset-inline: 14px; }
.reasoning-slider--compact .reasoning-slider-ticks i { width: 4px; height: 4px; }
.reasoning-slider--compact .reasoning-slider-hint { padding: 0; font-size: 10px; }
</style>
