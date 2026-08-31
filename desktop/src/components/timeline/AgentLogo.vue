<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps<{ active?: boolean; size?: "small" | "large" }>();
const root = ref<HTMLElement | null>(null);
// 主题适配：浅色模式黑底白瞳，深色模式白底黑瞳；跟随 data-app-theme 属性实时同步
const themeDark = ref(false);
let themeObserver: MutationObserver | null = null;
function syncTheme() {
  themeDark.value = document.documentElement.dataset.appTheme === "dark";
}

type Expression = "normal" | "happy" | "sleep" | "squint";
const expression = ref<Expression>("normal");
let randomTimer: number | null = null;
let expressionTimer: number | null = null;

const expressions: Expression[] = ["happy", "sleep", "squint"];

function clearTimers() {
  if (randomTimer !== null) {
    clearTimeout(randomTimer);
    randomTimer = null;
  }
  if (expressionTimer !== null) {
    clearTimeout(expressionTimer);
    expressionTimer = null;
  }
}

function triggerRandomExpression() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const next = expressions[Math.floor(Math.random() * expressions.length)];
  expression.value = next;
  const duration = next === "sleep" ? 2200 + Math.random() * 1500 : 1200 + Math.random() * 800;
  expressionTimer = window.setTimeout(() => {
    expression.value = "normal";
    scheduleNext();
  }, duration);
}

function scheduleNext() {
  const delay = 4000 + Math.random() * 8000;
  randomTimer = window.setTimeout(triggerRandomExpression, delay);
}

function trackPointer(event: PointerEvent) {
  if (expression.value !== "normal") return;
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

onMounted(() => {
  window.addEventListener("pointermove", trackPointer, { passive: true });
  syncTheme();
  themeObserver = new MutationObserver(syncTheme);
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-app-theme"] });
  scheduleNext();
});

onBeforeUnmount(() => {
  window.removeEventListener("pointermove", trackPointer);
  themeObserver?.disconnect();
  themeObserver = null;
  clearTimers();
});
</script>

<template>
  <div
    ref="root"
    class="app-icon"
    :class="[
      { active: props.active, 'theme-dark': themeDark },
      `app-icon--${props.size ?? 'small'}`,
      `expr-${expression}`,
    ]"
  >
    <div class="logo" role="img" aria-label="SztuCode Agent">
      <div class="dots"><i /><i /><i /></div>
      <div class="eyes">
        <div class="eye left">
          <div class="pupil" />
          <div class="eye-closed" />
          <div class="eye-happy" />
          <div class="eye-squint" />
        </div>
        <div class="eye right">
          <div class="pupil" />
          <div class="eye-closed" />
          <div class="eye-happy" />
          <div class="eye-squint" />
        </div>
      </div>
      <div class="zzz"><span>z</span><span>z</span><span>z</span></div>
      <div class="blush blush-left" />
      <div class="blush blush-right" />
    </div>
  </div>
</template>

