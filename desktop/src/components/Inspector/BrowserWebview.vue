<script setup lang="ts">
import { isTauri } from "@tauri-apps/api/core";
import { Webview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  tabId: number;
  url: string;
  visible: boolean;
}>();

const emit = defineEmits<{
  loaded: [url: string];
  "load-start": [url: string];
  error: [message: string];
  "url-change": [url: string];
}>();

const host = ref<HTMLElement | null>(null);
const iframeRef = ref<HTMLIFrameElement | null>(null);
const nativeRuntime = isTauri();
let webview: Webview | null = null;
let resizeObserver: ResizeObserver | null = null;
let generation = 0;
let currentUrl = props.url;
let pollTimer: number | null = null;

function webviewLabel() {
  return `workspace-browser-${props.tabId}`;
}

async function positionWebview(instance = webview) {
  if (!nativeRuntime || !instance || !host.value) return;
  if (!props.visible) return;
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
  try { await instance.setFocus(); } catch { /* ignore focus errors */ }
}

async function closeWebview() {
  generation += 1;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  const instance = webview;
  webview = null;
  if (!instance) return;
  try {
    await instance.close();
  } catch {
    // ignore close errors
  }
}

function startUrlPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = window.setInterval(async () => {
    if (!webview || !props.visible) return;
    try {
      const url = await webview.url();
      if (url && url !== "about:blank") {
        if (url !== currentUrl) {
          currentUrl = url;
          emit("url-change", url);
        }
        // URL稳定后触发loaded
        emit("loaded", url);
      }
    } catch {
      // ignore polling errors
    }
  }, 500);
}

async function renderNativePage() {
  if (!nativeRuntime) return;
  const targetUrl = props.url;
  if (!targetUrl) return;

  if (webview) {
    try {
      currentUrl = targetUrl;
      emit("load-start", targetUrl);
      await webview.navigate(targetUrl);
      emit("loaded", targetUrl);
      setTimeout(() => emit("loaded", targetUrl), 800);
    } catch (e) {
      emit("error", String(e));
    }
    return;
  }

  await nextTick();
  const rect = host.value?.getBoundingClientRect();
  if (!rect) return;

  const currentGeneration = ++generation;

  const instance = new Webview(getCurrentWindow(), webviewLabel(), {
    url: targetUrl,
    x: props.visible ? rect.left : -10000,
    y: props.visible ? rect.top : -10000,
    width: props.visible ? rect.width : 1,
    height: props.visible ? rect.height : 1,
    focus: props.visible,
    zoomHotkeysEnabled: true,
  });
  webview = instance;
  currentUrl = targetUrl;

  instance.once("tauri://created", async () => {
    if (webview !== instance || generation !== currentGeneration) return;
    await syncVisibility(instance);
    emit("load-start", targetUrl);
    startUrlPolling();
    setTimeout(() => emit("loaded", targetUrl), 500);
  });

  instance.once<string>("tauri://error", (event) => {
    if (webview !== instance || generation !== currentGeneration) return;
    webview = null;
    void instance.close().catch(() => undefined);
    emit("error", String(event.payload));
  });
}

async function goBack() {
  if (nativeRuntime && webview) {
    emit("load-start", currentUrl);
    try {
      await webview.eval("history.back()");
      setTimeout(() => emit("loaded", currentUrl), 300);
      return true;
    } catch {
      return false;
    }
  } else if (iframeRef.value?.contentWindow) {
    emit("load-start", currentUrl);
    try {
      iframeRef.value.contentWindow.history.back();
      setTimeout(() => emit("loaded", currentUrl), 300);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

async function goForward() {
  if (nativeRuntime && webview) {
    emit("load-start", currentUrl);
    try {
      await webview.eval("history.forward()");
      setTimeout(() => emit("loaded", currentUrl), 300);
      return true;
    } catch {
      return false;
    }
  } else if (iframeRef.value?.contentWindow) {
    emit("load-start", currentUrl);
    try {
      iframeRef.value.contentWindow.history.forward();
      setTimeout(() => emit("loaded", currentUrl), 300);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

async function reload() {
  if (nativeRuntime && webview) {
    emit("load-start", currentUrl);
    try {
      await webview.eval("location.reload()");
      setTimeout(() => emit("loaded", currentUrl), 500);
      return true;
    } catch {
      try {
        await webview.navigate(currentUrl);
        setTimeout(() => emit("loaded", currentUrl), 500);
        return true;
      } catch {
        return false;
      }
    }
  } else if (iframeRef.value) {
    emit("load-start", currentUrl);
    iframeRef.value.src = currentUrl;
    return true;
  }
  return false;
}

async function navigateTo(url: string) {
  if (nativeRuntime && webview) {
    currentUrl = url;
    emit("load-start", url);
    try {
      await webview.navigate(url);
      setTimeout(() => emit("loaded", url), 500);
      return true;
    } catch (e) {
      emit("error", String(e));
      return false;
    }
  } else if (nativeRuntime) {
    await renderNativePage();
    return true;
  } else if (iframeRef.value) {
    currentUrl = url;
    emit("load-start", url);
    iframeRef.value.src = url;
    return true;
  }
  return false;
}

function onIframeLoad() {
  try {
    const iframeUrl = iframeRef.value?.contentWindow?.location.href;
    if (iframeUrl && iframeUrl !== "about:blank") {
      if (iframeUrl !== currentUrl) {
        currentUrl = iframeUrl;
        emit("url-change", iframeUrl);
      }
      emit("loaded", iframeUrl);
    } else {
      emit("loaded", currentUrl);
    }
  } catch {
    emit("loaded", currentUrl);
  }
}

const syncPosition = () => { void positionWebview(); };

watch(() => props.url, (newUrl) => {
  if (newUrl && newUrl !== currentUrl) {
    void navigateTo(newUrl);
  }
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
  if (pollTimer) clearInterval(pollTimer);
  resizeObserver?.disconnect();
  window.removeEventListener("resize", syncPosition);
  void closeWebview();
});

defineExpose({ goBack, goForward, reload, navigateTo, openDevTools: async () => {
  if (nativeRuntime && webview) {
    try {
      // @ts-ignore
      if (webview.setDevtoolsVisible) {
        // @ts-ignore
        await webview.setDevtoolsVisible(true);
      } else if (webview.eval) {
        // Fallback: try invoking the command directly
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("plugin:webview|internal_toggle_devtools", {
          label: webviewLabel(),
        });
      }
    } catch (e) {
      console.error("Failed to open DevTools:", e);
    }
  }
} });
</script>

<template>
  <div ref="host" class="browser-renderer">
    <iframe
      v-if="!nativeRuntime"
      ref="iframeRef"
      :src="url"
      title="网页预览"
      class="browser-iframe"
      @load="onIframeLoad"
    />
  </div>
</template>

<style scoped>
.browser-renderer {
  width: 100%;
  height: 100%;
  position: relative;
  background: #fff;
}

.browser-iframe {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}
</style>
