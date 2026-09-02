<script setup lang="ts">
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n({ useScope: "global" });

// 纯色终端主题：白 + 深底，无彩色渐变
const INK = "#e9eef6";

// 启动阶段文案随语言包变化，用 computed 保持响应式
const stages = computed(() => [
  t("splash.stageStartingService"),
  t("splash.stageConnectingRuntime"),
  t("splash.stageLoadingWorkspace"),
  t("splash.stageAlmostReady"),
]);
const stage = ref(0);
const progress = ref(0);
const ready = ref(false);

const reduced =
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let progressTimer = 0;
let probeTimer = 0;
let closed = false;

// 平滑推进进度条（视觉节奏，与实际就绪无关）
function advance(): void {
  const target = ((stage.value + 1) / stages.value.length) * 100;
  progress.value = Math.min(target, progress.value + 1);
  if (progress.value >= target && stage.value < stages.value.length - 1) {
    stage.value += 1;
  }
}

function finish(): void {
  if (closed) return;
  closed = true;
  ready.value = true;
  progress.value = 100;
  window.clearInterval(progressTimer);
  window.clearInterval(probeTimer);
  // 短暂展示就绪态后关闭窗口
  window.setTimeout(() => {
    try {
      void getCurrentWindow().close();
    } catch {
      /* 非 Tauri 环境（浏览器预览）无需关闭 */
    }
  }, 420);
}

// 轮询探测：daemon 就绪（主窗口完成引导的充分条件）即关闭
// 与主窗口的 daemon_start 调用幂等，重复调用安全
async function probe(): Promise<void> {
  if (closed) return;
  try {
    const result = await invoke<{ status: string }>("daemon_start");
    if (result?.status === "already_running") finish();
  } catch {
    // daemon 未就绪或非 Tauri 环境，继续等待
  }
}

onMounted(() => {
  // 窗口创建时隐藏，避免内容加载前闪现透明窗口
  try {
    void getCurrentWindow().show();
  } catch {
    /* 非 Tauri 环境无需显示 */
  }
  if (!reduced) progressTimer = window.setInterval(advance, 24);
  probeTimer = window.setInterval(probe, 400);
  void probe();
  // 兜底：任何意外情况下 12 秒后自动关闭
  window.setTimeout(() => {
    if (!closed) finish();
  }, 12000);
});

onBeforeUnmount(() => {
  window.clearInterval(progressTimer);
  window.clearInterval(probeTimer);
});
</script>

<template>
  <div class="splash">
    <div class="card" :class="{ ready }">
      <div class="logo" aria-hidden="true">
        <svg viewBox="0 0 112 96" fill="none">
          <!-- 终端窗体外框 -->
          <rect
            x="20" y="14" width="72" height="64" rx="14"
            :stroke="INK" stroke-width="3"
          />
          <!-- 标题栏圆点 -->
          <circle cx="31" cy="26" r="2.4" :fill="INK" opacity="0.5" />
          <circle cx="40" cy="26" r="2.4" :fill="INK" opacity="0.5" />
          <circle cx="49" cy="26" r="2.4" :fill="INK" opacity="0.5" />
          <!-- 提示符 > 与闪烁光标 _ -->
          <path
            d="M31 58 L39 52 L31 46"
            :stroke="INK" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"
          />
          <rect
            x="46" y="48.5" width="3" height="7" rx="1.5"
            :fill="INK" class="cursor"
          />
        </svg>
      </div>

      <div class="brand">SztuCode</div>
      <div class="tagline">{{ t('splash.tagline') }}</div>

      <div class="track">
        <div class="fill" :class="{ full: ready }" :style="{ width: `${progress}%` }" />
      </div>

      <div class="stage" :class="{ ready }">
        {{ ready ? t('splash.ready') : stages[stage] }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.splash {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  user-select: none;
  -webkit-user-select: none;
}

.card {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 34px 44px 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0;
  background: #0d1117;
  overflow: hidden;
  transition: none;
}

.logo {
  width: 96px;
  height: 82px;
  display: block;
}

.logo svg {
  width: 100%;
  height: 100%;
}

.cursor {
  animation: blink 1.1s steps(1) infinite;
}

.brand {
  margin-top: 18px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #ffffff;
  font-family:
    "Cascadia Code", "JetBrains Mono", "SF Mono", Consolas, "Courier New", monospace;
}

.tagline {
  margin-top: 6px;
  font-size: 12px;
  letter-spacing: 3px;
  color: rgba(233, 238, 246, 0.55);
}

.track {
  margin-top: 30px;
  width: 100%;
  height: 4px;
  border-radius: 999px;
  background: rgba(233, 238, 246, 0.14);
  overflow: hidden;
}

.fill {
  height: 100%;
  border-radius: 999px;
  background: #e9eef6;
  transition: width 120ms linear, background 260ms ease;
}

.fill.full {
  background: #ffffff;
}

.stage {
  margin-top: 12px;
  font-size: 11px;
  letter-spacing: 1.5px;
  color: rgba(233, 238, 246, 0.5);
  transition: color 260ms ease;
}

.stage.ready {
  color: #ffffff;
}

@keyframes blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .cursor {
    animation: none;
  }
  .fill {
    transition: none;
  }
  .card {
    transition: none;
  }
}
</style>
