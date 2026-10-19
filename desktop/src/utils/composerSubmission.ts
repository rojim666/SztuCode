// 运行中提交追加任务的唯一归宿是输入框上方的队列卡片：输入框不再直接注入运行中的
// run（Ctrl/Cmd+Enter 与 Enter 同样只是入队）。是否把卡片内容注入运行中的任务，
// 由用户在卡片上显式触发（见 App.vue 的 steerQueuedSubmission）。
export type QueueDockItem = {
  id: string;
  text: string;
  attachmentCount: number;
};
