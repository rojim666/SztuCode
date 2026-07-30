<script setup lang="ts">
import { ShieldCheck } from "@lucide/vue";
import type { PermissionState } from "./types";
defineProps<{ permission: PermissionState }>();
defineEmits<{ decide: [decision: "allow_once" | "deny_once"] }>();
</script>
<template><section class="permission-badge" :class="permission.status"><ShieldCheck :size="17" /><div><b>{{ permission.status === 'pending' ? '等待权限审批' : permission.status === 'granted' ? '已获批准' : '已拒绝' }}</b><span>{{ permission.toolName }} · {{ permission.preview }}</span></div><div v-if="permission.status === 'pending'" class="permission-actions"><button @click="$emit('decide', 'deny_once')">拒绝</button><button class="allow" @click="$emit('decide', 'allow_once')">允许一次</button></div></section></template>
