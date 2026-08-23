import { createApp, h, ref } from "vue";
import QueueDock from "../../../src/components/Composer/QueueDock.vue";
import type { QueueDockItem } from "../../../src/utils/composerSubmission";
import "../../../src/kimi.css";
import "../../../src/queue-dock.css";

createApp({
  setup() {
    const items = ref<QueueDockItem[]>([
      { id: "queue-1", text: "补充接口错误态测试，并覆盖会话繁忙时的回退路径", attachmentCount: 0 },
      { id: "queue-2", text: "整理本轮改动并更新开发文档中的协议示例", attachmentCount: 2 },
    ]);
    const busyId = ref<string | null>(null);
    const edit = (id: string, text: string) => {
      items.value = items.value.map((item) => item.id === id ? { ...item, text } : item);
    };
    const remove = (id: string) => {
      items.value = items.value.filter((item) => item.id !== id);
    };
    const steer = (id: string) => {
      busyId.value = id;
      window.setTimeout(() => {
        items.value = items.value.filter((item) => item.id !== id);
        busyId.value = null;
      }, 80);
    };
    return () => h("main", {
      style: "min-height:100vh;padding:90px 0;background:#f5f6f6",
    }, [
      h(QueueDock, {
        items: items.value,
        running: true,
        busyId: busyId.value,
        onEdit: edit,
        onRemove: remove,
        onSteer: steer,
      }),
      h("form", { class: "kimi-composer", style: "margin-top:0" }, [
        h("textarea", { placeholder: "追加任务", rows: 3 }),
      ]),
    ]);
  },
}).mount("#app");
