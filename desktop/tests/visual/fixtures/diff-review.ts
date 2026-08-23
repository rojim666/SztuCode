import { createApp } from "vue";
import DiffReview from "../../../src/components/Diff/DiffReview.vue";
import "../../../src/kimi.css";

// DiffReview 组件独立挂载 fixture：测试通过 page.goto 访问本页面，
// 再通过 Vue 组件实例注入状态/触发交互（与 task-conversation fixture 同一模式）。
createApp(DiffReview, {
  workspaceId: "workspace-fixture",
  runId: "run-fixture-1234",
  paths: ["src/a.py", "src/b.py"],
}).mount("#app");
