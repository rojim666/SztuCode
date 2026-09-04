<script lang="ts">
/** 元素选择器捕获的元素信息 */
export interface PickedElement {
  tag: string;
  id: string;
  classes: string[];
  width: number;
  height: number;
  text: string;
  html: string;
  ts?: number;
  style: {
    display: string;
    position: string;
    font: string;
    color: string;
    background: string;
    margin: string;
    padding: string;
  };
  attrs: Record<string, string>;
}
</script>

<script setup lang="ts">
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Webview, getAllWebviews } from "@tauri-apps/api/webview";
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
  "element-picked": [data: PickedElement];
}>();

const host = ref<HTMLElement | null>(null);
const iframeRef = ref<HTMLIFrameElement | null>(null);
const nativeRuntime = isTauri();
let webview: Webview | null = null;
let resizeObserver: ResizeObserver | null = null;
let generation = 0;
let currentUrl = props.url;
let pollTimer: number | null = null;
let closePromise: Promise<void> | null = null;

function webviewLabel() {
  return `workspace-browser-${props.tabId}`;
}

/**
 * 注入到网页中的元素选择器脚本（Trae Work 风格）：
 * - 十字光标 + hover 高亮框 + 元素徽标（tag#id.class × 宽高，滚动/缩放跟随）
 * - 顶部提示胶囊（点击选择元素 · Esc 取消）
 * - 点击捕获 → 绿色确认反馈 → deliver() 回传数据：
 *   主通道 chrome.webview.postMessage('__szpk__:<json>')（Rust 侧原生
 *   WebMessageReceived 监听器转发，不经过 Tauri IPC，远程页面零权限可用）；
 *   主通道不可用时退化为 location.hash（#szpk=<encoded json>，主窗口轮询读取）
 * - 每条数据带 ts 时间戳，主窗口据此对两条通道去重
 * - Esc 退出；再次注入为切换开关；页面导航后脚本随文档销毁（需重新点击按钮）
 */
