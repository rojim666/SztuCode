<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

defineProps<{ active?: boolean }>();
const root = ref<HTMLElement | null>(null);
function trackPointer(event: PointerEvent) {
  const el = root.value;
  if (!el) return;
  const box = el.getBoundingClientRect();
  const dx = event.clientX - (box.left + box.width / 2);
  const dy = event.clientY - (box.top + box.height / 2);
  const distance = Math.hypot(dx, dy) || 1;
  const amount = Math.min(distance / 180, 1) * 2.8;
  el.style.setProperty("--look-x", `${(dx / distance * amount).toFixed(2)}px`);
  el.style.setProperty("--look-y", `${(dy / distance * amount).toFixed(2)}px`);
}
onMounted(() => window.addEventListener("pointermove", trackPointer, { passive: true }));
onBeforeUnmount(() => window.removeEventListener("pointermove", trackPointer));
</script>

<template>
  <div ref="root" class="app-icon theme-light" :class="{ active }">
    <div class="logo" role="img" aria-label="SztuCode Agent">
      <div class="dots"><i /><i /><i /></div>
      <div class="eyes">
        <div class="eye left"><div class="pupil" /></div>
        <div class="eye right"><div class="pupil" /></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-icon { --logo-size: 38px; --look-x: 0px; --look-y: 0px; position: relative; width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; }
.logo { position: relative; width: var(--logo-size); height: var(--logo-size); color: #1c2330; border: 3.2px solid currentColor; border-radius: 22%; background: #f4f6fa; }
.dots { position: absolute; top: 9%; left: 10%; display: flex; gap: calc(var(--logo-size) * .045); }
.dots i { width: calc(var(--logo-size) * .085); height: calc(var(--logo-size) * .085); border-radius: 50%; background: currentColor; }
.dots i:nth-child(2) { animation-delay: .22s; } .dots i:nth-child(3) { animation-delay: .44s; }
.eyes { position: absolute; top: 38%; right: 0; left: 0; height: 34%; display: flex; align-items: center; justify-content: center; gap: calc(var(--logo-size) * .10); }
.eye { position: relative; width: calc(var(--logo-size) * .20); height: calc(var(--logo-size) * .30); transform: translate(var(--look-x), var(--look-y)); transition: transform .16s ease-out; }
.pupil { position: absolute; inset: 0; border-radius: calc(var(--logo-size) * .09); background: currentColor; transform-origin: center; animation: blink 5.8s cubic-bezier(.42,0,.58,1) infinite; }
.active .dots i { animation: dot-pulse 1.8s ease-in-out infinite; }
@keyframes dot-pulse { 0%,100% { opacity: .72; transform: scale(.9); } 16% { opacity: 1; transform: scale(1.08); box-shadow: 0 0 5px currentColor; } 32%,72% { opacity: .78; transform: scale(1); } }
@keyframes blink { 0%,43% { transform: translateY(0) scaleY(1) scaleX(1); } 46% { transform: translateY(2%) scaleY(.72) scaleX(.98); } 48.5%,51% { transform: translateY(5%) scaleY(.08) scaleX(.92); } 54% { transform: translateY(1%) scaleY(.78) scaleX(.98); } 58%,100% { transform: translateY(0) scaleY(1) scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .dots i, .eye, .pupil { animation: none; } }
:global(:root[data-app-theme="dark"]) .logo { color: #eef2f8; background: #0b0e14; }
</style>
