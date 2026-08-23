import { createApp, defineComponent, h, ref } from "vue";
import UserQuestionComposer from "../../../src/components/UserQuestions/UserQuestionComposer.vue";
import type { PendingUserQuestion, UserQuestionAnswer } from "../../../src/services/sztu-runtime";
import "../../../src/kimi.css";

const pending: PendingUserQuestion = {
  rpc_id: "question-fixture",
  session_id: "session-fixture",
  run_id: "run-fixture",
  questions: [
    {
      id: "theme",
      header: "选择主题",
      question: "使用哪种界面方案？",
      options: [
        { label: "浅色", description: "保持明亮界面" },
        { label: "深色 (Recommended)", description: "降低视觉亮度" },
      ],
      multi_select: false,
    },
    {
      id: "checks",
      header: "验证范围",
      question: "需要运行哪些检查？",
      options: [
        { label: "单元测试", description: "验证核心逻辑" },
        { label: "类型检查", description: "验证静态类型" },
      ],
      multi_select: true,
    },
  ],
};

const Fixture = defineComponent({
  // 渲染可交互提问面板，并把提交结果显示为测试可断言的结构化文本
  setup() {
    const answer = ref<UserQuestionAnswer[] | null>(null);
    return () => h("main", { class: "user-question-fixture" }, [
      h(UserQuestionComposer, {
        pending,
        onSubmit: (value: UserQuestionAnswer[]) => { answer.value = value; },
      }),
      answer.value ? h("pre", { "data-testid": "answer" }, JSON.stringify(answer.value)) : null,
    ]);
  },
});

createApp(Fixture).mount("#app");
