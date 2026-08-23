import { createApp } from "vue";
import { getCurrentWindow } from "@tauri-apps/api/window";
import App from "./App.vue";
import SplashScreen from "./splash/SplashScreen.vue";
import "./lilia.css";
import "./kimi.css";
import "./chat.css";
import "./skill-center.css";
import "./timeline.css";
import "./link-menu.css";
import "./workbench.css";
import "./file-rail.css";
import "./typography.css";
import "./appearance.css";
import "./queue-dock.css";
import "./source-control.css";
import { initializeAppearance } from "./services/appearance";

// 多窗口分流：splashscreen 窗口渲染启动动画，其余（main）渲染工作台。
// 浏览器测试环境没有 Tauri host，回退到主应用。
function resolveWindowLabel(): string {
  if (!("__TAURI_INTERNALS__" in window)) return "main";
  try {
    return getCurrentWindow().label;
  } catch {
    return "main";
  }
}

const isSplash = resolveWindowLabel() === "splashscreen";
initializeAppearance();
createApp(isSplash ? SplashScreen : App).mount("#app");
