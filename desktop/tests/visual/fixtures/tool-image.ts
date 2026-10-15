import { createApp, h } from "vue";
import ToolCallCard from "../../../src/components/timeline/ToolCallCard.vue";
import { i18n } from "../../../src/i18n";
import "../../../src/sztu.css";

const data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN9sAAAAASUVORK5CYII=";
createApp({ render: () => h(ToolCallCard, { expanded: true, call: {
  id: "image-call", name: "view_image", status: "done", params: { path: "screenshot.png" }, output: "Image: screenshot.png",
  images: [{ mimeType: "image/png", data }, { mimeType: "image/png", data }],
} }) }).use(i18n).mount("#app");