function buildPickerScript(useNative: boolean) {
  return String.raw`
(() => {
  if (window.__sztuPicker) {
    window.__sztuPicker.active ? window.__sztuPicker.stop() : window.__sztuPicker.start();
    return;
  }
  const USE_NATIVE = ${useNative};
  const OVERLAY_STYLE = 'border:1.5px solid #4c8dff;background:rgba(76,141,255,.13);';
  let active = false, hovered = null, overlay = null, badge = null, tipbar = null, prevCursor = '';

  function ensure() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;border-radius:2px;box-shadow:0 0 0 1px rgba(76,141,255,.4);display:none;' + OVERLAY_STYLE;
    badge = document.createElement('div');
    badge.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;background:#1d2733;color:#fff;padding:3px 8px;font:11px/1.5 ui-monospace,Consolas,monospace;border-radius:4px;display:none;white-space:nowrap;max-width:88vw;overflow:hidden;text-overflow:ellipsis;';
    tipbar = document.createElement('div');
    tipbar.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483647;pointer-events:none;background:#1d2733;color:#fff;padding:5px 14px;font:12px/1.4 system-ui,-apple-system,sans-serif;border-radius:999px;box-shadow:0 2px 10px rgba(0,0,0,.28);display:none;';
    tipbar.textContent = '点击选择元素 · Esc 取消';
    document.documentElement.appendChild(overlay);
    document.documentElement.appendChild(badge);
    document.documentElement.appendChild(tipbar);
  }

  function resetVisual() {
    overlay.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;border-radius:2px;box-shadow:0 0 0 1px rgba(76,141,255,.4);display:none;' + OVERLAY_STYLE;
    badge.style.background = '#1d2733';
  }

  function tagOf(el) {
    const r = el.getBoundingClientRect();
    const cls = el.classList && el.classList.length ? '.' + Array.from(el.classList).slice(0, 2).join('.') : '';
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls + '  ' + Math.round(r.width) + ' × ' + Math.round(r.height);
  }

  function draw() {
    if (!hovered || !hovered.getBoundingClientRect) { hide(); return; }
    const r = hovered.getBoundingClientRect();
    if (!r.width && !r.height) { hide(); return; }
    overlay.style.display = 'block';
    overlay.style.left = r.left + 'px';
    overlay.style.top = r.top + 'px';
    overlay.style.width = r.width + 'px';
    overlay.style.height = r.height + 'px';
    badge.style.display = 'block';
    badge.textContent = tagOf(hovered);
    badge.style.left = Math.max(2, Math.min(r.left, window.innerWidth - 220)) + 'px';
    badge.style.top = (r.top > 28 ? r.top - 28 : r.top + r.height + 4) + 'px';
  }

  function hide() {
    if (overlay) overlay.style.display = 'none';
    if (badge) badge.style.display = 'none';
  }

  function onMove(e) {
    if (!active) return;
    const el = document.elementFromPoint(e.clientX, e.clientY);
    if (!el || el === overlay || el === badge) return;
    hovered = el;
    draw();
  }

  function onReflow() { if (active) draw(); }

  function deliver(json) {
    if (USE_NATIVE) {
      try {
        if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
          window.chrome.webview.postMessage('__szpk__:' + json);
          return;
        }
      } catch (e) { /* fallthrough */ }
    }
    try { location.hash = 'szpk=' + encodeURIComponent(json); } catch (e) { /* ignore */ }
  }

  function send(el) {
    const r = el.getBoundingClientRect();
    const cs = window.getComputedStyle(el);
    const data = {
      tag: el.tagName.toLowerCase(),
      id: el.id || '',
      classes: Array.from(el.classList || []).slice(0, 20),
      width: Math.round(r.width),
      height: Math.round(r.height),
      text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 160),
      html: el.outerHTML.slice(0, 4000),
      ts: Date.now(),
      style: {
        display: cs.display,
        position: cs.position,
        font: cs.fontSize + ' ' + String(cs.fontFamily).split(',')[0].replace(/["']/g, ''),
        color: cs.color,
        background: cs.backgroundColor,
        margin: cs.margin,
        padding: cs.padding
      },
      attrs: Object.fromEntries(Array.from(el.attributes || []).slice(0, 30).map(a => [a.name, a.value]))
    };
    deliver(JSON.stringify(data));
  }

  function onClick(e) {
    if (!active) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const el = hovered || e.target;
    if (el && el.tagName) {
      send(el);
      // 选中确认反馈：绿色一闪，随后退出点选模式
      overlay.style.border = '1.5px solid #22c55e';
      overlay.style.background = 'rgba(34,197,94,.16)';
      overlay.style.boxShadow = '0 0 0 1px rgba(34,197,94,.45)';
      badge.textContent = '✓ 已捕获元素';
      badge.style.background = '#15803d';
      setTimeout(() => window.__sztuPicker.stop(), 350);
    } else {
      window.__sztuPicker.stop();
    }
  }

  function onKey(e) {
    if (e.key === 'Escape' && active) {
      e.preventDefault();
      e.stopPropagation();
      window.__sztuPicker.stop();
    }
  }

  function start() {
    ensure();
    if (active) return;
    active = true;
    resetVisual();
    if (document.body) {
      prevCursor = document.body.style.cursor;
      document.body.style.cursor = 'crosshair';
    }
    tipbar.style.display = 'block';
    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('scroll', onReflow, true);
    window.addEventListener('resize', onReflow, true);
  }

  function stop() {
    active = false;
    hovered = null;
    hide();
    if (tipbar) tipbar.style.display = 'none';
    if (document.body) document.body.style.cursor = prevCursor;
    document.removeEventListener('mousemove', onMove, true);
    document.removeEventListener('click', onClick, true);
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('scroll', onReflow, true);
    window.removeEventListener('resize', onReflow, true);
  }

  window.__sztuPicker = { start, stop, get active() { return active; } };
  start();
})()
`;
}

/** 选择器激活时改用 150ms 快速轮询检测 #szpk= 后备结果；lastPickTs 用于两条通道去重 */
let pickerActive = false;
let lastPickTs = 0;
/** WebView2 原生消息桥是否已挂载（webview 创建后 attach，失败时走 hash 后备） */
let pickerBridgeReady = false;

/** 统一入口：按 ts 去重后向父组件抛出 element-picked */
function handlePickData(data: PickedElement) {
  const ts = typeof data.ts === "number" ? data.ts : 0;
  if (ts && ts <= lastPickTs) return;
  lastPickTs = ts || Date.now();
  if (pickerActive) {
    pickerActive = false;
    restartUrlPolling();
  }
  emit("element-picked", data);
}

