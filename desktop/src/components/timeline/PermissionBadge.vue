<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "../icons/AppIcon.vue";
import type { PermissionDecision, PermissionState } from "./types";

defineProps<{ permission: PermissionState }>();
defineEmits<{ decide: [decision: PermissionDecision] }>();
const { t } = useI18n({ useScope: "global" });
const moreOpen = ref(false);
</script>

<template>
  <section class="permission-badge" :class="permission.status">
    <AppIcon name="ShieldCheck" :size="17" />
    <div><b>{{ permission.status === 'pending' ? t('timeline.permission.pending') : permission.status === 'granted' ? t('timeline.permission.granted') : t('timeline.permission.denied') }}</b><span>{{ permission.toolName }} · {{ permission.preview }}</span></div>
    <div v-if="permission.status === 'pending'" class="permission-actions">
      <button @click="$emit('decide', 'deny_once')">{{ t('timeline.permission.deny') }}</button>
      <button class="allow" @click="$emit('decide', 'allow_once')">{{ t('timeline.permission.allowOnce') }}</button>
      <button class="permission-more" :title="t('timeline.permission.moreOptions')" @click="moreOpen = !moreOpen"><AppIcon name="ChevronDown" :size="14" /></button>
      <div v-if="moreOpen" class="permission-menu">
        <button @click="$emit('decide', 'always_allow')">{{ t('timeline.permission.alwaysAllow') }}</button>
        <button @click="$emit('decide', 'always_deny')">{{ t('timeline.permission.alwaysDeny') }}</button>
      </div>
    </div>
  </section>
</template>