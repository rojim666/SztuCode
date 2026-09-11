<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import ImageLightbox from "../ImageLightbox.vue";
import { fileTypeIconUrl } from "../../utils/fileIcon";

const props = defineProps<{ file: {
  name: string; size: number; kind: "image" | "text"; mime?: string; dataBase64?: string;
} }>();
const emit = defineEmits<{ remove: [] }>();
const { t } = useI18n();
const extension = computed(() => props.file.name.match(/\.([^.]+)$/)?.[1].toLowerCase() ?? "");
const category = computed(() => {
  if (props.file.kind === "image" || props.file.mime?.startsWith("image/")) return "image";
  if (extension.value === "pdf" || props.file.mime === "application/pdf") return "pdf";
  if (["doc", "docx", "odt", "rtf"].includes(extension.value)) return "word";
  if (["xls", "xlsx", "xlsm", "csv", "tsv", "ods"].includes(extension.value)) return "excel";
  if (["ppt", "pptx", "odp"].includes(extension.value)) return "powerpoint";
  if (["txt", "md", "markdown", "json", "xml", "yaml", "yml", "log"].includes(extension.value)) return "text";
  return "file";
});
const icon = computed(() => {
  const representative: Record<string, string> = {
    pdf: "file.pdf", word: "file.docx", excel: "file.xlsx", powerpoint: "file.pptx",
    text: "file.txt", file: props.file.name.toLowerCase(),
  };
  return fileTypeIconUrl(representative[category.value] ?? props.file.name.toLowerCase())
    || fileTypeIconUrl("file.txt");
});
const thumbnail = computed(() => props.file.kind === "image" && props.file.dataBase64
  ? `data:${props.file.mime ?? "image/png"};base64,${props.file.dataBase64}` : null);
const previewOpen = ref(false);
const typeLabel = computed(() => extension.value.toUpperCase()
  || (category.value === "pdf" ? "PDF" : category.value === "image" ? "IMAGE" : "FILE"));
const sizeLabel = computed(() => {
  if (props.file.size < 1024) return `${props.file.size} B`;
  if (props.file.size < 1024 * 1024) return `${Math.round(props.file.size / 1024)} KB`;
  return `${(props.file.size / (1024 * 1024)).toFixed(1)} MB`;
});
</script>

<template>
  <span class="composer-attachment" :data-category="category" :title="file.name">
    <button v-if="thumbnail" class="composer-attachment__visual composer-attachment__preview" type="button" :aria-label="`Preview ${file.name}`" @click="previewOpen = true">
      <img v-if="thumbnail" :src="thumbnail" alt="" />
    </button>
    <span v-else class="composer-attachment__visual" aria-hidden="true"><img v-if="icon" :src="icon" alt="" /><AppIcon v-else name="FileText" :size="25" /></span>
    <span class="composer-attachment__info">
      <b>{{ file.name }}</b>
      <small><span>{{ typeLabel }}</span><span aria-hidden="true">·</span>{{ sizeLabel }}</small>
    </span>
    <button class="composer-attachment__remove" type="button"
      :aria-label="`${t('app.removeAttachment')} ${file.name}`" :title="t('app.removeAttachment')"
      @click="emit('remove')"><AppIcon name="X" :size="13" /></button>
    <ImageLightbox v-if="previewOpen && thumbnail" :images="[{ src: thumbnail, alt: file.name }]" @close="previewOpen = false" />
  </span>
</template>

<style scoped>
.composer-attachment {
  --attachment-accent: var(--text-muted, #6f777b);
  display: inline-flex; align-items: center; gap: 10px; flex: 0 0 auto;
  width: 220px; max-width: calc(100vw - 96px); min-height: 56px;
  box-sizing: border-box; padding: 8px; border: 1px solid var(--border, #dfe3e4);
  border-radius: 10px; background: var(--surface-raised, #fff); color: var(--text, #202426);
  box-shadow: 0 2px 8px rgb(28 36 44 / 4%);
  transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
}
.composer-attachment:hover {
  border-color: color-mix(in srgb, var(--attachment-accent) 40%, var(--border, #dfe3e4));
  box-shadow: 0 4px 12px rgb(28 36 44 / 8%);
  transform: translateY(-1px);
}
.composer-attachment[data-category="pdf"] { --attachment-accent: #d64b47; }
.composer-attachment[data-category="word"] { --attachment-accent: #3379cf; }
.composer-attachment[data-category="excel"] { --attachment-accent: #279468; }
.composer-attachment[data-category="powerpoint"] { --attachment-accent: #d7773d; }
.composer-attachment[data-category="image"] { --attachment-accent: #9a67c7; }
.composer-attachment[data-category="text"] { --attachment-accent: #667c91; }
.composer-attachment__visual {
  position: relative;
  display: grid; place-items: center; flex: 0 0 38px; width: 38px; height: 40px;
  border-radius: 8px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--attachment-accent) 12%, #fff) 0%, color-mix(in srgb, var(--attachment-accent) 18%, transparent) 100%);
  border: 1px solid color-mix(in srgb, var(--attachment-accent) 18%, transparent);
  overflow: hidden;
}
.composer-attachment__preview { padding: 0; cursor: zoom-in; }
.composer-attachment__visual::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255,255,255,0.35) 0%, transparent 45%);
  pointer-events: none;
}
.composer-attachment__visual img { position: relative; z-index: 1; display: block; width: 26px; height: 29px; object-fit: contain; }
.composer-attachment__visual.is-thumbnail { background: var(--surface-soft); border-color: var(--border, #dfe3e4); }
.composer-attachment__visual.is-thumbnail::after { display: none; }
.composer-attachment__visual.is-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
.composer-attachment__info { display: flex; flex: 1; flex-direction: column; gap: 4px; min-width: 0; }
.composer-attachment__info b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; line-height: 16px; letter-spacing: -0.01em; }
.composer-attachment__info small { display: flex; align-items: center; gap: 5px; color: var(--text-muted, #6f777b); font-size: 10px; line-height: 13px; }
.composer-attachment__info small span:first-child {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 34px; padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600; font-size: 9px; letter-spacing: 0.02em;
  color: var(--attachment-accent);
  background: color-mix(in srgb, var(--attachment-accent) 10%, transparent);
}
.composer-attachment__remove {
  display: grid; place-items: center; flex: 0 0 24px; width: 24px; height: 24px;
  padding: 0; border: 0; border-radius: 6px; color: var(--text-muted, #6f777b);
  background: transparent; cursor: pointer;
  transition: color 120ms ease, background-color 120ms ease, transform 120ms ease;
}
.composer-attachment__remove:hover { background: color-mix(in srgb, var(--danger, #b64a42) 8%, var(--surface-soft, #f6f7f7)); color: var(--danger, #b64a42); transform: scale(1.05); }
.composer-attachment__remove:active { transform: scale(0.95); }
.composer-attachment__remove:focus-visible { outline: 2px solid var(--attachment-accent); outline-offset: 2px; }
</style>
