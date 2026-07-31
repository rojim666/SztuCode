<script setup lang="ts">
import { ref } from "vue";
import { ChevronDown, ShieldCheck } from "@lucide/vue";
import type { PermissionDecision, PermissionState } from "./types";

defineProps<{ permission: PermissionState }>();
defineEmits<{ decide: [decision: PermissionDecision] }>();
const moreOpen = ref(false);
</script>

<template>
  <section class="permission-badge" :class="permission.status">
    <ShieldCheck :size="17" />
    <div><b>{{ permission.status === 'pending' ? '等待权限审批' : permission.status === 'granted' ? '已获批准' : '已拒绝' }}</b><span>{{ permission.toolName }} · {{ permission.preview }}</span></div>
    <div v-if="permission.status === 'pending'" class="permission-actions">
      <button @click="$emit('decide', 'deny_once')">拒绝</button>
      <button class="allow" @click="$emit('decide', 'allow_once')">允许一次</button>
      <button class="permission-more" title="更多审批选项" @click="moreOpen = !moreOpen"><ChevronDown :size="14" /></button>
      <div v-if="moreOpen" class="permission-menu">
        <button @click="$emit('decide', 'always_allow')">始终允许此工具</button>
        <button @click="$emit('decide', 'always_deny')">始终拒绝此工具</button>
      </div>
    </div>
  </section>
</template>