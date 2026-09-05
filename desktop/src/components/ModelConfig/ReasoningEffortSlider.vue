<script setup lang="ts">
import AppIcon from "../icons/AppIcon.vue";
import { computed, ref, watch, useId } from "vue";
import { useI18n } from "vue-i18n";
import type { RuntimeSettings } from "../../services/sztu-runtime";

type Effort = RuntimeSettings["reasoning_effort"];
const props = defineProps<{ modelValue: Effort; disabled?: boolean; compact?: boolean; modelName?: string; statusText?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: Effort]; change: [value: Effort] }>();
const { t } = useI18n({ useScope: "global" });
const id = useId();
const levels = ["", "low", "medium", "high", "xhigh", "max"] as const;
const palettes = [
  { color: "#7c8797", gradient: "linear-gradient(110deg, #98a4b5, #c2cbd8)" },
  { color: "#159eaa", gradient: "linear-gradient(110deg, #16a6b6, #67dccb)" },
  { color: "#3498ff", gradient: "linear-gradient(110deg, #287bea, #48bbff)" },
  { color: "#6261ed", gradient: "linear-gradient(110deg, #3268ed, #8470fa, #aaa0ff)" },
  { color: "#9059f5", gradient: "linear-gradient(110deg, #4a48e8, #955af5, #cb97ff)" },
  { color: "#a451ff", gradient: "linear-gradient(110deg, #2245d8, #754dff 45%, #ba79ff 72%, #7145f8)" },
];
const stars = Array.from({ length: 18 }, (_, index) => ({
  left: ((index * 37 + 7) % 96) + "%",
  top: ((index * 23 + 17) % 78 + 11) + "%",
  size: (index % 3 === 0 ? 3 : 2) + "px",
  delay: -(index * 0.43) + "s",
}));
const livePosition = ref(Math.max(0, levels.indexOf(props.modelValue)));
const position = computed(() => livePosition.value);
const livePaletteIndex = computed(() => Math.min(levels.length - 1, Math.round(livePosition.value)));
const liveEffort = computed(() => levels[livePaletteIndex.value] || "default");
watch(() => props.modelValue, value => { if (!dragging.value) livePosition.value = Math.max(0, levels.indexOf(value)); });
const dragging = ref(false);
const label = computed(() => t(`model.reasoning.${levels[livePaletteIndex.value] || "default"}`));
function snapPosition() {
  const index = Math.max(0, Math.min(levels.length - 1, Math.round(livePosition.value)));
  livePosition.value = index;
  emit("update:modelValue", levels[index]);
  emit("change", levels[index]);
  dragging.value = false;
}
function choose(value: Effort) {
  if (props.disabled) return;
  livePosition.value = Math.max(0, levels.indexOf(value));
  emit("update:modelValue", value);
  emit("change", value);
}
function keyboard(event: KeyboardEvent) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || props.disabled) return;
  event.preventDefault();
  const next = event.key === "Home" ? 0 : event.key === "End" ? levels.length - 1 : Math.max(0, Math.min(levels.length - 1, Math.round(livePosition.value) + (event.key === "ArrowRight" ? 1 : -1)));
  livePosition.value = next;
  emit("update:modelValue", levels[next]);
  emit("change", levels[next]);
}
function update(event: Event, commit = false) {
  const raw = Number((event.target as HTMLInputElement).value);
  if (!Number.isFinite(raw) || props.disabled) return;
  livePosition.value = raw;
  dragging.value = !commit;
  if (commit) snapPosition();
}
</script>

