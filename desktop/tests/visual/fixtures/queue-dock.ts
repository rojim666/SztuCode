import { createApp, h, nextTick, ref } from "vue";
import QueueDock from "../../../src/components/Composer/QueueDock.vue";
import AppIcon from "../../../src/components/icons/AppIcon.vue";
import { i18n } from "../../../src/i18n";
import type { QueueDockItem } from "../../../src/utils/composerSubmission";
import "../../../src/kimi.css";
import "../../../src/workbench.css";
import "../../../src/appearance.css";
import "../../../src/queue-dock.css";

const params = new URLSearchParams(location.search);
document.documentElement.dataset.appTheme = params.get("theme") ?? "light";
document.documentElement.dataset.wallpaper = params.get("wallpaper") ?? "none";
i18n.global.locale.value = "zh-CN";

createApp({
  setup() {
    const items = ref<QueueDockItem[]>([
      { id: "queue-1", text: "补充接口错误态测试，并覆盖会话繁忙时的回退路径", attachmentCount: 0 },
      { id: "queue-2", text: "整理本轮改动并更新开发文档中的协议示例", attachmentCount: 2 },
    ]);
    const draft = ref("");
    const input = ref<HTMLTextAreaElement | null>(null);
    const busyId = ref<string | null>(null);
    const remove = (id: string) => { items.value = items.value.filter(item => item.id !== id); };
    const edit = (id: string) => {
      const item = items.value.find(item => item.id === id);
      if (!item) return;
      draft.value = [draft.value, item.text].filter(Boolean).join("\n\n");
      remove(id);
      void nextTick(() => input.value?.focus());
    };
    const steer = (id: string) => {
      busyId.value = id;
      window.setTimeout(() => { remove(id); busyId.value = null; }, 80);
    };
    const submit = (event: Event) => {
      event.preventDefault();
      if (!draft.value.trim()) return;
      items.value.push({ id: crypto.randomUUID(), text: draft.value, attachmentCount: 0 });
      draft.value = "";
    };
    return () => h("main", { style: "min-height:100vh;background:var(--app-bg);padding-top:24px" }, [
      h("h1", { style: "text-align:center;font-size:14px;color:var(--text-muted);font-weight:400" }, "输入卡片"),
      h("section", { class: "task-conversation", style: "height:440px;display:flex;flex-direction:column;justify-content:flex-end" }, [
        h(QueueDock, { items: items.value, running: true, busyId: busyId.value, onEdit: edit, onRemove: remove, onSteer: steer }, {
          default: () => h("form", { class: "kimi-composer active-composer", onSubmit: submit }, [
            h("textarea", { ref: input, value: draft.value, "aria-label": "任务输入", placeholder: "汝之所想，皆以言成", rows: 3, onInput: (e: Event) => { draft.value = (e.target as HTMLTextAreaElement).value; } }),
            h("div", { class: "composer-toolbar" }, [
              h("button", { type: "button", class: "round", "aria-label": "添加附件" }, [h(AppIcon, { name: "Plus", size: 18 })]),
              h("button", { type: "button", class: "permission permission--full-access" }, [h(AppIcon, { name: "ShieldCheck", size: 15 }), "全部允许", h(AppIcon, { name: "ChevronDown", size: 13 })]),
              h("span"),
              h("button", { type: "button", class: "model-config-trigger" }, [h("i", { class: "online" }), h("span", "6 Astra"), h(AppIcon, { name: "ChevronDown", size: 13 })]),
              h("button", { type: "button", class: "send stop", "aria-label": "停止任务" }, [h(AppIcon, { name: "Square", size: 14 })]),
              draft.value ? h("button", { type: "submit", class: "send", "aria-label": "追加任务" }, [h(AppIcon, { name: "ArrowUp", size: 15 })]) : null,
            ]),
          ]),
        }),
      ]),
    ]);
  },
}).use(i18n).mount("#app");
