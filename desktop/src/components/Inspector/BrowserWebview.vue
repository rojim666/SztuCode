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
  /** overlay 菜单：菜单项被点击（action 为动作标识，如 edit-address） */
  "menu-action": [action: string];
  /** overlay 菜单请求关闭（点击遮罩 / Esc / resize / 失焦等） */
  "menu-close": [];
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
/** 三点菜单 overlay：透明子 webview（z-order 在浏览器 webview 之上） */
let menuWebview: Webview | null = null;

function webviewLabel() {
  return `workspace-browser-${props.tabId}`;
}

function menuLabel() {
  return `workspace-browser-menu-${props.tabId}`;
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

  function selectorOf(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 5) {
      let part = node.tagName.toLowerCase();
      const classes = Array.from(node.classList || []).filter(c => /^[a-zA-Z_][\w-]*$/.test(c)).slice(0, 2);
      if (classes.length) part += classes.map(c => '.' + CSS.escape(c)).join('');
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter(child => child.tagName === node.tagName);
        if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(node) + 1) + ')';
      }
      parts.unshift(part);
      if (node.parentElement && node.parentElement.id) { parts.unshift('#' + CSS.escape(node.parentElement.id)); break; }
      node = node.parentElement;
    }
    return parts.join(' > ');
  }
  function tagOf(el) {
    const r = el.getBoundingClientRect();
    return selectorOf(el) + '  ' + Math.round(r.width) + ' × ' + Math.round(r.height);
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
  void hideMenuOverlay();
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

// ── 三点菜单 overlay（透明子 webview，z-order 高于浏览器 webview）──
// Tauri 原生 webview 是系统级窗口，主窗口 HTML 无法覆盖其上；此处把菜单
// 本身做成同窗口内的另一个子 webview（后创建 → z-order 在上、transparent
// 背景透出下方网页），视觉上等价于 TRAE/Electron 里浮在网页上的 HTML 菜单。
// 菜单页为 data URL（无 IPC 权限），点击经 chrome.webview.postMessage →
// Rust WebMessageReceived 桥 → sztu:menu-action 事件回传主窗口。

interface MenuOverlayOptions {
  /** 无 URL 时菜单项全部禁用（与 HTML 菜单的 :disabled 行为一致） */
  disabled?: boolean;
  /** 跟随主窗口暗色主题 */
  dark?: boolean;
}

/** 菜单 overlay 页面：全区域透明遮罩（点击=关闭）+ 右上角菜单卡片 */
function buildMenuHtml(options: MenuOverlayOptions) {
  const disabled = options.disabled ? " disabled" : "";
  const dark = !!options.dark;
  const icon = (paths: string) =>
    `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
  const item = (action: string, label: string, paths: string) =>
    `<button type="button" data-action="${action}"${disabled}>${icon(paths)}${label}</button>`;
  const body = [
    item("edit-address", "编辑地址", '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>'),
    item("copy-url", "复制链接", '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>'),
    '<div class="divider"></div>',
    item("select-element", "选择元素", '<path d="M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.062z"/>'),
    item("css-inspector", "CSS检查器", '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'),
    item("device-toolbar", "设备工具栏", '<rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>'),
    item("devtools", "打开 DevTools", '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>'),
  ].join("");
  const theme = dark
    ? ".menu{background:#292929;border-color:#464646;box-shadow:0 12px 28px rgb(0 0 0/38%)}.menu button{color:#d7d7d7}.menu button:hover:not(:disabled){background:#3a3a3a;color:#fff}.divider{background:#444}"
    : "";
  return `<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;background:transparent;overflow:hidden;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none;cursor:default}
.backdrop{position:fixed;inset:0}
.menu{position:fixed;top:6px;right:9px;display:grid;min-width:156px;padding:5px;background:#fff;border:1px solid #ddd;border-radius:10px;box-shadow:0 10px 24px rgb(20 25 30/16%)}
.menu button{display:flex;align-items:center;gap:8px;width:100%;padding:8px 9px;color:#444;background:transparent;border:0;border-radius:6px;font-size:12px;text-align:left;cursor:pointer}
.menu button:hover:not(:disabled){background:#f2f3f4;color:#222}
.menu button:disabled{color:#aaa;cursor:default}
.divider{height:1px;margin:4px 3px;background:#eee}
${theme}
</style></head><body><div class="backdrop" id="backdrop"></div><div class="menu" role="menu">${body}</div>
<script>
function send(action){
  try{window.chrome.webview.postMessage('__szmenu__:'+action)}catch(e){}
}
document.getElementById('backdrop').addEventListener('click',function(){send('close')});
document.addEventListener('keydown',function(e){if(e.key==='Escape')send('close')});
var btns=document.querySelectorAll('.menu button[data-action]');
for(var i=0;i<btns.length;i++)(function(btn){
  btn.addEventListener('click',function(){if(btn.disabled)return;send(btn.getAttribute('data-action'))});
})(btns[i]);
<\/script></body></html>`;
}

/** 关闭菜单 overlay；notify=true 时向父组件抛 menu-close 同步 browserMenuOpen 状态 */
async function hideMenuOverlay(notify = true) {
  const instance = menuWebview;
  menuWebview = null;
  if (!instance) return;
  try {
    await instance.close();
  } catch {
    // ignore close errors
  }
  if (notify) emit("menu-close");
}

/** 打开菜单 overlay：覆盖浏览器舞台区域的透明子 webview，返回是否创建成功 */
async function showMenuOverlay(options: MenuOverlayOptions = {}): Promise<boolean> {
  if (!nativeRuntime) return false;
  await hideMenuOverlay(false);
  const rect = host.value?.getBoundingClientRect();
  if (!rect || rect.width < 1 || rect.height < 1) return false;
  await new Promise((r) => setTimeout(r, 30)); // 等系统完成旧实例清理

  const dataUrl = "data:text/html;charset=utf-8," + encodeURIComponent(buildMenuHtml(options));
  let instance: Webview;
  try {
    instance = new Webview(getCurrentWindow(), menuLabel(), {
      url: dataUrl,
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
      focus: true,
      transparent: true,
    });
  } catch {
    return false;
  }
  menuWebview = instance;
  // 只有子 webview 创建成功且消息桥挂载完成后才切换到原生菜单；否则父组件
  // 继续显示 HTML 回退菜单，避免出现“状态已打开但界面上什么都没有”。
  const ready = await new Promise<boolean>((resolve) => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      resolve(ok);
    };
    const timeout = window.setTimeout(() => finish(false), 2_000);
    instance.once("tauri://error", () => finish(false));
    instance.once("tauri://created", async () => {
      try {
        await invoke<void>("browser_menu_attach", { label: menuLabel() });
        finish(true);
      } catch {
        finish(false);
      }
    });
  });
  if (!ready && menuWebview === instance) await hideMenuOverlay(false);
  return ready;
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

/** 视口/舞台尺寸变化：菜单 overlay 位置失效，直接关闭（父组件经 menu-close 同步状态） */
function handleViewportShift() {
  if (menuWebview) void hideMenuOverlay();
  void positionWebview();
}

watch(() => props.url, (newUrl) => {
  if (newUrl && newUrl !== currentUrl) {
    void navigateTo(newUrl);
  }
});
watch(() => props.visible, async () => {
  if (!props.visible && menuWebview) void hideMenuOverlay();
  await nextTick();
  void syncVisibility();
});

/** Rust 原生桥广播的事件监听句柄（sztu:element-picked / sztu:menu-action） */
let unlistenPick: UnlistenFn | null = null;
let unlistenMenu: UnlistenFn | null = null;

onMounted(async () => {
  resizeObserver = new ResizeObserver(handleViewportShift);
  if (host.value) resizeObserver.observe(host.value);
  window.addEventListener("resize", handleViewportShift);
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
    // 菜单 overlay 主通道：Rust 侧 WebView2 WebMessageReceived 转发的事件
    try {
      unlistenMenu = await listen<{ label: string; action: string }>(
        "sztu:menu-action",
        (event) => {
          if (event.payload.label !== menuLabel()) return;
          const action = event.payload.action;
          if (action === "close") {
            void hideMenuOverlay(); // 抛 menu-close → 父组件复位 browserMenuOpen
          } else {
            void hideMenuOverlay(false); // 状态复位交给 menu-action 处理器
            emit("menu-action", action);
          }
        },
      );
    } catch {
      // 监听失败时菜单退化为隐藏网页模式（showMenuOverlay 返回 false 前已处理）
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
  if (unlistenMenu) {
    unlistenMenu();
    unlistenMenu = null;
  }
  resizeObserver?.disconnect();
  window.removeEventListener("resize", handleViewportShift);
  void closeWebview();
});

defineExpose({
  goBack,
  goForward,
  reload,
  navigateTo,
  startElementPicker,
  showMenuOverlay,
  hideMenuOverlay,
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
