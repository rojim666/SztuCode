import { createApp } from "vue";
import { getCurrentWindow, IS_TAURI } from "./lib/tauri-shim";
import App from "./App.vue";
import TrayMenu from "./tray/TrayMenu.vue";
import "./lilia.css";
import "./kimi.css";
import "./chat.css";
import "./skill-center.css";
import "./timeline.css";
import "./pipeline.css";
import "./link-menu.css";
import "./workbench.css";
import "./canvas-panel.css";
import "./file-rail.css";
import "./typography.css";
import "./appearance.css";
import "./queue-dock.css";
import "./source-control.css";
import "./motion.css";
import { initializeAppearance } from "./services/appearance";

initializeAppearance();
// 浏览器模式下始终挂载主 App；Tauri 模式下根据窗口 label 决定挂载托盘菜单还是主界面
const label = IS_TAURI ? (getCurrentWindow() as { label?: string }).label ?? "main" : "main";
createApp(label === "tray-menu" ? TrayMenu : App).mount("#app");