/** 在 Rust 侧为 webview 注册原生 WebMessageReceived 监听器（元素数据主通道） */
async function attachPickBridge() {
  if (!nativeRuntime || !webview) return false;
  try {
    await invoke<void>("browser_webview_attach_picker", { label: webviewLabel() });
    pickerBridgeReady = true;
    return true;
  } catch {
    return false;
  }
}

/** 启动元素选择器：确保数据桥可用，注入选择脚本（页内幂等开关），并激活快速轮询（hash 后备） */
async function startElementPicker() {
  if (!nativeRuntime || !webview) {
    throw new Error("网页尚未加载");
  }
  if (!pickerBridgeReady) {
    await attachPickBridge();
  }
  pickerActive = true;
  restartUrlPolling();
  const script = buildPickerScript(pickerBridgeReady);
  try {
    await evalInWebview(script);
  } catch {
    // 页面可能正在跳转，稍候重试一次
    await new Promise((resolve) => setTimeout(resolve, 200));
    await evalInWebview(script);
  }
}

/** 在 webview 中执行 JS（经 Rust 命令桥接，JS API 无 eval 方法） */
function evalInWebview(code: string) {
  return invoke<void>("browser_webview_eval", { label: webviewLabel(), code });
}

/** 获取 webview 当前 URL（经 Rust 命令桥接） */
function getWebviewUrl() {
  return invoke<string>("browser_webview_url", { label: webviewLabel() });
}

/** 导航 webview 到指定 URL（经 Rust 命令桥接） */
function navigateWebviewTo(url: string) {
  return invoke<void>("browser_webview_navigate", { label: webviewLabel(), url });
}

/**
 * 确保同名旧webview被完全关闭，解决竞态问题
 */
async function ensureExistingClosed() {
  if (!nativeRuntime) return;
  if (closePromise) {
    try { await closePromise; } catch { /* ignore */ }
    closePromise = null;
  }
  try {
    const existing = await getAllWebviews();
    const label = webviewLabel();
    const stale = existing.find(w => w.label === label);
    if (stale) {
      try {
        await stale.close();
        // 给系统一点时间完成清理
        await new Promise(r => setTimeout(r, 50));
      } catch { /* ignore */ }
    }
  } catch { /* ignore getAll errors */ }
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
  closePromise = (async () => {
    try {
      await instance.close();
    } catch {
      // ignore close errors
    } finally {
      closePromise = null;
    }
  })();
  await closePromise;
}

/** 轮询 webview URL：同步地址栏 + 拾取元素选择器写入的 #szpk= 结果 */
function restartUrlPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = window.setInterval(pollUrlTick, pickerActive ? 150 : 500);
}

async function pollUrlTick() {
  if (!webview || !props.visible) return;
  let url: string;
  try {
    url = await getWebviewUrl();
  } catch {
    return;
  }
  if (!url || url === "about:blank") return;

  // 元素选择器 hash 后备结果：#szpk=<encoded JSON>
  const mark = url.indexOf("#szpk=");
  if (mark >= 0) {
    const raw = url.slice(mark + 6);
    if (raw) {
      try {
        handlePickData(JSON.parse(decodeURIComponent(raw)) as PickedElement);
      } catch {
        // ignore 解析错误
      }
    }
    // 清理 hash（replaceState 不新增历史记录）
    void evalInWebview("try{history.replaceState(null,'',location.pathname+location.search)}catch(e){}").catch(() => {});
    const cleanUrl = url.slice(0, mark);
    if (cleanUrl !== currentUrl) {
      currentUrl = cleanUrl;
      emit("url-change", cleanUrl);
    }
    emit("loaded", cleanUrl);
    return;
  }

  if (url !== currentUrl) {
    // 真实导航：注入的选择器脚本随旧页面销毁，退出快速轮询
    if (pickerActive) {
      pickerActive = false;
      restartUrlPolling();
    }
    currentUrl = url;
    emit("url-change", url);
  }
  // URL稳定后触发loaded
  emit("loaded", url);
}

