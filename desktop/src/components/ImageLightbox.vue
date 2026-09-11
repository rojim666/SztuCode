<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import AppIcon from "./icons/AppIcon.vue";

const props = withDefaults(defineProps<{ images: Array<{ src: string; alt: string }>; index?: number }>(), { index: 0 });
const emit = defineEmits<{ close: []; change: [index: number] }>();
const current = computed(() => props.images[props.index]);
const hasMultiple = computed(() => props.images.length > 1);
function close() { emit("close"); }
function move(delta: number) { if (props.images.length) emit("change", (props.index + delta + props.images.length) % props.images.length); }
function onKeydown(event: KeyboardEvent) { if (event.key === "Escape") { event.preventDefault(); close(); } if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); } if (event.key === "ArrowRight") { event.preventDefault(); move(1); } }
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
watch(() => props.images.length, (length) => { if (!length) close(); });
</script>

<template>
  <div class="image-lightbox" role="dialog" aria-modal="true" aria-label="Image preview" @click.self="close">
    <button class="image-lightbox__close" type="button" aria-label="Close image preview" @click="close"><AppIcon name="X" :size="20" /></button>
    <button v-if="hasMultiple" class="image-lightbox__nav image-lightbox__nav--previous" type="button" aria-label="Previous image" @click="move(-1)"><AppIcon name="ChevronLeft" :size="28" /></button>
    <figure><img v-if="current" :src="current.src" :alt="current.alt" /><figcaption v-if="hasMultiple">{{ index + 1 }} / {{ images.length }}</figcaption></figure>
    <button v-if="hasMultiple" class="image-lightbox__nav image-lightbox__nav--next" type="button" aria-label="Next image" @click="move(1)"><AppIcon name="ChevronRight" :size="28" /></button>
  </div>
</template>

<style scoped>
.image-lightbox { position: fixed; z-index: 10000; inset: 0; display: grid; place-items: center; padding: 44px 72px; background: rgb(10 13 16 / 84%); color: #fff; }
figure { display: grid; justify-items: center; gap: 10px; margin: 0; max-width: 100%; max-height: 100%; }
figure img { display: block; max-width: min(100%, 1500px); max-height: calc(100vh - 100px); object-fit: contain; border-radius: 8px; box-shadow: 0 18px 60px rgb(0 0 0 / 55%); }
figcaption { font-size: 13px; text-shadow: 0 1px 2px #000; }
.image-lightbox button { display: grid; place-items: center; border: 0; border-radius: 999px; color: #fff; background: rgb(255 255 255 / 14%); cursor: pointer; }
.image-lightbox button:hover { background: rgb(255 255 255 / 27%); }.image-lightbox button:focus-visible { outline: 3px solid #8cc8ff; outline-offset: 3px; }
.image-lightbox__close { position: absolute; top: 18px; right: 18px; width: 38px; height: 38px; }.image-lightbox__nav { position: absolute; top: 50%; width: 48px; height: 48px; transform: translateY(-50%); }.image-lightbox__nav--previous { left: 16px; }.image-lightbox__nav--next { right: 16px; }
@media (max-width: 640px) { .image-lightbox { padding: 52px 16px; }.image-lightbox__nav { width: 38px; height: 38px; }.image-lightbox__nav--previous { left: 4px; }.image-lightbox__nav--next { right: 4px; } }
</style>
