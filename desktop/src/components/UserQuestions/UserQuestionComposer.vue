<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Check, ChevronLeft, ChevronRight, Square } from "@lucide/vue";
import type { PendingUserQuestion, UserQuestionAnswer } from "../../services/sztu-runtime";

type DraftAnswer = { selected: string[]; custom: string; skipped: boolean };

const props = defineProps<{
  pending: PendingUserQuestion;
  busy?: boolean;
  error?: string;
}>();
const emit = defineEmits<{ submit: [answers: UserQuestionAnswer[]]; stop: [] }>();

const index = ref(0);
const drafts = ref<DraftAnswer[]>([]);
const validationError = ref("");
const question = computed(() => props.pending.questions[index.value]);
const draft = computed(() => drafts.value[index.value]);
const displayError = computed(() => props.error || validationError.value);

// 为新 rpcId 重置草稿，同一请求的重渲染保留当前选择
function resetDrafts() {
  index.value = 0;
  drafts.value = props.pending.questions.map(() => ({ selected: [], custom: "", skipped: false }));
  validationError.value = "";
}

// 解析推荐后缀，仅改变展示文案，不改变提交给模型的原始 label
function displayOption(label: string): { label: string; recommended: boolean } {
  const suffix = /\s*(?:\((?:recommended|推荐)\)|（(?:recommended|推荐)）)\s*$/i;
  return { label: label.replace(suffix, ""), recommended: suffix.test(label) };
}

// 切换单选或多选值，并清除当前问题的跳过状态
function choose(label: string) {
  const currentQuestion = question.value;
  const current = draft.value;
  if (!currentQuestion || !current) return;
  if (currentQuestion.multi_select) {
    current.selected = current.selected.includes(label)
      ? current.selected.filter((item) => item !== label)
      : [...current.selected, label];
  } else {
    current.selected = [label];
    current.custom = "";
  }
  current.skipped = false;
  validationError.value = "";
}

// 更新自定义回答；单选题中自定义文本替代预设选项
function updateCustom(value: string) {
  const currentQuestion = question.value;
  const current = draft.value;
  if (!currentQuestion || !current) return;
  current.custom = value;
  if (!currentQuestion.multi_select) current.selected = [];
  current.skipped = false;
  validationError.value = "";
}

// 从 textarea 输入事件读取文本并更新当前草稿
function onCustomInput(event: Event) {
  updateCustom((event.target as HTMLTextAreaElement).value);
}

// 判断一题是否已回答或被显式跳过
function completed(value: DraftAnswer): boolean {
  return value.skipped || value.selected.length > 0 || value.custom.trim().length > 0;
}

// 将当前问题标记为跳过，并继续或提交整个批次
function skip() {
  const current = draft.value;
  if (!current) return;
  current.selected = [];
  current.custom = "";
  current.skipped = true;
  validationError.value = "";
  continueFlow();
}

// 校验全部问题后提交稳定 ID 与结构化选择
function submitAll() {
  const missing = drafts.value.findIndex((item) => !completed(item));
  if (missing >= 0) {
    index.value = missing;
    validationError.value = "请回答或跳过此问题";
    return;
  }
  emit("submit", props.pending.questions.map((item, itemIndex) => {
    const value = drafts.value[itemIndex]!;
    const custom = value.custom.trim();
    return {
      id: item.id,
      selected: value.skipped ? [] : [...value.selected],
      ...(custom ? { custom } : {}),
    };
  }));
}

// 完成当前题后进入下一题，最后一题提交完整回答批次
function continueFlow() {
  const current = draft.value;
  if (!current || !completed(current)) {
    validationError.value = "请选择一个选项或填写回答";
    return;
  }
  if (index.value < props.pending.questions.length - 1) {
    index.value += 1;
    validationError.value = "";
    return;
  }
  submitAll();
}

watch(() => props.pending.rpc_id, resetDrafts, { immediate: true });
</script>

<template>
  <section v-if="question && draft" class="user-question-composer" :aria-labelledby="`user-question-${pending.rpc_id}-${index}`">
    <header class="user-question-header">
      <div>
        <span v-if="question.header">{{ question.header }}</span>
        <h2 :id="`user-question-${pending.rpc_id}-${index}`">{{ question.question }}</h2>
      </div>
      <small>Agent 正在等待你的回答</small>
    </header>

    <div class="user-question-options" :role="question.multi_select ? 'group' : 'radiogroup'">
      <button
        v-for="(option, optionIndex) in question.options"
        :key="`${option.label}-${optionIndex}`"
        type="button"
        class="user-question-option"
        :class="{ selected: draft.selected.includes(option.label) }"
        :role="question.multi_select ? 'checkbox' : 'radio'"
        :aria-checked="draft.selected.includes(option.label)"
        :disabled="busy"
        @click="choose(option.label)"
      >
        <i :class="{ checked: draft.selected.includes(option.label), multi: question.multi_select }">
          <Check v-if="draft.selected.includes(option.label)" :size="13" :stroke-width="2.5" />
          <template v-else>{{ optionIndex + 1 }}</template>
        </i>
        <span>
          <b>{{ displayOption(option.label).label }}</b>
          <em v-if="displayOption(option.label).recommended">推荐</em>
          <small v-if="option.description">{{ option.description }}</small>
        </span>
      </button>
    </div>

    <textarea
      class="user-question-custom"
      :value="draft.custom"
      :disabled="busy"
      :placeholder="question.options.length ? '其他回答…' : '输入你的回答…'"
      rows="2"
      @input="onCustomInput"
      @keydown.enter.exact.prevent="continueFlow"
    />

    <footer class="user-question-footer">
      <div class="user-question-pager">
        <button type="button" title="上一题" aria-label="上一题" :disabled="index === 0 || busy" @click="index -= 1"><ChevronLeft :size="15" /></button>
        <span>{{ index + 1 }} / {{ pending.questions.length }}</span>
        <button type="button" title="下一题" aria-label="下一题" :disabled="index === pending.questions.length - 1 || busy" @click="index += 1"><ChevronRight :size="15" /></button>
      </div>
      <p role="status">{{ displayError }}</p>
      <button type="button" class="user-question-stop" title="停止任务" aria-label="停止任务" :disabled="busy" @click="emit('stop')"><Square :size="13" /></button>
      <button type="button" class="user-question-skip" :disabled="busy" @click="skip">跳过</button>
      <button type="button" class="user-question-submit" :disabled="busy" @click="continueFlow">
        {{ busy ? '提交中…' : index === pending.questions.length - 1 ? '提交回答' : '下一题' }}
      </button>
    </footer>
  </section>
</template>