async function renderNativePage(retryCount = 0) {
  if (!nativeRuntime) return;
  const targetUrl = props.url;
  if (!targetUrl) return;

  if (webview) {
    try {
      currentUrl = targetUrl;
      emit("load-start", targetUrl);
      await navigateWebviewTo(targetUrl);
      emit("loaded", targetUrl);
      setTimeout(() => emit("loaded", targetUrl), 800);
    } catch (e) {
      emit("error", String(e));
    }
    return;
  }

  // 先确保旧实例完全关闭
  await ensureExistingClosed();

  await nextTick();
  const rect = host.value?.getBoundingClientRect();
  if (!rect) return;

  const currentGeneration = ++generation;

  let instance: Webview | null = null;
  try {
    instance = new Webview(getCurrentWindow(), webviewLabel(), {
      url: targetUrl,
      x: props.visible ? rect.left : -10000,
      y: props.visible ? rect.top : -10000,
      width: props.visible ? rect.width : 1,
      height: props.visible ? rect.height : 1,
      focus: props.visible,
      zoomHotkeysEnabled: true,
    });
  } catch (createErr) {
    // 如果创建失败（标签已存在），重试最多2次
    if (retryCount < 2) {
      await new Promise(r => setTimeout(r, 100 * (retryCount + 1)));
      await ensureExistingClosed();
      return renderNativePage(retryCount + 1);
    }
    emit("error", String(createErr));
    return;
  }

  webview = instance;
  currentUrl = targetUrl;
  // 新 webview 实例：原生消息桥需在 created 后重新挂载
  pickerBridgeReady = false;

  instance.once("tauri://created", async () => {
    if (webview !== instance || generation !== currentGeneration) return;
    await syncVisibility(instance);
    emit("load-start", targetUrl);
    restartUrlPolling();
    // 挂载元素选择器原生数据桥（失败时注入脚本自动退化为 hash 通道）
    void attachPickBridge();
    setTimeout(() => emit("loaded", targetUrl), 500);
  });

  instance.once<string>("tauri://error", async (event) => {
    if (webview !== instance || generation !== currentGeneration) return;
    webview = null;
    // 如果错误是标签已存在，尝试重试
    const errMsg = String(event.payload);
    if (errMsg.includes("already exists") && retryCount < 2) {
      await ensureExistingClosed();
      await new Promise(r => setTimeout(r, 100 * (retryCount + 1)));
      return renderNativePage(retryCount + 1);
    }
    void instance?.close().catch(() => undefined);
    emit("error", errMsg);
  });
}

async function goBack() {
  if (nativeRuntime && webview) {
    emit("load-start", currentUrl);
    try {
      await evalInWebview("history.back()");
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
      await evalInWebview("history.forward()");
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
      await evalInWebview("location.reload()");
      setTimeout(() => emit("loaded", currentUrl), 500);
      return true;
    } catch {
      try {
        await navigateWebviewTo(currentUrl);
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
      await navigateWebviewTo(url);
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

/** Rust 原生桥广播的事件监听句柄（sztu:element-picked） */
let unlistenPick: UnlistenFn | null = null;

onMounted(async () => {
  resizeObserver = new ResizeObserver(() => {
    void positionWebview();
  });
  if (host.value) resizeObserver.observe(host.value);
  window.addEventListener("resize", syncPosition);
  // 元素选择器主通道：Rust 侧 WebView2 WebMessageReceived 转发的事件
  if (nativeRuntime) {
    try {
      unlistenPick = await listen<{ label: string; payload: string }>(
        "sztu:element-picked",
        (event) => {
          const { label, payload } = event.payload;
          if (label !== webviewLabel()) return; // 忽略其他浏览器标签页的选择
          try {
            handlePickData(JSON.parse(payload) as PickedElement);
          } catch {
            // ignore 解析错误
          }
        },
      );
    } catch {
      // 监听失败时 hash 后备通道仍可用
    }
  }
  void renderNativePage();
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (unlistenPick) {
    unlistenPick();
    unlistenPick = null;
  }
  resizeObserver?.disconnect();
  window.removeEventListener("resize", syncPosition);
  void closeWebview();
});

defineExpose({
  goBack,
  goForward,
  reload,
  navigateTo,
  startElementPicker,
  /** 切换 DevTools，返回 true=已打开 / false=已关闭，失败时抛错 */
  openDevTools: async (): Promise<boolean> => {
    if (!nativeRuntime || !webview) {
      throw new Error("网页尚未加载");
    }
    return invoke<boolean>("browser_webview_toggle_devtools", {
      label: webviewLabel(),
    });
  },
});
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