<template>
  <div class="reasoning-slider" :data-effort="liveEffort" :style="{ '--reasoning-blue': palettes[livePaletteIndex].color }" :class="{ 'reasoning-slider--compact': compact, 'reasoning-slider--disabled': disabled }">
    <div class="reasoning-slider-card">
      <div class="reasoning-slider-heading">
        <span v-if="compact" class="reasoning-slider-caption">{{ t("model.reasoningLabel") }}</span>
        <span v-if="compact" class="reasoning-slider-status" role="status" :aria-label="t('model.reasoningSaveStatus')">{{ statusText }}</span>
        <button type="button" class="reasoning-slider-level" :disabled="disabled" :aria-label="t('model.reasoningNext')"
          @click="choose(levels[(position + 1) % levels.length])">
          <Transition name="reasoning-label" mode="out-in"><span :key="modelValue">{{ t(`model.reasoningShort.${modelValue || 'default'}`) }}</span></Transition><AppIcon name="ChevronRight" :size="16" />
        </button>
        <button type="button" class="reasoning-slider-reset" :disabled="disabled || !modelValue" :title="t('model.reasoningReset')"
          :aria-label="t('model.reasoningReset')" @click="choose('')"><AppIcon name="RotateCcw" :size="20" /></button>
        <p v-if="!compact" class="reasoning-slider-model" :title="modelName">{{ modelName || t("model.reasoningLabel") }}</p>
      </div>
      <div class="reasoning-slider-track" :style="{ '--reasoning-progress': `calc(${compact ? 16 : 22}px + (100% - ${compact ? 32 : 44}px) * ${position / (levels.length - 1)})` }">
        <div class="reasoning-slider-rail" aria-hidden="true">
          <div class="reasoning-slider-fill">
            <span v-for="(palette, index) in palettes" :key="index" class="reasoning-slider-gradient" :class="{ active: index <= Math.round(position) }" :style="{ backgroundImage: palette.gradient }" />
            <span class="reasoning-slider-shimmer" />
            <span class="reasoning-slider-stars">
              <i v-for="(star, index) in stars" :key="index" :style="{ left: star.left, top: star.top, width: star.size, height: star.size, animationDelay: star.delay }" />
            </span>
          </div>
        </div>
        <div class="reasoning-slider-ticks" aria-hidden="true">
          <i v-for="(level, index) in levels" :key="level" :class="{ filled: index < position }" />
        </div>
        <input :id="id" class="reasoning-slider-input" type="range" min="0" :max="levels.length - 1" step="0.01"
          :value="position" :disabled="disabled" :aria-label="t('model.reasoningLabel')" :aria-valuetext="label"
          :aria-describedby="compact ? undefined : `${id}-hint`"
          @input="update($event)" @change="update($event, true)" @keydown="keyboard" />
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
.reasoning-slider-rail { position: absolute; inset: 4px 0; border-radius: 999px; overflow: hidden; background: var(--border, #e7e7e9); box-shadow: inset 0 0 0 1px #00000004; }
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

/* Crossfade the palette independently of the native range input and its hit area. */
.reasoning-slider-fill { position: absolute; inset: 0 auto 0 0; width: var(--reasoning-progress); overflow: hidden; border-radius: inherit; transition: width 180ms ease-out; }
.reasoning-slider-gradient { position: absolute; inset: 0; opacity: 0; transition: opacity 360ms ease; }
.reasoning-slider-gradient.active { opacity: 1; }
.reasoning-slider-shimmer { position: absolute; inset: 0; opacity: 0; background: linear-gradient(110deg, transparent 15%, #ffffff26 45%, transparent 75%); transform: translateX(-110%); }
.reasoning-slider-stars { position: absolute; inset: 0; opacity: 0; transition: opacity 350ms ease; }
.reasoning-slider-stars i { position: absolute; border-radius: 50%; background: #fff; opacity: 0.6; box-shadow: 0 0 4px #ffffff55; }
.reasoning-slider[data-effort="high"] .reasoning-slider-shimmer,
.reasoning-slider[data-effort="xhigh"] .reasoning-slider-shimmer,
.reasoning-slider[data-effort="max"] .reasoning-slider-shimmer { opacity: 1; animation: reasoning-shimmer 6s ease-in-out infinite; }
.reasoning-slider[data-effort="xhigh"] .reasoning-slider-stars { opacity: 0.45; }
.reasoning-slider[data-effort="max"] .reasoning-slider-stars { opacity: 1; }
.reasoning-slider[data-effort="xhigh"] .reasoning-slider-stars i,
.reasoning-slider[data-effort="max"] .reasoning-slider-stars i { animation: reasoning-star 4s ease-in-out infinite alternate; }
.reasoning-slider[data-effort="max"] .reasoning-slider-gradient.active { background-size: 180% 100%; animation: reasoning-aurora 9s ease-in-out infinite alternate; }
.reasoning-slider-level { min-width: 46px; transition: color 250ms ease; }
.reasoning-slider-status { transition: color 250ms ease; }
.reasoning-slider-input::-webkit-slider-thumb { transition: box-shadow 200ms ease, border-color 200ms ease; }
.reasoning-slider-input::-moz-range-thumb { transition: box-shadow 200ms ease, border-color 200ms ease; }
.reasoning-slider-input:hover:not(:disabled)::-webkit-slider-thumb,
.reasoning-slider-input:active::-webkit-slider-thumb { border-color: color-mix(in srgb, var(--reasoning-blue) 40%, #fff); box-shadow: 0 1px 4px #0002, 0 0 0 3px color-mix(in srgb, var(--reasoning-blue) 12%, transparent); }
.reasoning-slider-input:hover:not(:disabled)::-moz-range-thumb { border-color: color-mix(in srgb, var(--reasoning-blue) 40%, #fff); }
.reasoning-slider-track:has(.reasoning-slider-input:active) .reasoning-slider-fill { transition: none; }
.reasoning-label-enter-active, .reasoning-label-leave-active { transition: opacity 110ms ease, transform 110ms ease; }
.reasoning-label-enter-from { opacity: 0; transform: translateY(4px); }
.reasoning-label-leave-to { opacity: 0; transform: translateY(-4px); }
@keyframes reasoning-shimmer { 0%, 20% { transform: translateX(-110%); } 65%, 100% { transform: translateX(110%); } }
@keyframes reasoning-star { from { opacity: 0.25; transform: translateY(1px) scale(0.8); } to { opacity: 0.8; transform: translateY(-2px) scale(1.15); } }
@keyframes reasoning-aurora { from { background-position: 0% 50%; } to { background-position: 100% 50%; } }
@media (prefers-reduced-motion: reduce) {
  .reasoning-slider *, .reasoning-slider *::before, .reasoning-slider *::after { animation: none !important; transition: none !important; }
  .reasoning-slider-input::-webkit-slider-thumb { transition: none; }
  .reasoning-slider-input::-moz-range-thumb { transition: none; }
  .reasoning-label-enter-from, .reasoning-label-leave-to { transform: none; }
}
</style>
