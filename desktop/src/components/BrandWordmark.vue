<script setup lang="ts">
import blackWordmark from "../assets/sztucode-black.svg";
import whiteWordmark from "../assets/sztucode-white.svg";
</script>

<template>
  <span class="brand-wordmark">
    <img class="brand-wordmark__light" :src="blackWordmark" alt="SztuCode" width="96" height="17" draggable="false" />
    <img class="brand-wordmark__dark" :src="whiteWordmark" alt="SztuCode" width="96" height="17" draggable="false" />
  </span>
</template>

<style>
.brand-wordmark {
  display: block;
  width: 96px;
  max-width: 100%;
  height: 17px;
}

.brand-wordmark img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.brand-wordmark .brand-wordmark__dark {
  display: none;
}

:root[data-app-theme="dark"] .brand-wordmark__light {
  display: none;
}

:root[data-app-theme="dark"] .brand-wordmark__dark {
  display: block;
}
</style>