<style scoped>
.app-icon {
  --logo-size: 32px;
  --look-x: 0px;
  --look-y: 0px;
  position: relative;
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.logo {
  position: relative;
  width: var(--logo-size);
  height: var(--logo-size);
  color: #fff;
  border: 0;
  border-radius: 26%;
  background: #000;
  box-shadow: none;
  overflow: hidden;
}
/* 深色主题：白底黑瞳；浅色主题保持默认的黑底白瞳 */
.app-icon.theme-dark .logo {
  color: #000;
  border: 1px solid #d9dddf;
  background: #fff;
  box-shadow: 0 1px 3px rgb(0 0 0 / 18%);
}
.app-icon--large { --logo-size: 48px; width: 62px; height: 62px; }

.dots {
  position: absolute;
  top: 15%;
  left: 13%;
  display: flex;
  gap: calc(var(--logo-size) * .045);
}
.dots i {
  width: calc(var(--logo-size) * .085);
  height: calc(var(--logo-size) * .085);
  border-radius: 50%;
  background: currentColor;
}
.dots i:nth-child(2) { animation-delay: .22s; }
.dots i:nth-child(3) { animation-delay: .44s; }

.eyes {
  position: absolute;
  top: 38%;
  right: 0;
  left: 0;
  height: 34%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: calc(var(--logo-size) * .10);
}
.eye {
  position: relative;
  width: calc(var(--logo-size) * .20);
  height: calc(var(--logo-size) * .30);
  transform: translate(var(--look-x), var(--look-y));
  transition: transform .16s ease-out;
}

/* Normal pupil */
.pupil {
  position: absolute;
  inset: 0;
  border-radius: calc(var(--logo-size) * .09);
  background: currentColor;
  transform-origin: center;
  animation: blink 5.8s cubic-bezier(.42,0,.58,1) infinite;
  transition: opacity .2s ease, transform .2s ease;
}

/* Eye shapes (hidden by default) */
.eye-closed,
.eye-happy,
.eye-squint {
  position: absolute;
  left: 0;
  right: 0;
  background: currentColor;
  opacity: 0;
  transition: opacity .18s ease;
}

/* Closed eye (sleep) - horizontal line */
.eye-closed {
  top: 50%;
  height: calc(var(--logo-size) * .06);
  border-radius: 999px;
  transform: translateY(-50%) scaleX(0);
  transition: opacity .18s ease, transform .25s cubic-bezier(.4,0,.2,1);
}

/* Happy eye - curved arc (using border-radius trick for smile shape) */
.eye-happy {
  bottom: 0;
  height: 80%;
  border-radius: 0 0 calc(var(--logo-size) * .22) calc(var(--logo-size) * .22);
  clip-path: inset(45% 0 0 0);
  transform: scaleY(0);
  transform-origin: bottom center;
  transition: opacity .18s ease, transform .3s cubic-bezier(.34,1.56,.64,1);
}

/* Squint eye - thin horizontal line, slightly curved */
.eye-squint {
  top: 50%;
  height: calc(var(--logo-size) * .05);
  border-radius: 999px;
  transform: translateY(-50%) scaleX(0.3);
  transition: opacity .15s ease, transform .2s ease;
}

/* Zzz for sleep */
.zzz {
  position: absolute;
  top: 8%;
  right: 10%;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  line-height: 1;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity .3s ease, transform .3s ease;
  pointer-events: none;
}
.zzz span {
  font-family: "Cascadia Code", "JetBrains Mono", monospace;
  font-weight: 700;
  color: currentColor;
  opacity: 0;
  transform: translateY(2px);
}
.zzz span:nth-child(1) { font-size: calc(var(--logo-size) * .18); }
.zzz span:nth-child(2) { font-size: calc(var(--logo-size) * .24); }
.zzz span:nth-child(3) { font-size: calc(var(--logo-size) * .30); }

/* Blush for happy */
.blush {
  position: absolute;
  bottom: 20%;
  width: calc(var(--logo-size) * .14);
  height: calc(var(--logo-size) * .08);
  border-radius: 50%;
  background: rgba(255, 120, 130, 0.6);
  opacity: 0;
  transform: scale(0);
  transition: opacity .25s ease, transform .25s cubic-bezier(.34,1.56,.64,1);
}
.blush-left { left: 10%; }
.blush-right { right: 10%; }

/* ===== Active state (dots pulse) ===== */
.active .dots i { animation: dot-pulse 1.8s ease-in-out infinite; }
@keyframes dot-pulse {
  0%,100% { opacity: .72; transform: scale(.9); }
  16% { opacity: 1; transform: scale(1.08); box-shadow: 0 0 5px currentColor; }
  32%,72% { opacity: .78; transform: scale(1); }
}

@keyframes blink {
  0%,43% { transform: translateY(0) scaleY(1) scaleX(1); }
  46% { transform: translateY(2%) scaleY(.72) scaleX(.98); }
  48.5%,51% { transform: translateY(5%) scaleY(.08) scaleX(.92); }
  54% { transform: translateY(1%) scaleY(.78) scaleX(.98); }
  58%,100% { transform: translateY(0) scaleY(1) scaleX(1); }
}

/* ===== Expression: Happy ===== */
.expr-happy .pupil { opacity: 0; }
.expr-happy .eye-happy {
  opacity: 1;
  transform: scaleY(1);
}
.expr-happy .blush {
  opacity: 1;
  transform: scale(1);
}
.expr-happy .blush-left { transition-delay: .1s; }
.expr-happy .blush-right { transition-delay: .15s; }
.expr-happy .eye { transform: translate(var(--look-x), calc(var(--look-y) - 2%)); }

/* ===== Expression: Sleep ===== */
.expr-sleep .pupil { opacity: 0; animation: none; }
.expr-sleep .eye-closed {
  opacity: 1;
  transform: translateY(-50%) scaleX(1);
}
.expr-sleep .zzz {
  opacity: 1;
  transform: translateY(0);
  animation: zzz-float 2s ease-in-out infinite;
}
.expr-sleep .zzz span {
  animation: zzz-pop 1.6s ease-in-out infinite;
}
.expr-sleep .zzz span:nth-child(1) { animation-delay: 0s; }
.expr-sleep .zzz span:nth-child(2) { animation-delay: .25s; }
.expr-sleep .zzz span:nth-child(3) { animation-delay: .5s; }
.expr-sleep .dots i { animation: dot-breathe 3s ease-in-out infinite; }
.expr-sleep .dots i:nth-child(2) { animation-delay: .4s; }
.expr-sleep .dots i:nth-child(3) { animation-delay: .8s; }

@keyframes zzz-float {
  0%,100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
@keyframes zzz-pop {
  0% { opacity: 0; transform: translateY(4px) scale(.7); }
  30% { opacity: .9; transform: translateY(0) scale(1); }
  80% { opacity: .5; transform: translateY(-3px) scale(.9); }
  100% { opacity: 0; transform: translateY(-6px) scale(.7); }
}
@keyframes dot-breathe {
  0%,100% { opacity: .35; transform: scale(.8); }
  50% { opacity: .6; transform: scale(.95); }
}

/* ===== Expression: Squint ===== */
.expr-squint .pupil { opacity: 0; }
.expr-squint .eye-squint {
  opacity: 1;
  transform: translateY(-50%) scaleX(1);
}
.expr-squint .eye { transform: translate(calc(var(--look-x) * .5), calc(var(--look-y) * .3 + 8%)); }

/* ===== Reduced motion ===== */
@media (prefers-reduced-motion: reduce) {
  .dots i, .eye, .pupil, .zzz, .zzz span, .blush { animation: none !important; }
}
</style>
