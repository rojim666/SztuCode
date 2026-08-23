<script setup lang="ts">
import { isTauri } from "@tauri-apps/api/core";
import { Webview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  tabId: number;
  url: string;
  reloadKey: number;
  visible: boolean;
}>();

const emit = defineEmits<{
  loaded: [];
  error: [message: string];
}>();

const host = ref<HTMLElement | null>(null);
const nativeRuntime = isTauri();
let webview: Webview | null = null;
let resizeObserver: ResizeObserver | null = null;
let generation = 0;
const syncPosition = () => { void positionWebview(); };

function webviewLabel() {
  return `workspace-browser-${props.tabId}`;
}

async function positionWebview(instance = webview) {
  if (!nativeRuntime || !instance || !host.value || !props.visible) return;
  const rect = host.value.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return;
  await Promise.all([
    instance.setPosition({ type: "Logical", x: rect.left, y: rect.top }),
    instance.setSize({ type: "Logical", width: rect.width, height: rect.height }),
  ]);
}

async function syncVisibility(instance = webview) {
  if (!nativeRuntime || !instance) return;
  if (!props.visible) {
    await instance.hide();
    return;
  }
  await positionWebview(instance);
  await instance.show();
}

async function closeWebview() {
  generation += 1;
  const instance = webview;
  webview = null;
  if (!instance) return;
  try {
    await instance.close();
  } catch {
    // The runtime may already have removed a view whose navigation failed.
  }
}

async function renderNativePage() {
  if (!nativeRuntime) return;
  await closeWebview();
  if (!props.url) return;
  await nextTick();
  const rect = host.value?.getBoundingClientRect();
  if (!rect || rect.width < 1 || rect.height < 1) return;

  const currentGeneration = ++generation;
  const initialRect = props.visible ? rect : { left: -10_000, top: -10_000, width: 1, height: 1 };
  const instance = new Webview(getCurrentWindow(), webviewLabel(), {
    url: props.url,
    x: initialRect.left,
    y: initialRect.top,
    width: initialRect.width,
    height: initialRect.height,
    focus: props.visible,
    zoomHotkeysEnabled: true,
  });
  webview = instance;
  instance.once("tauri://created", async () => {
    if (webview !== instance || generation !== currentGeneration) return;
    await syncVisibility(instance);
    emit("loaded");
  });
  instance.once<string>("tauri://error", (event) => {
    if (webview !== instance || generation !== currentGeneration) return;
    webview = null;
    // 失败实例立即关闭，避免残留失效 webview 泄漏资源
    void instance.close().catch(() => undefined);
    emit("error", String(event.payload));
  });
}

watch(() => [props.url, props.reloadKey], () => {
  void renderNativePage();
});
watch(() => props.visible, () => {
  void syncVisibility();
});

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    void positionWebview();
  });
  if (host.value) resizeObserver.observe(host.value);
  window.addEventListener("resize", syncPosition);
  void renderNativePage();
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  window.removeEventListener("resize", syncPosition);
  void closeWebview();
});
</script>

<template>
  <div ref="host" class="browser-renderer">
    <iframe
      v-if="!nativeRuntime && url"
      :key="reloadKey"
      :src="url"
      title="网页预览"
      @load="emit('loaded')"
    />
  </div>
</template>
